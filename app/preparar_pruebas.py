"""Prepara cuentas vinculadas y jornadas completas para pruebas locales."""
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
import logging
import os
import struct
import uuid
import zlib

from sqlalchemy import select

from app.hojas_vida.infraestructura import OperarioModelo
from app.identidad.dominio import Rol
from app.identidad.infraestructura import UsuarioModelo
from app.identidad.seguridad import ServicioIdentidad
from app.jornada.dominio import EstadoActividad, MomentoEvidencia
from app.jornada.infraestructura import (
    ActividadModelo,
    EvidenciaModelo,
    EventoSincronizadoModelo,
    JornadaModelo,
)
from app.programacion.casos_uso import PublicarProgramacion
from app.programacion.dominio import AsignacionProgramacion
from app.programacion.infraestructura import (
    CatalogoProgramacionSQL,
    RepositorioOutboxSQL,
    RepositorioProgramacionesSQL,
)
from app.programacion.modelos import (
    AsignacionProgramacionModelo,
    CentroTrabajoModelo,
    ProgramacionSemanalModelo,
)
from app.semilla import NOMBRES_CENTROS, cargar as cargar_datos_base

logger = logging.getLogger(__name__)

CUENTAS = (
    ("sgml.admin", "Admin2026!", Rol.ADMINISTRADOR, None, "demo.admin"),
    ("sgml.gestion", "Gestion2026!", Rol.ADMINISTRATIVO, None, "demo.administrativo"),
    ("sgml.supervisor", "Supervisor2026!", Rol.SUPERVISOR, None, "demo.supervisor"),
    ("operario.carlos", "Carlos2026!", Rol.OPERARIO, "1075001001", "demo.operario"),
    ("operario.luisa", "Luisa2026!", Rol.OPERARIO, "1075002002", None),
    ("operario.jorge", "Jorge2026!", Rol.OPERARIO, "1075003003", None),
)

ACTIVIDADES_HOY = (
    ("PINTURA", "Pintura de la fachada y acceso principal"),
    ("ASEO_GENERAL", "Limpieza profunda de zonas comunes"),
)

TAREAS_SEMANA = (
    ("PISCINA", "Limpieza y revisión del sistema de piscina"),
    ("PINTURA", "Mantenimiento de pintura en zonas comunes"),
    ("JARDINERIA", "Poda y mantenimiento de zonas verdes"),
)

COLORES_EVIDENCIA = {
    MomentoEvidencia.ANTES: (49, 90, 133),
    MomentoEvidencia.DURANTE: (31, 111, 92),
    MomentoEvidencia.DESPUES: (166, 99, 0),
}


