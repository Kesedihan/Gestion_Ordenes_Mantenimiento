"""Pruebas de la capa de dominio: no necesitan base de datos ni HTTP
(evidencia de SoC y DIP: las reglas se prueban aisladas)."""
from datetime import date, datetime

import pytest

from app.compartido.errores import ErrorDeNegocio
from app.hojas_vida.dominio import Especialidad, Experiencia, Operario
from app.jornada.dominio import (Actividad, EstadoActividad, Jornada, MomentoEvidencia,
                                 ResultadoRevision)

H = lambda h, m=0: datetime(2026, 11, 9, h, m)


def actividad():
    return Actividad(1, operario_id=7, centro_id=1, centro_nombre="C1", fecha=date(2026, 11, 9),
                     tipo_servicio="PISCINA", descripcion="Limpieza")


def test_no_se_inicia_sin_foto_antes():
    a = actividad()
    with pytest.raises(ErrorDeNegocio, match="ANTES"):
        a.iniciar(H(8))


def test_flujo_completo_de_actividad():
    a = actividad()
    a.registrar_evidencia(MomentoEvidencia.ANTES)
    a.iniciar(H(8))
    a.registrar_evidencia(MomentoEvidencia.DURANTE)
    a.registrar_evidencia(MomentoEvidencia.DESPUES)
    a.finalizar(H(10))
    assert a.estado is EstadoActividad.FINALIZADA and a.evidencias_completas()
    a.revisar(ResultadoRevision.ACEPTADA, supervisor_id=99, observacion=None)
    assert a.estado is EstadoActividad.ACEPTADA


def test_no_se_finaliza_sin_las_tres_evidencias():
    a = actividad()
    a.registrar_evidencia(MomentoEvidencia.ANTES)
    a.iniciar(H(8))
    with pytest.raises(ErrorDeNegocio, match="DESPUES, DURANTE"):
        a.finalizar(H(9))


def test_evidencia_no_se_reemplaza():
    a = actividad()
    a.registrar_evidencia(MomentoEvidencia.ANTES)
    with pytest.raises(ErrorDeNegocio, match="ya fue registrada"):
        a.registrar_evidencia(MomentoEvidencia.ANTES)


def test_rechazo_exige_observacion():
    a = actividad()
    a.registrar_evidencia(MomentoEvidencia.ANTES)
    a.iniciar(H(8))
    a.registrar_evidencia(MomentoEvidencia.DURANTE)
    a.registrar_evidencia(MomentoEvidencia.DESPUES)
    a.finalizar(H(9))
    with pytest.raises(ErrorDeNegocio, match="observación"):
        a.revisar(ResultadoRevision.RECHAZADA, 99, "  ")


def test_salida_no_anterior_a_entrada():
    j = Jornada(7, 1, H(8))
    with pytest.raises(ErrorDeNegocio):
        j.registrar_salida(H(7))
    j.registrar_salida(H(17))
    assert not j.esta_abierta()


def test_operario_encapsula_validaciones():
    with pytest.raises(ErrorDeNegocio, match="documento"):
        Operario("12AB", "Ana", "Ruiz", "300", "ana@mantenimiento.com.co", date(2025, 1, 1),
                 [Especialidad.PINTURA])
    o = Operario("12345678", "Ana", "Ruiz", "300", "ana@mantenimiento.com.co", date(2025, 1, 1),
                 [Especialidad.PINTURA], experiencia=[Experiencia("X", "Pintora", 18)])
    assert o.anios_experiencia() == 1.5
    o.inactivar()
    assert not o.esta_activo()
    with pytest.raises(AttributeError):
        o.estado = "ACTIVO"  # no hay setter: encapsulación
