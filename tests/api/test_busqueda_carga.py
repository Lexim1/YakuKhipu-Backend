from test_api_actores import entorno,entrar
from app.modules import busqueda_agente

def test_busqueda_usa_actor_de_sesion_y_no_crea_conversacion(entorno):
    e=entorno
    assert e.client.get('/api/agente/buscar',params={'q':'oficio'}).status_code==401
    called=[]
    def query(db,actor,q,limite):
        called.append((actor.perfil,actor.eps_id,q,limite))
        return {'items':[],'sin_inferencia':True,'limite':limite,'parcial':False}
    e.monkeypatch.setattr(busqueda_agente,'buscar',query)
    entrar(e,'empresa-a')
    r=e.client.get('/api/agente/buscar',params={'q':'Oficio 123','limite':4})
    assert r.status_code==200 and called==[('eps','eps-a','Oficio 123',4)]
    assert e.client.get('/api/agente/buscar',params={'q':'Oficio','limite':21}).status_code==422
    assert not e.calls and not e.db.tablas['conversacion']

def test_carga_no_se_expone_a_eps_o_analista(entorno):
    from test_autorizacion import cambiar_rol
    e=entorno
    assert e.client.get('/api/asignaciones/carga').status_code==401
    entrar(e,'empresa-a')
    assert e.client.get('/api/asignaciones/carga').status_code==403
    cambiar_rol(e,'analista_srt',['expediente.consultar','agente.consultar'])
    entrar(e)
    assert e.client.get('/api/asignaciones/carga').status_code==403
