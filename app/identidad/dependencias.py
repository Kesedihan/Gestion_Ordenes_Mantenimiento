"""Autenticación HTTP y autorización por rol para endpoints protegidos."""
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.identidad.api import obtener_servicio
from app.identidad.dominio import Rol, Usuario
from app.identidad.seguridad import ServicioIdentidad

ESQUEMA_BEARER = HTTPBearer(auto_error=False)


def obtener_usuario_actual(
    credenciales: Annotated[
        HTTPAuthorizationCredentials | None, Depends(ESQUEMA_BEARER)
    ],
    servicio: ServicioIdentidad = Depends(obtener_servicio),
) -> Usuario:
    if credenciales is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Se requiere autenticación",
            headers={"WWW-Authenticate": "Bearer"},
        )
    usuario = servicio.validar_access_token(credenciales.credentials)
    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido, expirado o usuario inactivo",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return usuario


def exigir_roles(*roles_permitidos: Rol) -> Callable:
    permitidos = frozenset(roles_permitidos)

    def verificar(usuario: Usuario = Depends(obtener_usuario_actual)) -> Usuario:
        if usuario.rol not in permitidos:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tu rol no tiene permiso para esta operación",
            )
        return usuario

    return verificar
