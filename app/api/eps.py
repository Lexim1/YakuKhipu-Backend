"""Vista EPS. La EPS sale de la sesión: el frontend nunca envía cuál es."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.db import get_db
from ..auth.sesion import actor_eps
from ..repositories import tramites as repo
from ..schemas.comun import Actor
from ..schemas.tramite import NuevaRespuestaEps
from ..schemas.salidas import FichaEps, ResumenEps
from ..schemas.comun import ListaPaginada
from ..modules import eps as servicio

router = APIRouter(prefix="/api/eps", tags=["EPS"])


@router.get("/tramites", response_model=ListaPaginada[ResumenEps], summary="Trámites propios de la EPS autenticada")
def listar(actor: Actor = Depends(actor_eps), db: Session = Depends(get_db)) -> dict:
    items = servicio.listar(db, actor, settings.hoy())
    return {"items": items, "total": len(items)}


@router.get("/tramites/{tramite_id}", response_model=FichaEps, summary="Ficha comprensible y siguiente acción")
def detalle(tramite_id: str, actor: Actor = Depends(actor_eps), db: Session = Depends(get_db)) -> dict:
    return servicio.ficha(db, repo.obtener_tramite(db, actor, tramite_id), settings.hoy())


@router.post("/tramites/{tramite_id}/respuestas", response_model=FichaEps, summary="Informar la presentación y guardar el cargo")
def responder(tramite_id: str, datos: NuevaRespuestaEps, actor: Actor = Depends(actor_eps),
              db: Session = Depends(get_db), idempotency_key: str | None = Header(default=None, max_length=80)) -> dict:
    return servicio.informar_respuesta(db, actor, tramite_id, datos.model_dump(), idempotency_key, settings.hoy())
