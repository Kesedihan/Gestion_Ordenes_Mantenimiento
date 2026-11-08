"""M2 - Jornada, actividades y evidencias: capa de DOMINIO.

Reglas de negocio (derivadas del enunciado):
  1. Una actividad solo se INICIA si ya tiene la foto ANTES y el operario
     registró ENTRADA en ese centro ese día.
  2. Las fotos DURANTE y DESPUES solo se toman con la actividad EN_CURSO.
  3. Una actividad solo se FINALIZA con sus 3 evidencias.
  4. Una evidencia, una vez recibida, no se reemplaza (integridad).
  5. El supervisor solo revisa actividades FINALIZADAS; un rechazo exige
     observación.
  6. La salida no puede ser anterior a la entrada.
Encapsulación: el estado cambia solo mediante métodos que validan reglas.
"""
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum

from app.compartido.errores import ErrorDeNegocio


class TipoEvento(str, Enum):
    ENTRADA = "ENTRADA"
    SALIDA = "SALIDA"
    INICIO_ACTIVIDAD = "INICIO_ACTIVIDAD"
    FIN_ACTIVIDAD = "FIN_ACTIVIDAD"
    EVIDENCIA = "EVIDENCIA"


class MomentoEvidencia(str, Enum):
    ANTES = "ANTES"
    DURANTE = "DURANTE"
    DESPUES = "DESPUES"


class EstadoActividad(str, Enum):
    PROGRAMADA = "PROGRAMADA"
    EN_CURSO = "EN_CURSO"
    FINALIZADA = "FINALIZADA"
    ACEPTADA = "ACEPTADA"
    RECHAZADA = "RECHAZADA"


class ResultadoRevision(str, Enum):
    ACEPTADA = "ACEPTADA"
    RECHAZADA = "RECHAZADA"


class EstadoEvento(str, Enum):
    ACEPTADO = "ACEPTADO"
    RECHAZADO = "RECHAZADO"


@dataclass(frozen=True)
class Evento:
    """Hecho inmutable registrado en el celular (posiblemente sin conexión)."""
    id: str                      # UUID generado en el celular -> idempotencia
    tipo: TipoEvento
    operario_id: int
    hora_dispositivo: datetime
    datos: dict = field(default_factory=dict)


