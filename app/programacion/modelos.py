"""Modelos ORM de catálogos y programación semanal."""
from datetime import date, datetime

from sqlalchemy import (Date, DateTime, ForeignKey, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.compartido.db import Base


class CentroTrabajoModelo(Base):
    __tablename__ = "centros_trabajo"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    direccion: Mapped[str] = mapped_column(String(200))


class ProgramacionSemanalModelo(Base):
    __tablename__ = "programaciones_semanales"
    __table_args__ = (UniqueConstraint("semana_inicio"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    semana_inicio: Mapped[date] = mapped_column(Date)
    estado: Mapped[str] = mapped_column(String(12), default="BORRADOR")
    creada_por: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    creada_en: Mapped[datetime] = mapped_column(DateTime)
    publicada_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    asignaciones: Mapped[list["AsignacionProgramacionModelo"]] = relationship(
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="AsignacionProgramacionModelo.fecha, AsignacionProgramacionModelo.id",
    )


class AsignacionProgramacionModelo(Base):
    __tablename__ = "asignaciones_programacion"
    __table_args__ = (
        UniqueConstraint(
            "programacion_id", "operario_id", "centro_id", "fecha",
            "tipo_servicio", "descripcion",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    programacion_id: Mapped[int] = mapped_column(
        ForeignKey("programaciones_semanales.id", ondelete="CASCADE"), index=True
    )
    operario_id: Mapped[int] = mapped_column(ForeignKey("operarios.id"))
    centro_id: Mapped[int] = mapped_column(ForeignKey("centros_trabajo.id"))
    fecha: Mapped[date] = mapped_column(Date)
    tipo_servicio: Mapped[str] = mapped_column(String(30))
    descripcion: Mapped[str] = mapped_column(String(300))


class MensajeOutboxModelo(Base):
    __tablename__ = "outbox"
    __table_args__ = (
        UniqueConstraint("programacion_id", "destinatario"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    programacion_id: Mapped[int] = mapped_column(
        ForeignKey("programaciones_semanales.id", ondelete="CASCADE"), index=True
    )
    destinatario: Mapped[str] = mapped_column(String(254))
    asunto: Mapped[str] = mapped_column(String(200))
    cuerpo: Mapped[str] = mapped_column(Text)
    estado: Mapped[str] = mapped_column(String(12), default="PENDIENTE", index=True)
    intentos: Mapped[int] = mapped_column(default=0)
    disponible_en: Mapped[datetime] = mapped_column(DateTime, index=True)
    bloqueado_hasta: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime)
    enviado_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
