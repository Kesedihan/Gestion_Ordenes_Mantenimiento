"""Puertos de salida requeridos por los casos de uso de Identidad."""
from typing import Protocol

from app.identidad.dominio import Usuario


class RepositorioUsuarios(Protocol):
    def obtener_por_nombre(self, nombre_usuario: str) -> Usuario | None: ...

    def guardar(self, usuario: Usuario) -> Usuario: ...
