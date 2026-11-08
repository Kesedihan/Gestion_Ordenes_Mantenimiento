from datetime import date, datetime, timedelta, timezone
import smtplib

import pytest
from fastapi.testclient import TestClient

from app.compartido.reloj import RelojFijo
from app.contenedor import Contenedor
from app.identidad.dominio import Rol
from app.jornada.infraestructura import ActividadModelo
from app.main import crear_app
from app.programacion.casos_uso import ProcesarOutbox
from app.programacion.infraestructura import RepositorioOutboxSQL
from app.programacion.modelos import (
    CentroTrabajoModelo,
    MensajeOutboxModelo,
)

LUNES = date(2026, 11, 9)


@pytest.fixture
def entorno_programacion(tmp_path):
    contenedor = Contenedor(
        "sqlite:///:memory:",
        str(tmp_path / "evidencias"),
        reloj=RelojFijo(datetime(2026, 11, 9, 8, 0)),
        secreto_jwt="test-secret-at-least-32-bytes-long",
    )
    cliente = TestClient(crear_app(contenedor))
    with contenedor.Sesion() as sesion:
        identidad = contenedor.servicio_identidad(sesion)
        identidad.crear_usuario("admin-m3", "clave-admin-m3", Rol.ADMINISTRADOR)
        identidad.crear_usuario("supervisor-m3", "clave-supervisor-m3", Rol.SUPERVISOR)
        sesion.add(CentroTrabajoModelo(nombre="Centro Norte", direccion="Neiva"))
        sesion.commit()
    operario = {
        "documento": "1098765001",
        "nombres": "María",
        "apellidos": "López",
        "telefono": "3001234567",
        "correo_institucional": "maria.lopez@mantenimiento.com.co",
        "fecha_ingreso": LUNES.isoformat(),
        "especialidades": ["PINTURA"],
        "formacion": [],
        "experiencia": [],
    }
    operario_id = cliente.post("/api/operarios", json=operario).json()["id"]
    with contenedor.Sesion() as sesion:
        identidad = contenedor.servicio_identidad(sesion)
        identidad.crear_usuario(
            "operario-m3",
            "clave-operario-m3",
            Rol.OPERARIO,
            operario_id=operario_id,
        )
        sesion.commit()
    operario_auth = _autorizacion(
        cliente, "operario-m3", "clave-operario-m3"
    )
    centro_id = cliente.get(
        "/api/programaciones/catalogos",
        headers=_autorizacion(cliente, "admin-m3", "clave-admin-m3"),
    ).json()["centros"][0]["id"]
    return cliente, contenedor, operario_id, centro_id, operario_auth


def _autorizacion(cliente, nombre, contrasena):
    respuesta = cliente.post(
        "/api/auth/token",
        data={"username": nombre, "password": contrasena},
    )
    assert respuesta.status_code == 200
    return {"Authorization": f"Bearer {respuesta.json()['access_token']}"}


def _cuerpo_programacion(operario_id, centro_id):
    return {
        "semana_inicio": LUNES.isoformat(),
        "asignaciones": [
            {
                "operario_id": operario_id,
                "centro_id": centro_id,
                "fecha": (LUNES + timedelta(days=1)).isoformat(),
                "tipo_servicio": "pintura",
                "descripcion": "Pintar muro del bloque A",
            },
            {
                "operario_id": operario_id,
                "centro_id": centro_id,
                "fecha": (LUNES + timedelta(days=3)).isoformat(),
                "tipo_servicio": "PINTURA",
                "descripcion": "Retocar zonas comunes",
            },
        ],
    }


def test_programar_publicar_y_reflejar_en_jornada_en_misma_transaccion(entorno_programacion):
    cliente, contenedor, operario_id, centro_id, operario_auth = entorno_programacion
    admin = _autorizacion(cliente, "admin-m3", "clave-admin-m3")

    borrador = cliente.post(
        "/api/programaciones",
        json=_cuerpo_programacion(operario_id, centro_id),
        headers=admin,
    )

    assert borrador.status_code == 201
    programacion = borrador.json()
    assert programacion["estado"] == "BORRADOR"
    assert len(programacion["asignaciones"]) == 2
    assert cliente.get(
        f"/api/jornada/programacion/{operario_id}",
        params={"desde": LUNES.isoformat(), "dias": 7},
        headers=operario_auth,
    ).json() == []
    with contenedor.Sesion() as sesion:
        assert sesion.query(MensajeOutboxModelo).count() == 0

    publicada = cliente.post(
        f"/api/programaciones/{programacion['id']}/publicar",
        headers=admin,
    )

    assert publicada.status_code == 200
    assert publicada.json()["estado"] == "PUBLICADA"
    assert publicada.json()["publicada_en"]
    actividades = cliente.get(
        f"/api/jornada/programacion/{operario_id}",
        params={"desde": LUNES.isoformat(), "dias": 7},
        headers=operario_auth,
    ).json()
    assert len(actividades) == 2
    assert all(actividad["estado"] == "PROGRAMADA" for actividad in actividades)
    with contenedor.Sesion() as sesion:
        mensajes = sesion.query(MensajeOutboxModelo).all()
        assert len(mensajes) == 1
        assert mensajes[0].destinatario == "maria.lopez@mantenimiento.com.co"
        assert mensajes[0].estado == "PENDIENTE"
        assert "Pintar muro del bloque A" in mensajes[0].cuerpo
        assert sesion.query(ActividadModelo).count() == 2

    assert cliente.post(
        f"/api/programaciones/{programacion['id']}/publicar",
        headers=admin,
    ).status_code == 409
    lista = cliente.get("/api/programaciones", headers=admin).json()
    assert len(lista) == 1 and lista[0]["estado"] == "PUBLICADA"


