from test_api_actores import entorno, entrar


def test_recepcion_expone_sugerencia_sin_crear_ni_asignar_expediente(entorno):
    e = entorno
    entrar(e)
    datos = {'titulo': 'Solicitud recibida', 'referencia': 'DEMO-UFI-AUDITORIA',
             'fecha_documento': '2026-11-20', 'eps_id': 'eps-a',
             'texto': 'Solicitud de uso excepcional del fondo de inversiones UFI-2024-0001.'}
    r = e.client.post('/api/recepcion', json=datos, headers={'Idempotency-Key': 'clasificacion-ufi'})
    assert r.status_code == 201, r.text
    item = next(x for x in e.client.get('/api/recepcion').json()['items'] if x['id'] == r.json()['id'])
    assert item['clasificacion']['procedimiento'] == 'UFI'
    assert item['clasificacion']['requiere_confirmacion'] is True
    assert len(e.db.tablas['tramite']) == 2
    entrar(e, 'empresa-a')
    assert e.client.get('/api/recepcion').status_code == 403
