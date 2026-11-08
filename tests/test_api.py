"""Pruebas de extremo a extremo de los dos módulos a través de la API.

Usan una base SQLite en memoria y un reloj fijo, inyectados por el
contenedor (IoC): el código de producción no cambia para probarse.
"""
import uuid
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient

from app.compartido.reloj import RelojFijo
from app.contenedor import Contenedor
from app.identidad.dominio import Rol
from app.jornada.infraestructura import ActividadModelo
from app.main import crear_app
from app.programacion.modelos import CentroTrabajoModelo

HOY = date(2026, 11, 9)
H = lambda h, m=0: datetime(2026, 11, 9, h, m).isoformat()
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 2000

OPERARIO = {
    "documento": "1075001001", "nombres": "Carlos", "apellidos": "Perdomo",
    "telefono": "3101234567", "correo_institucional": "carlos@mantenimiento.com.co",
    "fecha_ingreso": "2024-02-01", "especialidades": ["PISCINA"],
    "formacion": [{"nivel": "Técnico", "titulo": "Piscinas", "institucion": "SENA", "anio_fin": 2022}],
    "experiencia": [{"empresa": "Aqua", "cargo": "Piscinero", "meses": 30}],
}


@pytest.fixture
def entorno(tmp_path):
    contenedor = Contenedor("sqlite:///:memory:", str(tmp_path / "evid"),
                            reloj=RelojFijo(datetime(2026, 11, 9, 18, 0)),
                            secreto_jwt="test-secret-at-least-32-bytes-long")
    cliente = TestClient(crear_app(contenedor))
    with contenedor.Sesion() as sesion:
        identidad = contenedor.servicio_identidad(sesion)
        identidad.crear_usuario("admin", "clave-admin", Rol.ADMINISTRATIVO)
        identidad.crear_usuario("supervisor", "clave-supervisor", Rol.SUPERVISOR)
        sesion.commit()
    operario_id = cliente.post("/api/operarios", json=OPERARIO).json()["id"]
    with contenedor.Sesion() as sesion:
        identidad = contenedor.servicio_identidad(sesion)
        identidad.crear_usuario(
            "operario", "clave-operario", Rol.OPERARIO, operario_id=operario_id
        )
        sesion.commit()
    cliente.headers.update(encabezado_auth(cliente, "operario", "clave-operario"))
    with contenedor.Sesion() as s:
        centro = CentroTrabajoModelo(nombre="Conjunto Reservas del Río", direccion="Neiva")
        s.add(centro)
        s.flush()
        act = ActividadModelo(operario_id=operario_id, centro_id=centro.id, fecha=HOY,
                              tipo_servicio="PISCINA", descripcion="Limpieza")
        s.add(act)
        s.commit()
        return cliente, operario_id, centro.id, act.id


def encabezado_auth(cliente, usuario, contrasena):
    respuesta = cliente.post("/api/auth/token", data={
        "username": usuario, "password": contrasena,
    })
    assert respuesta.status_code == 200
    return {"Authorization": f"Bearer {respuesta.json()['access_token']}"}


def evento(tipo, hora, **datos):
    return {"id": str(uuid.uuid4()), "tipo": tipo, "hora_dispositivo": hora, "datos": datos}


def foto(cliente, op, act, momento, hora, evento_id=None):
    return cliente.post("/api/jornada/evidencias", data={
        "evento_id": evento_id or str(uuid.uuid4()), "operario_id": op, "actividad_id": act,
        "momento": momento, "tomada_en": hora}, files={"foto": ("f.jpg", JPEG, "image/jpeg")}).json()


# ------------------------------------------------------------- M1 Hojas de vida
def test_m1_crud_hoja_de_vida(entorno):
    cliente, op, *_ = entorno
    hoja = cliente.get(f"/api/operarios/{op}").json()
    assert hoja["nombre_completo"] == "Carlos Perdomo" and hoja["anios_experiencia"] == 2.5
    r = cliente.put(f"/api/operarios/{op}/contacto",
                    json={"telefono": "3000000000", "correo_institucional": "c.perdomo@mantenimiento.com.co"})
    assert r.status_code == 200 and r.json()["telefono"] == "3000000000"
    assert cliente.patch(f"/api/operarios/{op}/estado", json={"activo": False}).json()["estado"] == "INACTIVO"


