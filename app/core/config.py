"""Configuración leída de backend/.env (nunca se sube) o de variables de entorno."""
from __future__ import annotations

from datetime import date,datetime
from zoneinfo import ZoneInfo
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND / ".env", extra="ignore", env_ignore_empty=True)

    # Aplicación
    database_url: str = "postgresql+psycopg://yakukhipu:clave@localhost:5432/yakukhipu_final"
    cookie_secure: bool = False  # true en despliegues HTTPS
    frontend_origin: str = "http://localhost:5173"
    secret_key: str = "cambiar-en-env"
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    portal_origin: str = ""
    pdf_bucket: str = ""
    pdf_endpoint: str = ""
    pdf_region: str = "auto"
    pdf_access_key: str = ""
    pdf_secret_key: str = ""
    pdf_addressing_style: str = "virtual"
    # Fecha «de hoy» para la demo. Vacía = fecha real. Fijarla hace reproducibles los plazos.
    fecha_demo: date | None = None
    # Carpeta local con los PDF de los casos (no se sube). Permite abrir el documento citado.
    documentos_dir: Path | None = None

    # Asistente (API compatible con OpenAI: OpenRouter u OmniRoute)
    llm_base_url: str = "https://openrouter.ai/api/v1"
    llm_api_key: str = ""
    llm_model: str = "openrouter/free"
    llm_enabled: bool = False
    llm_timeout: float = 60.0
    llm_max_tokens: int = 2000

    max_fragmentos: int = 5        # fragmentos que recibe el modelo por pregunta
    min_puntaje: float = 1.5       # por debajo no hay evidencia suficiente → sin_fuentes
    turnos_memoria: int = 4        # pares pregunta-respuesta que se recuerdan por conversación
    cache_activa: bool = True
    cache_horas: float = 24.0
    limite_publico_por_hora: int = 30  # preguntas del asistente ciudadano por IP

    def hoy(self) -> date:
        return self.fecha_demo or datetime.now(ZoneInfo('America/Lima')).date()


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
