from test_api_actores import entorno,entrar
from app.models import Tramite

def test_archivo_con_oficio_no_autoriza_ni_completa_etapas_futuras(entorno):
    e=entorno;entrar(e);t=e.db.get(Tramite,'caso-a')
    t.paso_actual=4;t.estado='requiere_subsanacion'
    body={'tipo':'cerrar_expediente','version':1,'documento_id':'caso-a-partes','fecha_acreditada':'2026-11-20','detalle':'Oficio acredita cierre por no subsanar'}
    assert e.client.post('/api/tramites/caso-a/eventos',json={**body,'detalle':None}).status_code==422
    assert e.client.post('/api/tramites/caso-a/eventos',json={**body,'documento_id':'caso-a-interno'}).status_code==422
    r=e.client.post('/api/tramites/caso-a/eventos',json=body)
    assert r.status_code==200,r.text
    assert r.json()['estado']=='concluido' and t.paso_actual==4
    pasos=r.json()['flujo']['pasos']
    assert [p['estado'] for p in pasos[:4]]==['hecho']*4
    assert all(p['estado']!='hecho' and p['nota']=='No realizado: expediente archivado' for p in pasos[4:])
    entrar(e,'empresa-a');f=e.client.get('/api/eps/tramites/caso-a').json()
    assert f['estado_texto']=='Archivado' and f['siguiente_accion'] is None
    assert f['seguimiento'][-1]['titulo']=='Archivo registrado: caso-a-partes'

def test_eps_no_puede_archivar_el_expediente(entorno):
    e=entorno;entrar(e,'empresa-a')
    assert e.client.post('/api/tramites/caso-a/eventos',json={'tipo':'cerrar_expediente','version':1,'documento_id':'caso-a-partes','fecha_acreditada':'2026-11-20','detalle':'Intento EPS'}).status_code==403
