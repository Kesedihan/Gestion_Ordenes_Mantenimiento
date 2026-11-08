"""Adaptador SMTP configurado por variables de entorno."""
from dataclasses import dataclass
from email.message import EmailMessage
import os
import smtplib
import ssl

from app.programacion.puertos import EmisorCorreo


@dataclass(frozen=True)
class ConfiguracionSMTP:
    host: str = "localhost"
    puerto: int = 1025
    remitente: str = "sgml@localhost"
    usuario: str | None = None
    contrasena: str | None = None
    usar_starttls: bool = False
    timeout: float = 10

    @classmethod
    def desde_entorno(cls) -> "ConfiguracionSMTP":
        return cls(
            host=os.getenv("SGML_SMTP_HOST", "localhost"),
            puerto=int(os.getenv("SGML_SMTP_PORT", "1025")),
            remitente=os.getenv("SGML_SMTP_FROM", "sgml@localhost"),
            usuario=os.getenv("SGML_SMTP_USER") or None,
            contrasena=os.getenv("SGML_SMTP_PASSWORD") or None,
            usar_starttls=os.getenv("SGML_SMTP_STARTTLS", "false").lower() == "true",
        )


class EmisorSMTP(EmisorCorreo):
    def __init__(self, configuracion: ConfiguracionSMTP):
        self._configuracion = configuracion

    def enviar(self, destinatario: str, asunto: str, cuerpo: str) -> None:
        mensaje = EmailMessage()
        mensaje["From"] = self._configuracion.remitente
        mensaje["To"] = destinatario
        mensaje["Subject"] = asunto
        mensaje.set_content(cuerpo)
        with smtplib.SMTP(
            self._configuracion.host,
            self._configuracion.puerto,
            timeout=self._configuracion.timeout,
        ) as servidor:
            if self._configuracion.usar_starttls:
                servidor.starttls(context=ssl.create_default_context())
            if self._configuracion.usuario:
                servidor.login(
                    self._configuracion.usuario,
                    self._configuracion.contrasena or "",
                )
            servidor.send_message(mensaje)
