"""Dominio de programación semanal y mensajes en cola."""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum

from app.compartido.errores import ErrorDeNegocio


class EstadoProgramacion(str, Enum):
    BORRADOR = "BORRADOR"
    PUBLICADA = "PUBLICADA"


@dataclass(frozen=True)
class AsignacionProgramacion:
    operario_id: int
    centro_id: int
    fecha: date
    tipo_servicio: str
    descripcion: str

    def __post_init__(self):
        if self.operario_id <= 0 or self.centro_id <= 0:
            raise ErrorDeNegocio("Operario y centro deben ser válidos")
        if not self.tipo_servicio.strip() or len(self.tipo_servicio) > 30:
            raise ErrorDeNegocio("El servicio es obligatorio y admite hasta 30 caracteres")
        if not self.descripcion.strip() or len(self.descripcion) > 300:
            raise ErrorDeNegocio("La descripción es obligatoria y admite hasta 300 caracteres")
        object.__setattr__(self, "tipo_servicio", self.tipo_servicio.strip().upper())
        object.__setattr__(self, "descripcion", self.descripcion.strip())


class ProgramacionSemanal:
    def __init__(
        self,
        semana_inicio: date,
        asignaciones: list[AsignacionProgramacion],
        creada_por: int,
        estado: EstadoProgramacion = EstadoProgramacion.BORRADOR,
        id: int | None = None,
        creada_en: datetime | None = None,
        publicada_en: datetime | None = None,
    ):
        if semana_inicio.weekday() != 0:
            raise ErrorDeNegocio("La programación debe iniciar un lunes")
        if creada_por <= 0:
            raise ErrorDeNegocio("El usuario creador no es válido")
        if not asignaciones:
            raise ErrorDeNegocio("La programación debe incluir al menos una asignación")
        fin_semana = semana_inicio + timedelta(days=6)
        if any(not semana_inicio <= asignacion.fecha <= fin_semana
               for asignacion in asignaciones):
            raise ErrorDeNegocio("Todas las asignaciones deben estar dentro de la semana")
        if len(set(asignaciones)) != len(asignaciones):
            raise ErrorDeNegocio("La programación contiene asignaciones duplicadas")
        if estado is EstadoProgramacion.PUBLICADA and publicada_en is None:
            raise ErrorDeNegocio("Una programación publicada requiere su fecha de publicación")
        self._id = id
        self._semana_inicio = semana_inicio
        self._asignaciones = tuple(asignaciones)
        self._creada_por = creada_por
        self._estado = EstadoProgramacion(estado)
        self._creada_en = creada_en
        self._publicada_en = publicada_en

    def publicar(self, fecha_publicacion: datetime) -> None:
        if self._estado is EstadoProgramacion.PUBLICADA:
            raise ErrorDeNegocio("La programación ya fue publicada")
        self._estado = EstadoProgramacion.PUBLICADA
        self._publicada_en = fecha_publicacion

    @property
    def id(self) -> int | None:
        return self._id

    @property
    def semana_inicio(self) -> date:
        return self._semana_inicio

    @property
    def asignaciones(self) -> tuple[AsignacionProgramacion, ...]:
        return self._asignaciones

    @property
    def creada_por(self) -> int:
        return self._creada_por

    @property
    def estado(self) -> EstadoProgramacion:
        return self._estado

    @property
    def creada_en(self) -> datetime | None:
        return self._creada_en

    @property
    def publicada_en(self) -> datetime | None:
        return self._publicada_en


@dataclass(frozen=True)
class MensajeOutbox:
    id: str
    destinatario: str
    asunto: str
    cuerpo: str
    intentos: int


@dataclass(frozen=True)
class OperarioNotificable:
    id: int
    nombre: str
    correo: str
