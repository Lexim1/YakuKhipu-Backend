import json
import pytest
from sqlalchemy.exc import OperationalError,IntegrityError
from app.agent import llm
from app.auth import sesion
from app.core.config import settings
from app.api.asistente import _consultas
from test_api_actores import entorno,entrar,publicar


@pytest.mark.parametrize('method,path,status',[('get','/ruta-inexistente',404),('put','/api/sesion',405),
    ('get','/api/publico/decisiones?page=0',422),('get','/api/publico/documentos/xxx/contenido?formato=exe',422)])
def test_errores_uniformes(entorno,method,path,status):
    r=getattr(entorno.client,method)(path)
    assert r.status_code==status,r.text
    assert isinstance(r.json()['detail'],str) and r.json()['codigo']


def test_bd_no_disponible_responde_503_sin_detalles(entorno):
    entrar(entorno)
    def falla(*args,**kwargs): raise OperationalError('consulta',None,Exception('credencial-privada'))
    entorno.monkeypatch.setattr(entorno.db,'scalars',falla)
    r=entorno.client.get('/api/tramites')
    assert r.status_code==503 and r.json()['codigo']=='no_disponible'
    assert 'credencial-privada' not in r.text


def test_error_inesperado_500_y_cors(entorno):
    entrar(entorno)
    def falla(*args,**kwargs): raise RuntimeError('detalle-interno-privado')
    entorno.monkeypatch.setattr(entorno.db,'scalars',falla)
    r=entorno.client.get('/api/tramites',headers={'Origin':settings.frontend_origin})
    assert r.status_code==500 and 'detalle-interno-privado' not in r.text
    assert r.headers['access-control-allow-origin']==settings.frontend_origin


def test_conflicto_commit_hace_rollback(entorno):
    entrar(entorno)
    def falla(): raise IntegrityError('consulta',None,Exception('restricción'))
    entorno.monkeypatch.setattr(entorno.db,'commit',falla)
    r=entorno.client.post('/api/tramites/caso-a/eventos',json={'tipo':'avanzar_paso','version':1,'documento_id':'caso-a-publico','fecha_acreditada':'2026-11-20'})
    assert r.status_code==409 and entorno.db.rollbacks==1


def test_cookie_manipulada_y_vencida(entorno):
    for value in ('operador.9999999999.firma-falsa',f'operador.1.{sesion._firma("operador.1")}'):
        entorno.client.cookies.set(sesion.COOKIE,value)
        assert entorno.client.get('/api/sesion').status_code==401


def test_cors_permite_credentials_y_put_de_publicacion(entorno):
    r=entorno.client.options('/api/tramites/caso-a/publicacion',headers={'Origin':settings.frontend_origin,'Access-Control-Request-Method':'PUT','Access-Control-Request-Headers':'Content-Type,Idempotency-Key'})
    assert r.status_code==200
    assert r.headers['access-control-allow-credentials']=='true'


def test_pdf_ausente_no_cambia_el_tipo_de_respuesta(entorno):
    entrar(entorno)
    assert entorno.client.get('/api/documentos/caso-a-publico/contenido?formato=pdf').status_code==404
    assert entorno.client.get('/api/documentos/caso-a-publico/contenido?pagina=5').status_code==404


@pytest.mark.parametrize('respuesta',[{'respuesta':'Dato inventado [F9].','citas':['F9']},
    {'respuesta':'Se autorizaron 999999 medidores [F1].','citas':['F1']},
    {'respuesta':'Una afirmación sin citas.','citas':[]},
    {'respuesta':'malformado','citas':{}}, 'no-json'])
def test_modelo_no_verificable_se_descarta(entorno,respuesta):
    entrar(entorno)
    async def model(*args,**kwargs): return json.dumps(respuesta) if not isinstance(respuesta,str) else respuesta,'modelo-aislado'
    entorno.monkeypatch.setattr(llm,'completar',model)
    r=entorno.client.post('/api/agente/chat',json={'tramite_id':'caso-a','pregunta':'¿Qué dicen los documentos de los medidores?'})
    assert r.status_code in (200,503),r.text
    if r.status_code==200:
        assert r.json()['estado']=='ok' and r.json()['fuentes'] and r.json()['advertencias']
        assert '999999' not in r.json()['respuesta'] and '[F9]' not in r.json()['respuesta']
    assert not entorno.db.tablas['respuesta_cache']


def test_proveedor_caido_503_y_portal_operativo(entorno):
    entrar(entorno)
    async def falla(*args,**kwargs): raise llm.ModeloNoDisponible('sin conexión')
    entorno.monkeypatch.setattr(llm,'completar',falla)
    r=entorno.client.post('/api/agente/chat',json={'tramite_id':'caso-a','pregunta':'¿Cuál es el estado?'})
    assert r.status_code==503 and r.json()['conversacion_id']
    assert entorno.client.get('/api/tramites/caso-a').status_code==200


def test_ciudadano_503_conserva_cookie_para_reintentar(entorno):
    cid=publicar(entorno); entorno.client.delete('/api/sesion')
    async def falla(*args,**kwargs): raise llm.ModeloNoDisponible('sin conexión')
    entorno.monkeypatch.setattr(llm,'completar',falla)
    data={'caso_id':cid,'pregunta':'¿Cuál es el estado?'}
    r=entorno.client.post('/api/publico/asistente/chat',json=data)
    assert r.status_code==503 and 'yakukhipu_visitante' in entorno.client.cookies
    data['conversacion_id']=r.json()['conversacion_id']
    assert entorno.client.post('/api/publico/asistente/chat',json=data).status_code==503


def test_agente_eps_ajena_y_caso_no_publicado_no_llaman_modelo(entorno):
    entrar(entorno,'empresa-b')
    assert entorno.client.post('/api/agente/chat',json={'tramite_id':'caso-a','pregunta':'¿Cuál es el estado?'}).status_code==404
    assert entorno.client.post('/api/publico/asistente/chat',json={'caso_id':'inexistente','pregunta':'¿Cuál es el estado?'}).status_code==404
    assert not entorno.calls


def test_limite_ciudadano_429(entorno):
    cid=publicar(entorno)
    entorno.monkeypatch.setattr(settings,'limite_publico_por_hora',1)
    data={'caso_id':cid,'pregunta':'¿Cuál es el estado?'}
    assert entorno.client.post('/api/publico/asistente/chat',json=data).status_code==200
    r=entorno.client.post('/api/publico/asistente/chat',json=data)
    assert r.status_code==429 and r.headers['retry-after']


def test_agente_sin_evidencia_no_llama_modelo(entorno):
    entrar(entorno)
    entorno.db.tablas['fragmento'].clear()
    r=entorno.client.post('/api/agente/chat',json={'tramite_id':'caso-a','pregunta':'¿Cómo cocinar arroz?'})
    assert r.status_code==200 and r.json()['estado']=='sin_fuentes' and not entorno.calls
