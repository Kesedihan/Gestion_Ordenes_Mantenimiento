"""Casos de uso de autenticación y emisión de credenciales."""
from datetime import datetime, timedelta, timezone
import secrets

import bcrypt
import jwt
from jwt.exceptions import InvalidTokenError

from app.compartido.errores import ErrorDeNegocio
from app.identidad.dominio import Rol, Usuario
from app.identidad.puertos import RepositorioUsuarios

ALGORITMO_JWT = "HS256"
DURACION_ACCESS = timedelta(minutes=15)
DURACION_REFRESH = timedelta(days=30)
MAX_BYTES_BCRYPT = 72


class ServicioIdentidad:
    def __init__(self, repositorio: RepositorioUsuarios, secreto_jwt: str):
        if not secreto_jwt:
            raise ValueError("Se requiere configurar un secreto JWT")
        self._repositorio = repositorio
        self._secreto_jwt = secreto_jwt

    @staticmethod
    def crear_hash_contrasena(contrasena: str) -> str:
        contrasena_bytes = contrasena.encode("utf-8")
        if not contrasena_bytes or len(contrasena_bytes) > MAX_BYTES_BCRYPT:
            raise ErrorDeNegocio("La contraseña debe tener entre 1 y 72 bytes UTF-8")
        return bcrypt.hashpw(contrasena_bytes, bcrypt.gensalt()).decode("ascii")

    @staticmethod
    def verificar_contrasena(contrasena: str, hash_contrasena: str) -> bool:
        contrasena_bytes = contrasena.encode("utf-8")
        if not contrasena_bytes or len(contrasena_bytes) > MAX_BYTES_BCRYPT:
            return False
        try:
            return bcrypt.checkpw(contrasena_bytes, hash_contrasena.encode("ascii"))
        except (ValueError, TypeError):
            return False

    def crear_usuario(
        self,
        nombre_usuario: str,
        contrasena: str,
        rol: Rol,
        operario_id: int | None = None,
    ) -> Usuario:
        if self._repositorio.obtener_por_nombre(nombre_usuario):
            raise ErrorDeNegocio("El nombre de usuario ya está registrado")
        usuario = Usuario(
            nombre_usuario=nombre_usuario,
            hash_contrasena=self.crear_hash_contrasena(contrasena),
            rol=rol,
            operario_id=operario_id,
        )
        return self._repositorio.guardar(usuario)

    def autenticar(self, nombre_usuario: str, contrasena: str) -> dict | None:
        usuario = self._repositorio.obtener_por_nombre(nombre_usuario)
        if not usuario or not usuario.activo:
            return None
        if not self.verificar_contrasena(contrasena, usuario.hash_contrasena):
            return None

        ahora = datetime.now(timezone.utc)
        return {
            "access_token": self._generar_token(usuario, "access", ahora, DURACION_ACCESS),
            "refresh_token": self._generar_token(usuario, "refresh", ahora, DURACION_REFRESH),
            "token_type": "bearer",
            "rol": usuario.rol.value,
            "nombre_usuario": usuario.nombre_usuario,
            "operario_id": usuario.operario_id,
            "expires_in": int(DURACION_ACCESS.total_seconds()),
        }

    def validar_access_token(self, token: str) -> Usuario | None:
        try:
            claims = jwt.decode(
                token,
                self._secreto_jwt,
                algorithms=[ALGORITMO_JWT],
                options={"require": ["sub", "exp", "iat", "type", "role"]},
            )
        except InvalidTokenError:
            return None
        if claims.get("type") != "access":
            return None

        usuario = self._repositorio.obtener_por_nombre(claims["sub"])
        if (
            usuario is None
            or not usuario.activo
            or usuario.rol.value != claims.get("role")
        ):
            return None
        return usuario

    def _generar_token(
        self, usuario: Usuario, tipo: str, ahora: datetime, duracion: timedelta
    ) -> str:
        return jwt.encode(
            {
                "sub": usuario.nombre_usuario,
                "role": usuario.rol.value,
                "operario_id": usuario.operario_id,
                "type": tipo,
                "iat": ahora,
                "exp": ahora + duracion,
                "jti": secrets.token_urlsafe(16),
            },
            self._secreto_jwt,
            algorithm=ALGORITMO_JWT,
        )
