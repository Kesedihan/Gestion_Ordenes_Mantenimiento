"""M2 - Capa de APLICACIÓN: casos de uso del módulo Jornada.

Todas las dependencias llegan por el constructor (IoC / principio
Hollywood): ningún caso de uso hace "BaseDatos()" o "Disco()" por su cuenta.
"""
import hashlib
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable

from app.compartido.errores import ErrorDeNegocio, NoEncontrado
from app.compartido.reloj import Reloj
from app.jornada.dominio import (Actividad, EstadoActividad, EstadoEvento, Evento, MomentoEvidencia,
                                 ResultadoRevision, TipoEvento)
from app.jornada.manejadores import ManejadorEvento
from app.jornada.puertos import (AlmacenArchivos, DirectorioOperarios, RegistroEventos,
                                 RepositorioActividades, RepositorioEvidencias,
                                 RepositorioJornadas)

TOLERANCIA_RELOJ = timedelta(minutes=5)
TAMANO_MAXIMO_FOTO = 2 * 1024 * 1024  # 2 MB; el celular comprime a ~300 KB
TIPOS_IMAGEN = {"image/jpeg": "jpg", "image/png": "png"}


@dataclass(frozen=True)
class ResultadoEvento:
    id: str
    estado: str          # ACEPTADO | RECHAZADO | DUPLICADO
    motivo: str | None = None


class ProcesadorIdempotente:
    """DRY + D4 (decisión crítica): un evento con el mismo UUID se procesa
    una sola vez, venga del lote de eventos o de la subida de una foto."""

    def __init__(self, registro: RegistroEventos, reloj: Reloj):
        self._registro = registro
        self._reloj = reloj

    def procesar(self, evento: Evento, accion: Callable[[], None]) -> ResultadoEvento:
        previo = self._registro.estado_de(evento.id)
        if previo is not None:
            return ResultadoEvento(evento.id, "DUPLICADO", previo[1])
        recibido = self._reloj.ahora()
        sospechosa = evento.hora_dispositivo > recibido + TOLERANCIA_RELOJ  # D5
        try:
            accion()
        except ErrorDeNegocio as error:
            self._registro.registrar(evento, recibido, EstadoEvento.RECHAZADO, str(error), sospechosa)
            return ResultadoEvento(evento.id, EstadoEvento.RECHAZADO.value, str(error))
        self._registro.registrar(evento, recibido, EstadoEvento.ACEPTADO, None, sospechosa)
        return ResultadoEvento(evento.id, EstadoEvento.ACEPTADO.value)


class SincronizarLote:
    """Escenario crítico E2: recibe la cola de eventos que el celular guardó sin conexión."""

    def __init__(self, manejadores: dict[TipoEvento, ManejadorEvento],
                 procesador: ProcesadorIdempotente, directorio: DirectorioOperarios):
        self._manejadores = manejadores
        self._procesador = procesador
        self._directorio = directorio

    def ejecutar(self, operario_id: int, eventos: list[Evento]) -> list[ResultadoEvento]:
        if not self._directorio.esta_activo(operario_id):
            raise ErrorDeNegocio("El operario no existe o está inactivo")
        resultados = []
        for evento in sorted(eventos, key=lambda e: e.hora_dispositivo):
            if evento.operario_id != operario_id:
                resultados.append(ResultadoEvento(evento.id, "RECHAZADO", "Evento de otro operario"))
                continue
            manejador = self._manejadores.get(evento.tipo)
            if manejador is None:
                resultados.append(ResultadoEvento(evento.id, "RECHAZADO", "Tipo de evento no soportado"))
                continue
            resultados.append(self._procesador.procesar(evento, lambda: manejador.manejar(evento)))
        return resultados


class SubirEvidencia:
    """Recibe una foto (antes/durante/después) tomada sin conexión."""

    def __init__(self, actividades: RepositorioActividades, evidencias: RepositorioEvidencias,
                 almacen: AlmacenArchivos, procesador: ProcesadorIdempotente, reloj: Reloj):
        self._actividades = actividades
        self._evidencias = evidencias
        self._almacen = almacen
        self._procesador = procesador
        self._reloj = reloj

    def ejecutar(self, evento: Evento, contenido: bytes, tipo_contenido: str) -> ResultadoEvento:
        def accion():
            if tipo_contenido not in TIPOS_IMAGEN:
                raise ErrorDeNegocio("La evidencia debe ser una imagen JPEG o PNG")
            if not 0 < len(contenido) <= TAMANO_MAXIMO_FOTO:
                raise ErrorDeNegocio("La foto supera el tamaño máximo de 2 MB o está vacía")
            actividad = self._actividades.obtener(int(evento.datos["actividad_id"]))
            if actividad is None:
                raise ErrorDeNegocio("La actividad no existe")
            actividad.verificar_asignada_a(evento.operario_id)
            momento = MomentoEvidencia(evento.datos["momento"])
            actividad.registrar_evidencia(momento)  # valida reglas 2 y 4
            huella = hashlib.sha256(contenido).hexdigest()
            nombre = f"{actividad.id}_{momento.value}_{huella[:12]}.{TIPOS_IMAGEN[tipo_contenido]}"
            ruta = self._almacen.guardar(nombre, contenido)
            self._evidencias.agregar(actividad.id, momento, ruta, huella,
                                     evento.hora_dispositivo, self._reloj.ahora())
            self._actividades.guardar(actividad)

        return self._procesador.procesar(evento, accion)


