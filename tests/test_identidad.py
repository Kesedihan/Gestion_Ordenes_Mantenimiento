from datetime import datetime, timezone

import jwt
import pytest
from fastapi.testclient import TestClient

from app.compartido.errores import ErrorDeNegocio
from app.contenedor import Contenedor
from app.identidad.dominio import Rol
from app.identidad.seguridad import ServicioIdentidad
from app.main import crear_app


@pytest.fixture
def identidad(tmp_path):
    contenedor = Contenedor(
        "sqlite:///:memory:",
        str(tmp_path / "evidencias"),
        secreto_jwt="secreto-de-prueba-suficientemente-largo",
    )
    cliente = TestClient(crear_app(contenedor))
    with contenedor.Sesion() as sesion:
        servicio = contenedor.servicio_identidad(sesion)
        usuario = servicio.crear_usuario("supervisor", "clave-segura", Rol.SUPERVISOR)
        sesion.commit()
    return cliente, contenedor, usuario


def test_login_emite_access_y_refresh_con_rol(identidad):
    cliente, contenedor, usuario = identidad

    respuesta = cliente.post(
        "/api/auth/token",
        data={"username": usuario.nombre_usuario, "password": "clave-segura"},
    )

    assert respuesta.status_code == 200
    tokens = respuesta.json()
    assert tokens["token_type"] == "bearer"
    assert tokens["rol"] == Rol.SUPERVISOR.value
    assert tokens["expires_in"] == 15 * 60

    access = jwt.decode(
        tokens["access_token"], contenedor.secreto_jwt, algorithms=["HS256"]
    )
    refresh = jwt.decode(
        tokens["refresh_token"], contenedor.secreto_jwt, algorithms=["HS256"]
    )
    assert access["type"] == "access"
    assert refresh["type"] == "refresh"
    assert access["role"] == refresh["role"] == Rol.SUPERVISOR.value
    assert refresh["exp"] - access["iat"] == 30 * 24 * 60 * 60
    assert access["exp"] - access["iat"] == 15 * 60
    assert datetime.fromtimestamp(access["exp"], timezone.utc) > datetime.now(timezone.utc)


def test_login_y_script_se_publican_desde_la_pwa(identidad):
    cliente, *_ = identidad

    pagina = cliente.get("/app/login.html")
    script = cliente.get("/app/js/auth.js")
    backoffice = cliente.get("/app/backoffice.html")
    admin_script = cliente.get("/app/js/admin.js")
    supervisor = cliente.get("/app/supervisor.html")
    dashboard = cliente.get("/app/dashboard.html")
    api_script = cliente.get("/app/js/api.js")
    programacion = cliente.get("/app/programacion.html")
    programacion_script = cliente.get("/app/js/programacion.js")
    jornada = cliente.get("/app/")
    jornada_script = cliente.get("/app/app.js")
    jornada_html = cliente.get("/app/index.html")
    dashboard_script = cliente.get("/app/js/dashboard.js")

    assert (
        pagina.status_code
        == script.status_code
        == backoffice.status_code
        == admin_script.status_code
        == supervisor.status_code
        == dashboard.status_code
        == api_script.status_code
        == programacion.status_code
        == programacion_script.status_code
        == jornada.status_code
        == jornada_script.status_code
        == jornada_html.status_code
        == dashboard_script.status_code
        == 200
    )
    assert 'id="form-login"' in pagina.text
    assert "/api/auth/token" in script.text
    assert 'id="form-registro"' in backoffice.text
    assert "/api/operarios" in admin_script.text
    assert 'id="actividades"' in supervisor.text
    assert 'id="jornadas"' in dashboard.text
    assert 'id="form-asignacion"' in programacion.text
    assert "/api/programaciones" in programacion_script.text
    assert 'id="operario"' not in jornada.text
    assert "/api/jornada/mi-programacion" in jornada_script.text
    assert "ESTADOS_ACTIVIDAD" in jornada_script.text
    assert "estado-finalizada" in jornada_html.text
    assert "Trabajo finalizado en servidor" in jornada_script.text
    assert 'id="cerrar-sesion"' in jornada_html.text
    assert 'window.location.assign("/app/login.html")' in jornada_script.text
    assert 'id="filtro-centro"' in dashboard.text
    assert "fila.jornadas" in dashboard_script.text


@pytest.mark.parametrize(
    ("nombre_usuario", "contrasena"),
    [("supervisor", "incorrecta"), ("desconocido", "clave-segura")],
)
def test_login_rechaza_credenciales_invalidas(identidad, nombre_usuario, contrasena):
    cliente, *_ = identidad

    respuesta = cliente.post(
        "/api/auth/token",
        data={"username": nombre_usuario, "password": contrasena},
    )

    assert respuesta.status_code == 401
    assert respuesta.headers["www-authenticate"] == "Bearer"


def test_usuario_guarda_hash_bcrypt_y_rechaza_contrasena_mayor_a_72_bytes(identidad):
    _, _, usuario = identidad

    assert usuario.hash_contrasena.startswith("$2")
    assert usuario.hash_contrasena != "clave-segura"
    assert ServicioIdentidad.verificar_contrasena("clave-segura", usuario.hash_contrasena)
    assert not ServicioIdentidad.verificar_contrasena("x" * 73, usuario.hash_contrasena)
    with pytest.raises(ErrorDeNegocio):
        ServicioIdentidad.crear_hash_contrasena("x" * 73)
