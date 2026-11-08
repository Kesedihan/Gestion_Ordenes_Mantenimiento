"""Proceso en segundo plano: python -m app.programacion.trabajador_outbox."""
import logging
import os
import time

from sqlalchemy.exc import SQLAlchemyError

from app.main import app
from app.programacion.casos_uso import ProcesarOutbox
from app.programacion.correo import ConfiguracionSMTP, EmisorSMTP
from app.programacion.infraestructura import RepositorioOutboxSQL

logger = logging.getLogger("sgml.outbox")


def ejecutar() -> None:
    contenedor = app.state.contenedor
    emisor = EmisorSMTP(ConfiguracionSMTP.desde_entorno())
    espera = max(1, int(os.getenv("SGML_OUTBOX_POLL_SECONDS", "5")))
    logger.info(
        "Trabajador outbox activo; SMTP %s:%s, consulta cada %s s",
        os.getenv("SGML_SMTP_HOST", "localhost"),
        os.getenv("SGML_SMTP_PORT", "1025"),
        espera,
    )
    while True:
        try:
            with contenedor.Sesion() as sesion:
                procesador = ProcesarOutbox(RepositorioOutboxSQL(sesion), emisor)
                procesado = procesador.ejecutar_siguiente()
        except SQLAlchemyError:
            logger.exception("Error procesando el outbox; se reintentará en el siguiente ciclo")
            procesado = False
        if not procesado:
            time.sleep(espera)


if __name__ == "__main__":
    logging.basicConfig(
        level=os.getenv("SGML_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    ejecutar()
