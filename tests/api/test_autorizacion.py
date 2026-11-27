from datetime import datetime, timezone
from test_api_actores import entorno, entrar
from app.models import Usuario, Tramite
from app.models.seguridad import Asignacion, RolPermiso

def cambiar_rol(e, rol, permisos):
    e.db.get(Usuario, 'operador').rol_id = rol
    for i, permiso in enumerate(permisos):
        row = RolPermiso(rol_id=rol, permiso_id=permiso)
        row.id = rol+str(i)
        e.db.add(row)

def test_analista_solo_asignados_y_agente(entorno):
    e = entorno
    cambiar_rol(e, 'analista_srt', ['expediente.consultar','trazabilidad.consultar','agente.consultar','evaluacion.validar'])
    entrar(e)
    assert e.client.get('/api/tramites').json()['items'] == []
    e.db.add(Asignacion(tramite_id='caso-a',usuario_id='operador',asignado_por='coordinador',
        inicio=datetime.now(timezone.utc),fin=None))
    assert [t['id'] for t in e.client.get('/api/tramites').json()['items']] == ['caso-a']
    assert e.client.get('/api/tramites/caso-a/eventos').status_code == 200
    assert e.client.get('/api/tramites/caso-b').status_code == 404
    assert e.client.get('/api/documentos/caso-b-interno/contenido').status_code == 404
    assert e.client.post('/api/agente/chat',json={'tramite_id':'caso-b','pregunta':'Estado'}).status_code == 404
    assert not e.calls
    assert e.client.get('/api/tramites/caso-a/asignaciones/candidatos').status_code == 403
    chat = e.client.post('/api/agente/chat', json={
        'tramite_id': 'caso-a', 'pregunta': '¿Qué dice el documento de los medidores?'})
    assert chat.status_code == 200, chat.text
    assert chat.json()['fuentes']
    assert e.client.get('/api/recepcion').status_code == 403
    assert e.client.post('/api/tramites/caso-a/eventos',json={'tipo':'resolver','version':1}).status_code == 403

def test_coordinacion_no_valida_tecnicamente(entorno):
    cambiar_rol(entorno, 'coordinacion_dre', ['expediente.consultar','recepcion.gestionar'])
    entrar(entorno)
    assert entorno.client.get('/api/recepcion').status_code == 200
    assert entorno.client.post('/api/tramites/caso-a/eventos',json={'tipo':'validar_expediente','version':1}).status_code == 403

def test_cookie_copiada_se_revoca_al_salir(entorno):
    entrar(entorno)
    token = entorno.client.cookies.get('yakukhipu_sesion')
    assert entorno.client.delete('/api/sesion').status_code == 204
    entorno.client.cookies.set('yakukhipu_sesion', token)
    assert entorno.client.get('/api/sesion').status_code == 401

def test_cambio_credenciales_revoca_sesion(entorno):
    entrar(entorno)
    entorno.db.get(Usuario,'operador').credenciales_version += 1
    assert entorno.client.get('/api/sesion').status_code == 401

def test_procedimiento_fuera_de_portal_no_se_expone(entorno):
    entorno.db.get(Tramite,'caso-a').procedimiento = 'OTRO'
    entrar(entorno)
    assert entorno.client.get('/api/tramites/caso-a').status_code == 404
    assert [t['id'] for t in entorno.client.get('/api/tramites').json()['items']] == ['caso-b']

def test_permiso_retirado_se_aplica_sin_login_nuevo(entorno):
    entrar(entorno)
    entorno.db.tablas['rol_permiso'].clear()
    assert entorno.client.get('/api/tramites/caso-a').status_code == 404

def test_login_demo_retirado(entorno):
    assert entorno.client.post('/api/sesion/demo',json={'usuario_id':'operador'}).status_code == 404

def test_cookie_excesiva_responde_401(entorno):
    entorno.client.cookies.set('yakukhipu_sesion','x'*5000)
    assert entorno.client.get('/api/sesion').status_code == 401

def test_asignacion_y_reasignacion_conservan_historial(entorno):
    e = entorno
    for uid in ('analista-a','analista-b'):
        e.db.add(Usuario(id=uid,nombre_visible=uid,perfil='sunass',rol_id='analista_srt',
            activo=True,credenciales_version=1))
    entrar(e)
    e.db.add(Usuario(id='analista-inactivo', nombre_visible='Inactivo', perfil='sunass',
        rol_id='analista_srt', activo=False, credenciales_version=1))
    candidatos = e.client.get('/api/tramites/caso-a/asignaciones/candidatos')
    assert candidatos.status_code == 200, candidatos.text
    assert candidatos.json() == [
        {'id': 'analista-a', 'nombre': 'analista-a'},
        {'id': 'analista-b', 'nombre': 'analista-b'},
    ]
    def asignar(uid, version):
        return e.client.post('/api/tramites/caso-a/asignaciones',json={
            'usuario_id':uid,'version':version,'motivo':'Distribución de cartera'})
    assert asignar('empresa-a',1).status_code == 422
    primera = asignar('analista-a',1)
    assert primera.status_code == 201, primera.text
    assert asignar('analista-b',1).status_code == 409
    segunda = asignar('analista-b',primera.json()['version'])
    assert segunda.status_code == 201, segunda.text
    rows = list(e.db.tablas['asignacion_tramite'].values())
    assert len(rows) == 2 and rows[0].fin is not None and rows[1].fin is None
