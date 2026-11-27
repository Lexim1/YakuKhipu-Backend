import json
from datetime import date,datetime,timezone
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from fastapi import Response
from http.cookies import SimpleCookie
from app.main import app
from app.core.db import get_db
from app.core.config import settings
from app.models import Eps,Usuario,Tramite,Documento,Fragmento,Publicacion
from app.api import asistente as router_agente
from app.modules import datos
from app.agent import llm
from soporte_api import Memoria


@pytest.fixture
def entorno(monkeypatch):
    db=Memoria()
    from app.modules import carga_analistas
    def cargas_memoria(db,actor,tramite_id=None):
        from app.auth.permisos import exigir
        exigir(actor,'asignacion.gestionar')
        filas=[]
        for u in db.tablas['usuario'].values():
            if not u.activo or u.rol_id!='analista_srt':continue
            acts=[a for a in db.tablas['asignacion_tramite'].values() if a.usuario_id==u.id]
            abiertos={a.tramite_id for a in acts if a.fin is None and db.tablas['tramite'][a.tramite_id].estado not in ('concluido','autorizado','no_autorizado')}
            filas.append({'id':u.id,'nombre':u.nombre_visible,'carga_activa':len(abiertos),'ultima_asignacion':max((a.inicio for a in acts),default=None),'asignacion_actual':any(a.fin is None and a.tramite_id==tramite_id for a in acts)})
        return carga_analistas.ordenar_cargas(filas)
    monkeypatch.setattr(carga_analistas,'consultar',cargas_memoria)
    from app.modules import calidad
    monkeypatch.setattr(calidad, 'listar', lambda db, tramites: [])
    monkeypatch.setattr(settings,'secret_key','clave-aislada-de-pruebas-http-de-32-caracteres')
    monkeypatch.setattr(settings,'cache_activa',False)
    monkeypatch.setattr(settings,'fecha_demo',date(2026,11,22))
    monkeypatch.setattr(settings,'min_puntaje',0.0)
    monkeypatch.setattr(datos,'proyeccion',lambda db,t:{'documentos':[],'linea_tiempo':[],'comparador':{'solicitado':None,'autorizado':None,'ejecutado':None},'impacto':None,'plazos':None})
    monkeypatch.setattr(datos,'contexto',lambda db,t:{'eps_id':t.eps_id,'programa_inversion':[]})
    # El router ya importó la función: sustituir su frontera de consulta de contexto.
    import app.api.tramites as rutas
    monkeypatch.setattr(rutas,'contexto',lambda db,t:{'eps_id':t.eps_id,'programa_inversion':[]})
    for eid in ('eps-a','eps-b'): db.add(Eps(id=eid,nombre=eid,region='Región',tamano='Pequeña',simulado=False))
    for uid,perfil,eid in [('operador','sunass',None),('empresa-a','eps','eps-a'),('empresa-b','eps','eps-b')]:
        db.add(Usuario(id=uid,nombre_visible=uid,perfil=perfil,eps_id=eid,activo=True,
                       rol_id="jefatura_dre" if perfil=="sunass" else "eps",credenciales_version=1))
    from app.models.seguridad import RolPermiso
    permisos = ["expediente.consultar","trazabilidad.consultar","alerta.consultar","agente.consultar",
        "evaluacion.validar","acto_externo.registrar","requerimiento.registrar","respuesta.verificar",
        "recepcion.gestionar","publicacion.gestionar","asignacion.gestionar","eps.respuesta_informar"]
    for rol in ("jefatura_dre","eps"):
        for i, permiso in enumerate(permisos):
            row = RolPermiso(rol_id=rol,permiso_id=permiso)
            row.id = rol+str(i)
            db.add(row)
    for tid,eid in [('caso-a','eps-a'),('caso-b','eps-b')]:
        db.add(Tramite(id=tid,procedimiento='CPI',eps_id=eid,titulo='Expediente de prueba aislada',estado='en_evaluacion',paso_actual=7,etapa='Firma',responsable='SRT',
                       version=1,simulado=False,publicable=False,huella_fuentes='',fecha_inicio=None,fecha_fin=None,presentacion=None,ficha_eps=None,ficha_agente=None))
        for suffix,vis,text in [('interno','interna','Nota interna reservada: evaluación del caso.'),('partes','partes','Oficio solicita sustento sobre medidores a la empresa.'),('publico','publica','Resolución autoriza 120 medidores. No acredita instalación.')]:
            did=f'{tid}-{suffix}'
            db.add(Documento(id=did,tramite_id=tid,titulo=suffix,visibilidad=vis,estado_validacion='validado',simulado=False,paginas=1,referencia=did,archivo=None))
            db.add(Fragmento(id=did+'-p1',documento_id=did,tramite_id=tid,pagina_pdf=1,texto=text,requiere_ocr=False,pagina_impresa=None))
    app.dependency_overrides[get_db]=lambda:db
    router_agente._consultas.clear()
    calls=[]
    async def modelo(messages,max_tokens=None):
        calls.append(messages)
        return json.dumps({'respuesta':'La resolución no acredita instalación [F1].','citas':['F1'],'advertencias':[]}), 'modelo-aislado'
    monkeypatch.setattr(llm,'completar',modelo)
    with TestClient(app,raise_server_exceptions=False) as client:
        yield SimpleNamespace(db=db,client=client,calls=calls,monkeypatch=monkeypatch)
    app.dependency_overrides.clear()


