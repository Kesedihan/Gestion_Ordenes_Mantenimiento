"""Casos de uso de programación semanal y entrega confiable del outbox."""
from datetime import date, datetime, timedelta, timezone
from email.utils import parseaddr
import logging
import smtplib

from app.compartido.errores import Conflicto, ErrorDeNegocio, NoEncontrado
from app.programacion.dominio import (
    AsignacionProgramacion,
    EstadoProgramacion,
    ProgramacionSemanal,
)
from app.programacion.puertos import (
    CatalogoProgramacion,
    EmisorCorreo,
    RepositorioOutbox,
    RepositorioProgramaciones,
)

logger = logging.getLogger(__name__)


def ahora_utc_sin_zona() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class CrearProgramacion:
    def __init__(
        self,
        programaciones: RepositorioProgramaciones,
        catalogo: CatalogoProgramacion,
    ):
        self._programaciones = programaciones
        self._catalogo = catalogo

    def ejecutar(
        self,
        semana_inicio: date,
        asignaciones: list[AsignacionProgramacion],
        creada_por: int,
    ) -> ProgramacionSemanal:
        programacion = ProgramacionSemanal(semana_inicio, asignaciones, creada_por)
        if self._programaciones.obtener_por_semana(semana_inicio):
            raise Conflicto("Ya existe una programación para esa semana")
        for asignacion in programacion.asignaciones:
            if self._catalogo.obtener_operario_notificable(asignacion.operario_id) is None:
                raise ErrorDeNegocio(
                    f"El operario {asignacion.operario_id} no existe o está inactivo"
                )
            if not self._catalogo.centro_existe(asignacion.centro_id):
                raise ErrorDeNegocio(f"El centro {asignacion.centro_id} no existe")
        return self._programaciones.guardar(programacion)


class ListarProgramaciones:
    def __init__(self, programaciones: RepositorioProgramaciones):
        self._programaciones = programaciones

    def ejecutar(self, semana_inicio: date | None = None) -> list[ProgramacionSemanal]:
        return self._programaciones.listar(semana_inicio)


class ListarCatalogosProgramacion:
    def __init__(self, catalogo: CatalogoProgramacion):
        self._catalogo = catalogo

    def ejecutar(self) -> dict:
        return {
            "operarios": self._catalogo.listar_operarios(),
            "centros": self._catalogo.listar_centros(),
        }


class PublicarProgramacion:
    def __init__(
        self,
        programaciones: RepositorioProgramaciones,
        catalogo: CatalogoProgramacion,
        outbox: RepositorioOutbox,
    ):
        self._programaciones = programaciones
        self._catalogo = catalogo
        self._outbox = outbox

    def ejecutar(self, programacion_id: int) -> ProgramacionSemanal:
        programacion = self._programaciones.obtener(programacion_id)
        if programacion is None:
            raise NoEncontrado(f"Programación {programacion_id} no existe")
        if programacion.estado is EstadoProgramacion.PUBLICADA:
            raise Conflicto("La programación ya fue publicada")

        por_operario: dict[int, list[AsignacionProgramacion]] = {}
        destinatarios = {}
        centros = {centro["id"]: centro["nombre"]
                   for centro in self._catalogo.listar_centros()}
        for asignacion in programacion.asignaciones:
            operario = self._catalogo.obtener_operario_notificable(asignacion.operario_id)
            if operario is None:
                raise ErrorDeNegocio(
                    f"El operario {asignacion.operario_id} ya no existe o está inactivo"
                )
            direccion = parseaddr(operario.correo)[1]
            if not direccion or direccion != operario.correo:
                raise ErrorDeNegocio(
                    f"El operario {asignacion.operario_id} no tiene un correo válido"
                )
            destinatarios[asignacion.operario_id] = operario
            por_operario.setdefault(asignacion.operario_id, []).append(asignacion)

        ahora = ahora_utc_sin_zona()
        programacion.publicar(ahora)
        guardada = self._programaciones.guardar(programacion)
        self._catalogo.crear_actividades(programacion.asignaciones)

        fin_semana = programacion.semana_inicio + timedelta(days=6)
        for operario_id, asignaciones in por_operario.items():
            operario = destinatarios[operario_id]
            lineas = [
                f"- {asignacion.fecha.isoformat()}: {asignacion.tipo_servicio} en "
                f"{centros[asignacion.centro_id]}. {asignacion.descripcion}"
                for asignacion in asignaciones
            ]
            cuerpo = (
                f"Hola {operario.nombre},\n\n"
                f"Tu programación semanal ({programacion.semana_inicio.isoformat()} a "
                f"{fin_semana.isoformat()}) ha sido publicada:\n\n"
                + "\n".join(lineas)
                + "\n\nConsulta tu jornada en la aplicación SGML."
            )
            self._outbox.agregar(
                guardada.id,
                operario.correo,
                f"SGML: programación semanal desde {programacion.semana_inicio.isoformat()}",
                cuerpo,
                ahora,
            )
        return guardada


class ProcesarOutbox:
    REINTENTO_BASE = timedelta(seconds=30)
    REINTENTO_MAXIMO = timedelta(hours=6)
    DURACION_LEASE = timedelta(minutes=2)

    def __init__(self, outbox: RepositorioOutbox, emisor: EmisorCorreo):
        self._outbox = outbox
        self._emisor = emisor

    def ejecutar_siguiente(self) -> bool:
        ahora = ahora_utc_sin_zona()
        mensaje = self._outbox.reclamar_siguiente(ahora, self.DURACION_LEASE)
        if mensaje is None:
            return False
        try:
            self._emisor.enviar(mensaje.destinatario, mensaje.asunto, mensaje.cuerpo)
        except (OSError, smtplib.SMTPException) as error:
            demora = min(
                self.REINTENTO_BASE * (2 ** max(mensaje.intentos - 1, 0)),
                self.REINTENTO_MAXIMO,
            )
            self._outbox.reintentar(
                mensaje.id,
                ahora + demora,
                f"{type(error).__name__}: {error}"[:1000],
            )
            logger.exception(
                "No se pudo enviar el mensaje outbox %s a %s; se reintentará",
                mensaje.id,
                mensaje.destinatario,
            )
            return True
        self._outbox.marcar_enviado(mensaje.id, ahora_utc_sin_zona())
        return True