class Actividad:
    def __init__(self, id: int | None, operario_id: int, centro_id: int, centro_nombre: str,
                 fecha: date, tipo_servicio: str, descripcion: str,
                 estado: EstadoActividad = EstadoActividad.PROGRAMADA,
                 hora_inicio: datetime | None = None, hora_fin: datetime | None = None,
                 evidencias: set[MomentoEvidencia] | None = None,
                 revisada_por: int | None = None, observacion: str | None = None,
                 correccion_de_id: int | None = None,
                 motivo_correccion: str | None = None):
        self._id = id
        self._operario_id = operario_id
        self._centro_id = centro_id
        self._centro_nombre = centro_nombre
        self._fecha = fecha
        self._tipo_servicio = tipo_servicio
        self._descripcion = descripcion
        self._estado = estado
        self._hora_inicio = hora_inicio
        self._hora_fin = hora_fin
        self._evidencias = set(evidencias or set())
        self._revisada_por = revisada_por
        self._observacion = observacion
        self._correccion_de_id = correccion_de_id
        self._motivo_correccion = motivo_correccion

    def verificar_asignada_a(self, operario_id: int) -> None:
        if self._operario_id != operario_id:
            raise ErrorDeNegocio("La actividad no está asignada a este operario")

    def registrar_evidencia(self, momento: MomentoEvidencia) -> None:
        if momento in self._evidencias:
            raise ErrorDeNegocio(f"La evidencia {momento.value} ya fue registrada")
        if momento is MomentoEvidencia.ANTES and self._estado is not EstadoActividad.PROGRAMADA:
            raise ErrorDeNegocio("La foto ANTES se toma antes de iniciar la actividad")
        if momento is not MomentoEvidencia.ANTES and self._estado is not EstadoActividad.EN_CURSO:
            raise ErrorDeNegocio(f"La foto {momento.value} requiere la actividad EN_CURSO")
        self._evidencias.add(momento)

    def iniciar(self, hora: datetime) -> None:
        if self._estado is not EstadoActividad.PROGRAMADA:
            raise ErrorDeNegocio(f"No se puede iniciar una actividad {self._estado.value}")
        if MomentoEvidencia.ANTES not in self._evidencias:
            raise ErrorDeNegocio("Falta la foto ANTES para iniciar la actividad")
        self._estado = EstadoActividad.EN_CURSO
        self._hora_inicio = hora

    def finalizar(self, hora: datetime) -> None:
        if self._estado is not EstadoActividad.EN_CURSO:
            raise ErrorDeNegocio("Solo se finaliza una actividad EN_CURSO")
        if not self.evidencias_completas():
            faltan = sorted(m.value for m in set(MomentoEvidencia) - self._evidencias)
            raise ErrorDeNegocio(f"Faltan evidencias: {', '.join(faltan)}")
        if hora < self._hora_inicio:
            raise ErrorDeNegocio("La hora de fin es anterior a la de inicio")
        self._estado = EstadoActividad.FINALIZADA
        self._hora_fin = hora

    def revisar(self, resultado: ResultadoRevision, supervisor_id: int, observacion: str | None) -> None:
        if self._estado is not EstadoActividad.FINALIZADA:
            raise ErrorDeNegocio("Solo se revisan actividades FINALIZADAS")
        if resultado is ResultadoRevision.RECHAZADA and not (observacion or "").strip():
            raise ErrorDeNegocio("El rechazo requiere una observación")
        self._estado = EstadoActividad(resultado.value)
        self._revisada_por = supervisor_id
        self._observacion = observacion

    def evidencias_completas(self) -> bool:
        return self._evidencias == set(MomentoEvidencia)

    @property
    def id(self) -> int | None: return self._id
    @property
    def operario_id(self): return self._operario_id
    @property
    def centro_id(self): return self._centro_id
    @property
    def centro_nombre(self): return self._centro_nombre
    @property
    def fecha(self): return self._fecha
    @property
    def tipo_servicio(self): return self._tipo_servicio
    @property
    def descripcion(self): return self._descripcion
    @property
    def estado(self): return self._estado
    @property
    def hora_inicio(self): return self._hora_inicio
    @property
    def hora_fin(self): return self._hora_fin
    @property
    def evidencias(self): return frozenset(self._evidencias)
    @property
    def revisada_por(self): return self._revisada_por
    @property
    def observacion(self): return self._observacion
    @property
    def correccion_de_id(self): return self._correccion_de_id
    @property
    def motivo_correccion(self): return self._motivo_correccion


class Jornada:
    """Control de horario: entrada y salida de un operario en un centro de trabajo."""

    def __init__(self, operario_id: int, centro_id: int, hora_entrada: datetime,
                 hora_salida: datetime | None = None, id: int | None = None,
                 centro_nombre: str | None = None):
        self._id = id
        self._operario_id = operario_id
        self._centro_id = centro_id
        self._centro_nombre = centro_nombre
        self._hora_entrada = hora_entrada
        self._hora_salida = hora_salida

    def registrar_salida(self, hora: datetime) -> None:
        if self._hora_salida is not None:
            raise ErrorDeNegocio("La salida ya fue registrada")
        if hora < self._hora_entrada:
            raise ErrorDeNegocio("La salida no puede ser anterior a la entrada")
        self._hora_salida = hora

    def esta_abierta(self) -> bool:
        return self._hora_salida is None

    def es_del_centro(self, centro_id: int) -> bool:
        return self._centro_id == centro_id

    @property
    def id(self): return self._id
    @property
    def operario_id(self): return self._operario_id
    @property
    def centro_id(self): return self._centro_id
    @property
    def centro_nombre(self): return self._centro_nombre
    @property
    def fecha(self): return self._hora_entrada.date()
    @property
    def hora_entrada(self): return self._hora_entrada
    @property
    def hora_salida(self): return self._hora_salida
