"""Asignación y reasignación con historia; nunca reemplaza una asignación cerrada."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.orm import Session
from ..auth.sesion import actor_sunass
from ..auth.permisos import exigir
from ..core.db import get_db
from ..core.errores import Conflicto
from ..repositories import tramites as repo
from ..schemas.comun import Actor
from ..modules.tramites import _guardar, _nueva, cambiar_asignacion
from ..modules import carga_analistas
from datetime import datetime

router = APIRouter(tags=['Asignaciones'])

class NuevaAsignacion(BaseModel):
    model_config = ConfigDict(extra='forbid')
    usuario_id: str = Field(min_length=1,max_length=80)
    version: int = Field(ge=1)
    motivo: str = Field(min_length=3,max_length=1000)

class CandidatoAsignacion(BaseModel):
    id: str
    nombre: str
    carga_activa: int
    menor_carga: bool
    recomendado: bool
    asignacion_actual: bool
    ultima_asignacion: datetime | None


@router.get('/api/tramites/{tramite_id}/asignaciones/candidatos', response_model=list[CandidatoAsignacion])
def candidatos(tramite_id: str, actor: Actor = Depends(actor_sunass),
               db: Session = Depends(get_db)) -> list[CandidatoAsignacion]:
    exigir(actor, 'asignacion.gestionar')
    repo.obtener_tramite(db, actor, tramite_id)
    return carga_analistas.consultar(db,actor,tramite_id)


@router.get('/api/asignaciones/carga', response_model=list[CandidatoAsignacion])
def carga(actor: Actor = Depends(actor_sunass), db: Session = Depends(get_db)):
    exigir(actor,'asignacion.gestionar')
    return carga_analistas.consultar(db,actor)


@router.post('/api/tramites/{tramite_id}/asignaciones', status_code=201)
def asignar(tramite_id: str, datos: NuevaAsignacion, actor: Actor = Depends(actor_sunass), db: Session = Depends(get_db)) -> dict:
    exigir(actor, 'asignacion.gestionar')
    t = repo.obtener_tramite(db, actor, tramite_id, bloquear=True)
    if t.version != datos.version:
        raise Conflicto('El expediente cambió. Actualiza antes de asignar.')
    if not cambiar_asignacion(db, actor, t, datos.usuario_id, datos.motivo):
        raise Conflicto('El expediente ya está asignado a esa persona.')
    _guardar(db,t,_nueva(t,actor,'asignar','Asignación de expediente',{'detalle':datos.motivo}))
    return {'tramite_id':t.id,'usuario_id':datos.usuario_id,'version':t.version}
