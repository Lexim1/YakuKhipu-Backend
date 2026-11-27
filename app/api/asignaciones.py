"""Asignación y reasignación con historia; nunca reemplaza una asignación cerrada."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..auth.sesion import actor_sunass
from ..auth.permisos import exigir
from ..core.db import get_db
from ..core.errores import Conflicto
from ..models import Usuario
from ..repositories import tramites as repo
from ..schemas.comun import Actor
from ..modules.tramites import _guardar, _nueva, cambiar_asignacion

router = APIRouter(prefix='/api/tramites', tags=['Asignaciones'])

class NuevaAsignacion(BaseModel):
    model_config = ConfigDict(extra='forbid')
    usuario_id: str = Field(min_length=1,max_length=80)
    version: int = Field(ge=1)
    motivo: str = Field(min_length=3,max_length=1000)

class CandidatoAsignacion(BaseModel):
    id: str
    nombre: str


@router.get('/{tramite_id}/asignaciones/candidatos', response_model=list[CandidatoAsignacion])
def candidatos(tramite_id: str, actor: Actor = Depends(actor_sunass),
               db: Session = Depends(get_db)) -> list[CandidatoAsignacion]:
    exigir(actor, 'asignacion.gestionar')
    repo.obtener_tramite(db, actor, tramite_id)
    consulta = select(Usuario).where(
        Usuario.rol_id == 'analista_srt', Usuario.activo.is_(True),
    ).order_by(Usuario.nombre_visible, Usuario.id)
    return [CandidatoAsignacion(id=u.id, nombre=u.nombre_visible) for u in db.scalars(consulta)]


@router.post('/{tramite_id}/asignaciones', status_code=201)
def asignar(tramite_id: str, datos: NuevaAsignacion, actor: Actor = Depends(actor_sunass), db: Session = Depends(get_db)) -> dict:
    exigir(actor, 'asignacion.gestionar')
    t = repo.obtener_tramite(db, actor, tramite_id, bloquear=True)
    if t.version != datos.version:
        raise Conflicto('El expediente cambió. Actualiza antes de asignar.')
    if not cambiar_asignacion(db, actor, t, datos.usuario_id, datos.motivo):
        raise Conflicto('El expediente ya está asignado a esa persona.')
    _guardar(db,t,_nueva(t,actor,'asignar','Asignación de expediente',{'detalle':datos.motivo}))
    return {'tramite_id':t.id,'usuario_id':datos.usuario_id,'version':t.version}
