"""Consulta ciudadana: solo la proyección pública de cada caso habilitado."""
from __future__ import annotations

import unicodedata

from sqlalchemy import select,text
from sqlalchemy.orm import Session

from ..models import CifraSector, Publicacion, Tramite
from ..repositories import tramites as repo
from ..schemas.salidas import DecisionPublica


def proyectar(pub: Publicacion) -> dict:
    return DecisionPublica.model_validate({**pub.resumen,**(pub.ficha or {})}).model_dump(mode='json')


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t.lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def _publicadas(db: Session) -> list[Publicacion]:
    consulta = (select(Publicacion).join(Tramite, Tramite.id == Publicacion.tramite_id)
                .where(Publicacion.publicada.is_(True), Tramite.publicable.is_(True),
                       text('tramite.id IN (SELECT canonical_id FROM registro_fuente WHERE presente)')).order_by(Publicacion.id))
    return [p for p in db.scalars(consulta) if db.get(Tramite,p.tramite_id).procedimiento in repo.PROCEDIMIENTOS]


def buscar(db: Session, q: str | None, eps_id: str | None, localidad: str | None, page: int, page_size: int) -> dict:
    items = []
    for pub in _publicadas(db):
        r = proyectar(pub)
        if q and _norm(q) not in _norm(f"{r['eps']} {r['localidad']} {r['titulo']}"):
            continue
        if eps_id and db.get(Tramite, pub.tramite_id).eps_id != eps_id:
            continue
        if localidad and _norm(localidad) not in _norm(r["localidad"]):
            continue
        items.append(r)
    inicio = (page - 1) * page_size
    return {"items": items[inicio:inicio + page_size], "total": len(items), "page": page, "page_size": page_size}


def ficha(db: Session, caso_id: str) -> dict:
    pub = repo.publicacion(db, caso_id)
    return proyectar(pub)


def cifras(db: Session) -> list[dict]:
    casos=[proyectar(p) for p in _publicadas(db)]
    return [{'concepto':'Decisiones publicadas','valor':len(casos),'fuente':'Publicaciones habilitadas en el portal'},
            *[{'concepto':proc,'valor':sum(r['procedimiento']==proc for r in casos),'fuente':'Publicaciones habilitadas en el portal'} for proc in ('CPI','UFI','RP')]]
