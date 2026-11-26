"""Asignación y reasignación con historia; nunca reemplaza una asignación cerrada."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..auth.sesion import actor_sunass
from ..auth.permisos import exigir
from ..core.db import get_db
from ..core.errores import Conflicto, DatosInvalidos
from ..models import Usuario
from ..models.seguridad import Asignacion
from ..repositories import tramites as repo
from ..schemas.comun import Actor
from ..modules.tramites import _guardar, _nueva

router = APIRouter(prefix='/api/tramites', tags=['Asignaciones'])

class NuevaAsignacion(BaseModel):
    model_config = ConfigDict(extra='forbid')
    usuario_id: str = Field(min_length=1,max_length=80)
    version: int = Field(ge=1)
    motivo: str = Field(min_length=3,max_length=1000)

@router.post('/{tramite_id}/asignaciones', status_code=201)
def asignar(tramite_id: str, datos: NuevaAsignacion, actor: Actor = Depends(actor_sunass), db: Session = Depends(get_db)) -> dict:
    exigir(actor, 'asignacion.gestionar')
    t = repo.obtener_tramite(db, actor, tramite_id, bloquear=True)
    if t.version != datos.version:
        raise Conflicto('El expediente cambió. Actualiza antes de asignar.')
    usuario = db.get(Usuario, datos.usuario_id)
    if usuario is None or not usuario.activo or usuario.rol_id != 'analista_srt':
        raise DatosInvalidos('La asignación requiere un Analista SRT activo.')
    ahora = datetime.now(timezone.utc)
    anterior = db.scalars(select(Asignacion).where(Asignacion.tramite_id == t.id, Asignacion.fin.is_(None))).first()
    if anterior:
        if anterior.usuario_id == usuario.id:
            raise Conflicto('El expediente ya está asignado a esa persona.')
        anterior.fin = ahora
        db.flush()
    db.add(Asignacion(tramite_id=t.id,usuario_id=usuario.id,asignado_por=actor.usuario_id,
        inicio=ahora,fin=None,motivo=datos.motivo))
    t.responsable = usuario.nombre_visible
    _guardar(db,t,_nueva(t,actor,'asignar','Asignación de expediente',{'detalle':datos.motivo}))
    return {'tramite_id':t.id,'usuario_id':usuario.id,'version':t.version}
