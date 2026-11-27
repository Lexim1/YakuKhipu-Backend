"""Recomendación explicable con asignaciones actuales; no utiliza modelos de IA."""
from datetime import datetime, timezone

from sqlalchemy import text

from ..auth.permisos import exigir


def ordenar_cargas(filas):
    items = [dict(row) for row in filas]
    if not items:
        return []
    minimo = min(row['carga_activa'] for row in items)
    for row in items:
        row['menor_carga'] = row['carga_activa'] == minimo
        row['recomendado'] = not row['asignacion_actual'] and row['menor_carga']
    items.sort(key=lambda row: (row['carga_activa'],
        row['ultima_asignacion'] or datetime.min.replace(tzinfo=timezone.utc), row['nombre'].casefold(), row['id']))
    return items


def consultar(db, actor, tramite_id=None):
    exigir(actor, 'asignacion.gestionar')
    filas = db.execute(text("""
        SELECT u.id,u.nombre_visible AS nombre,
          count(DISTINCT a.tramite_id) FILTER (
            WHERE a.fin IS NULL AND t.estado NOT IN ('concluido','autorizado','no_autorizado')
              AND t.procedimiento IN ('CPI','UFI','RP') AND EXISTS (
                SELECT 1 FROM registro_fuente r WHERE r.canonical_id=t.id AND r.presente)
          )::int AS carga_activa,
          coalesce(bool_or(a.fin IS NULL AND a.tramite_id=:tramite),false) AS asignacion_actual,
          max(a.inicio) AS ultima_asignacion
        FROM usuario u LEFT JOIN asignacion_tramite a ON a.usuario_id=u.id
        LEFT JOIN tramite t ON t.id=a.tramite_id
        WHERE u.activo AND u.perfil='sunass' AND u.rol_id='analista_srt'
        GROUP BY u.id,u.nombre_visible
    """), {'tramite': tramite_id}).mappings()
    return ordenar_cargas(filas)
