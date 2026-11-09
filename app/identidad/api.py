"""Adaptador HTTP de entrada para autenticación OAuth 2.0."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from app.dependencias import obtener_contenedor, obtener_sesion
from app.identidad.seguridad import ServicioIdentidad

router = APIRouter(prefix="/api/auth", tags=["Identidad"])


class RenovarTokenIn(BaseModel):
    refresh_token: str


def obtener_servicio(
    sesion=Depends(obtener_sesion),
    contenedor=Depends(obtener_contenedor),
) -> ServicioIdentidad:
    return contenedor.servicio_identidad(sesion)


@router.post("/token")
def emitir_token(
    formulario: Annotated[OAuth2PasswordRequestForm, Depends()],
    servicio: Annotated[ServicioIdentidad, Depends(obtener_servicio)],
):
    tokens = servicio.autenticar(formulario.username, formulario.password)
    if tokens is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return tokens


@router.post("/refresh")
def renovar_token(
    datos: RenovarTokenIn,
    servicio: ServicioIdentidad = Depends(obtener_servicio),
):
    tokens = servicio.renovar_access_token(datos.refresh_token)
    if tokens is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return tokens
