"""Adaptador HTTP de entrada para la programación semanal."""
from datetime import date, datetime

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from app.dependencias import obtener_contenedor, obtener_sesion
from app.identidad.dependencias import exigir_roles, obtener_usuario_actual
from app.identidad.dominio import Rol, Usuario
from app.programacion.dominio import AsignacionProgramacion, ProgramacionSemanal

router = APIRouter(prefix="/api/programaciones", tags=["M3 - Programación"])


def obtener_casos_uso(
    sesion=Depends(obtener_sesion),
    contenedor=Depends(obtener_contenedor),
):
    return contenedor.casos_uso_programacion(sesion)


class AsignacionIn(BaseModel):
    operario_id: int = Field(gt=0)
    centro_id: int = Field(gt=0)
    fecha: date
    tipo_servicio: str = Field(min_length=1, max_length=30)
    descripcion: str = Field(min_length=1, max_length=300)


class ProgramacionIn(BaseModel):
    semana_inicio: date
    asignaciones: list[AsignacionIn] = Field(min_length=1, max_length=200)


class AsignacionOut(BaseModel):
    operario_id: int
    centro_id: int
    fecha: date
    tipo_servicio: str
    descripcion: str


class ProgramacionOut(BaseModel):
    id: int
    semana_inicio: date
    estado: str
    creada_por: int
    creada_en: datetime | None
    publicada_en: datetime | None
    asignaciones: list[AsignacionOut]

    @classmethod
    def desde(cls, programacion: ProgramacionSemanal) -> "ProgramacionOut":
        return cls(
            id=programacion.id,
            semana_inicio=programacion.semana_inicio,
            estado=programacion.estado.value,
            creada_por=programacion.creada_por,
            creada_en=programacion.creada_en,
            publicada_en=programacion.publicada_en,
            asignaciones=[
                AsignacionOut(
                    operario_id=asignacion.operario_id,
                    centro_id=asignacion.centro_id,
                    fecha=asignacion.fecha,
                    tipo_servicio=asignacion.tipo_servicio,
                    descripcion=asignacion.descripcion,
                )
                for asignacion in programacion.asignaciones
            ],
        )


@router.get(
    "/catalogos",
    dependencies=[Depends(exigir_roles(Rol.ADMINISTRADOR))],
)
def catalogos(casos=Depends(obtener_casos_uso)):
    return casos.catalogos.ejecutar()


@router.post(
    "",
    response_model=ProgramacionOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(exigir_roles(Rol.ADMINISTRADOR))],
)
def crear(
    datos: ProgramacionIn,
    casos=Depends(obtener_casos_uso),
    usuario: Usuario = Depends(obtener_usuario_actual),
):
    programacion = casos.crear.ejecutar(
        semana_inicio=datos.semana_inicio,
        asignaciones=[
            AsignacionProgramacion(**asignacion.model_dump())
            for asignacion in datos.asignaciones
        ],
        creada_por=usuario.id,
    )
    return ProgramacionOut.desde(programacion)


@router.get(
    "",
    response_model=list[ProgramacionOut],
    dependencies=[Depends(exigir_roles(Rol.ADMINISTRADOR))],
)
def listar(
    semana_inicio: date | None = None,
    casos=Depends(obtener_casos_uso),
):
    return [
        ProgramacionOut.desde(programacion)
        for programacion in casos.listar.ejecutar(semana_inicio)
    ]


@router.post(
    "/{programacion_id}/publicar",
    response_model=ProgramacionOut,
    dependencies=[Depends(exigir_roles(Rol.ADMINISTRADOR))],
)
def publicar(programacion_id: int, casos=Depends(obtener_casos_uso)):
    return ProgramacionOut.desde(casos.publicar.ejecutar(programacion_id))
