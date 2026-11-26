"""Cliente asíncrono para una API compatible con OpenAI (OpenRouter u OmniRoute).

LLM_BASE_URL termina en /v1 y aquí se añade /chat/completions. Las claves viven solo en el backend.
"""
from __future__ import annotations

import httpx

from ..core.config import settings


class ModeloNoDisponible(Exception):
    pass


async def completar(mensajes: list[dict], max_tokens: int | None = None) -> tuple[str, str]:
    """Devuelve (texto, modelo_usado). Un solo reintento ante 429 o 5xx para no gastar la cuota."""
    if not settings.llm_enabled:
        raise ModeloNoDisponible("El asistente está deshabilitado (LLM_ENABLED=false).")
    ultimo_error = None
    async with httpx.AsyncClient(timeout=settings.llm_timeout) as cliente:
        for _ in range(2):
            try:
                r = await cliente.post(
                    f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                    json={"model": settings.llm_model, "messages": mensajes, "temperature": 0.1,
                          "max_tokens": max_tokens or settings.llm_max_tokens},
                )
                if r.status_code in (429, 500, 502, 503, 504):
                    ultimo_error = f"HTTP {r.status_code}"
                    continue
                if r.is_error:
                    raise ModeloNoDisponible(f'El proveedor rechazó la solicitud (HTTP {r.status_code}).')
                r.raise_for_status()
                datos = r.json()
                contenido=datos["choices"][0]["message"]["content"]
                if not isinstance(contenido,str): raise ValueError('Contenido no textual')
                return contenido, datos.get("model", settings.llm_model)
            except (httpx.HTTPError, KeyError, IndexError, ValueError,TypeError,AttributeError) as e:
                ultimo_error = type(e).__name__
    raise ModeloNoDisponible(f"El proveedor de IA no respondió ({ultimo_error}).")
