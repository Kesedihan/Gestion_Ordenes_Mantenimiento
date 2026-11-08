"""Adaptadores SQLAlchemy para Programación, catálogo y patrón outbox."""
from datetime import date, datetime, timedelta, timezone
import uuid

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from app.hojas_vida.dominio import EstadoOperario
from app.hojas_vida.infraestructura import OperarioModelo
from app.jornada.dominio import EstadoActividad
from app.jornada.infraestructura import ActividadModelo
from app.programacion.dominio import (
    AsignacionProgramacion,
    MensajeOutbox,
    OperarioNotificable,
    ProgramacionSemanal,
)
from app.programacion.modelos import (
    AsignacionProgramacionModelo,
    CentroTrabajoModelo,
    MensajeOutboxModelo,
    ProgramacionSemanalModelo,
)
from app.programacion.puertos import (
    CatalogoProgramacion,
    RepositorioOutbox,
    RepositorioProgramaciones,
)


class RepositorioProgramacionesSQL(RepositorioProgramaciones):
    def __init__(self, sesion: Session):
        self._sesion = sesion

    def obtener(self, programacion_id: int) -> ProgramacionSemanal | None:
        modelo = self._sesion.get(ProgramacionSemanalModelo, programacion_id)
        return self._a_dominio(modelo) if modelo else None

    def obtener_por_semana(self, semana_inicio: date) -> ProgramacionSemanal | None:
        modelo = self._sesion.scalar(select(ProgramacionSemanalModelo).where(
            ProgramacionSemanalModelo.semana_inicio == semana_inicio
        ))
        return self._a_dominio(modelo) if modelo else None

    def guardar(self, programacion: ProgramacionSemanal) -> ProgramacionSemanal:
        modelo = (
            self._sesion.get(ProgramacionSemanalModelo, programacion.id)
            if programacion.id is not None
            else ProgramacionSemanalModelo()
        )
        modelo.semana_inicio = programacion.semana_inicio
        modelo.estado = programacion.estado.value
        modelo.creada_por = programacion.creada_por
        modelo.creada_en = programacion.creada_en or datetime.now(timezone.utc).replace(
            tzinfo=None
        )
        modelo.publicada_en = programacion.publicada_en
        if programacion.id is None:
            modelo.asignaciones = [
                AsignacionProgramacionModelo(
                    operario_id=asignacion.operario_id,
                    centro_id=asignacion.centro_id,
                    fecha=asignacion.fecha,
                    tipo_servicio=asignacion.tipo_servicio,
                    descripcion=asignacion.descripcion,
                )
                for asignacion in programacion.asignaciones
            ]
        self._sesion.add(modelo)
        self._sesion.flush()
        return self._a_dominio(modelo)

    def listar(self, semana_inicio: date | None = None) -> list[ProgramacionSemanal]:
        consulta = select(ProgramacionSemanalModelo).order_by(
            ProgramacionSemanalModelo.semana_inicio.desc()
        )
        if semana_inicio is not None:
            consulta = consulta.where(
                ProgramacionSemanalModelo.semana_inicio == semana_inicio
            )
        return [self._a_dominio(modelo) for modelo in self._sesion.scalars(consulta)]

    @staticmethod
    def _a_dominio(modelo: ProgramacionSemanalModelo) -> ProgramacionSemanal:
        return ProgramacionSemanal(
            id=modelo.id,
            semana_inicio=modelo.semana_inicio,
            asignaciones=[
                AsignacionProgramacion(
                    operario_id=asignacion.operario_id,
                    centro_id=asignacion.centro_id,
                    fecha=asignacion.fecha,
                    tipo_servicio=asignacion.tipo_servicio,
                    descripcion=asignacion.descripcion,
                )
                for asignacion in modelo.asignaciones
            ],
            creada_por=modelo.creada_por,
            estado=modelo.estado,
            creada_en=modelo.creada_en,
            publicada_en=modelo.publicada_en,
        )


