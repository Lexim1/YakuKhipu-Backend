"""Clave de la caché de respuestas comprobadas.

- Incluye el perfil y la EPS: una respuesta para SUNASS nunca se entrega a una EPS ni al público.
- Incluye la versión del trámite (ficha y documentos) y la fecha: si cambia un documento, un estado o el día
  (los días restantes cambian), la respuesta anterior deja de usarse.
- Incluye el último turno, porque una pregunta de seguimiento depende de la conversación.
- «¿Cuánto se autorizó?» y «cuanto se autorizo» comparten clave.
El almacenamiento (tabla respuesta_cache) lo implementa FuentesAgente.
"""
from __future__ import annotations

import hashlib
import json

from .retrieval import tokens


def clave(actor: dict, tramite_id: str, version: str, pregunta: str, ultimo_turno: str = "") -> str:
    partes = [actor.get("rol_id") or "-", ",".join(sorted(actor.get("permisos", []))), actor["perfil"], actor.get("eps_id") or "-", actor.get('usuario_id') or actor.get('visitante_id') or '-',tramite_id, version,
              pregunta.strip(), ultimo_turno]
    return hashlib.sha256("|".join(partes).encode()).hexdigest()
