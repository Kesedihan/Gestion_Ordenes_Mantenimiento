"""M1 - Hojas de vida: PUERTOS (interfaces que el caso de uso necesita).

DIP: el caso de uso (alto nivel) depende de esta abstracción; el repositorio
SQLAlchemy (bajo nivel) la implementa. Ninguno depende del otro.
ISP: interfaz pequeña, solo con lo que el caso de uso usa.
"""
from abc import ABC, abstractmethod

from app.hojas_vida.dominio import Operario


class RepositorioOperarios(ABC):
    @abstractmethod
    def guardar(self, operario: Operario) -> Operario: ...

    @abstractmethod
    def obtener(self, operario_id: int) -> Operario | None: ...

    @abstractmethod
    def listar(self, solo_activos: bool = False) -> list[Operario]: ...

    @abstractmethod
    def existe_documento(self, documento: str) -> bool: ...

    @abstractmethod
    def existe_correo(self, correo: str, excepto_id: int | None = None) -> bool: ...
