"""RAÍZ DE COMPOSICIÓN (Inversión de Control).

Es el único lugar del sistema donde se crean las clases concretas y se
conectan entre sí. Los casos de uso nunca crean sus dependencias: el
contenedor se las entrega ("no nos llames, nosotros te llamamos").

Cambiar un detalle técnico se hace AQUÍ y solo aquí. Por ejemplo:
  - SQLite -> PostgreSQL: cambiar la URL.
  - Disco -> MinIO: pasar un AlmacenArchivosS3 en vez de AlmacenArchivosDisco.
  - Nuevo tipo de evento: agregarlo al diccionario de manejadores (OCP).
"""
from dataclasses import dataclass
import secrets

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.compartido.db import Base, crear_fabrica_sesiones
from app.compartido.reloj import Reloj, RelojSistema
from app.identidad.infraestructura import RepositorioUsuariosSQL
from app.identidad.seguridad import ServicioIdentidad
from app.hojas_vida.casos_uso import ServicioHojasVida
from app.hojas_vida.infraestructura import RepositorioOperariosSQL
from app.jornada import casos_uso as cu
from app.jornada.infraestructura import (AlmacenArchivosDisco, RegistroEventosSQL,
                                         RepositorioActividadesSQL, RepositorioEvidenciasSQL,
                                         RepositorioJornadasSQL)
from app.jornada.manejadores import (ManejadorEntrada, ManejadorFinActividad,
                                     ManejadorInicioActividad, ManejadorSalida)
from app.jornada.puertos import DirectorioOperarios
from app.programacion import casos_uso as programacion_cu
from app.programacion.infraestructura import (
    CatalogoProgramacionSQL,
    RepositorioOutboxSQL,
    RepositorioProgramacionesSQL,
)


class DirectorioOperariosDesdeHojasVida(DirectorioOperarios):
    """Adaptador entre módulos: Jornada consulta Hojas de vida SOLO a través
    de su caso de uso público, nunca de sus tablas (bajo acoplamiento)."""

    def __init__(self, servicio: ServicioHojasVida):
        self._servicio = servicio

    def esta_activo(self, operario_id: int) -> bool:
        operario = self._servicio.buscar(operario_id)
        return operario is not None and operario.esta_activo()

    def nombre(self, operario_id: int) -> str:
        operario = self._servicio.buscar(operario_id)
        return operario.nombre_completo() if operario else f"Operario {operario_id}"


@dataclass
class CasosUsoJornada:
    sincronizar_lote: cu.SincronizarLote
    subir_evidencia: cu.SubirEvidencia
    revisar_actividad: cu.RevisarActividad
    consultar_evidencia: cu.ConsultarEvidencia
    consultar_pendientes_revision: cu.ConsultarPendientesRevision
    consultar_programacion: cu.ConsultarProgramacion
    consultar_seguimiento: cu.ConsultarSeguimiento


@dataclass
class CasosUsoProgramacion:
    crear: programacion_cu.CrearProgramacion
    publicar: programacion_cu.PublicarProgramacion
    listar: programacion_cu.ListarProgramaciones
    catalogos: programacion_cu.ListarCatalogosProgramacion