def entrar(e,uid='operador'):
    from app.auth import sesion
    respuesta=Response()
    sesion.abrir(respuesta,e.db.get(Usuario,uid),e.db)
    cookie=SimpleCookie(); cookie.load(respuesta.headers['set-cookie'])
    e.client.cookies.set(sesion.COOKIE,cookie[sesion.COOKIE].value)
    r=e.client.get('/api/sesion')
    assert r.status_code==200,r.text
    return r


def publicar(e):
    t=e.db.get(Tramite,'caso-a'); t.estado='autorizado'; t.paso_actual=8; t.fecha_fin=date(2026,11,20)
    entrar(e)
    r=e.client.put('/api/tramites/caso-a/publicacion',json={'version':t.version,'titulo':'Decisión publicada','localidad':'Localidad',
        'resumen_ciudadano':'Se autorizó la adquisición. La instalación no está acreditada.','documentos_publicos':['caso-a-publico']})
    assert r.status_code==200,r.text
    return r.json()['id']


@pytest.mark.parametrize('method,path',[('get','/api/tramites'),('get','/api/eps/tramites'),('get','/api/recepcion'),('get','/api/alertas'),
    ('get','/api/tramites/caso-a/eventos'),('get','/api/tramites/caso-a/contexto'),('post','/api/agente/chat')])
def test_rutas_institucionales_exigen_sesion(entorno,method,path):
    r=getattr(entorno.client,method)(path,json={'pregunta':'¿Cuál es el estado?','tramite_id':'caso-a'}) if method=='post' else entorno.client.get(path)
    assert r.status_code==401 and r.json()['codigo']=='sin_sesion'


@pytest.mark.parametrize('uid,path,status',[('operador','/api/eps/tramites',403),('empresa-a','/api/tramites',403),
    ('empresa-a','/api/tramites/caso-b/acciones',404),('empresa-a','/api/documentos/caso-a-interno/contenido',404),
    ('empresa-a','/api/documentos/caso-b-partes/contenido',404)])
def test_roles_y_aislamiento_eps(entorno,uid,path,status):
    entrar(entorno,uid)
    assert entorno.client.get(path).status_code==status


@pytest.mark.parametrize('path',['/api/tramites','/api/tramites/caso-a','/api/tramites/caso-a/flujo','/api/tramites/caso-a/eventos',
    '/api/tramites/caso-a/acciones','/api/tramites/caso-a/contexto','/api/tramites/caso-a/plazos','/api/tramites/caso-a/documentos','/api/recepcion','/api/alertas'])
