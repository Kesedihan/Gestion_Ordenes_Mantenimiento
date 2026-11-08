"""Dominio de identidad, independiente de HTTP y persistencia."""
from enum import Enum

from app.compartido.errores import ErrorDeNegocio


class Rol(str, Enum):
    ADMINISTRADOR = "ADMINISTRADOR"
    ADMINISTRATIVO = "ADMINISTRATIVO"
    SUPERVISOR = "SUPERVISOR"
    OPERARIO = "OPERARIO"


class Usuario:
    def __init__(
        self,
        nombre_usuario: str,
        hash_contrasena: str,
        rol: Rol,
        activo: bool = True,
        id: int | None = None,
        operario_id: int | None = None,
    ):
        if not nombre_usuario.strip():
            raise ErrorDeNegocio("El nombre de usuario es obligatorio")
        if not hash_contrasena:
            raise ErrorDeNegocio("La contraseña debe almacenarse cifrada")
        self._id = id
        self._nombre_usuario = nombre_usuario.strip()
        self._hash_contrasena = hash_contrasena
        self._rol = Rol(rol)
        self._activo = activo
        if self._rol is Rol.OPERARIO and operario_id is None:
            raise ErrorDeNegocio("La cuenta de operario debe vincularse a una hoja de vida")
        if self._rol is not Rol.OPERARIO and operario_id is not None:
            raise ErrorDeNegocio("Solo una cuenta de operario puede vincularse a una hoja de vida")
        self._operario_id = operario_id

    @property
    def id(self) -> int | None:
        return self._id

    @property
    def nombre_usuario(self) -> str:
        return self._nombre_usuario

    @property
    def hash_contrasena(self) -> str:
        return self._hash_contrasena

    @property
    def rol(self) -> Rol:
        return self._rol

    @property
    def activo(self) -> bool:
        return self._activo

    @property
    def operario_id(self) -> int | None:
        return self._operario_id

    def desactivar(self) -> None:
        self._activo = False

    def activar(self) -> None:
        self._activo = True