def _crear_png(color: tuple[int, int, int]) -> bytes:
    ancho, alto = 480, 270
    filas = []
    for y in range(alto):
        fila = bytearray((0,))
        for x in range(ancho):
            if y < 18 or y > alto - 18 or x < 18 or x > ancho - 18:
                pixel = (35, 54, 68)
            elif (x // 48 + y // 45) % 2:
                pixel = tuple(min(255, canal + 26) for canal in color)
            else:
                pixel = color
            fila.extend(pixel)
        filas.append(bytes(fila))

    def bloque(tipo: bytes, contenido: bytes) -> bytes:
        return (
            struct.pack(">I", len(contenido))
            + tipo
            + contenido
            + struct.pack(">I", zlib.crc32(tipo + contenido) & 0xFFFFFFFF)
        )

    encabezado = struct.pack(">IIBBBBB", ancho, alto, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + bloque(b"IHDR", encabezado)
        + bloque(b"IDAT", zlib.compress(b"".join(filas)))
        + bloque(b"IEND", b"")
    )


def _asegurar_cuentas(contenedor) -> dict[str, int]:
    operarios = dict(_listar_operarios(contenedor))
    ids = {}
    with contenedor.Sesion() as sesion:
        for nombre, contrasena, rol, documento, nombre_anterior in CUENTAS:
            anterior = (
                sesion.scalar(select(UsuarioModelo).where(
                    UsuarioModelo.nombre_usuario == nombre_anterior
                ))
                if nombre_anterior
                else None
            )
            usuario = sesion.scalar(
                select(UsuarioModelo).where(
                    UsuarioModelo.nombre_usuario == nombre
                )
            )
            if usuario is None and anterior is not None:
                conflicto = sesion.scalar(
                    select(UsuarioModelo.id).where(
                        UsuarioModelo.nombre_usuario == nombre
                    )
                )
                if conflicto is not None:
                    raise RuntimeError(
                        f"No se puede renombrar {nombre_anterior}: {nombre} ya existe"
                    )
                anterior.nombre_usuario = nombre
                usuario = anterior

            operario_id = operarios.get(documento) if documento else None
            if usuario is None:
                servicio = contenedor.servicio_identidad(sesion)
                usuario = servicio.crear_usuario(
                    nombre,
                    contrasena,
                    rol,
                    operario_id=operario_id,
                )
                usuario_id = usuario.id
            else:
                usuario.rol = rol.value
                usuario.activo = True
                usuario.operario_id = operario_id
                usuario.hash_contrasena = ServicioIdentidad.crear_hash_contrasena(
                    contrasena
                )
                usuario_id = usuario.id
            ids[nombre] = usuario_id
        sesion.commit()
    return ids


def _listar_operarios(contenedor) -> list[tuple[str, int]]:
    with contenedor.Sesion() as sesion:
        return [
            (documento, operario_id)
            for documento, operario_id in sesion.execute(
                select(OperarioModelo.documento, OperarioModelo.id)
                .order_by(OperarioModelo.id)
            )
        ]


def _asegurar_jornada_y_evidencias(contenedor, operarios) -> tuple[list[int], int]:
    hoy = date.today()
    ahora = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    ids_actividades = []
    evidencias_creadas = 0
    with contenedor.Sesion() as sesion:
        centros = {
            centro.nombre: centro
            for centro in sesion.scalars(select(CentroTrabajoModelo))
        }
        centro = centros[NOMBRES_CENTROS[0][0]]
        primer_operario_id = operarios["1075001001"]

        antiguas = list(sesion.scalars(
            select(ActividadModelo).where(
                ActividadModelo.operario_id == primer_operario_id,
                ActividadModelo.descripcion.like("DEMOSTRACION:%"),
            )
        ))
        for antigua, (servicio, descripcion) in zip(antiguas, ACTIVIDADES_HOY):
            antigua.tipo_servicio = servicio
            antigua.descripcion = descripcion

        for indice, (servicio, descripcion) in enumerate(ACTIVIDADES_HOY):
            actividad = sesion.scalar(
                select(ActividadModelo).where(
                    ActividadModelo.operario_id == primer_operario_id,
                    ActividadModelo.fecha == hoy,
                    ActividadModelo.descripcion == descripcion,
                )
            )
            if actividad is None:
                actividad = ActividadModelo(
                    operario_id=primer_operario_id,
                    centro_id=centro.id,
                    fecha=hoy,
                    tipo_servicio=servicio,
                    descripcion=descripcion,
                    estado=EstadoActividad.FINALIZADA.value,
                    hora_inicio=datetime.combine(hoy, time(8 + indice, 0)),
                    hora_fin=datetime.combine(hoy, time(9 + indice, 0)),
                )
                sesion.add(actividad)
                sesion.flush()
            ids_actividades.append(actividad.id)

            evidencia_existente = set(sesion.scalars(
                select(EvidenciaModelo.momento).where(
                    EvidenciaModelo.actividad_id == actividad.id
                )
            ))
            for momento in MomentoEvidencia:
                if momento.value in evidencia_existente:
                    continue
                contenido = _crear_png(COLORES_EVIDENCIA[momento])
                nombre = f"actividad_{actividad.id}_{momento.value.lower()}.png"
                ruta = contenedor.almacen.guardar(nombre, contenido)
                sesion.add(EvidenciaModelo(
                    actividad_id=actividad.id,
                    momento=momento.value,
                    ruta=ruta,
                    sha256=hashlib.sha256(contenido).hexdigest(),
                    tomada_en=ahora - timedelta(minutes=15),
                    recibida_en=ahora,
                ))
                evidencias_creadas += 1

        entrada = datetime.combine(hoy, time(7, 55))
        salida = datetime.combine(hoy, time(10, 5))
        jornada = sesion.scalar(
            select(JornadaModelo).where(
                JornadaModelo.operario_id == primer_operario_id,
                JornadaModelo.fecha == hoy,
            )
        )
        if jornada is None:
            sesion.add(JornadaModelo(
                operario_id=primer_operario_id,
                centro_id=centro.id,
                fecha=hoy,
                hora_entrada=entrada,
                hora_salida=salida,
            ))

        eventos = (
            ("ENTRADA", entrada, False),
            ("FIN_ACTIVIDAD", datetime.combine(hoy, time(10, 0)), False),
            ("SALIDA", salida + timedelta(minutes=15), True),
        )
        for tipo, hora_dispositivo, sospechosa in eventos:
            evento_id = str(uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"sgml-pruebas:{hoy.isoformat()}:{primer_operario_id}:{tipo}",
            ))
            existente = sesion.get(EventoSincronizadoModelo, evento_id)
            if existente is not None:
                existente.datos = json.dumps({"origen": "pruebas locales"})
                existente.hora_sospechosa = sospechosa
                continue
            sesion.add(EventoSincronizadoModelo(
                id=evento_id,
                operario_id=primer_operario_id,
                tipo=tipo,
                datos=json.dumps({"origen": "pruebas locales"}),
                hora_dispositivo=hora_dispositivo,
                recibido_en=hora_dispositivo - timedelta(minutes=15)
                if sospechosa else hora_dispositivo,
                estado="ACEPTADO",
                motivo=None,
                hora_sospechosa=sospechosa,
            ))
        sesion.commit()
    return ids_actividades, evidencias_creadas


