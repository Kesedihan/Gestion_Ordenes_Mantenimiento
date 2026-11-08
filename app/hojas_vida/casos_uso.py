"""M1 - Hojas de vida: capa de APLICACIÓN (casos de uso).

- Recibe el repositorio por el constructor (inyección de dependencias / IoC):
  la clase NO crea su repositorio (a diferencia del ejemplo de violación
  del principio Hollywood visto en clase).
- SoC: aquí no hay HTTP ni SQL; solo la orquestación del caso de uso.
"""
from app.compartido.errores import Conflicto, ErrorDeNegocio, NoEncontrado
from app.hojas_vida.dominio import Operario
from app.hojas_vida.puertos import RepositorioOperarios


class ServicioHojasVida:
    def __init__(self, repositorio: RepositorioOperarios, dominio_institucional: str):
        self._repo = repositorio
        self._dominio = dominio_institucional.lower()

    def registrar(self, operario: Operario) -> Operario:
        self._exigir_correo_institucional(operario.correo_institucional)
        if self._repo.existe_documento(operario.documento):
            raise Conflicto(f"Ya existe un operario con documento {operario.documento}")
        if self._repo.existe_correo(operario.correo_institucional):
            raise Conflicto("El correo institucional ya está asignado")
        return self._repo.guardar(operario)

    def obtener(self, operario_id: int) -> Operario:
        operario = self._repo.obtener(operario_id)
        if operario is None:
            raise NoEncontrado(f"Operario {operario_id} no existe")
        return operario

    def buscar(self, operario_id: int) -> Operario | None:
        """Como obtener(), pero sin excepción: lo usan otros módulos."""
        return self._repo.obtener(operario_id)

    def listar(self, solo_activos: bool = False) -> list[Operario]:
        return self._repo.listar(solo_activos)

    def actualizar_contacto(self, operario_id: int, telefono: str, correo: str) -> Operario:
        operario = self.obtener(operario_id)
        self._exigir_correo_institucional(correo)
        if self._repo.existe_correo(correo, excepto_id=operario_id):
            raise Conflicto("El correo institucional ya está asignado")
        operario.actualizar_contacto(telefono, correo)
        return self._repo.guardar(operario)

    def cambiar_estado(self, operario_id: int, activo: bool) -> Operario:
        operario = self.obtener(operario_id)
        operario.activar() if activo else operario.inactivar()
        return self._repo.guardar(operario)

    def _exigir_correo_institucional(self, correo: str) -> None:
        # DRY: la política del dominio de correo vive en un solo lugar.
        if not correo.lower().endswith("@" + self._dominio):
            raise ErrorDeNegocio(f"El correo debe ser institucional (@{self._dominio})")
