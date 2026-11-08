"""Carga de forma idempotente 2 centros, 3 operarios y su programación semanal.

Ejecutar:  python -m app.semilla
"""
from datetime import date, timedelta

from sqlalchemy import select

from app.hojas_vida.dominio import (
    Especialidad,
    Experiencia,
    Formacion,
    Operario,
)
from app.hojas_vida.infraestructura import OperarioModelo
from app.jornada.infraestructura import ActividadModelo
from app.programacion.modelos import CentroTrabajoModelo

OPERARIOS = [
    Operario("1075001001", "Carlos", "Perdomo", "3101234567", "carlos.perdomo@mantenimiento.com.co",
             date(2024, 2, 1), [Especialidad.PISCINA, Especialidad.ASEO_GENERAL],
             [Formacion("Técnico", "Mantenimiento de piscinas", "SENA", 2022)],
             [Experiencia("Aqua Servicios", "Piscinero", 30)]),
    Operario("1075002002", "Luisa", "Cabrera", "3112223344", "luisa.cabrera@mantenimiento.com.co",
             date(2023, 8, 15), [Especialidad.PINTURA],
             [Formacion("Bachiller", "Bachiller académico", "IE Santa Librada", 2015)],
             [Experiencia("Pinturas del Huila", "Pintora", 48)]),
    Operario("1075003003", "Jorge", "Trujillo", "3205556677", "jorge.trujillo@mantenimiento.com.co",
             date(2025, 1, 10), [Especialidad.JARDINERIA],
             [], [Experiencia("Viveros Neiva", "Jardinero", 18)]),
]

TAREAS = {
    0: ("PISCINA", "Limpieza de fondo, medición de pH y cloro"),
    1: ("PINTURA", "Pintura de muro perimetral, torre {n}"),
    2: ("JARDINERIA", "Poda de setos y corte de césped, zona {n}"),
}


NOMBRES_CENTROS = (
    ("Conjunto Reservas del Río", "Cra 5 # 45-10, Neiva"),
    ("Conjunto Torres de Altamira", "Cl 26 # 12-30, Neiva"),
)


def _copiar_operario(plantilla: Operario) -> Operario:
    return Operario(
        documento=plantilla.documento,
        nombres=plantilla.nombres,
        apellidos=plantilla.apellidos,
        telefono=plantilla.telefono,
        correo_institucional=plantilla.correo_institucional,
        fecha_ingreso=plantilla.fecha_ingreso,
        especialidades=list(plantilla.especialidades),
        formacion=list(plantilla.formacion),
        experiencia=list(plantilla.experiencia),
    )


def cargar(contenedor=None) -> None:
    if contenedor is None:
        from app.main import app

        contenedor = app.state.contenedor
    with contenedor.Sesion() as sesion:
        centros_por_nombre = {
            centro.nombre: centro
            for centro in sesion.scalars(select(CentroTrabajoModelo))
        }
        for nombre, direccion in NOMBRES_CENTROS:
            if nombre not in centros_por_nombre:
                centro = CentroTrabajoModelo(nombre=nombre, direccion=direccion)
                sesion.add(centro)
                centros_por_nombre[nombre] = centro
        sesion.flush()
        centros = [centros_por_nombre[nombre] for nombre, _ in NOMBRES_CENTROS]

        documentos_existentes = set(
            sesion.scalars(select(OperarioModelo.documento))
        )
        servicio = contenedor.servicio_hojas_vida(sesion)
        operarios = []
        for plantilla in OPERARIOS:
            if plantilla.documento not in documentos_existentes:
                servicio.registrar(_copiar_operario(plantilla))
            existente = sesion.scalar(
                select(OperarioModelo.id).where(
                    OperarioModelo.documento == plantilla.documento
                )
            )
            operarios.append((existente, plantilla))

        lunes = date.today() - timedelta(days=date.today().weekday())
        actividades_existentes = {
            (
                actividad.operario_id,
                actividad.centro_id,
                actividad.fecha,
                actividad.tipo_servicio,
                actividad.descripcion,
            )
            for actividad in sesion.scalars(select(ActividadModelo))
        }
        for i, (operario_id, plantilla) in enumerate(operarios):
            servicio_tipo, descripcion = TAREAS[i]
            for dia in range(7):
                fecha = lunes + timedelta(days=dia)
                for n in (1, 2):
                    centro = centros[(i + n) % len(centros)]
                    detalle = descripcion.format(n=n)
                    clave = (
                        operario_id,
                        centro.id,
                        fecha,
                        servicio_tipo,
                        detalle,
                    )
                    if clave not in actividades_existentes:
                        sesion.add(ActividadModelo(
                            operario_id=operario_id,
                            centro_id=centro.id,
                            fecha=fecha,
                            tipo_servicio=servicio_tipo,
                            descripcion=detalle,
                        ))
                        actividades_existentes.add(clave)
        sesion.commit()
    print("Datos base listos: 2 centros, 3 operarios y hasta 14 actividades por operario.")


if __name__ == "__main__":
    cargar()
