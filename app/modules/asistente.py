"""Conversaciones del asistente: dueño, ámbito, memoria y registro técnico de cada respuesta."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agent import graph
from ..core.config import settings
from ..core.errores import NoEncontrado, ServicioNoDisponible
from ..models import Conversacion, Mensaje
from ..schemas.agente import RespuestaChat
from ..schemas.comun import Actor
from . import documentos
from .fuentes import FuentesBD
from ..auth.permisos import exigir


def _conversacion(db: Session, actor: Actor, tramite_id: str, conversacion_id: str | None) -> Conversacion:
    """Una conversación solo continúa con su dueño, su perfil y su trámite."""
    if conversacion_id:
        c = db.get(Conversacion, conversacion_id)
        mismo_dueno = c is not None and c.ambito == actor.perfil and c.tramite_id == tramite_id and (
            c.usuario_id == actor.usuario_id and c.eps_id == actor.eps_id and
            (actor.perfil!='publico' or bool(actor.visitante_id) and c.visitante_id==actor.visitante_id))
        if not mismo_dueno:
            raise NoEncontrado("No encontramos esa conversación.")
        return c
    c = Conversacion(id=str(uuid.uuid4()), usuario_id=actor.usuario_id, ambito=actor.perfil, eps_id=actor.eps_id,
                     tramite_id=tramite_id,visitante_id=actor.visitante_id)
    db.add(c)
    db.commit()
    return c


def _historial(db: Session, c: Conversacion) -> list[dict]:
    consulta = (select(Mensaje).where(Mensaje.conversacion_id == c.id, Mensaje.estado.in_(("ok", "sin_fuentes")))
                .order_by(Mensaje.id.desc()).limit(settings.turnos_memoria))
    return [{"pregunta": m.pregunta, "respuesta": m.respuesta} for m in reversed(db.scalars(consulta).all())]


async def responder(db: Session, actor: Actor, tramite_id: str, pregunta: str, conversacion_id: str | None) -> RespuestaChat:
    if actor.perfil != "publico":
        exigir(actor, "agente.consultar")
    fuentes = FuentesBD(db)
    # La autorización ocurre dentro del grafo; aquí se comprueba primero para no crear hilos de casos ajenos.
    try:
        fuentes.consultar_tramite(actor, tramite_id)
    except graph.SinAcceso as e:
        raise NoEncontrado(str(e)) from e
    c = _conversacion(db, actor, tramite_id, conversacion_id)
    r = await graph.preguntar(fuentes, actor, tramite_id, pregunta, _historial(db, c))
    if r.estado == "denegado":
        raise NoEncontrado(r.respuesta)
    publico = actor.perfil == "publico"
    for f in r.fuentes:
        f.enlace = documentos.enlace(f.documento_id, f.pagina_pdf, publico)
    db.add(Mensaje(conversacion_id=c.id, pregunta=pregunta, respuesta=r.respuesta, estado=r.estado,
                   fuentes=[f.model_dump() for f in r.fuentes], advertencias=r.advertencias, modelo=r.modelo,
                   duracion_ms=r.duracion_ms, desde_cache=r.desde_cache))
    db.commit()
    salida = RespuestaChat(estado=r.estado, respuesta=r.respuesta, fuentes=r.fuentes, advertencias=r.advertencias,
                           conversacion_id=c.id, modelo=r.modelo, duracion_ms=r.duracion_ms, desde_cache=r.desde_cache)
    if r.estado == "no_disponible":
        raise ServicioNoDisponible("El asistente no está disponible ahora. Puedes seguir consultando el trámite.",
                                  estado='no_disponible',conversacion_id=c.id)
    return salida
