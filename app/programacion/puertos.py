"""Abstracciones de persistencia, catálogos y entrega de correo."""
from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta

from app.programacion.dominio import (
    AsignacionProgramacion,
    MensajeOutbox,
    OperarioNotificable,
    ProgramacionSemanal,
)


class RepositorioProgramaciones(ABC):
    @abstractmethod
    def obtener(self, programacion_id: int) -> ProgramacionSemanal | None: ...

    @abstractmethod
    def obtener_por_semana(self, semana_inicio: date) -> ProgramacionSemanal | None: ...

    @abstractmethod
    def guardar(self, programacion: ProgramacionSemanal) -> ProgramacionSemanal: ...

    @abstractmethod
    def listar(self, semana_inicio: date | None = None) -> list[ProgramacionSemanal]: ...


class CatalogoProgramacion(ABC):
    @abstractmethod
    def obtener_operario_notificable(self, operario_id: int) -> OperarioNotificable | None: ...

    @abstractmethod
    def centro_existe(self, centro_id: int) -> bool: ...

    @abstractmethod
    def listar_centros(self) -> list[dict]: ...

    @abstractmethod
    def listar_operarios(self) -> list[dict]: ...

    @abstractmethod
    def crear_actividades(self, asignaciones: tuple[AsignacionProgramacion, ...]) -> None: ...


class RepositorioOutbox(ABC):
    @abstractmethod
    def agregar(
        self,
        programacion_id: int,
        destinatario: str,
        asunto: str,
        cuerpo: str,
        ahora: datetime,
    ) -> None: ...

    @abstractmethod
    def reclamar_siguiente(
        self, ahora: datetime, duracion_lease: timedelta
    ) -> MensajeOutbox | None: ...

    @abstractmethod
    def marcar_enviado(self, mensaje_id: str, enviado_en: datetime) -> None: ...

    @abstractmethod
    def reintentar(
        self,
        mensaje_id: str,
        disponible_en: datetime,
        error: str,
    ) -> None: ...


class EmisorCorreo(ABC):
    @abstractmethod
    def enviar(self, destinatario: str, asunto: str, cuerpo: str) -> None: ...
