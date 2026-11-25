"""Endpoints del asistente. Si el proveedor de IA falla, responden 503 y el resto del portal sigue funcionando."""
from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.db import get_db
from ..core.errores import DemasiadasConsultas
from ..auth.sesion import actor_institucional, visitante
from ..repositories import tramites as repo
from ..schemas.agente import PreguntaInstitucional, PreguntaPublica, RespuestaChat
from ..schemas.comun import Actor
from ..modules import asistente

router = APIRouter(tags=["Asistente"])
_consultas: dict[str, deque] = defaultdict(deque)


def _limitar(ip: str) -> None:
    """Control de uso del asistente ciudadano: N preguntas por hora y por IP (en memoria del proceso)."""
    ahora, cola = time.time(), _consultas[ip]
    while cola and ahora - cola[0] > 3600:
        cola.popleft()
    if len(cola) >= settings.limite_publico_por_hora:
        raise DemasiadasConsultas("Hiciste muchas preguntas seguidas. Intenta de nuevo en unos minutos.")
    cola.append(ahora)


@router.post("/api/agente/chat", response_model=RespuestaChat,
             summary="Respuesta con fuentes accesibles para el usuario autenticado")
async def chat(datos: PreguntaInstitucional, actor: Actor = Depends(actor_institucional),
               db: Session = Depends(get_db)) -> RespuestaChat:
    return await asistente.responder(db, actor, datos.tramite_id, datos.pregunta, datos.conversacion_id)


@router.post("/api/publico/asistente/chat", response_model=RespuestaChat,
             summary="Explicación del caso con fuentes públicas")
async def chat_publico(datos: PreguntaPublica, request: Request, response: Response, db: Session = Depends(get_db)) -> RespuestaChat:
    _limitar(request.client.host if request.client else "-")
    pub = repo.publicacion(db, datos.caso_id)
    return await asistente.responder(db, visitante(request,response), pub.tramite_id, datos.pregunta, datos.conversacion_id)