class Contenedor:
    def __init__(self, url_bd: str, carpeta_evidencias: str,
                 dominio_correo: str = "mantenimiento.com.co", reloj: Reloj | None = None,
                 secreto_jwt: str | None = None):
        self.motor, self.Sesion = crear_fabrica_sesiones(url_bd)
        self.almacen = AlmacenArchivosDisco(carpeta_evidencias)
        self.dominio_correo = dominio_correo
        self.reloj = reloj or RelojSistema()
        self.secreto_jwt = secreto_jwt or secrets.token_urlsafe(32)

    def crear_tablas(self) -> None:
        import app.identidad.infraestructura  # noqa: F401  (registra el modelo)
        import app.hojas_vida.infraestructura  # noqa: F401  (registra modelos)
        import app.jornada.infraestructura  # noqa: F401
        import app.programacion.modelos  # noqa: F401
        inspector = inspect(self.motor)
        if inspector.has_table("usuarios"):
            columnas_usuario = {
                columna["name"]
                for columna in inspector.get_columns("usuarios")
            }
            if "operario_id" not in columnas_usuario:
                with self.motor.begin() as conexion:
                    conexion.execute(text(
                        "ALTER TABLE usuarios ADD COLUMN operario_id "
                        "INTEGER REFERENCES operarios (id)"
                    ))
        if inspector.has_table("actividades"):
            columnas_actividad = {
                columna["name"]
                for columna in inspector.get_columns("actividades")
            }
            with self.motor.begin() as conexion:
                if "correccion_de_id" not in columnas_actividad:
                    conexion.execute(text(
                        "ALTER TABLE actividades ADD COLUMN correccion_de_id "
                        "INTEGER REFERENCES actividades (id)"
                    ))
                if "motivo_correccion" not in columnas_actividad:
                    conexion.execute(text(
                        "ALTER TABLE actividades ADD COLUMN motivo_correccion "
                        "VARCHAR(300)"
                    ))
        Base.metadata.create_all(self.motor)
        with self.motor.begin() as conexion:
            conexion.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_usuarios_operario_id "
                "ON usuarios (operario_id)"
            ))
            conexion.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_actividades_correccion_de_id "
                "ON actividades (correccion_de_id)"
            ))

    def servicio_identidad(self, sesion: Session) -> ServicioIdentidad:
        return ServicioIdentidad(RepositorioUsuariosSQL(sesion), self.secreto_jwt)

    def servicio_hojas_vida(self, sesion: Session) -> ServicioHojasVida:
        return ServicioHojasVida(RepositorioOperariosSQL(sesion), self.dominio_correo)

    def casos_uso_programacion(self, sesion: Session) -> CasosUsoProgramacion:
        programaciones = RepositorioProgramacionesSQL(sesion)
        catalogo = CatalogoProgramacionSQL(sesion)
        outbox = RepositorioOutboxSQL(sesion)
        return CasosUsoProgramacion(
            crear=programacion_cu.CrearProgramacion(programaciones, catalogo),
            publicar=programacion_cu.PublicarProgramacion(programaciones, catalogo, outbox),
            listar=programacion_cu.ListarProgramaciones(programaciones),
            catalogos=programacion_cu.ListarCatalogosProgramacion(catalogo),
        )

    def casos_uso_jornada(self, sesion: Session) -> CasosUsoJornada:
        actividades = RepositorioActividadesSQL(sesion)
        jornadas = RepositorioJornadasSQL(sesion)
        registro = RegistroEventosSQL(sesion)
        directorio = DirectorioOperariosDesdeHojasVida(self.servicio_hojas_vida(sesion))
        procesador = cu.ProcesadorIdempotente(registro, self.reloj)
        manejadores = {m.tipo: m for m in (
            ManejadorEntrada(jornadas),
            ManejadorSalida(jornadas),
            ManejadorInicioActividad(actividades, jornadas),
            ManejadorFinActividad(actividades, jornadas),
        )}
        return CasosUsoJornada(
            sincronizar_lote=cu.SincronizarLote(manejadores, procesador, directorio),
            subir_evidencia=cu.SubirEvidencia(actividades, RepositorioEvidenciasSQL(sesion),
                                              self.almacen, procesador, self.reloj),
            revisar_actividad=cu.RevisarActividad(actividades),
            consultar_evidencia=cu.ConsultarEvidencia(RepositorioEvidenciasSQL(sesion)),
            consultar_pendientes_revision=cu.ConsultarPendientesRevision(actividades, directorio),
            consultar_programacion=cu.ConsultarProgramacion(actividades),
            consultar_seguimiento=cu.ConsultarSeguimiento(actividades, jornadas, registro, directorio),
        )