def _asignaciones_semana(operarios, centros, inicio) -> list[AsignacionProgramacion]:
    asignaciones = []
    for indice, (documento, (servicio, descripcion)) in enumerate(
        zip(operarios, TAREAS_SEMANA)
    ):
        for dia in (1, 3):
            asignaciones.append(AsignacionProgramacion(
                operario_id=operarios[documento],
                centro_id=centros[indice % len(centros)].id,
                fecha=inicio + timedelta(days=dia),
                tipo_servicio=servicio,
                descripcion=descripcion,
            ))
    return asignaciones


def _asegurar_programacion_publicada(contenedor, administrador_id, operarios) -> int:
    hoy = date.today()
    inicio = hoy + timedelta(days=7 - hoy.weekday())
    with contenedor.Sesion() as sesion:
        programacion = sesion.scalar(
            select(ProgramacionSemanalModelo).where(
                ProgramacionSemanalModelo.semana_inicio == inicio
            )
        )
        if programacion is not None and programacion.estado == "PUBLICADA":
            return programacion.id

        centros = list(sesion.scalars(
            select(CentroTrabajoModelo).order_by(CentroTrabajoModelo.id)
        ))
        asignaciones = _asignaciones_semana(operarios, centros, inicio)
        repositorio = RepositorioProgramacionesSQL(sesion)
        catalogo = CatalogoProgramacionSQL(sesion)
        outbox = RepositorioOutboxSQL(sesion)
        if programacion is None:
            from app.programacion.casos_uso import CrearProgramacion

            programacion = CrearProgramacion(repositorio, catalogo).ejecutar(
                semana_inicio=inicio,
                asignaciones=asignaciones,
                creada_por=administrador_id,
            )
        else:
            asignaciones_existentes = list(programacion.asignaciones)
            es_carga_anterior = bool(asignaciones_existentes) and all(
                asignacion.descripcion.strip().lower().startswith("demo:")
                for asignacion in asignaciones_existentes
            )
            if not asignaciones_existentes or es_carga_anterior:
                programacion.asignaciones = [
                    AsignacionProgramacionModelo(
                        operario_id=asignacion.operario_id,
                        centro_id=asignacion.centro_id,
                        fecha=asignacion.fecha,
                        tipo_servicio=asignacion.tipo_servicio,
                        descripcion=asignacion.descripcion,
                    )
                    for asignacion in asignaciones
                ]
            else:
                claves_existentes = {
                    (
                        asignacion.operario_id,
                        asignacion.centro_id,
                        asignacion.fecha,
                        asignacion.tipo_servicio,
                        asignacion.descripcion,
                    )
                    for asignacion in asignaciones_existentes
                }
                programacion.asignaciones.extend(
                    AsignacionProgramacionModelo(
                        operario_id=asignacion.operario_id,
                        centro_id=asignacion.centro_id,
                        fecha=asignacion.fecha,
                        tipo_servicio=asignacion.tipo_servicio,
                        descripcion=asignacion.descripcion,
                    )
                    for asignacion in asignaciones
                    if (
                        asignacion.operario_id,
                        asignacion.centro_id,
                        asignacion.fecha,
                        asignacion.tipo_servicio,
                        asignacion.descripcion,
                    ) not in claves_existentes
                )
            sesion.flush()

        publicada = PublicarProgramacion(repositorio, catalogo, outbox).ejecutar(
            programacion.id
        )
        sesion.commit()
        return publicada.id


def preparar(contenedor) -> dict[str, object]:
    cargar_datos_base(contenedor)
    operarios = dict(_listar_operarios(contenedor))
    cuentas = _asegurar_cuentas(contenedor)
    ids_actividades, evidencias_creadas = _asegurar_jornada_y_evidencias(
        contenedor, operarios
    )
    programacion_id = _asegurar_programacion_publicada(
        contenedor, cuentas["sgml.admin"], operarios
    )
    return {
        "cuentas": len(cuentas),
        "actividades": ids_actividades,
        "evidencias_nuevas": evidencias_creadas,
        "programacion_publicada": programacion_id,
    }


def main() -> None:
    if os.getenv("SGML_ENV", "development").lower() == "production":
        raise SystemExit(
            "La preparación de cuentas y tareas de prueba está deshabilitada "
            "en producción."
        )
    from app.main import app

    resultado = preparar(app.state.contenedor)
    logger.info("Entorno local preparado: %s", resultado)
    print("Cuentas activas: administrador, administrativo, supervisor y tres operarios.")
    print(f"Actividades finalizadas con evidencias: {resultado['actividades']}")
    print(f"Programación publicada: {resultado['programacion_publicada']}")


if __name__ == "__main__":
    main()
