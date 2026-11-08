"""M1 - Hojas de vida: capa de INFRAESTRUCTURA (adaptador de salida).

Implementa el puerto RepositorioOperarios con SQLAlchemy. Es el ÚNICO
lugar del módulo que conoce tablas y SQL. Si mañana se cambia el ORM o
la base de datos, solo cambia este archivo (bajo acoplamiento).
"""
from datetime import date

from sqlalchemy import ForeignKey, Integer, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from app.compartido.db import Base
from app.hojas_vida.dominio import (EstadoOperario, Especialidad, Experiencia,
                                    Formacion, Operario)
from app.hojas_vida.puertos import RepositorioOperarios


class OperarioModelo(Base):
    __tablename__ = "operarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    documento: Mapped[str] = mapped_column(String(12), unique=True)
    nombres: Mapped[str] = mapped_column(String(80))
    apellidos: Mapped[str] = mapped_column(String(80))
    telefono: Mapped[str] = mapped_column(String(20))
    correo_institucional: Mapped[str] = mapped_column(String(120), unique=True)
    fecha_ingreso: Mapped[date]
    especialidades: Mapped[str] = mapped_column(String(200))  # CSV de Especialidad
    estado: Mapped[str] = mapped_column(String(10))
    formacion: Mapped[list["FormacionModelo"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin")
    experiencia: Mapped[list["ExperienciaModelo"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin")


class FormacionModelo(Base):
    __tablename__ = "formacion"

    id: Mapped[int] = mapped_column(primary_key=True)
    operario_id: Mapped[int] = mapped_column(ForeignKey("operarios.id"))
    nivel: Mapped[str] = mapped_column(String(40))
    titulo: Mapped[str] = mapped_column(String(120))
    institucion: Mapped[str] = mapped_column(String(120))
    anio_fin: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ExperienciaModelo(Base):
    __tablename__ = "experiencia"

    id: Mapped[int] = mapped_column(primary_key=True)
    operario_id: Mapped[int] = mapped_column(ForeignKey("operarios.id"))
    empresa: Mapped[str] = mapped_column(String(120))
    cargo: Mapped[str] = mapped_column(String(80))
    meses: Mapped[int]


class RepositorioOperariosSQL(RepositorioOperarios):
    def __init__(self, sesion: Session):
        self._s = sesion

    def guardar(self, operario: Operario) -> Operario:
        modelo = self._s.get(OperarioModelo, operario.id) if operario.id else OperarioModelo()
        modelo.documento = operario.documento
        modelo.nombres = operario.nombres
        modelo.apellidos = operario.apellidos
        modelo.telefono = operario.telefono
        modelo.correo_institucional = operario.correo_institucional
        modelo.fecha_ingreso = operario.fecha_ingreso
        modelo.especialidades = ",".join(e.value for e in operario.especialidades)
        modelo.estado = operario.estado.value
        modelo.formacion = [FormacionModelo(**vars(f)) for f in operario.formacion]
        modelo.experiencia = [ExperienciaModelo(**vars(e)) for e in operario.experiencia]
        self._s.add(modelo)
        self._s.flush()
        if operario.id is None:
            operario.asignar_id(modelo.id)
        return operario

    def obtener(self, operario_id: int) -> Operario | None:
        modelo = self._s.get(OperarioModelo, operario_id)
        return _a_dominio(modelo) if modelo else None

    def listar(self, solo_activos: bool = False) -> list[Operario]:
        consulta = select(OperarioModelo).order_by(OperarioModelo.apellidos)
        if solo_activos:
            consulta = consulta.where(OperarioModelo.estado == EstadoOperario.ACTIVO.value)
        return [_a_dominio(m) for m in self._s.scalars(consulta)]

    def existe_documento(self, documento: str) -> bool:
        return self._s.scalar(select(OperarioModelo.id).where(
            OperarioModelo.documento == documento)) is not None

    def existe_correo(self, correo: str, excepto_id: int | None = None) -> bool:
        consulta = select(OperarioModelo.id).where(
            OperarioModelo.correo_institucional == correo.lower())
        if excepto_id is not None:
            consulta = consulta.where(OperarioModelo.id != excepto_id)
        return self._s.scalar(consulta) is not None


def _a_dominio(m: OperarioModelo) -> Operario:
    return Operario(
        id=m.id,
        documento=m.documento,
        nombres=m.nombres,
        apellidos=m.apellidos,
        telefono=m.telefono,
        correo_institucional=m.correo_institucional,
        fecha_ingreso=m.fecha_ingreso,
        especialidades=[Especialidad(e) for e in m.especialidades.split(",") if e],
        formacion=[Formacion(f.nivel, f.titulo, f.institucion, f.anio_fin) for f in m.formacion],
        experiencia=[Experiencia(e.empresa, e.cargo, e.meses) for e in m.experiencia],
        estado=EstadoOperario(m.estado),
    )
