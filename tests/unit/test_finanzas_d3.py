from datetime import date
from app.modules.finanzas import aggregate,total
from scripts.importar_d3 import merge_rows

def test_actualizacion_reemplaza_clave_y_conserva_duplicados_para_cuarentena():
    base=[{'id':'a','v':'viejo'},{'id':'b','v':'1'},{'id':'b','v':'2'}]
    patch=[{'id':'a','v':'actual'},{'id':'c','v':'nuevo'}]
    result=merge_rows(base,patch,('id',))
    assert [r['v'] for r in result if r['id']=='a']==['actual']
    assert len([r for r in result if r['id']=='b'])==2
    assert len(result)==4

def test_sumas_desconocidas_no_se_vuelven_cero():
    assert total([None,None]) is None
    assert total([0,None])==0

def test_ejecucion_acumulada_no_se_suma_varias_veces_y_corte_excluye_futuros():
    programas=[{'eps_id':'a','cod_proyecto':'p','tipo_periodo':'vigente','anio':2026,'monto_programado_vigente':100}]
    ejecuciones=[{'eps_id':'a','cod_proyecto':'p','anio_trimestre':'2026-T1','fecha_reporte':'2026-04-10','ejecucion_financiera_trimestre':20,'ejecucion_financiera_acumulada':20},
                 {'eps_id':'a','cod_proyecto':'p','anio_trimestre':'2026-T2','fecha_reporte':'2026-07-10','ejecucion_financiera_trimestre':30,'ejecucion_financiera_acumulada':50}]
    d=aggregate(programas,ejecuciones,[],{'a':'EPS A'},date(2026,11,20))
    assert d['total']=={'programado':100,'ejecutado':50,'avance_pct':50}
    assert d['variacion_trimestral_pct']==50
    first=aggregate(programas,ejecuciones,[],{'a':'EPS A'},date(2026,5,1))
    assert first['total']['ejecutado']==20

def test_cobertura_distinta_no_se_presenta_como_caida_comparable():
    rows=[{'eps_id':'a','cod_proyecto':p,'anio_trimestre':q,'fecha_reporte':'2026-10-01','ejecucion_financiera_trimestre':10,'ejecucion_financiera_acumulada':10} for p,q in [('p','2026-T2'),('q','2026-T2'),('p','2026-T3')]]
    result=aggregate([],rows,[],{'a':'EPS A'},date(2026,11,20))
    assert result['variacion_trimestral_pct'] is None
    assert result['ejecucion_trimestral'][-1]['proyectos_reportantes']==1

def test_no_hay_ranking_ni_division_si_no_hay_datos():
    result=aggregate([],[],[],{},date(2026,11,20))
    assert result['total']['avance_pct'] is None
    assert result['menor_avance']==[]
