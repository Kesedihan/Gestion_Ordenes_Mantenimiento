"""Adaptador HTTP de entrada para autenticación OAuth 2.0."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.dependencias import obtener_contenedor, obtener_sesion
from app.identidad.seguridad import ServicioIdentidad

router = APIRouter(prefix="/api/auth", tags=["Identidad"])


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