def test_m1_reglas_de_negocio(entorno):
    cliente, *_ = entorno
    assert cliente.post("/api/operarios", json=OPERARIO).status_code == 409  # documento duplicado
    externo = {**OPERARIO, "documento": "99999999", "correo_institucional": "x@gmail.com"}
    r = cliente.post("/api/operarios", json=externo)
    assert r.status_code == 422 and "institucional" in r.json()["detail"]
    assert cliente.get("/api/operarios/999").status_code == 404


# ------------------------------------------------- M2 Jornada sin conexión (E1/E2)
def test_m2_jornada_completa_offline_e_idempotente(entorno):
    cliente, op, centro, act = entorno
    tokens = cliente.post(
        "/api/auth/token",
        data={"username": "operario", "password": "clave-operario"},
    ).json()
    assert tokens["rol"] == Rol.OPERARIO.value
    assert tokens["operario_id"] == op
    admin = encabezado_auth(cliente, "admin", "clave-admin")
    supervisor = encabezado_auth(cliente, "supervisor", "clave-supervisor")
    # 1) El celular descarga la programación antes de salir.
    prog = cliente.get(f"/api/jornada/programacion/{op}", params={"desde": HOY.isoformat()}).json()
    assert prog[0]["id"] == act and prog[0]["centro"] == "Conjunto Reservas del Río"
    mi_programacion = cliente.get(
        "/api/jornada/mi-programacion", params={"desde": HOY.isoformat()}
    )
    assert mi_programacion.status_code == 200
    assert mi_programacion.json()[0]["id"] == act
    assert cliente.get("/api/jornada/programacion/999").status_code == 403
    assert cliente.post(
        "/api/jornada/sincronizar",
        json={"operario_id": 999, "eventos": []},
    ).status_code == 403

    # 2) Sin conexión registra todo; al llegar a un wifi sincroniza (fotos + lote).
    entrada = evento("ENTRADA", H(7, 55), centro_id=centro)
    r = cliente.post("/api/jornada/sincronizar", json={"operario_id": op, "eventos": [entrada]}).json()
    assert r[0]["estado"] == "ACEPTADO"
    assert foto(cliente, op, act, "ANTES", H(8, 0))["estado"] == "ACEPTADO"
    inicio = evento("INICIO_ACTIVIDAD", H(8, 2), actividad_id=act)
    assert cliente.post("/api/jornada/sincronizar",
                        json={"operario_id": op, "eventos": [inicio]}).json()[0]["estado"] == "ACEPTADO"
    foto_durante_id = str(uuid.uuid4())
    assert foto(cliente, op, act, "DURANTE", H(9), foto_durante_id)["estado"] == "ACEPTADO"
    assert foto(cliente, op, act, "DESPUES", H(10))["estado"] == "ACEPTADO"
    lote = [evento("FIN_ACTIVIDAD", H(10, 5), actividad_id=act), evento("SALIDA", H(16, 30))]
    assert [x["estado"] for x in cliente.post(
        "/api/jornada/sincronizar", json={"operario_id": op, "eventos": lote}).json()] == ["ACEPTADO"] * 2

    # 3) Corte de red: el celular reenvía lo mismo -> no se duplica nada (D4).
    reenvio = cliente.post("/api/jornada/sincronizar",
                           json={"operario_id": op, "eventos": [entrada, inicio] + lote}).json()
    assert {x["estado"] for x in reenvio} == {"DUPLICADO"}
    assert foto(cliente, op, act, "DURANTE", H(9), foto_durante_id)["estado"] == "DUPLICADO"

    # 4) Seguimiento: el tablero refleja la jornada.
    pendientes = cliente.get(
        "/api/jornada/revisiones", params={"fecha": HOY.isoformat()}, headers=supervisor
    ).json()
    assert pendientes[0]["id"] == act
    assert pendientes[0]["operario"] == "Carlos Perdomo"
    assert pendientes[0]["evidencias"] == ["ANTES", "DESPUES", "DURANTE"]
    fila = cliente.get("/api/seguimiento", params={"fecha": HOY.isoformat()},
                       headers=admin).json()[0]
    assert fila["operario"] == "Carlos Perdomo" and fila["salida"].startswith("2026-11-09T16:30")
    assert fila["actividades"][0]["estado"] == "FINALIZADA"
    assert fila["actividades"][0]["evidencias"] == ["ANTES", "DESPUES", "DURANTE"]
    for momento in ("ANTES", "DURANTE", "DESPUES"):
        foto_response = cliente.get(
            f"/api/jornada/actividades/{act}/evidencias/{momento}", headers=admin
        )
        assert foto_response.status_code == 200
        assert foto_response.content.startswith(b"\xff\xd8")

    # 5) E4: el supervisor revisa.
    r = cliente.patch(f"/api/jornada/actividades/{act}/revision",
                      json={"resultado": "ACEPTADA"}, headers=supervisor)
    assert r.json()["estado"] == "ACEPTADA"
    assert r.json()["observacion"] is None


