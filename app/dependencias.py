"""Dependencias HTTP compartidas por los routers (DRY).

Una sesión de base de datos = una transacción por petición: si el caso de
uso termina bien se confirma (commit); si lanza una excepción, se revierte.
"""
from fastapi import Request


def obtener_contenedor(request: Request):
    return request.app.state.contenedor


def obtener_sesion(request: Request):
    sesion = request.app.state.contenedor.Sesion()
    try:
        yield sesion
        sesion.commit()
    except Exception:
        sesion.rollback()
        raise
    finally:
        sesion.close()
