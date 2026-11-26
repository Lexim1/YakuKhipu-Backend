from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, ConfigDict


class PreguntaInstitucional(BaseModel):
    model_config = ConfigDict(extra='forbid',str_strip_whitespace=True)
    """POST /api/agente/chat. El perfil y la EPS NO se aceptan aquí: salen de la sesión."""
    pregunta: str = Field(min_length=2, max_length=1000)
    tramite_id: str = Field(min_length=3, max_length=80)
    conversacion_id: str | None = Field(default=None, max_length=36)


class PreguntaPublica(BaseModel):
    model_config = ConfigDict(extra='forbid',str_strip_whitespace=True)
    """POST /api/publico/asistente/chat. Solo recupera datos habilitados para publicación."""
    pregunta: str = Field(min_length=2, max_length=600)
    caso_id: str = Field(min_length=3, max_length=60)
    conversacion_id: str | None = Field(default=None, max_length=36)


class Fuente(BaseModel):
    documento_id: str
    titulo: str
    fragmento_id: str
    pagina_pdf: int | None
    extracto: str = ""
    enlace: str | None = None   # lo arma el backend solo para documentos autorizados


class Respuesta(BaseModel):
    """Salida interna del grafo. «denegado» se convierte en 404 en el router."""
    estado: Literal["ok", "sin_fuentes", "no_disponible", "denegado"]
    respuesta: str
    fuentes: list[Fuente] = Field(default_factory=list)
    advertencias: list[str] = Field(default_factory=list)
    modelo: str | None = None
    duracion_ms: int | None = None
    desde_cache: bool = False


class RespuestaChat(BaseModel):
    """Contrato con el frontend."""
    estado: Literal["ok", "sin_fuentes", "no_disponible"]
    respuesta: str
    fuentes: list[Fuente]
    advertencias: list[str]
    conversacion_id: str
    modelo: str | None = None
    duracion_ms: int | None = None
    desde_cache: bool = False
