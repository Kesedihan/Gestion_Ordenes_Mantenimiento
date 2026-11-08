"""Adaptador SQLAlchemy del repositorio de usuarios."""
from sqlalchemy import Boolean, ForeignKey, Index, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.compartido.db import Base
from app.identidad.dominio import Rol, Usuario
from app.identidad.puertos import RepositorioUsuarios


class UsuarioModelo(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre_usuario: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    hash_contrasena: Mapped[str] = mapped_column(String(100))
    rol: Mapped[str] = mapped_column(String(20))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    operario_id: Mapped[int | None] = mapped_column(
        ForeignKey("operarios.id"), nullable=True
    )

    __table_args__ = (
        Index("uq_usuarios_operario_id", "operario_id", unique=True),
    )


class RepositorioUsuariosSQL(RepositorioUsuarios):
    def __init__(self, sesion: Session):
        self._sesion = sesion

    def obtener_por_nombre(self, nombre_usuario: str) -> Usuario | None:
        modelo = self._sesion.scalar(
            select(UsuarioModelo).where(UsuarioModelo.nombre_usuario == nombre_usuario)
        )
        return self._a_dominio(modelo) if modelo else None

    def guardar(self, usuario: Usuario) -> Usuario:
        modelo = UsuarioModelo(
            nombre_usuario=usuario.nombre_usuario,
            hash_contrasena=usuario.hash_contrasena,
            rol=usuario.rol.value,
            activo=usuario.activo,
            operario_id=usuario.operario_id,
        )
        self._sesion.add(modelo)
        self._sesion.flush()
        return Usuario(
            id=modelo.id,
            nombre_usuario=modelo.nombre_usuario,
            hash_contrasena=modelo.hash_contrasena,
            rol=Rol(modelo.rol),
            activo=modelo.activo,
            operario_id=modelo.operario_id,
        )

    @staticmethod
    def _a_dominio(modelo: UsuarioModelo) -> Usuario:
        return Usuario(
            id=modelo.id,
            nombre_usuario=modelo.nombre_usuario,
            hash_contrasena=modelo.hash_contrasena,
            rol=Rol(modelo.rol),
            activo=modelo.activo,
            operario_id=modelo.operario_id,
        )
