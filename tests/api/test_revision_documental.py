from datetime import date

from test_api_actores import entorno, entrar
from app.models import Tramite


def test_visibilidad_revisada_versionada_y_reversible_solo_sunass(entorno):
    e = entorno
    ruta = '/api/tramites/caso-a/documentos/caso-a-interno/visibilidad'
    body = {'visibilidad': 'partes', 'motivo': 'Revisión documental de acceso', 'version': 1}
    assert e.client.put(ruta, json=body).status_code == 401
    entrar(e, 'empresa-a')
    assert e.client.put(ruta, json=body).status_code == 403
    entrar(e)
    assert e.client.put(ruta, json={**body, 'visibilidad': 'publica'}).status_code == 422
    assert e.client.put(ruta.replace('caso-a-interno', 'caso-b-interno'), json=body).status_code == 422
    r = e.client.put(ruta, json=body)
    assert r.status_code == 200, r.text
    assert r.json()['version'] == 2
    assert e.client.put(ruta, json=body).status_code == 409
    entrar(e, 'empresa-a')
    assert e.client.get('/api/documentos/caso-a-interno/contenido').status_code == 200
    entrar(e, 'empresa-b')
    assert e.client.get('/api/documentos/caso-a-interno/contenido').status_code == 404
    entrar(e)
    r = e.client.put(ruta, json={**body, 'version': 2, 'visibilidad': 'interna'})
    assert r.status_code == 200
    entrar(e, 'empresa-a')
    assert e.client.get('/api/documentos/caso-a-interno/contenido').status_code == 404


def test_actos_dirigidos_a_eps_requieren_documento_compartido(entorno):
    e = entorno; entrar(e)
    cuerpo = {'tipo': 'requerir_informacion', 'documento_id': 'caso-a-interno', 'fecha_acreditada': '2026-11-20',
              'version': 1, 'plazo_dias': 10, 'requisitos': ['Sustento de costos unitarios']}
    assert e.client.post('/api/tramites/caso-a/eventos', json=cuerpo).status_code == 422
    assert e.db.get(Tramite, 'caso-a').version == 1
    cuerpo.update(documento_id='caso-a-partes')
    r = e.client.post('/api/tramites/caso-a/eventos', json=cuerpo)
    assert r.status_code == 200
    entrar(e, 'empresa-a')
    ficha = e.client.get('/api/eps/tramites/caso-a').json()
    assert ficha['siguiente_accion']['titulo'] == 'Responde el caso-a-partes'


def test_informe_registra_evaluacion_sin_fingir_firma_o_resolucion(entorno):
    e = entorno; entrar(e)
    t = e.db.get(Tramite, 'caso-a'); t.procedimiento = 'UFI'; t.paso_actual = 5
    cuerpo = {'tipo': 'registrar_informe', 'documento_id': 'caso-a-interno', 'fecha_acreditada': '2026-11-20', 'version': 1}
    r = e.client.post('/api/tramites/caso-a/eventos', json=cuerpo)
    assert r.status_code == 200, r.text
    assert t.paso_actual == 5 and t.estado == 'en_evaluacion'
    assert r.json()['version'] == 2
    assert e.client.get('/api/tramites/caso-a/eventos').json()['items'][-1]['tipo'] == 'registrar_informe'


def test_no_admite_fecha_anterior_al_ingreso(entorno):
    e = entorno; entrar(e)
    e.db.get(Tramite, 'caso-a').fecha_inicio = date(2026, 11, 21)
    r = e.client.post('/api/tramites/caso-a/eventos', json={'tipo': 'avanzar_paso', 'documento_id': 'caso-a-interno',
        'fecha_acreditada': '2026-11-20', 'version': 1})
    assert r.status_code == 422


def test_resolucion_parcial_llega_a_eps_y_no_se_confunde_con_aprobacion_total(entorno):
    e=entorno; entrar(e)
    t=e.db.get(Tramite,'caso-a');t.procedimiento='UFI';t.paso_actual=9
    assert e.client.post('/api/tramites/caso-a/eventos',json={'tipo':'resolver','documento_id':'caso-a-interno',
        'fecha_acreditada':'2026-11-20','version':1,'resultado':'autorizado'}).status_code==422
    r=e.client.post('/api/tramites/caso-a/eventos',json={'tipo':'resolver','documento_id':'caso-a-partes',
        'fecha_acreditada':'2026-11-20','version':1,'resultado':'autorizado','alcance_autorizacion':'parcial'})
    assert r.status_code==200,r.text
    entrar(e,'empresa-a')
    ficha=e.client.get('/api/eps/tramites/caso-a').json()
    assert ficha['estado_texto']=='Autorizado parcialmente' and ficha['siguiente_accion'] is None
    assert ficha['aviso']['titulo']=='Autorizado parcialmente'
    assert ficha['seguimiento'][-1]['titulo']=='Resolución registrada: caso-a-partes'
    assert all(s['estado']=='hecho' and 'avisaremos' not in s['fecha_texto'].lower() for s in ficha['seguimiento'])