def test_programacion_valida_semana_catalogos_y_rol(entorno_programacion):
    cliente, _, operario_id, centro_id, _ = entorno_programacion
    admin = _autorizacion(cliente, "admin-m3", "clave-admin-m3")
    supervisor = _autorizacion(cliente, "supervisor-m3", "clave-supervisor-m3")
    cuerpo = _cuerpo_programacion(operario_id, centro_id)

    assert cliente.get("/api/programaciones").status_code == 401
    assert cliente.get("/api/programaciones", headers=supervisor).status_code == 403
    assert cliente.get("/api/programaciones/catalogos", headers=admin).json()["operarios"] == [
        {"id": operario_id, "nombre": "María López"}
    ]

    cuerpo_semana_invalida = {**cuerpo, "semana_inicio": (LUNES + timedelta(days=1)).isoformat()}
    assert cliente.post(
        "/api/programaciones", json=cuerpo_semana_invalida, headers=admin
    ).status_code == 422

    cuerpo_fecha_invalida = _cuerpo_programacion(operario_id, centro_id)
    cuerpo_fecha_invalida["asignaciones"][0]["fecha"] = (LUNES + timedelta(days=7)).isoformat()
    assert cliente.post(
        "/api/programaciones", json=cuerpo_fecha_invalida, headers=admin
    ).status_code == 422

    assert cliente.post(
        "/api/programaciones", json=cuerpo, headers=admin
    ).status_code == 201
    assert cliente.post(
        "/api/programaciones", json=cuerpo, headers=admin
    ).status_code == 409


def test_error_smtp_reintenta_sin_perder_el_mensaje(entorno_programacion):
    cliente, contenedor, operario_id, centro_id, _ = entorno_programacion
    admin = _autorizacion(cliente, "admin-m3", "clave-admin-m3")
    borrador = cliente.post(
        "/api/programaciones",
        json=_cuerpo_programacion(operario_id, centro_id),
        headers=admin,
    ).json()
    assert cliente.post(
        f"/api/programaciones/{borrador['id']}/publicar", headers=admin
    ).status_code == 200

    class EmisorFallido:
        def __init__(self):
            self.mensajes = []

        def enviar(self, destinatario, asunto, cuerpo):
            self.mensajes.append((destinatario, asunto, cuerpo))
            raise smtplib.SMTPException("SMTP fuera de servicio")

    class EmisorCorrecto:
        def __init__(self):
            self.mensajes = []

        def enviar(self, destinatario, asunto, cuerpo):
            self.mensajes.append((destinatario, asunto, cuerpo))

    emisor_fallido = EmisorFallido()
    with contenedor.Sesion() as sesion:
        assert ProcesarOutbox(
            RepositorioOutboxSQL(sesion), emisor_fallido
        ).ejecutar_siguiente()

    with contenedor.Sesion() as sesion:
        mensaje = sesion.query(MensajeOutboxModelo).one()
        assert mensaje.estado == "PENDIENTE"
        assert mensaje.intentos == 1
        assert "SMTP fuera de servicio" in mensaje.error
        ahora = datetime.now(timezone.utc).replace(tzinfo=None)
        assert ahora < mensaje.disponible_en <= ahora + timedelta(seconds=31)
        mensaje.disponible_en = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
        sesion.commit()

    emisor = EmisorCorrecto()
    with contenedor.Sesion() as sesion:
        assert ProcesarOutbox(
            RepositorioOutboxSQL(sesion), emisor
        ).ejecutar_siguiente()
    with contenedor.Sesion() as sesion:
        mensaje = sesion.query(MensajeOutboxModelo).one()
        assert mensaje.estado == "ENVIADO"
        assert mensaje.intentos == 2
        assert mensaje.enviado_en is not None
    assert emisor.mensajes == emisor_fallido.mensajes
