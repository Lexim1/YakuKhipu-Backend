from datetime import datetime,timezone
from app.agent.graph import _problemas
from app.modules.carga_analistas import ordenar_cargas
from app.modules.busqueda_agente import palabras
from app.agent import retrieval


def test_flexiones_solicitud_y_autorizacion():
    docs=[{'texto':'La EPS solicita S/ 424,142.40 por colapso del colector.','titulo':'Carta de solicitud'},
          {'texto':'La resolución autoriza S/ 254,485.44.','titulo':'Resolución del Consejo Directivo'},
          {'texto':'Anexo financiero.','titulo':'Anexo 1'}]
    encontrados=retrieval.buscar('¿Cuánto solicitó la EPS y cuánto autorizó la resolución?',docs,3)
    assert {x['titulo'] for _,x in encontrados[:2]}=={'Carta de solicitud','Resolución del Consejo Directivo'}

def row(id,carga,actual=False,fecha=None):
    return {'id':id,'nombre':id,'carga_activa':carga,'asignacion_actual':actual,'ultima_asignacion':fecha}

def test_menor_carga_y_empate_por_antiguedad_sin_reasignar_al_actual():
    newer=datetime(2026,11,20,tzinfo=timezone.utc)
    older=datetime(2026,11,1,tzinfo=timezone.utc)
    items=ordenar_cargas([row('muchos',8),row('nuevo',2,fecha=newer),row('antiguo',2,fecha=older),row('sin_historia',2)])
    assert [i['id'] for i in items]==['sin_historia','antiguo','nuevo','muchos']
    assert all(i['recomendado'] for i in items[:3])
    assert not items[-1]['recomendado']
    items=ordenar_cargas([row('actual',1,True),row('mas_carga',4)])
    assert items[0]['menor_carga'] and not any(i['recomendado'] for i in items)
    assert ordenar_cargas([])==[]

def test_busqueda_no_usa_palabras_de_intencion_ni_operadores_sql():
    assert palabras('¿Dónde está el expediente CPI-2026-0001?')==['cpi','2026','0001']
    assert palabras('Busca documentos')==[]
    assert all(w.isalnum() for w in palabras("oficio '); DROP TABLE usuario --"))

def test_cifras_se_validan_solo_con_el_extracto_enviado_al_modelo():
    state={'ficha':{},'plazos':[],'fragmentos':[{'texto':'Se pidieron 120 medidores. Presupuesto antiguo 999 soles.','extracto':'Se pidieron 120 medidores.'}]}
    assert _problemas(state,{'respuesta':'El presupuesto es 999 soles [F1].','citas':['F1']})
    assert not _problemas(state,{'respuesta':'Se pidieron 120 medidores [F1].','citas':['F1']})
    state['fragmentos'][0].update(titulo='Oficio 76321',pagina_pdf=2)
    assert not _problemas(state,{'respuesta':'El oficio 76321, página 2, menciona 120 medidores [F1].','citas':['F1']})

def test_una_pagina_pertinente_no_desaparece_por_tamano_del_corpus():
    pages=[{'texto':'Se solicitaron 120 medidores para el proyecto.','titulo':'Oficio'}]
    found=retrieval.buscar('medidores',pages)
    assert found and found[0][0] < 1.5
    assert found[0][0] >= retrieval.umbral(1,1.5)
    assert retrieval.buscar('telescopios orbitales',pages)==[]
    assert retrieval.umbral(1000,1.5)==1.5