class RevisarActividad:
    """Escenario crítico E4: el supervisor acepta o rechaza el trabajo."""

    def __init__(self, actividades: RepositorioActividades):
        self._actividades = actividades

    def ejecutar(self, actividad_id: int, supervisor_id: int,
                 resultado: ResultadoRevision, observacion: str | None) -> Actividad:
        actividad = self._actividades.obtener(actividad_id)
        if actividad is None:
            raise NoEncontrado(f"Actividad {actividad_id} no existe")
        actividad.revisar(resultado, supervisor_id, observacion)
        self._actividades.guardar(actividad)
        if resultado is ResultadoRevision.RECHAZADA:
            self._actividades.guardar(Actividad(
                id=None,
                operario_id=actividad.operario_id,
                centro_id=actividad.centro_id,
                centro_nombre=actividad.centro_nombre,
                fecha=actividad.fecha,
                tipo_servicio=actividad.tipo_servicio,
                descripcion=actividad.descripcion,
                correccion_de_id=actividad.id,
                motivo_correccion=observacion,
            ))
        return actividad


class ConsultarEvidencia:
    """Obtiene la ruta de una evidencia sin exponer el almacenamiento completo."""

    def __init__(self, evidencias: RepositorioEvidencias):
        self._evidencias = evidencias

    def ejecutar(self, actividad_id: int, momento: MomentoEvidencia) -> str:
        ruta = self._evidencias.obtener_ruta(actividad_id, momento)
        if ruta is None:
            raise NoEncontrado(
                f"No existe la evidencia {momento.value} para la actividad {actividad_id}"
            )
        return ruta


class ConsultarPendientesRevision:
    """Lista las actividades finalizadas que requieren decisión del supervisor."""

    def __init__(
        self, actividades: RepositorioActividades, directorio: DirectorioOperarios
    ):
        self._actividades = actividades
        self._directorio = directorio

    def ejecutar(self, fecha: date) -> list[dict]:
        pendientes = self._actividades.listar_por_fecha(fecha)
        return [
            {
                "id": actividad.id,
                "operario": self._directorio.nombre(actividad.operario_id),
                "fecha": actividad.fecha,
                "centro": actividad.centro_nombre,
                "tipo_servicio": actividad.tipo_servicio,
                "descripcion": actividad.descripcion,
                "estado": actividad.estado.value,
                "correccion_de_id": actividad.correccion_de_id,
                "motivo_correccion": actividad.motivo_correccion,
                "hora_inicio": actividad.hora_inicio,
                "hora_fin": actividad.hora_fin,
                "evidencias": sorted(momento.value for momento in actividad.evidencias),
            }
            for actividad in pendientes
            if actividad.estado is EstadoActividad.FINALIZADA
        ]


class ConsultarProgramacion:
    """Lo que el celular descarga para trabajar sin conexión durante la semana."""

    def __init__(self, actividades: RepositorioActividades):
        self._actividades = actividades

    def ejecutar(self, operario_id: int, desde: date, dias: int = 7) -> list[Actividad]:
        return self._actividades.listar_por_operario(operario_id, desde, desde + timedelta(days=dias - 1))


class ConsultarSeguimiento:
    """Tablero de control y seguimiento de los trabajos de cada operario."""

    def __init__(self, actividades: RepositorioActividades, jornadas: RepositorioJornadas,
                 registro: RegistroEventos, directorio: DirectorioOperarios):
        self._actividades = actividades
        self._jornadas = jornadas
        self._registro = registro
        self._directorio = directorio

    def ejecutar(self, fecha: date) -> list[dict]:
        por_operario: dict[int, dict] = {}

        def fila(operario_id: int) -> dict:
            if operario_id not in por_operario:
                ultima, sospechosos = self._registro.resumen_operario(operario_id)
                por_operario[operario_id] = {
                    "operario_id": operario_id,
                    "operario": self._directorio.nombre(operario_id),
                    "entrada": None, "salida": None,
                    "jornadas": [],
                    "ultima_sincronizacion": ultima,
                    "eventos_hora_sospechosa": sospechosos,
                    "actividades": [],
                }
            return por_operario[operario_id]

        for j in self._jornadas.listar_por_fecha(fecha):
            f = fila(j.operario_id)
            f["jornadas"].append({
                "centro_id": j.centro_id,
                "centro": j.centro_nombre,
                "entrada": j.hora_entrada,
                "salida": j.hora_salida,
            })
            if f["entrada"] is None or j.hora_entrada > f["entrada"]:
                f["entrada"], f["salida"] = j.hora_entrada, j.hora_salida
        for a in self._actividades.listar_por_fecha(fecha):
            fila(a.operario_id)["actividades"].append({
                "id": a.id, "centro_id": a.centro_id, "centro": a.centro_nombre,
                "servicio": a.tipo_servicio,
                "correccion_de_id": a.correccion_de_id,
                "motivo_correccion": a.motivo_correccion,
                "estado": a.estado.value, "inicio": a.hora_inicio, "fin": a.hora_fin,
                "evidencias": sorted(m.value for m in a.evidencias),
            })
        return sorted(por_operario.values(), key=lambda f: f["operario"])
