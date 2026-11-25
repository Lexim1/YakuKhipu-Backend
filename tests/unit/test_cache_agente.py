from app.agent.cache import clave


def test_cache_separa_actores_visitantes_orden_y_negacion():
    actor={'perfil':'sunass','usuario_id':'persona-a'}
    original=clave(actor,'caso','v1','¿Se ejecutó?','historial')
    assert original!=clave({**actor,'usuario_id':'persona-b'},'caso','v1','¿Se ejecutó?','historial')
    assert original!=clave(actor,'caso','v1','¿No se ejecutó?','historial')
    assert original!=clave(actor,'caso','v2','¿Se ejecutó?','historial')
    assert original!=clave(actor,'caso','v1','¿Se ejecutó?','otro historial')
    assert clave({'perfil':'publico','visitante_id':'a'},'caso','v1','estado')!=clave({'perfil':'publico','visitante_id':'b'},'caso','v1','estado')