class CatalogoProgramacionSQL(CatalogoProgramacion):
    def __init__(self, sesion: Session):
        self._sesion = sesion

    def obtener_operario_notificable(self, operario_id: int) -> OperarioNotificable | None:
        modelo = self._sesion.scalar(select(OperarioModelo).where(
            OperarioModelo.id == operario_id,
            OperarioModelo.estado == EstadoOperario.ACTIVO.value,
        ))
        if modelo is None:
            return None
        return OperarioNotificable(
            id=modelo.id,
            nombre=f"{modelo.nombres} {modelo.apellidos}",
            correo=modelo.correo_institucional,
        )

    def centro_existe(self, centro_id: int) -> bool:
        return self._sesion.scalar(select(CentroTrabajoModelo.id).where(
            CentroTrabajoModelo.id == centro_id
        )) is not None

    def listar_centros(self) -> list[dict]:
        return [
            {"id": modelo.id, "nombre": modelo.nombre, "direccion": modelo.direccion}
            for modelo in self._sesion.scalars(
                select(CentroTrabajoModelo).order_by(CentroTrabajoModelo.nombre)
            )
        ]

    def listar_operarios(self) -> list[dict]:
        modelos = self._sesion.scalars(
            select(OperarioModelo)
            .where(OperarioModelo.estado == EstadoOperario.ACTIVO.value)
            .order_by(OperarioModelo.apellidos, OperarioModelo.nombres)
        )
        return [
            {"id": modelo.id, "nombre": f"{modelo.nombres} {modelo.apellidos}"}
            for modelo in modelos
        ]

    def crear_actividades(
        self, asignaciones: tuple[AsignacionProgramacion, ...]
    ) -> None:
        self._sesion.add_all([
            ActividadModelo(
                operario_id=asignacion.operario_id,
                centro_id=asignacion.centro_id,
                fecha=asignacion.fecha,
                tipo_servicio=asignacion.tipo_servicio,
                descripcion=asignacion.descripcion,
                estado=EstadoActividad.PROGRAMADA.value,
            )
            for asignacion in asignaciones
        ])
        self._sesion.flush()


class RepositorioOutboxSQL(RepositorioOutbox):
    def __init__(self, sesion: Session):
        self._sesion = sesion

    def agregar(
        self,
        programacion_id: int,
        destinatario: str,
        asunto: str,
        cuerpo: str,
        ahora: datetime,
    ) -> None:
        self._sesion.add(MensajeOutboxModelo(
            id=str(uuid.uuid4()),
            programacion_id=programacion_id,
            destinatario=destinatario,
            asunto=asunto,
            cuerpo=cuerpo,
            estado="PENDIENTE",
            intentos=0,
            disponible_en=ahora,
            creado_en=ahora,
        ))
        self._sesion.flush()

    def reclamar_siguiente(
        self, ahora: datetime, duracion_lease: timedelta
    ) -> MensajeOutbox | None:
        disponible = and_(
            MensajeOutboxModelo.estado == "PENDIENTE",
            MensajeOutboxModelo.disponible_en <= ahora,
        )
        lease_vencido = and_(
            MensajeOutboxModelo.estado == "PROCESANDO",
            MensajeOutboxModelo.bloqueado_hasta <= ahora,
        )
        modelo = self._sesion.scalar(
            select(MensajeOutboxModelo)
            .where(or_(disponible, lease_vencido))
            .order_by(MensajeOutboxModelo.creado_en, MensajeOutboxModelo.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if modelo is None:
            return None

        intentos = modelo.intentos + 1
        puede_reclamar = or_(
            and_(
                MensajeOutboxModelo.estado == "PENDIENTE",
                MensajeOutboxModelo.disponible_en <= ahora,
            ),
            and_(
                MensajeOutboxModelo.estado == "PROCESANDO",
                MensajeOutboxModelo.bloqueado_hasta <= ahora,
            ),
        )
        cambio = self._sesion.execute(
            update(MensajeOutboxModelo)
            .where(MensajeOutboxModelo.id == modelo.id, puede_reclamar)
            .values(
                estado="PROCESANDO",
                bloqueado_hasta=ahora + duracion_lease,
                intentos=intentos,
            )
            .execution_options(synchronize_session=False)
        )
        if cambio.rowcount != 1:
            self._sesion.rollback()
            return None
        self._sesion.commit()
        return MensajeOutbox(
            id=modelo.id,
            destinatario=modelo.destinatario,
            asunto=modelo.asunto,
            cuerpo=modelo.cuerpo,
            intentos=intentos,
        )

    def marcar_enviado(self, mensaje_id: str, enviado_en: datetime) -> None:
        modelo = self._sesion.get(MensajeOutboxModelo, mensaje_id)
        if modelo is None or modelo.estado != "PROCESANDO":
            raise RuntimeError(f"El mensaje outbox {mensaje_id} no está reclamado")
        modelo.estado = "ENVIADO"
        modelo.enviado_en = enviado_en
        modelo.bloqueado_hasta = None
        modelo.error = None
        self._sesion.commit()

    def reintentar(
        self,
        mensaje_id: str,
        disponible_en: datetime,
        error: str,
    ) -> None:
        modelo = self._sesion.get(MensajeOutboxModelo, mensaje_id)
        if modelo is None or modelo.estado != "PROCESANDO":
            raise RuntimeError(f"El mensaje outbox {mensaje_id} no está reclamado")
        modelo.estado = "PENDIENTE"
        modelo.disponible_en = disponible_en
        modelo.bloqueado_hasta = None
        modelo.error = error[:1000]
        self._sesion.commit()
