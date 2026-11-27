from fastapi import APIRouter,Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from ..auth.sesion import actor_sunass
from ..auth.permisos import exigir
from ..core.config import settings
from ..core.db import get_db
from ..repositories import tramites as repo
from ..schemas.comun import Actor

router=APIRouter(prefix='/api/seguimiento',tags=['Seguimiento'])

@router.get('/actuaciones')
def actuaciones(actor:Actor=Depends(actor_sunass),db:Session=Depends(get_db)):
    exigir(actor,'trazabilidad.consultar')
    tids=[t.id for t in repo.listar_tramites(db,actor)]
    rows=db.execute(text('''SELECT a.id,a.tramite_id,a.tipo,a.titulo,a.detalle,a.actor,a.fecha_acreditada,a.fuente,a.documento_id,
        a.verificada,t.titulo AS expediente FROM actuacion a JOIN tramite t ON t.id=a.tramite_id
        WHERE a.tramite_id=ANY(:ids) ORDER BY a.fecha_acreditada DESC NULLS LAST,a.id DESC LIMIT 200'''),{'ids':tids}).mappings() if tids else []
    items=[dict(r) for r in rows]
    return {'items':items,'limite':200,'nota':'Actuaciones registradas. Las importadas de D3 son de muestra, pendientes de verificación; no son actos emitidos por el portal.'}

@router.get('/encargos')
def encargos(actor:Actor=Depends(actor_sunass),db:Session=Depends(get_db)):
    exigir(actor,'encargo.consultar')
    tids=[t.id for t in repo.listar_tramites(db,actor)]
    rows=db.execute(text('''SELECT e.id::text AS id,e.tramite_id,e.titulo,e.responsable_nombre AS actor,e.fecha_acreditada,
       e.documento_id AS fuente,e.fecha_limite,e.estado,e.version
       FROM encargo e WHERE e.tramite_id=ANY(:ids) ORDER BY e.fecha_limite NULLS LAST,e.id LIMIT 200'''),{'ids':tids}).mappings() if tids else []
    return {'items':[dict(r) for r in rows],'nota':'Encargos documentados en la base del portal. No se infieren obligaciones ni vencimientos de texto libre del dataset.'}

@router.get('/configuracion')
def configuracion(actor:Actor=Depends(actor_sunass),db:Session=Depends(get_db)):
    exigir(actor,'configuracion.consultar')
    reglas=db.execute(text('SELECT id,procedimiento,etapa,dias,calendario,fuente,validada,motivo_pendiente FROM regla_plazo ORDER BY procedimiento,id')).mappings()
    roles=db.execute(text('SELECT rol_id,array_agg(permiso_id ORDER BY permiso_id) AS permisos FROM seguridad.rol_permiso GROUP BY rol_id ORDER BY rol_id')).mappings()
    return {'reglas':[dict(r) for r in reglas],'roles':[dict(r) for r in roles],'calendario_validado':db.execute(text('SELECT count(*) FROM calendario_dia WHERE validado')).scalar(),
       'ia_habilitada':settings.llm_enabled,'corte':settings.hoy(),'nota':'Consulta de la configuración efectiva. No se editan reglas legales desde esta pantalla.'}
