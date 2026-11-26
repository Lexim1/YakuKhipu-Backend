"""Proyecciones consultadas de PostgreSQL, sin leer CSV ni semillas en requests."""
from sqlalchemy import text


def contexto(db, tramite):
    tables = ('programa_inversion','ejecucion_inversion','fondo_inversion','estado_financiero','meta_gestion')
    result = {}
    for table in tables:
        rows=db.execute(text(f'''SELECT x.*, r.source_hash, f.source_file, f.source_type
            FROM {table} x JOIN registro_fuente r ON r.canonical_id=x.canonical_id
            JOIN fuente f ON f.id=r.fuente_id WHERE x.eps_id=:eps AND r.presente'''),{'eps':tramite.eps_id}).mappings().all()
        result[table]=[dict(r) for r in rows]
    result['nota']='Contexto por EPS; no demuestra causalidad ni ejecución de una decisión específica.'
    return result


def proyeccion(db, tramite):
    provenance = db.execute(text('''SELECT r.source_record_id, f.source_type, f.source_file, r.source_hash
        FROM registro_fuente r JOIN fuente f ON f.id=r.fuente_id WHERE r.canonical_id=:id'''), {'id':tramite.id}).mappings().first()
    hitos = db.execute(text('SELECT h.* FROM hito h JOIN registro_fuente r ON r.canonical_id=h.canonical_id WHERE h.tramite_id=:id AND r.presente ORDER BY nro_hito'), {'id':tramite.id}).mappings().all()
    documentos = db.execute(text('SELECT d.id,d.titulo,d.estado_validacion FROM documento d JOIN registro_fuente r ON r.canonical_id=d.id WHERE d.tramite_id=:id AND r.presente ORDER BY d.id'), {'id':tramite.id}).mappings().all()
    ds = db.execute(text('SELECT e.* FROM procedimiento_fuente e JOIN registro_fuente r ON r.canonical_id=e.canonical_id WHERE e.tramite_id=:id AND r.presente'), {'id':tramite.id}).mappings().first()
    proyectos = db.execute(text('''SELECT p.* FROM programa_inversion p
        JOIN procedimiento_fuente e ON e.eps_id=p.eps_id JOIN registro_fuente r ON r.canonical_id=p.canonical_id
        WHERE e.tramite_id=:id AND r.presente AND (p.id_expediente_modificacion=e.id_expediente OR p.cod_proyecto=e.cod_proyecto)'''), {'id':tramite.id}).mappings().all()
    return {'tema':tramite.titulo, 'resumen': {'procedencia':dict(provenance) if provenance else None},
        'linea_tiempo':[{'id':h['canonical_id'], 'fecha_texto':str(h['fecha_fin'] or h['fecha_inicio'] or 'Fecha por validar'),
                       'titulo':h['hito'],'detalle':h['descripcion'],'fuente':h['canonical_id'],
                       'chip':{'texto':'Dataset de muestra','tono':'aviso'},'validar':False} for h in hitos],
        'comparador':{'solicitado':ds['monto_solicitado'] if ds else None,'autorizado':ds['monto_aprobado'] if ds else None,
                      'ejecutado':None,'fuente':ds['canonical_id'] if ds else None},
        'impacto':{'proyectos':[dict(p) for p in proyectos], 'beneficio_comprobado':None,
                   'nota':'Población potencial por proyecto. No sumar sin controlar solapamientos.'},
        'plazos':{'datos_fuente': {'fecha_limite':ds['fecha_limite'],'dias_suspension_dh':ds['dias_suspension_dh']} if ds else None,
                   'validacion':'pendiente_de_validacion'},
        'documentos':[dict(d) for d in documentos]}
