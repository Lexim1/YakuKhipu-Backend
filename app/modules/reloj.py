"""Reloj sobre días de calendario acreditados; no infiere feriados."""
from datetime import timedelta
from sqlalchemy import text
from ..models import Documento


def contar(inicio, fin, dias, calendario, suspensiones=()):
    usados=0
    limite=None
    d=inicio
    for _ in range(3660):
        if d>=fin and limite is not None: return usados,limite
        d+=timedelta(days=1)
        if d not in calendario: raise ValueError(f'Falta calendario validado para {d}.')
        computa=calendario[d] and not any(a<=d<=b for a,b in suspensiones)
        if computa and d<=fin: usados+=1
        if computa: dias-=1
        if dias==0 and limite is None: limite=d
    raise ValueError('Calendario insuficiente o plazo sin horizonte verificable.')


def calcular(db, tramite, hoy, etapa=None):
    pending={'situacion':'pendiente_de_validacion','dias_usados':None,'dias_totales':None,
             'etapa':etapa,'fecha_limite':None,'regla':None,'fuente':None,
             'validacion':'pendiente_de_validacion','motivo':'Faltan regla, notificación o calendario validados.'}
    rows=db.execute(text('''SELECT * FROM plazo WHERE tramite_id=:id AND tipo='normativo'
        AND etapa IS NOT DISTINCT FROM :etapa'''),{'id':tramite.id,'etapa':etapa}).mappings().all()
    if len(rows)!=1: return pending
    p=rows[0]
    if not p['validado'] or not p['fecha_inicio'] or not p['dias']: return {**pending,'motivo':p['motivo'] or pending['motivo']}
    if p['fecha_inicio']>(tramite.fecha_fin or hoy):
        return {**pending,'motivo':'El inicio acreditado es posterior a la fecha de evaluación.'}
    susp=db.execute(text('SELECT * FROM suspension WHERE plazo_id=:id'),{'id':p['id']}).mappings().all()
    extensions=db.execute(text('SELECT * FROM prorroga WHERE plazo_id=:id'),{'id':p['id']}).mappings().all()
    if any(not x['validada'] for x in [*susp,*extensions]):
        return {**pending,'motivo':'Hay suspensiones o prórrogas pendientes de validación.'}
    for row in [p,*susp,*extensions]:
        if row.get('documento_id'):
            doc=db.get(Documento,row['documento_id'])
            if not doc or doc.tramite_id!=tramite.id:
                return {**pending,'motivo':'Una evidencia del plazo no pertenece al expediente.'}
    calendar=dict(db.execute(text('SELECT fecha,laborable FROM calendario_dia WHERE validado AND fecha>:inicio ORDER BY fecha'),{'inicio':p['fecha_inicio']}).all())
    dias=p['dias']+sum(x['dias'] for x in extensions)
    try: used,deadline=contar(p['fecha_inicio'],tramite.fecha_fin or hoy,dias,calendar,[(x['inicio'],x['fin']) for x in susp])
    except ValueError as exc: return {**pending,'motivo':str(exc)}
    situation='concluido' if tramite.fecha_fin else 'vencido' if used>dias else 'por_vencer' if used>=dias*.75 else 'en_plazo'
    return {**pending,'situacion':situation,'dias_usados':used,'dias_totales':dias,'fecha_limite':deadline.isoformat(),
            'regla':p['regla'],'fuente':p['fuente_id'],'validacion':'validado','motivo':None}