def test_m2_permite_nueva_entrada_despues_de_registrar_salida(entorno):
    cliente, op, centro, _ = entorno
    with cliente.app.state.contenedor.Sesion() as sesion:
        otro_centro = CentroTrabajoModelo(
            nombre="Conjunto Torres de Altamira", direccion="Neiva"
        )
        sesion.add(otro_centro)
        sesion.commit()
        otro_centro_id = otro_centro.id

    entrada_1 = cliente.post(
        "/api/jornada/sincronizar",
        json={"operario_id": op, "eventos": [
            evento("ENTRADA", H(7), centro_id=centro),
        ]},
    )
    salida_1 = cliente.post(
        "/api/jornada/sincronizar",
        json={"operario_id": op, "eventos": [
            evento("SALIDA", H(8)),
        ]},
    )
    entrada_2 = cliente.post(
        "/api/jornada/sincronizar",
        json={"operario_id": op, "eventos": [
            evento("ENTRADA", H(9), centro_id=otro_centro_id),
        ]},
    )
    salida_2 = cliente.post(
        "/api/jornada/sincronizar",
        json={"operario_id": op, "eventos": [
            evento("SALIDA", H(10)),
        ]},
    )

    assert [respuesta.json()[0]["estado"] for respuesta in (
        entrada_1, salida_1, entrada_2, salida_2,
    )] == ["ACEPTADO"] * 4
    admin = encabezado_auth(cliente, "admin", "clave-admin")
    fila = cliente.get(
        "/api/seguimiento",
        params={"fecha": HOY.isoformat()},
        headers=admin,
    ).json()[0]
    assert [
        (jornada["centro_id"], jornada["centro"])
        for jornada in fila["jornadas"]
    ] == [
        (centro, "Conjunto Reservas del Río"),
        (otro_centro_id, "Conjunto Torres de Altamira"),
    ]


def test_m2_reglas_rechazan_eventos_invalidos(entorno):
    cliente, op, centro, act = entorno
    # Iniciar sin entrada ni foto ANTES -> rechazado, con motivo para el operario.
    r = cliente.post("/api/jornada/sincronizar", json={"operario_id": op, "eventos": [
        evento("INICIO_ACTIVIDAD", H(8), actividad_id=act)]}).json()[0]
    assert r["estado"] == "RECHAZADO"
    # Foto DURANTE sin actividad en curso -> rechazada.
    assert foto(cliente, op, act, "DURANTE", H(9))["estado"] == "RECHAZADO"
    # Hora del celular en el futuro (reloj manipulado) -> se acepta pero queda marcada (D5).
    cliente.post("/api/jornada/sincronizar", json={"operario_id": op, "eventos": [
        evento("ENTRADA", H(23, 0), centro_id=centro)]})
    admin = encabezado_auth(cliente, "admin", "clave-admin")
    fila = cliente.get("/api/seguimiento", params={"fecha": HOY.isoformat()},
                       headers=admin).json()[0]
    assert fila["eventos_hora_sospechosa"] == 1
    # Revisar una actividad no finalizada -> 422.
    supervisor = encabezado_auth(cliente, "supervisor", "clave-supervisor")
    assert cliente.patch(f"/api/jornada/actividades/{act}/revision",
                         json={"resultado": "ACEPTADA"}, headers=supervisor).status_code == 422


