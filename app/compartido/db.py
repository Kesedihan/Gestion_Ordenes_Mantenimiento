"""Infraestructura compartida de base de datos (adaptador técnico).

KISS: SQLite para el despliegue local del taller; en producción basta con
cambiar la URL por PostgreSQL (postgresql+psycopg://...). Ningún módulo de
dominio importa este archivo (DIP).
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    """Base declarativa común para los modelos ORM de todos los módulos."""


def crear_fabrica_sesiones(url: str):
    opciones = {}
    if url.startswith("sqlite"):
        opciones["connect_args"] = {"check_same_thread": False}
        if ":memory:" in url:
            opciones["poolclass"] = StaticPool
    motor = create_engine(url, **opciones)
    return motor, sessionmaker(bind=motor, expire_on_commit=False)
