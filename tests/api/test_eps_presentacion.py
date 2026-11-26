from test_api_actores import entorno,entrar
from app.models import Tramite

def test_aviso_eps_sin_pdf_no_verifica_ni_da_acceso_a_documentos(entorno):
    e=entorno;entrar(e)
    r=e.client.post('/api/tramites/caso-a/eventos',json={'tipo':'requerir_informacion','version':1,
        'documento_id':'caso-a-partes','fecha_acreditada':'2026-11-20','plazo_dias':3,'requisitos':['Sustento']})
    assert r.status_code==200
    entrar(e,'empresa-a')
    datos={'referencia_presentada':'Oficio EPS 321','fecha_presentacion':'2026-11-21','cargo':'Cargo 123',
           'canal':'Mesa de Partes','version':r.json()['version']}
    r=e.client.post('/api/eps/tramites/caso-a/respuestas',json=datos,headers={'Idempotency-Key':'aviso-qa'})
    assert r.status_code==200,r.text
    assert r.json()['respuesta_informada']['documento']=='Oficio EPS 321'
    assert r.json()['respuesta_informada']['verificada'] is False
    assert e.client.get('/api/documentos/caso-a-interno/contenido').status_code==404
    assert e.client.post('/api/eps/tramites/caso-a/respuestas',json=datos,headers={'Idempotency-Key':'aviso-qa'}).status_code==200
    entrar(e)
    actions=e.client.get('/api/tramites/caso-a/acciones').json()['items']
    assert actions==[{'tipo':'verificar_respuesta','texto':'Verificar la respuesta de la EPS','requiere_documento':True}]
    version=e.db.get(Tramite,'caso-a').version
    assert e.client.post('/api/tramites/caso-a/eventos',json={'tipo':'verificar_respuesta','version':version}).status_code==422
    r=e.client.post('/api/tramites/caso-a/eventos',json={'tipo':'verificar_respuesta','version':version,
        'documento_id':'caso-a-partes','fecha_acreditada':'2026-11-22'})
    assert r.status_code==200,r.text

def test_id_de_documento_ajeno_sigue_rechazado(entorno):
    e=entorno;entrar(e)
    r=e.client.post('/api/tramites/caso-a/eventos',json={'tipo':'requerir_informacion','version':1,
        'documento_id':'caso-a-partes','fecha_acreditada':'2026-11-20','plazo_dias':3})
    entrar(e,'empresa-a')
    r=e.client.post('/api/eps/tramites/caso-a/respuestas',json={'documento':'caso-b-partes',
        'referencia_presentada':'Un oficio','fecha_presentacion':'2026-11-21','canal':'Mesa de Partes','version':r.json()['version']})
    assert r.status_code==404