def test_lecturas_sunass_contrato_http(entorno,path):
    entrar(entorno)
    r=entorno.client.get(path)
    assert r.status_code==200,r.text


def test_recorrido_sunass_eps_resolucion_publicacion_ciudadania(entorno):
    e=entorno; entrar(e)
    body={'tipo':'requerir_informacion','version':1,'documento_id':'caso-a-partes','fecha_acreditada':'2026-11-20','plazo_dias':3,'requisitos':['Sustento técnico']}
    r=e.client.post('/api/tramites/caso-a/eventos',json=body,headers={'Idempotency-Key':'solicitud-1'})
    assert r.status_code==200,r.text
    version=r.json()['version']
    assert r.json()['estado']=='requiere_respuesta'
    assert e.client.post('/api/tramites/caso-a/eventos',json=body,headers={'Idempotency-Key':'solicitud-1'}).status_code==200
    assert e.client.post('/api/tramites/caso-a/eventos',json={**body,'detalle':'Otra petición'},headers={'Idempotency-Key':'solicitud-1'}).status_code==409
    entrar(e,'empresa-a')
    assert e.client.get('/api/eps/tramites').json()['total']==1
    ficha=e.client.get('/api/eps/tramites/caso-a').json()
    assert ficha['siguiente_accion']['fecha_limite'] is None
    r=e.client.post('/api/eps/tramites/caso-a/respuestas',json={'version':version,'documento':'caso-a-publico','fecha_presentacion':'2026-11-21','canal':'Mesa de Partes'},headers={'Idempotency-Key':'respuesta-1'})
    assert r.status_code==200,r.text
    assert r.json()['respuesta_informada']['verificada'] is False
    entrar(e)
    assert [a['tipo'] for a in e.client.get('/api/tramites/caso-a/acciones').json()['items']]==['verificar_respuesta']
    t=e.db.get(Tramite,'caso-a')
    r=e.client.post('/api/tramites/caso-a/eventos',json={'tipo':'verificar_respuesta','version':t.version})
    assert r.status_code==200,r.text
    for tipo in ('avanzar_paso','resolver'):
        r=e.client.post('/api/tramites/caso-a/eventos',json={'tipo':tipo,'version':t.version,'documento_id':'caso-a-publico','fecha_acreditada':'2026-11-22',**({'resultado':'autorizado'} if tipo=='resolver' else {})})
        assert r.status_code==200,r.text
    cid=publicar(e)
    e.client.delete('/api/sesion')
    assert e.client.get('/api/publico/decisiones').json()['total']==1
    assert e.client.get('/api/publico/decisiones/'+cid).status_code==200
    assert e.client.get('/api/publico/documentos/caso-a-interno/contenido').status_code==404
    assert e.client.get('/api/publico/documentos/caso-a-publico/contenido').status_code==200


@pytest.mark.parametrize('uid',['operador','empresa-a'])
def test_agente_institucional_fuentes_filtradas_y_memoria(entorno,uid):
    entrar(entorno,uid)
    r=entorno.client.post('/api/agente/chat',json={'tramite_id':'caso-a','pregunta':'¿Qué dice el documento de los medidores?'})
    assert r.status_code==200,r.text
    assert r.json()['estado']=='ok' and r.json()['fuentes']
    if uid=='empresa-a': assert 'Nota interna reservada' not in json.dumps(entorno.calls)
    conv=r.json()['conversacion_id']
    r=entorno.client.post('/api/agente/chat',json={'tramite_id':'caso-a','pregunta':'¿Y la instalación?','conversacion_id':conv})
    assert r.status_code==200,r.text
    assert any(m['role']=='assistant' for m in entorno.calls[-1])


