"""Lecturas financieras de los datos autorizados. Sin inferencia ni diagnósticos regulatorios."""
from collections import defaultdict
from datetime import date
from decimal import Decimal
from sqlalchemy import select,text
from ..auth.permisos import exigir
from ..core.errores import NoEncontrado
from ..models import Eps
from ..repositories import tramites as repo

TABLES=('programa_inversion','ejecucion_inversion','fondo_inversion','estado_financiero','meta_gestion')

def total(values):
    available=[Decimal(str(v)) for v in values if v is not None]
    return float(sum(available)) if available else None

def percent(value,base):
    return round(value/base*100,2) if value is not None and base is not None and base>0 else None

def aggregate(programas,ejecuciones,fondos,nombres,corte):
    programas=[r for r in programas if r.get('tipo_periodo')=='vigente' and (r.get('anio') or 0)<=corte.year]
    ejecuciones=[r for r in ejecuciones if r.get('fecha_reporte') and str(r['fecha_reporte'])<=corte.isoformat()]
    fondos=[r for r in fondos if r.get('fecha_reporte') and str(r['fecha_reporte'])<=corte.isoformat()]
    latest={};quarters=defaultdict(list)
    for row in sorted(ejecuciones,key=lambda r:r['anio_trimestre']):
        latest[(row['eps_id'],row['cod_proyecto'])]=row
        quarters[row['anio_trimestre']].append(row)
    valid_projects={(r['eps_id'],r['cod_proyecto']) for r in programas}
    selected=[r for key,r in latest.items() if key in valid_projects]
    programmed=total(r['monto_programado_vigente'] for r in programas)
    executed=total(r['ejecucion_financiera_acumulada'] for r in selected)
    series=[{'x':q,'y':total(r['ejecucion_financiera_trimestre'] for r in rows),
             'proyectos_reportantes':len({(r['eps_id'],r['cod_proyecto']) for r in rows}),'eps_reportantes':len({r['eps_id'] for r in rows})}
            for q,rows in sorted(quarters.items())][-8:]
    growth=None
    if len(series)>=2:
        a,b=series[-2:];ka={(r['eps_id'],r['cod_proyecto']) for r in quarters[a['x']]};kb={(r['eps_id'],r['cod_proyecto']) for r in quarters[b['x']]}
        if ka==kb and a['y'] and b['y'] is not None:growth=round((b['y']/a['y']-1)*100,2)
    months=defaultdict(list)
    for r in fondos:
        if r['anio_mes'].startswith(str(corte.year)):months[r['anio_mes']].append(r)
    fund_series=[]
    for month,rows in sorted(months.items()):
        p=total(r['deposito_programado'] for r in rows);e=total(r['deposito_efectuado'] for r in rows)
        fund_series.append({'x':month,'programado':p,'efectuado':e,'cumplimiento_pct':percent(e,p),'registros':len(rows),'eps_reportantes':len({r['eps_id'] for r in rows})})
    ranking=[]
    for eid,name in nombres.items():
        p=total(r['monto_programado_vigente'] for r in programas if r['eps_id']==eid)
        e=total(r['ejecucion_financiera_acumulada'] for r in selected if r['eps_id']==eid)
        if p is not None:ranking.append({'eps_id':eid,'eps':name,'programado':p,'ejecutado':e,'avance_pct':percent(e,p)})
    ranking.sort(key=lambda r:(r['avance_pct'] is None,r['avance_pct'] or 0,r['eps']))
    return {'total':{'programado':programmed,'ejecutado':executed,'avance_pct':percent(executed,programmed)},
            'ejecucion_trimestral':series,'variacion_trimestral_pct':growth,'fondos':fund_series,'menor_avance':ranking[:6],
            'cobertura':{'proyectos_programados':len(valid_projects),'proyectos_con_ejecucion':len(selected),'eps':len(nombres)},
            'advertencias':['Datos de muestra D3; no son indicadores oficiales ni acreditan beneficios ejecutados.',
              'Montos en soles. Programa vigente hasta el año de corte; ejecución acumulada del último reporte por proyecto.',
              'Las series muestran lo reportado: la ausencia de un reporte no se convierte en cero. Los trimestres con distinta cobertura no se comparan porcentualmente.']}

def scope(db,actor,eps_id=None):
    exigir(actor,'ficha360.consultar')
    tramites=repo.listar_tramites(db,actor)
    eps_ids={t.eps_id for t in tramites}
    if eps_id:
        if eps_id not in eps_ids:raise NoEncontrado('La EPS no existe o no tienes acceso.')
        tramites=[t for t in tramites if t.eps_id==eps_id];eps_ids={eps_id}
    eps=list(db.scalars(select(Eps).where(Eps.id.in_(eps_ids)).order_by(Eps.nombre))) if eps_ids else []
    return tramites,eps

