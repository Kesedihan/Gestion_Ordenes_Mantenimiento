from sqlalchemy import func, select

from app.contenedor import Contenedor
from app.identidad.dominio import Rol
from app.identidad.infraestructura import UsuarioModelo
from app.preparar_pruebas import CUENTAS, preparar
from app.programacion.modelos import (
    MensajeOutboxModelo,
    ProgramacionSemanalModelo,
)


def test_preparar_crea_perfiles_vinculados_y_programacion_publicada(tmp_path):
    contenedor = Contenedor(
        "sqlite:///:memory:",
        str(tmp_path / "evidencias"),
        secreto_jwt="secreto-de-prueba-suficientemente-largo",
    )
    contenedor.crear_tablas()

    resultado = preparar(contenedor)
    with contenedor.Sesion() as sesion:
        usuarios = list(sesion.scalars(select(UsuarioModelo)))
        programaciones = list(sesion.scalars(select(ProgramacionSemanalModelo)))
        mensajes = list(sesion.scalars(select(MensajeOutboxModelo)))

        assert len(usuarios) == len(CUENTAS) == 6
        assert {usuario.rol for usuario in usuarios} == {rol.value for _, _, rol, _, _ in CUENTAS}
        assert all(
            usuario.operario_id is not None
            for usuario in usuarios
            if usuario.rol == Rol.OPERARIO.value
        )
        assert all(
            usuario.operario_id is None
            for usuario in usuarios
            if usuario.rol != Rol.OPERARIO.value
        )
        assert len(programaciones) == 1
        assert programaciones[0].estado == "PUBLICADA"
        assert programaciones[0].publicada_en is not None
        assert len(programaciones[0].asignaciones) == 6
        assert len(mensajes) == 3
        assert {mensaje.programacion_id for mensaje in mensajes} == {
            programaciones[0].id
        }

    resultado_repetido = preparar(contenedor)
    assert resultado_repetido["programacion_publicada"] == resultado["programacion_publicada"]
    with contenedor.Sesion() as sesion:
        assert sesion.scalar(
            select(func.count()).select_from(ProgramacionSemanalModelo)
        ) == 1
        assert sesion.scalar(
            select(func.count()).select_from(MensajeOutboxModelo)
        ) == 3
