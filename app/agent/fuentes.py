"""Interfaz de lectura del agente. El grafo solo conoce estas firmas; la implementación con PostgreSQL está en
app/modules/fuentes.py y las pruebas pueden usar otra con la misma forma.

Todas las funciones aplican el permiso del actor ANTES de devolver datos: el agente nunca filtra por su cuenta.
"""
from __future__ import annotations

from typing import Protocol

from ..schemas.comun import Actor


class SinAcceso(Exception):
    """El trámite no existe o el actor no puede verlo (se responde igual en ambos casos)."""


class FuentesAgente(Protocol):
    def consultar_tramite(self, actor: Actor, tramite_id: str) -> dict: ...

    def consultar_plazo(self, actor: Actor, tramite_id: str) -> list[dict]: ...

    def listar_fuentes(self, actor: Actor, tramite_id: str) -> list[dict]:
        """Fragmentos visibles: documento_id, titulo, fragmento_id, pagina_pdf, texto."""
        ...

    def consultar_caso_publico(self, caso_id: str) -> dict: ...

    def listar_fuentes_publicas(self, caso_id: str) -> list[dict]: ...

    def version(self, tramite_id: str) -> str:
        """Huella de la ficha y de los documentos: si cambia, la caché anterior deja de usarse."""
        ...

    def cache_obtener(self, clave: str) -> dict | None: ...

    def cache_guardar(self, clave: str, tramite_id: str, salida: dict) -> None: ...
