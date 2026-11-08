"""M1 - Hojas de vida: capa de DOMINIO.

No importa FastAPI ni SQLAlchemy: es lógica de negocio pura.
- Encapsulación: los atributos son privados y solo cambian por métodos
  que validan las reglas (no hay "operario.estado = ..." desde afuera).
- SRP: la entidad solo conoce las reglas de un operario; no sabe guardar,
  ni enviar correos, ni generar informes.
"""
import re
from dataclasses import dataclass
from datetime import date
from enum import Enum

from app.compartido.errores import ErrorDeNegocio

PATRON_CORREO = re.compile(r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$")


class EstadoOperario(str, Enum):
    ACTIVO = "ACTIVO"
    INACTIVO = "INACTIVO"


class Especialidad(str, Enum):
    PISCINA = "PISCINA"
    PINTURA = "PINTURA"
    JARDINERIA = "JARDINERIA"
    ASEO_GENERAL = "ASEO_GENERAL"
    ELECTRICIDAD = "ELECTRICIDAD"
    PLOMERIA = "PLOMERIA"


@dataclass(frozen=True)
class Formacion:
    nivel: str
    titulo: str
    institucion: str
    anio_fin: int | None = None


@dataclass(frozen=True)
class Experiencia:
    empresa: str
    cargo: str
    meses: int

    def __post_init__(self):
        if self.meses < 0:
            raise ErrorDeNegocio("Los meses de experiencia no pueden ser negativos")


class Operario:
    def __init__(
        self,
        documento: str,
        nombres: str,
        apellidos: str,
        telefono: str,
        correo_institucional: str,
        fecha_ingreso: date,
        especialidades: list[Especialidad],
        formacion: list[Formacion] | None = None,
        experiencia: list[Experiencia] | None = None,
        estado: EstadoOperario = EstadoOperario.ACTIVO,
        id: int | None = None,
    ):
        if not documento.isdigit() or not 6 <= len(documento) <= 12:
            raise ErrorDeNegocio("El documento debe tener entre 6 y 12 dígitos")
        if not nombres.strip() or not apellidos.strip():
            raise ErrorDeNegocio("Nombres y apellidos son obligatorios")
        if not especialidades:
            raise ErrorDeNegocio("El operario debe tener al menos una especialidad")
        self._validar_correo(correo_institucional)
        self._id = id
        self._documento = documento
        self._nombres = nombres.strip()
        self._apellidos = apellidos.strip()
        self._telefono = telefono
        self._correo = correo_institucional.lower()
        self._fecha_ingreso = fecha_ingreso
        self._especialidades = list(dict.fromkeys(especialidades))
        self._formacion = list(formacion or [])
        self._experiencia = list(experiencia or [])
        self._estado = estado

    # --- comportamiento (las únicas formas de cambiar el estado) ---------
    def actualizar_contacto(self, telefono: str, correo_institucional: str) -> None:
        self._validar_correo(correo_institucional)
        self._telefono = telefono
        self._correo = correo_institucional.lower()

    def inactivar(self) -> None:
        if self._estado is EstadoOperario.INACTIVO:
            raise ErrorDeNegocio("El operario ya está inactivo")
        self._estado = EstadoOperario.INACTIVO

    def activar(self) -> None:
        if self._estado is EstadoOperario.ACTIVO:
            raise ErrorDeNegocio("El operario ya está activo")
        self._estado = EstadoOperario.ACTIVO

    def esta_activo(self) -> bool:
        return self._estado is EstadoOperario.ACTIVO

    def nombre_completo(self) -> str:
        return f"{self._nombres} {self._apellidos}"

    def anios_experiencia(self) -> float:
        return round(sum(e.meses for e in self._experiencia) / 12, 1)

    def asignar_id(self, id: int) -> None:
        if self._id is not None:
            raise ErrorDeNegocio("El operario ya tiene identificador")
        self._id = id

    # --- lectura (sin setters públicos) ----------------------------------
    @property
    def id(self): return self._id
    @property
    def documento(self): return self._documento
    @property
    def nombres(self): return self._nombres
    @property
    def apellidos(self): return self._apellidos
    @property
    def telefono(self): return self._telefono
    @property
    def correo_institucional(self): return self._correo
    @property
    def fecha_ingreso(self): return self._fecha_ingreso
    @property
    def especialidades(self): return tuple(self._especialidades)
    @property
    def formacion(self): return tuple(self._formacion)
    @property
    def experiencia(self): return tuple(self._experiencia)
    @property
    def estado(self): return self._estado

    @staticmethod
    def _validar_correo(correo: str) -> None:
        if not PATRON_CORREO.match(correo or ""):
            raise ErrorDeNegocio("Correo institucional con formato inválido")
