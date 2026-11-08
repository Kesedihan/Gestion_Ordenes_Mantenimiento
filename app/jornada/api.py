"""M2 - Adaptador de ENTRADA REST del módulo Jornada (solo traduce HTTP)."""
from datetime import date, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.compartido.errores import NoEncontrado
from app.dependencias import obtener_contenedor, obtener_sesion
from app.identidad.dependencias import exigir_roles, obtener_usuario_actual
from app.identidad.dominio import Rol, Usuario
from app.jornada.dominio import (Actividad, Evento, MomentoEvidencia,
                                 ResultadoRevision, TipoEvento)

router = APIRouter(tags=["M2 - Jornada, actividades y evidencias"])


def casos_uso(sesion=Depends(obtener_sesion), c=Depends(obtener_contenedor)):
    return c.casos_uso_jornada(sesion)


class EventoIn(BaseModel):
    id: str = Field(min_length=8, max_length=36, description="UUID generado en el celular")
    tipo: TipoEvento
    hora_dispositivo: datetime
    datos: dict = {}


class LoteIn(BaseModel):
    operario_id: int
    eventos: list[EventoIn] = Field(max_length=500)


class ResultadoOut(BaseModel):
    id: str
    estado: str
    motivo: str | None = None


class RevisionIn(BaseModel):
    resultado: ResultadoRevision
    observacion: str | None = None


class PendienteRevisionOut(BaseModel):
    id: int
    operario: str
    fecha: date
    centro: str
    tipo_servicio: str
    descripcion: str
    estado: str
    correccion_de_id: int | None = None
    motivo_correccion: str | None = None
    hora_inicio: datetime | None
    hora_fin: datetime | None
    evidencias: list[str]


class ActividadOut(BaseModel):
    id: int
    fecha: date
    centro_id: int
    centro: str
    tipo_servicio: str
    descripcion: str
    estado: str
    hora_inicio: datetime | None
    hora_fin: datetime | None
    evidencias: list[str]
    observacion: str | None
    correccion_de_id: int | None = None
    motivo_correccion: str | None = None

    @classmethod
    def desde(cls, a: Actividad) -> "ActividadOut":
        return cls(id=a.id, fecha=a.fecha, centro_id=a.centro_id, centro=a.centro_nombre,
                   tipo_servicio=a.tipo_servicio, descripcion=a.descripcion,
                   estado=a.estado.value, hora_inicio=a.hora_inicio, hora_fin=a.hora_fin,
                   evidencias=sorted(m.value for m in a.evidencias), observacion=a.observacion,
                   correccion_de_id=a.correccion_de_id,
                   motivo_correccion=a.motivo_correccion)


@router.get("/api/jornada/programacion/{operario_id}", response_model=list[ActividadOut])
def programacion(
    operario_id: int,
    desde: date | None = None,
    dias: int = 7,
    cu=Depends(casos_uso),
    usuario: Usuario = Depends(exigir_roles(Rol.OPERARIO)),
):
    if usuario.operario_id != operario_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo puedes consultar tu propia programación",
        )
    actividades = cu.consultar_programacion.ejecutar(operario_id, desde or date.today(), dias)
    return [ActividadOut.desde(a) for a in actividades]


@router.get("/api/jornada/mi-programacion", response_model=list[ActividadOut])
def mi_programacion(
    desde: date | None = None,
    dias: int = 14,
    cu=Depends(casos_uso),
    usuario: Usuario = Depends(exigir_roles(Rol.OPERARIO)),
):
    if usuario.operario_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La cuenta no está vinculada a una hoja de vida de operario",
        )
    actividades = cu.consultar_programacion.ejecutar(
        usuario.operario_id, desde or date.today(), dias
    )
    return [ActividadOut.desde(actividad) for actividad in actividades]


@router.post("/api/jornada/sincronizar", response_model=list[ResultadoOut])
def sincronizar(
    lote: LoteIn,
    cu=Depends(casos_uso),
    usuario: Usuario = Depends(exigir_roles(Rol.OPERARIO)),
):
    _exigir_mismo_operario(usuario, lote.operario_id)
    eventos = [Evento(e.id, e.tipo, lote.operario_id, e.hora_dispositivo.replace(tzinfo=None), e.datos)
               for e in lote.eventos]
    return [vars(r) for r in cu.sincronizar_lote.ejecutar(lote.operario_id, eventos)]


@router.post("/api/jornada/evidencias", response_model=ResultadoOut)
async def subir_evidencia(
    evento_id: str = Form(...), operario_id: int = Form(...), actividad_id: int = Form(...),
    momento: str = Form(...), tomada_en: datetime = Form(...), foto: UploadFile = File(...),
    cu=Depends(casos_uso),
    usuario: Usuario = Depends(exigir_roles(Rol.OPERARIO)),
):
    _exigir_mismo_operario(usuario, operario_id)
    evento = Evento(evento_id, TipoEvento.EVIDENCIA, operario_id, tomada_en.replace(tzinfo=None),
                    {"actividad_id": actividad_id, "momento": momento})
    resultado = cu.subir_evidencia.ejecutar(evento, await foto.read(), foto.content_type)
    return vars(resultado)


def _exigir_mismo_operario(usuario: Usuario, operario_id: int) -> None:
    if usuario.operario_id != operario_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo puedes sincronizar trabajo de tu propia hoja de vida",
        )


@router.patch("/api/jornada/actividades/{actividad_id}/revision", response_model=ActividadOut)
def revisar(actividad_id: int, datos: RevisionIn,
            cu=Depends(casos_uso), supervisor=Depends(exigir_roles(Rol.SUPERVISOR))):
    actividad = cu.revisar_actividad.ejecutar(actividad_id, supervisor.id,
                                              datos.resultado, datos.observacion)
    return ActividadOut.desde(actividad)


@router.get(
    "/api/jornada/revisiones",
    response_model=list[PendienteRevisionOut],
    dependencies=[Depends(exigir_roles(Rol.SUPERVISOR))],
)
def pendientes_revision(fecha: date | None = None, cu=Depends(casos_uso)):
    return cu.consultar_pendientes_revision.ejecutar(fecha or date.today())


@router.get(
    "/api/jornada/actividades/{actividad_id}/evidencias/{momento}",
    dependencies=[Depends(exigir_roles(
        Rol.SUPERVISOR, Rol.ADMINISTRADOR, Rol.ADMINISTRATIVO))],
)
def consultar_evidencia(actividad_id: int, momento: MomentoEvidencia,
                        cu=Depends(casos_uso)):
    ruta = Path(cu.consultar_evidencia.ejecutar(actividad_id, momento))
    if not ruta.is_file():
        raise NoEncontrado(f"El archivo de evidencia {momento.value} no está disponible")
    tipo = "image/png" if ruta.suffix.lower() == ".png" else "image/jpeg"
    return FileResponse(ruta, media_type=tipo)


@router.get(
    "/api/seguimiento",
    dependencies=[Depends(exigir_roles(Rol.ADMINISTRADOR, Rol.ADMINISTRATIVO))],
)
def seguimiento(fecha: date | None = None, cu=Depends(casos_uso)):
    return cu.consultar_seguimiento.ejecutar(fecha or date.today())
