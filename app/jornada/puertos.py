"""M2 - PUERTOS del módulo Jornada.

ISP: en lugar de un "RepositorioGeneral" con 20 métodos, hay interfaces
pequeñas por rol. Cada manejador o caso de uso depende solo de las que usa.
DIP: el dominio y los casos de uso dependen de estas abstracciones; SQLAlchemy,
el disco o MinIO son detalles que las implementan.
"""
from abc import ABC, abstractmethod
from datetime import date, datetime

from app.jornada.dominio import Actividad, EstadoEvento, Evento, Jornada, MomentoEvidencia


class RepositorioActividades(ABC):
    @abstractmethod
    def obtener(self, actividad_id: int) -> Actividad | None: ...
    @abstractmethod
    def guardar(self, actividad: Actividad) -> None: ...
    @abstractmethod
    def listar_por_operario(self, operario_id: int, desde: date, hasta: date) -> list[Actividad]: ...
    @abstractmethod
    def listar_por_fecha(self, fecha: date) -> list[Actividad]: ...


class RepositorioJornadas(ABC):
    @abstractmethod
    def jornada_abierta(self, operario_id: int, fecha: date) -> Jornada | None: ...
    @abstractmethod
    def guardar(self, jornada: Jornada) -> None: ...
    @abstractmethod
    def listar_por_fecha(self, fecha: date) -> list[Jornada]: ...


class RegistroEventos(ABC):
    """Bitácora de eventos sincronizados: garantiza idempotencia y auditoría."""
    @abstractmethod
    def estado_de(self, evento_id: str) -> tuple[EstadoEvento, str | None] | None: ...
    @abstractmethod
    def registrar(self, evento: Evento, recibido_en: datetime, estado: EstadoEvento,
                  motivo: str | None, hora_sospechosa: bool) -> None: ...
    @abstractmethod
    def resumen_operario(self, operario_id: int) -> tuple[datetime | None, int]:
        """(última sincronización, cantidad de eventos con hora sospechosa)."""


class RepositorioEvidencias(ABC):
    @abstractmethod
    def agregar(self, actividad_id: int, momento: MomentoEvidencia, ruta: str,
                sha256: str, tomada_en: datetime, recibida_en: datetime) -> None: ...
    @abstractmethod
    def obtener_ruta(self, actividad_id: int, momento: MomentoEvidencia) -> str | None: ...


class AlmacenArchivos(ABC):
    """Dónde viven los binarios de las fotos (disco local, MinIO/S3...)."""
    @abstractmethod
    def guardar(self, nombre: str, contenido: bytes) -> str: ...


class DirectorioOperarios(ABC):
    """Lo ÚNICO que Jornada necesita saber del módulo Hojas de vida.

    Ley de Demeter: Jornada no navega operario.hoja_vida.datos.nombre; pide
    directamente lo que necesita a esta interfaz.
    """
    @abstractmethod
    def esta_activo(self, operario_id: int) -> bool: ...
    @abstractmethod
    def nombre(self, operario_id: int) -> str: ...
