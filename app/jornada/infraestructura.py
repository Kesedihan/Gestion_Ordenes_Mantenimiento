"""M2 - INFRAESTRUCTURA: adaptadores que implementan los puertos de Jornada."""
import json
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import (Boolean, ForeignKey, Index, String, Text, UniqueConstraint, func,
                        select)
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.compartido.db import Base
from app.jornada.dominio import (Actividad, EstadoActividad, EstadoEvento, Evento,
                                 Jornada, MomentoEvidencia)
from app.jornada.puertos import (AlmacenArchivos, RegistroEventos,
                                 RepositorioActividades, RepositorioEvidencias,
                                 RepositorioJornadas)
from app.programacion.modelos import CentroTrabajoModelo


# ----------------------------------------------------------------- modelos ORM
class ActividadModelo(Base):
    __tablename__ = "actividades"
    __table_args__ = (
        Index("uq_actividades_correccion_de_id", "correccion_de_id", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    operario_id: Mapped[int] = mapped_column(ForeignKey("operarios.id"))
    centro_id: Mapped[int] = mapped_column(ForeignKey("centros_trabajo.id"))
    fecha: Mapped[date]
    tipo_servicio: Mapped[str] = mapped_column(String(30))
    descripcion: Mapped[str] = mapped_column(String(300))
    estado: Mapped[str] = mapped_column(String(12), default=EstadoActividad.PROGRAMADA.value)
    hora_inicio: Mapped[datetime | None]
    hora_fin: Mapped[datetime | None]
    revisada_por: Mapped[int | None]
    observacion: Mapped[str | None] = mapped_column(String(300))
    correccion_de_id: Mapped[int | None] = mapped_column(
        ForeignKey("actividades.id"), nullable=True
    )
    motivo_correccion: Mapped[str | None] = mapped_column(String(300), nullable=True)


class JornadaModelo(Base):
    __tablename__ = "jornadas"

    id: Mapped[int] = mapped_column(primary_key=True)
    operario_id: Mapped[int] = mapped_column(ForeignKey("operarios.id"))
    centro_id: Mapped[int] = mapped_column(ForeignKey("centros_trabajo.id"))
    fecha: Mapped[date]
    hora_entrada: Mapped[datetime]
    hora_salida: Mapped[datetime | None]


class EvidenciaModelo(Base):
    __tablename__ = "evidencias"
    __table_args__ = (UniqueConstraint("actividad_id", "momento"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    actividad_id: Mapped[int] = mapped_column(ForeignKey("actividades.id"))
    momento: Mapped[str] = mapped_column(String(8))
    ruta: Mapped[str] = mapped_column(String(300))
    sha256: Mapped[str] = mapped_column(String(64))
    tomada_en: Mapped[datetime]
    recibida_en: Mapped[datetime]


class EventoSincronizadoModelo(Base):
    __tablename__ = "eventos_sincronizados"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # UUID del celular
    operario_id: Mapped[int] = mapped_column(ForeignKey("operarios.id"), index=True)
    tipo: Mapped[str] = mapped_column(String(20))
    datos: Mapped[str] = mapped_column(Text)
    hora_dispositivo: Mapped[datetime]
    recibido_en: Mapped[datetime]
    estado: Mapped[str] = mapped_column(String(10))
    motivo: Mapped[str | None] = mapped_column(String(300))
    hora_sospechosa: Mapped[bool] = mapped_column(Boolean, default=False)


# ------------------------------------------------------------- repositorios
class RepositorioActividadesSQL(RepositorioActividades):
    def __init__(self, sesion: Session):
        self._s = sesion

    def obtener(self, actividad_id: int) -> Actividad | None:
        filas = self._consulta().where(ActividadModelo.id == actividad_id)
        resultado = self._s.execute(filas).first()
        return self._a_dominio(*resultado) if resultado else None

    def guardar(self, actividad: Actividad) -> None:
        if actividad.id is None:
            m = ActividadModelo(
                operario_id=actividad.operario_id,
                centro_id=actividad.centro_id,
                fecha=actividad.fecha,
                tipo_servicio=actividad.tipo_servicio,
                descripcion=actividad.descripcion,
            )
            self._s.add(m)
        else:
            m = self._s.get(ActividadModelo, actividad.id)
        m.estado = actividad.estado.value
        m.hora_inicio = actividad.hora_inicio
        m.hora_fin = actividad.hora_fin
        m.revisada_por = actividad.revisada_por
        m.observacion = actividad.observacion
        m.correccion_de_id = actividad.correccion_de_id
        m.motivo_correccion = actividad.motivo_correccion
        self._s.flush()

    def listar_por_operario(self, operario_id: int, desde: date, hasta: date) -> list[Actividad]:
        consulta = self._consulta().where(
            ActividadModelo.operario_id == operario_id,
            ActividadModelo.fecha.between(desde, hasta))
        return [self._a_dominio(*f) for f in self._s.execute(consulta)]

    def listar_por_fecha(self, fecha: date) -> list[Actividad]:
        consulta = self._consulta().where(ActividadModelo.fecha == fecha)
        return [self._a_dominio(*f) for f in self._s.execute(consulta)]

    @staticmethod
    def _consulta():
        return (select(ActividadModelo, CentroTrabajoModelo.nombre)
                .join(CentroTrabajoModelo, CentroTrabajoModelo.id == ActividadModelo.centro_id)
                .order_by(ActividadModelo.fecha, ActividadModelo.id))

    def _a_dominio(self, m: ActividadModelo, centro_nombre: str) -> Actividad:
        momentos = self._s.scalars(select(EvidenciaModelo.momento).where(
            EvidenciaModelo.actividad_id == m.id))
        return Actividad(
            id=m.id, operario_id=m.operario_id, centro_id=m.centro_id,
            centro_nombre=centro_nombre, fecha=m.fecha, tipo_servicio=m.tipo_servicio,
            descripcion=m.descripcion, estado=EstadoActividad(m.estado),
            hora_inicio=m.hora_inicio, hora_fin=m.hora_fin,
            evidencias={MomentoEvidencia(x) for x in momentos},
            revisada_por=m.revisada_por, observacion=m.observacion,
            correccion_de_id=m.correccion_de_id,
            motivo_correccion=m.motivo_correccion)


class RepositorioJornadasSQL(RepositorioJornadas):
    def __init__(self, sesion: Session):
        self._s = sesion

    def jornada_abierta(self, operario_id: int, fecha: date) -> Jornada | None:
        m = self._s.scalar(select(JornadaModelo).where(
            JornadaModelo.operario_id == operario_id, JornadaModelo.fecha == fecha,
            JornadaModelo.hora_salida.is_(None)))
        return self._a_dominio(m) if m else None

    def guardar(self, jornada: Jornada) -> None:
        m = self._s.get(JornadaModelo, jornada.id) if jornada.id else JornadaModelo()
        m.operario_id = jornada.operario_id
        m.centro_id = jornada.centro_id
        m.fecha = jornada.fecha
        m.hora_entrada = jornada.hora_entrada
        m.hora_salida = jornada.hora_salida
        self._s.add(m)
        self._s.flush()

    def listar_por_fecha(self, fecha: date) -> list[Jornada]:
        filas = self._s.execute(
            select(JornadaModelo, CentroTrabajoModelo.nombre)
            .join(CentroTrabajoModelo, CentroTrabajoModelo.id == JornadaModelo.centro_id)
            .where(JornadaModelo.fecha == fecha)
            .order_by(JornadaModelo.hora_entrada)
        )
        return [
            self._a_dominio(modelo, centro_nombre)
            for modelo, centro_nombre in filas
        ]

    @staticmethod
    def _a_dominio(
        m: JornadaModelo, centro_nombre: str | None = None
    ) -> Jornada:
        return Jornada(
            m.operario_id,
            m.centro_id,
            m.hora_entrada,
            m.hora_salida,
            id=m.id,
            centro_nombre=centro_nombre,
        )


class RepositorioEvidenciasSQL(RepositorioEvidencias):
    def __init__(self, sesion: Session):
        self._s = sesion

    def agregar(self, actividad_id, momento, ruta, sha256, tomada_en, recibida_en) -> None:
        self._s.add(EvidenciaModelo(actividad_id=actividad_id, momento=momento.value, ruta=ruta,
                                    sha256=sha256, tomada_en=tomada_en, recibida_en=recibida_en))
        self._s.flush()

    def obtener_ruta(self, actividad_id: int, momento: MomentoEvidencia) -> str | None:
        return self._s.scalar(select(EvidenciaModelo.ruta).where(
            EvidenciaModelo.actividad_id == actividad_id,
            EvidenciaModelo.momento == momento.value,
        ))


class RegistroEventosSQL(RegistroEventos):
    def __init__(self, sesion: Session):
        self._s = sesion

    def estado_de(self, evento_id: str):
        m = self._s.get(EventoSincronizadoModelo, evento_id)
        return (EstadoEvento(m.estado), m.motivo) if m else None

    def registrar(self, evento: Evento, recibido_en, estado, motivo, hora_sospechosa) -> None:
        self._s.add(EventoSincronizadoModelo(
            id=evento.id, operario_id=evento.operario_id, tipo=evento.tipo.value,
            datos=json.dumps(evento.datos), hora_dispositivo=evento.hora_dispositivo,
            recibido_en=recibido_en, estado=estado.value, motivo=motivo,
            hora_sospechosa=hora_sospechosa))
        self._s.flush()

    def resumen_operario(self, operario_id: int):
        ultima = self._s.scalar(select(func.max(EventoSincronizadoModelo.recibido_en)).where(
            EventoSincronizadoModelo.operario_id == operario_id))
        sospechosos = self._s.scalar(select(func.count()).where(
            EventoSincronizadoModelo.operario_id == operario_id,
            EventoSincronizadoModelo.hora_sospechosa.is_(True)))
        return ultima, sospechosos or 0


# ------------------------------------------------- almacenamiento de archivos
class AlmacenArchivosDisco(AlmacenArchivos):
    """Despliegue local. En producción se reemplaza por un AlmacenArchivosS3
    (MinIO) sin tocar los casos de uso: LSP + DIP."""

    def __init__(self, carpeta: str | Path):
        self._carpeta = Path(carpeta)
        self._carpeta.mkdir(parents=True, exist_ok=True)

    def guardar(self, nombre: str, contenido: bytes) -> str:
        destino = self._carpeta / nombre
        destino.write_bytes(contenido)
        return str(destino)
