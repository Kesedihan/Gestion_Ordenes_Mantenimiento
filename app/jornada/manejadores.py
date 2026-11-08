"""M2 - Manejadores de eventos de sincronización.

OCP (abierto/cerrado): el caso de uso SincronizarLote NO tiene un
if/elif por tipo de evento (como la CalculadoraDescuento del ejemplo de
violación visto en clase). Cada tipo tiene su propia clase y se registra
en un diccionario. Para soportar un nuevo evento (p. ej. PAUSA) se crea una
clase nueva y se registra en el contenedor; SincronizarLote no se modifica.

LSP: todos los manejadores son intercambiables a través de ManejadorEvento.
SRP: cada manejador tiene una única responsabilidad (un tipo de evento).
"""
from abc import ABC, abstractmethod

from app.compartido.errores import ErrorDeNegocio
from app.jornada.dominio import Actividad, Evento, Jornada, TipoEvento
from app.jornada.puertos import RepositorioActividades, RepositorioJornadas


class ManejadorEvento(ABC):
    tipo: TipoEvento

    @abstractmethod
    def manejar(self, evento: Evento) -> None: ...


class ManejadorEntrada(ManejadorEvento):
    tipo = TipoEvento.ENTRADA

    def __init__(self, jornadas: RepositorioJornadas):
        self._jornadas = jornadas

    def manejar(self, evento: Evento) -> None:
        if self._jornadas.jornada_abierta(evento.operario_id, evento.hora_dispositivo.date()):
            raise ErrorDeNegocio("Ya existe una entrada sin salida para este día")
        self._jornadas.guardar(Jornada(
            operario_id=evento.operario_id,
            centro_id=int(evento.datos["centro_id"]),
            hora_entrada=evento.hora_dispositivo,
        ))


class ManejadorSalida(ManejadorEvento):
    tipo = TipoEvento.SALIDA

    def __init__(self, jornadas: RepositorioJornadas):
        self._jornadas = jornadas

    def manejar(self, evento: Evento) -> None:
        jornada = self._jornadas.jornada_abierta(evento.operario_id, evento.hora_dispositivo.date())
        if jornada is None:
            raise ErrorDeNegocio("No hay entrada registrada para registrar la salida")
        jornada.registrar_salida(evento.hora_dispositivo)
        self._jornadas.guardar(jornada)


class _ManejadorActividad(ManejadorEvento, ABC):
    """DRY: la búsqueda y validación de la actividad se escribe una sola vez."""

    def __init__(self, actividades: RepositorioActividades, jornadas: RepositorioJornadas):
        self._actividades = actividades
        self._jornadas = jornadas

    def _actividad_de(self, evento: Evento) -> Actividad:
        actividad = self._actividades.obtener(int(evento.datos["actividad_id"]))
        if actividad is None:
            raise ErrorDeNegocio("La actividad no existe")
        actividad.verificar_asignada_a(evento.operario_id)
        return actividad


class ManejadorInicioActividad(_ManejadorActividad):
    tipo = TipoEvento.INICIO_ACTIVIDAD

    def manejar(self, evento: Evento) -> None:
        actividad = self._actividad_de(evento)
        jornada = self._jornadas.jornada_abierta(evento.operario_id, evento.hora_dispositivo.date())
        if jornada is None or not jornada.es_del_centro(actividad.centro_id):
            raise ErrorDeNegocio("Debe registrar la entrada en el centro de trabajo antes de iniciar")
        actividad.iniciar(evento.hora_dispositivo)
        self._actividades.guardar(actividad)


class ManejadorFinActividad(_ManejadorActividad):
    tipo = TipoEvento.FIN_ACTIVIDAD

    def manejar(self, evento: Evento) -> None:
        actividad = self._actividad_de(evento)
        actividad.finalizar(evento.hora_dispositivo)
        self._actividades.guardar(actividad)