def test_m2_rechazar_actividad_exige_observacion_y_guarda_usuario_autenticado(entorno):
    cliente, op, centro, act = entorno
    supervisor = encabezado_auth(cliente, "supervisor", "clave-supervisor")
    cliente.post("/api/jornada/sincronizar", json={"operario_id": op, "eventos": [
        evento("ENTRADA", H(7, 50), centro_id=centro)]})
    foto(cliente, op, act, "ANTES", H(8))
    cliente.post("/api/jornada/sincronizar", json={"operario_id": op, "eventos": [
        evento("INICIO_ACTIVIDAD", H(8, 5), actividad_id=act)]})
    foto(cliente, op, act, "DURANTE", H(9))
    foto(cliente, op, act, "DESPUES", H(10))
    cliente.post("/api/jornada/sincronizar", json={"operario_id": op, "eventos": [
        evento("FIN_ACTIVIDAD", H(10, 30), actividad_id=act)]})

    rechazo_sin_observacion = cliente.patch(
        f"/api/jornada/actividades/{act}/revision",
        json={"resultado": "RECHAZADA"},
        headers=supervisor,
    )
    assert rechazo_sin_observacion.status_code == 422

    rechazo = cliente.patch(
        f"/api/jornada/actividades/{act}/revision",
        json={"resultado": "RECHAZADA", "observacion": "La terminación requiere corrección."},
        headers=supervisor,
    )
    assert rechazo.status_code == 200
    assert rechazo.json()["estado"] == "RECHAZADA"
    assert rechazo.json()["observacion"] == "La terminación requiere corrección."

    programacion = cliente.get(
        "/api/jornada/mi-programacion", params={"desde": HOY.isoformat()}
    )
    assert programacion.status_code == 200
    actividad_original, correccion = programacion.json()
    assert actividad_original["id"] == act
    assert actividad_original["estado"] == "RECHAZADA"
    assert actividad_original["observacion"] == "La terminación requiere corrección."
    assert correccion["estado"] == "PROGRAMADA"
    assert correccion["correccion_de_id"] == act
    assert correccion["motivo_correccion"] == "La terminación requiere corrección."

    admin = encabezado_auth(cliente, "admin", "clave-admin")
    for momento in ("ANTES", "DURANTE", "DESPUES"):
        evidencia_original = cliente.get(
            f"/api/jornada/actividades/{act}/evidencias/{momento}",
            headers=admin,
        )
        assert evidencia_original.status_code == 200
        assert evidencia_original.content.startswith(b"\xff\xd8")

    correction_id = correccion["id"]
    assert foto(cliente, op, correction_id, "ANTES", H(10, 35))["estado"] == "ACEPTADO"
    inicio = cliente.post("/api/jornada/sincronizar", json={"operario_id": op, "eventos": [
        evento("INICIO_ACTIVIDAD", H(10, 40), actividad_id=correction_id)]}).json()
    assert inicio[0]["estado"] == "ACEPTADO"
    assert foto(cliente, op, correction_id, "DURANTE", H(11))["estado"] == "ACEPTADO"
    assert foto(cliente, op, correction_id, "DESPUES", H(11, 10))["estado"] == "ACEPTADO"
    fin = cliente.post("/api/jornada/sincronizar", json={"operario_id": op, "eventos": [
        evento("FIN_ACTIVIDAD", H(11, 30), actividad_id=correction_id)]}).json()
    assert fin[0]["estado"] == "ACEPTADO"

    aceptacion = cliente.patch(
        f"/api/jornada/actividades/{correction_id}/revision",
        json={"resultado": "ACEPTADA"},
        headers=supervisor,
    )
    assert aceptacion.status_code == 200
    assert aceptacion.json()["estado"] == "ACEPTADA"


def test_m2_consultas_y_revision_exigen_rol_autorizado(entorno):
    cliente, _, _, act = entorno
    admin = encabezado_auth(cliente, "admin", "clave-admin")
    supervisor = encabezado_auth(cliente, "supervisor", "clave-supervisor")
    cliente.headers.pop("Authorization")

    assert cliente.get("/api/seguimiento").status_code == 401
    assert cliente.get("/api/jornada/revisiones").status_code == 401
    assert cliente.get(
        f"/api/jornada/actividades/{act}/evidencias/ANTES"
    ).status_code == 401
    assert cliente.get("/api/seguimiento", headers=supervisor).status_code == 403
    assert cliente.get("/api/jornada/revisiones", headers=admin).status_code == 403
    assert cliente.patch(
        f"/api/jornada/actividades/{act}/revision",
        json={"resultado": "ACEPTADA"},
        headers=admin,
    ).status_code == 403


def test_m2_operario_inactivo_no_sincroniza(entorno):
    cliente, op, centro, _ = entorno
    cliente.patch(f"/api/operarios/{op}/estado", json={"activo": False})
    r = cliente.post("/api/jornada/sincronizar", json={"operario_id": op, "eventos": [
        evento("ENTRADA", H(8), centro_id=centro)]})
    assert r.status_code == 422
