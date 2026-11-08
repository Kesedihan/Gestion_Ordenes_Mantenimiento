"""M1 - Hojas de vida: adaptador de ENTRADA (REST).

SoC: este archivo solo traduce HTTP <-> caso de uso. No contiene reglas.
IoC: FastAPI (el framework) llama a obtener_servicio() e inyecta el caso de
uso ya armado por el contenedor; el router no crea sus dependencias.
"""
from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.dependencias import obtener_contenedor, obtener_sesion
from app.hojas_vida.casos_uso import ServicioHojasVida
from app.hojas_vida.dominio import Especialidad, Experiencia, Formacion, Operario

router = APIRouter(prefix="/api/operarios", tags=["M1 - Hojas de vida"])


def obtener_servicio(sesion=Depends(obtener_sesion), c=Depends(obtener_contenedor)):
    return c.servicio_hojas_vida(sesion)


class FormacionIn(BaseModel):
    nivel: str
    titulo: str
    institucion: str
    anio_fin: int | None = None


class ExperienciaIn(BaseModel):
    empresa: str
    cargo: str
    meses: int = Field(ge=0)


class OperarioIn(BaseModel):
    documento: str
    nombres: str
    apellidos: str
    telefono: str
    correo_institucional: str
    fecha_ingreso: date
    especialidades: list[Especialidad]
    formacion: list[FormacionIn] = []
    experiencia: list[ExperienciaIn] = []


class ContactoIn(BaseModel):
    telefono: str
    correo_institucional: str


class EstadoIn(BaseModel):
    activo: bool


class OperarioOut(BaseModel):
    id: int
    documento: str
    nombre_completo: str
    telefono: str
    correo_institucional: str
    fecha_ingreso: date
    especialidades: list[Especialidad]
    formacion: list[FormacionIn]
    experiencia: list[ExperienciaIn]
    anios_experiencia: float
    estado: str

    @classmethod
    def desde(cls, o: Operario) -> "OperarioOut":
        return cls(
            id=o.id, documento=o.documento, nombre_completo=o.nombre_completo(),
            telefono=o.telefono, correo_institucional=o.correo_institucional,
            fecha_ingreso=o.fecha_ingreso, especialidades=list(o.especialidades),
            formacion=[FormacionIn(**vars(f)) for f in o.formacion],
            experiencia=[ExperienciaIn(**vars(e)) for e in o.experiencia],
            anios_experiencia=o.anios_experiencia(), estado=o.estado.value,
        )


@router.post("", response_model=OperarioOut, status_code=201)
def registrar(datos: OperarioIn, servicio: ServicioHojasVida = Depends(obtener_servicio)):
    operario = Operario(
        **datos.model_dump(exclude={"formacion", "experiencia"}),
        formacion=[Formacion(**f.model_dump()) for f in datos.formacion],
        experiencia=[Experiencia(**e.model_dump()) for e in datos.experiencia],
    )
    return OperarioOut.desde(servicio.registrar(operario))


@router.get("", response_model=list[OperarioOut])
def listar(solo_activos: bool = False, servicio: ServicioHojasVida = Depends(obtener_servicio)):
    return [OperarioOut.desde(o) for o in servicio.listar(solo_activos)]


@router.get("/{operario_id}", response_model=OperarioOut)
def obtener(operario_id: int, servicio: ServicioHojasVida = Depends(obtener_servicio)):
    return OperarioOut.desde(servicio.obtener(operario_id))


@router.put("/{operario_id}/contacto", response_model=OperarioOut)
def actualizar_contacto(operario_id: int, datos: ContactoIn,
                        servicio: ServicioHojasVida = Depends(obtener_servicio)):
    return OperarioOut.desde(
        servicio.actualizar_contacto(operario_id, datos.telefono, datos.correo_institucional))


@router.patch("/{operario_id}/estado", response_model=OperarioOut)
def cambiar_estado(operario_id: int, datos: EstadoIn,
                   servicio: ServicioHojasVida = Depends(obtener_servicio)):
    return OperarioOut.desde(servicio.cambiar_estado(operario_id, datos.activo))