def load(db,table,ids):
    if table not in TABLES:raise ValueError('Tabla no permitida')
    if not ids:return []
    return [dict(r) for r in db.execute(text(f'''SELECT x.*,r.source_hash,r.datos->>'_origen_archivo' AS archivo_actualizacion,f.source_file
        FROM {table} x JOIN registro_fuente r ON r.canonical_id=x.canonical_id
        JOIN fuente f ON f.id=r.fuente_id WHERE r.presente AND x.eps_id=ANY(:ids)'''),{'ids':list(ids)}).mappings()]

def resumen(db,actor,corte,eps_id=None):
    tramites,eps=scope(db,actor,eps_id);names={e.id:e.nombre for e in eps};ids=list(names)
    rows={t:load(db,t,ids) for t in TABLES[:3]}
    result=aggregate(rows['programa_inversion'],rows['ejecucion_inversion'],rows['fondo_inversion'],names,corte)
    result.update(corte=corte,eps_disponibles=[{'id':e.id,'nombre':e.nombre} for e in eps],fuente='PostgreSQL · registros D3 importados con procedencia',simulado=True)
    result['archivos_fuente']=sorted({r['archivo_actualizacion'] or r['source_file'] for values in rows.values() for r in values})
    result['resueltos']=sum(t.fecha_fin is not None and t.fecha_fin.year==corte.year and t.fecha_fin<=corte for t in tramites)
    procedures=db.execute(text('''SELECT p.monto_solicitado FROM procedimiento_fuente p JOIN registro_fuente r ON r.canonical_id=p.canonical_id
        WHERE r.presente AND p.tramite_id=ANY(:ids)'''),{'ids':[t.id for t in tramites if t.estado not in ('concluido','autorizado','no_autorizado')]}).scalars().all() if tramites else []
    result['monto_solicitado_en_evaluacion']=total(procedures)
    months=defaultdict(int)
    for t in tramites:
        if t.fecha_fin and t.fecha_fin.year==corte.year and t.fecha_fin<=corte:months[t.fecha_fin.strftime('%Y-%m')]+=1
    result['resueltos_por_mes']=[{'mes':month,'total':value} for month,value in sorted(months.items())]
    tids=[t.id for t in tramites]
    events=db.execute(text('''SELECT a.titulo,a.actor,a.fecha_acreditada,a.tramite_id,t.titulo AS expediente
        FROM actuacion a JOIN tramite t ON t.id=a.tramite_id WHERE a.tramite_id=ANY(:ids)
        AND a.fecha_acreditada<=:corte ORDER BY a.fecha_acreditada DESC,a.id DESC LIMIT 8'''),{'ids':tids,'corte':corte}).mappings().all() if tids else []
    result['movimientos']=[dict(r) for r in events]
    stages=db.execute(text('''SELECT h.etapa,avg(h.fecha_fin-h.fecha_inicio) AS dias,count(*) AS registros FROM hito h
        JOIN registro_fuente r ON r.canonical_id=h.canonical_id WHERE r.presente AND h.tramite_id=ANY(:ids)
        AND h.fecha_inicio IS NOT NULL AND h.fecha_fin IS NOT NULL AND h.fecha_fin>=h.fecha_inicio AND h.fecha_fin<=:corte
        GROUP BY h.etapa ORDER BY dias DESC'''),{'ids':tids,'corte':corte}).mappings().all() if tids else []
    result['demora_por_etapa']=[{'etapa':r['etapa'],'dias':round(float(r['dias']),1),'registros':r['registros']} for r in stages]
    return result

def ficha_eps(db,actor,eps_id,corte):
    tramites,eps=scope(db,actor,eps_id)
    data={t:load(db,t,[eps_id]) for t in TABLES}
    data['programa_inversion']=[r for r in data['programa_inversion'] if (r.get('anio') or 0)<=corte.year]
    for table in ('ejecucion_inversion','fondo_inversion'):
        data[table]=[r for r in data[table] if r.get('fecha_reporte') and str(r['fecha_reporte'])<=corte.isoformat()]
    for table in ('estado_financiero','meta_gestion'):
        data[table]=[r for r in data[table] if (r.get('anio') or 0)<=corte.year]
    return {'eps':{'id':eps[0].id,'nombre':eps[0].nombre,'region':eps[0].region},'corte':corte,'simulado':eps[0].simulado,
            'tramites':[{'id':t.id,'titulo':t.titulo,'procedimiento':t.procedimiento,'etapa':t.etapa,'estado':t.estado} for t in tramites],
            'datos':data,'nota':'Datos fuente; no implican aprobación, ejecución ni beneficio comprobado.'}
