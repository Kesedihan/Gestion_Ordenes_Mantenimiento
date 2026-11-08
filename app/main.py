"""Punto de entrada de la API (monolito modular).

Ejecutar:  uvicorn app.main:app --reload
Documentación interactiva: http://localhost:8000/docs
App del operario (PWA):    http://localhost:8000/app/
"""
import os
import logging
import secrets
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.compartido.errores import Conflicto, ErrorDeNegocio, NoEncontrado
from app.contenedor import Contenedor
from app.identidad.api import router as router_identidad
from app.hojas_vida.api import router as router_hojas_vida
from app.jornada.api import router as router_jornada
from app.programacion.api import router as router_programacion

RAIZ = Path(__file__).resolve().parent.parent
logger = logging.getLogger(__name__)


def crear_app(contenedor: Contenedor | None = None) -> FastAPI:
    if contenedor is None:
        secreto_jwt = os.getenv("SGML_JWT_SECRET")
        if not secreto_jwt:
            if os.getenv("SGML_ENV", "development").lower() == "production":
                raise RuntimeError("SGML_JWT_SECRET es obligatorio en producción")
            secreto_jwt = secrets.token_urlsafe(32)
            logger.warning("SGML_JWT_SECRET no está configurado; se usará uno temporal.")
        contenedor = Contenedor(
            url_bd=os.getenv("SGML_BD_URL", f"sqlite:///{RAIZ / 'sgml.db'}"),
            carpeta_evidencias=os.getenv("SGML_EVIDENCIAS", str(RAIZ / "evidencias")),
            secreto_jwt=secreto_jwt,
        )
    contenedor.crear_tablas()

    app = FastAPI(
        title="SGML - Sistema de Gestión de Mantenimiento Locativo",
        description="Identidad · M1 Hojas de vida · M2 Jornada, evidencias y seguimiento",
        version="1.0.0",
    )
    app.state.contenedor = contenedor
    app.include_router(router_identidad)
    app.include_router(router_hojas_vida)
    app.include_router(router_jornada)
    app.include_router(router_programacion)

    # DRY: un solo lugar traduce errores de negocio a HTTP para todos los módulos.
    for tipo_error, codigo in ((ErrorDeNegocio, 422), (NoEncontrado, 404), (Conflicto, 409)):
        app.add_exception_handler(
            tipo_error,
            lambda _req, exc, codigo=codigo: JSONResponse({"detail": str(exc)}, status_code=codigo))

    app.mount("/app", StaticFiles(directory=RAIZ / "pwa", html=True), name="pwa")

    @app.get("/", include_in_schema=False)
    def inicio(_: Request):
        return RedirectResponse("/docs")

    return app


app = crear_app()
