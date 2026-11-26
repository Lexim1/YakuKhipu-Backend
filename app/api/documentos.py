from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..auth.sesion import actor_institucional
from ..schemas.comun import Actor
from ..modules import documentos
from ..schemas.salidas import DocumentoContenido

router = APIRouter(prefix="/api/documentos", tags=["Documentos"])


@router.get("/{documento_id}/contenido", response_model=DocumentoContenido, summary="Documento autorizado para abrir una cita")
def contenido(documento_id: str, pagina: int | None = Query(default=None, ge=1),
              formato: str = Query(default="texto", pattern="^(texto|pdf)$"),
              actor: Actor = Depends(actor_institucional), db: Session = Depends(get_db)):
    """formato=pdf devuelve el archivo si está en DOCUMENTOS_DIR; si no, el texto por página."""
    return documentos.contenido(db, actor, documento_id, pagina, formato)
