"""Consulta ciudadana sin sesión. Solo proyecciones públicas."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..auth.sesion import ACTOR_PUBLICO
from ..modules import documentos, publico
from ..schemas.salidas import DecisionPublica,DocumentoContenido,FichaDecisionPublica
from ..schemas.comun import ListaPublica

router = APIRouter(prefix="/api/publico", tags=["Ciudadanía"])


@router.get("/decisiones", response_model=ListaPublica[DecisionPublica], summary="Listado público con búsqueda por EPS o localidad")
def decisiones(q: str | None = Query(default=None, max_length=100), eps_id: str | None = None,
               localidad: str | None = Query(default=None, max_length=100), page: int = Query(default=1, ge=1),
               page_size: int = Query(default=10, ge=1, le=50), db: Session = Depends(get_db)) -> dict:
    return publico.buscar(db, q, eps_id, localidad, page, page_size)


@router.get("/decisiones/{caso_id}", response_model=FichaDecisionPublica, summary="Ficha pública con decisión, ejecución, impacto y fuentes")
def decision(caso_id: str, db: Session = Depends(get_db)) -> dict:
    return publico.ficha(db, caso_id)


@router.get("/cifras", summary="Cifras generales del sector con su fuente")
def cifras(db: Session = Depends(get_db)) -> list[dict]:
    return publico.cifras(db)


@router.get("/documentos/{documento_id}/contenido", response_model=DocumentoContenido, summary="Fuente habilitada para publicación")
def documento(documento_id: str, pagina: int | None = Query(default=None, ge=1), formato: str = Query(default='texto',pattern='^(texto|pdf)$'),
              db: Session = Depends(get_db)):
    return documentos.contenido(db, ACTOR_PUBLICO, documento_id, pagina, formato)