def test_agente_ciudadano_sin_sesion_y_aislamiento_visitantes(entorno):
    e=entorno; cid=publicar(e); e.client.delete('/api/sesion')
    r=e.client.post('/api/publico/asistente/chat',json={'caso_id':cid,'pregunta':'¿Qué dice el documento sobre medidores?'})
    assert r.status_code==200,r.text
    assert all(f['enlace'].startswith('/api/publico/') for f in r.json()['fuentes'])
    assert 'Nota interna reservada' not in json.dumps(e.calls)
    assert 'Oficio solicita' not in json.dumps(e.calls)
    conv=r.json()['conversacion_id']
    e.client.cookies.clear()
    r=e.client.post('/api/publico/asistente/chat',json={'caso_id':cid,'pregunta':'¿Y el plazo?','conversacion_id':conv})
    assert r.status_code==404,r.text


def test_recepcion_incorporacion_y_documentos(entorno):
    e=entorno; entrar(e)
    datos={'titulo':'Oficio recibido','referencia':'Oficio 123','fecha_documento':'2026-11-20','eps_id':'eps-a','texto':'Sustento recibido en Mesa de Partes.'}
    r=e.client.post('/api/recepcion',json=datos,headers={'Idempotency-Key':'recepcion-1'})
    assert r.status_code==201,r.text
    did=r.json()['id']
    assert e.client.post('/api/recepcion',json=datos,headers={'Idempotency-Key':'recepcion-1'}).json()['id']==did
    r=e.client.post('/api/recepcion/incorporaciones',json={'documento_id':did,'tramite_id':'caso-a','tipo_actuacion':'respuesta','asignado_a':None,'version':1})
    assert r.status_code==204,r.text
    assert e.client.get('/api/documentos/'+did+'/contenido').json()['paginas'][0]['texto']==datos['texto']


@pytest.mark.parametrize('payload',[{'pregunta':'   ','tramite_id':'caso-a'},{'pregunta':'Estado','tramite_id':'caso-a','perfil':'sunass'}])
def test_agente_rechaza_entrada_vacia_o_perfil_inyectado(entorno,payload):
    entrar(entorno,'empresa-a')
    r=entorno.client.post('/api/agente/chat',json=payload)
    assert r.status_code==422 and not entorno.calls


def test_publicacion_retirada_invalida_consulta_y_agente(entorno):
    cid=publicar(entorno)
    assert entorno.client.delete('/api/tramites/caso-a/publicacion').status_code==204
    assert entorno.client.get('/api/publico/decisiones/'+cid).status_code==404
    assert entorno.client.post('/api/publico/asistente/chat',json={'caso_id':cid,'pregunta':'¿Qué se autorizó?'}).status_code==404


@pytest.mark.parametrize('method,path,payload',[
    ('post','/api/recepcion',{'titulo':'Documento recibido','referencia':'Oficio 123','fecha_documento':'2026-11-20','eps_id':'eps-a','texto':'Texto'}),
    ('post','/api/recepcion/incorporaciones',{'documento_id':'documento','tramite_id':'caso-a','tipo_actuacion':'respuesta','asignado_a':'SRT','version':1}),
    ('post','/api/tramites/caso-a/eventos',{'tipo':'verificar_respuesta','version':1}),
    ('put','/api/tramites/caso-a/publicacion',{'version':1,'titulo':'Decisión publicada','localidad':'Localidad','resumen_ciudadano':'Resumen para ciudadanía.','documentos_publicos':['caso-a-publico']}),
    ('delete','/api/tramites/caso-a/publicacion',None),
])
def test_eps_no_puede_operar_como_sunass(entorno,method,path,payload):
    entrar(entorno,'empresa-a')
    args={'headers':{'Idempotency-Key':'clave-aislada'}}
    if payload is not None: args['json']=payload
    assert entorno.client.request(method,path,**args).status_code==403


def test_conversacion_institucional_no_se_comparte_entre_perfiles(entorno):
    entrar(entorno)
    r=entorno.client.post('/api/agente/chat',json={'tramite_id':'caso-a','pregunta':'¿Qué dice el documento sobre medidores?'})
    assert r.status_code==200,r.text
    entrar(entorno,'empresa-a')
    r=entorno.client.post('/api/agente/chat',json={'tramite_id':'caso-a','pregunta':'¿Y el plazo?','conversacion_id':r.json()['conversacion_id']})
    assert r.status_code==404,r.text
