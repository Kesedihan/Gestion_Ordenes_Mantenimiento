"""Puerto de reloj.

DIP: los casos de uso piden la hora a una abstracción y no a datetime.now().
Así las pruebas pueden fijar la hora (RelojFijo) sin modificar el código
de negocio.
"""
from abc import ABC, abstractmethod
from datetime import datetime


class Reloj(ABC):
    @abstractmethod
    def ahora(self) -> datetime: ...


class RelojSistema(Reloj):
    def ahora(self) -> datetime:
        return datetime.now()


class RelojFijo(Reloj):
    def __init__(self, momento: datetime):
        self._momento = momento

    def ahora(self) -> datetime:
        return self._momento
