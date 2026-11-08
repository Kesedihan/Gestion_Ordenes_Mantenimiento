"""Alta interactiva de cuentas desde la consola, sin endpoint público."""
from getpass import getpass

from app.identidad.dominio import Rol
from app.main import app


def main() -> None:
    nombre_usuario = input("Nombre de usuario: ").strip()
    roles = {rol.value: rol for rol in Rol}
    print("Roles disponibles: " + ", ".join(roles))
    rol_ingresado = input("Rol: ").strip().upper()
    rol = roles.get(rol_ingresado)
    if rol is None:
        raise SystemExit(f"Rol inválido. Elige uno de: {', '.join(roles)}")

    operario_id = None
    if rol is Rol.OPERARIO:
        try:
            operario_id = int(input("ID de la hoja de vida del operario: ").strip())
        except ValueError as error:
            raise SystemExit("El ID del operario debe ser un número entero.") from error

    contrasena = getpass("Contraseña: ")
    if contrasena != getpass("Confirma la contraseña: "):
        raise SystemExit("Las contraseñas no coinciden.")

    contenedor = app.state.contenedor
    sesion = contenedor.Sesion()
    try:
        usuario = contenedor.servicio_identidad(sesion).crear_usuario(
            nombre_usuario, contrasena, rol, operario_id=operario_id
        )
        sesion.commit()
    finally:
        sesion.close()
    print(f"Usuario creado: {usuario.nombre_usuario} ({usuario.rol.value})")


if __name__ == "__main__":
    main()
