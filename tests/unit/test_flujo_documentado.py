from types import SimpleNamespace

from app.modules.tramites import _puede_registrar, flujo


def actor(*permisos):
    return SimpleNamespace(permisos=set(permisos))


def tramite(procedimiento, paso):
    return SimpleNamespace(procedimiento=procedimiento, paso_actual=paso,
                           estado='en_evaluacion', etapa='Evaluación', responsable='Analista SRT')


def test_analista_avanza_evaluacion_pero_no_derivacion_ni_decision():
    analista = actor('evaluacion.validar', 'requerimiento.registrar')
    assert not _puede_registrar(analista, tramite('CPI', 1), 'avanzar_paso')
    assert _puede_registrar(analista, tramite('CPI', 3), 'avanzar_paso')
    assert not _puede_registrar(analista, tramite('CPI', 6), 'avanzar_paso')
    assert _puede_registrar(analista, tramite('CPI', 4), 'requerir_subsanacion')
    assert _puede_registrar(actor('acto_externo.registrar'), tramite('CPI', 1), 'avanzar_paso')
    assert _puede_registrar(analista, tramite('RP', 1), 'avanzar_paso')


def test_el_flujo_colorea_solo_los_pasos_registrados():
    t = tramite('CPI', 4)
    estado = flujo(t, None, {'situacion':'pendiente_de_validacion', 'validacion':'pendiente_de_validacion'})
    assert [p['estado'] for p in estado['pasos']] == ['hecho'] * 3 + ['actual'] + ['pendiente'] * 4
