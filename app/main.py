"""Aplicación FastAPI. Arranca aunque el proveedor de IA esté deshabilitado (LLM_ENABLED=false)."""
from __future__ import annotations


from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .api import asistente, documentos, eps, publico, sesion, tramites, asignaciones
from .core import errores
from .core.config import settings
from .core.db import engine
from .schemas.comun import ErrorApi
from .core.errores import ServicioNoDisponible

app = FastAPI(title="YakuKhipu", version="0.2.0", responses={code:{'model':ErrorApi} for code in (401,403,404,409,422,429,500,503)},
              description="API sobre fuentes importadas a PostgreSQL. Los datasets de muestra conservan su procedencia.")
app.add_middleware(CORSMiddleware, allow_origins=[settings.frontend_origin], allow_credentials=True,
                   allow_methods=["GET", "POST", "PUT", "DELETE"], allow_headers=["Content-Type", "Idempotency-Key"],
                   expose_headers=["X-Logout-URL"])
errores.registrar(app)
for r in (sesion.router, sesion.auth_router, tramites.router, asignaciones.router, eps.router, documentos.router, publico.router, asistente.router):
    app.include_router(r)


@app.middleware("http")
async def proteger_escrituras(request: Request, call_next):
    if (settings.portal_origin and request.url.path.startswith("/api/") and
            not request.url.path.startswith("/api/publico/") and
            request.method in {"POST", "PUT", "PATCH", "DELETE"} and
            request.headers.get("origin") != settings.portal_origin.rstrip("/")):
        return JSONResponse({"detail":"Origen de solicitud no autorizado.", "codigo":"acceso_denegado"},
                            status_code=403)
    if request.method == "POST" and request.url.path.rstrip("/") == "/api/recepcion/pdf":
        from .modules.archivos_pdf import LIMITE
        longitud = request.headers.get("content-length", "")
        if not longitud.isascii() or not longitud.isdigit() or len(longitud) > 12:
            return JSONResponse({"detail":"La carga requiere un tamaño conocido.", "codigo":"tamano_requerido"},
                                status_code=411)
        if int(longitud) > LIMITE + 65536:
            return JSONResponse({"detail":"El PDF supera el límite de 20 MiB.", "codigo":"pdf_muy_grande"},
                                status_code=413)
    return await call_next(request)


@app.get("/health", tags=["Sistema"])
def health() -> dict:
    try:
        with engine.connect() as c:
            c.execute(text("select 1"))
        base = "ok"
    except Exception:  # noqa: BLE001 - el chequeo informa, no falla
        base = "sin_conexion"
    return {"estado": "ok" if base=='ok' else 'degradado', "base_de_datos": base, "asistente": "habilitado" if settings.llm_enabled else "deshabilitado",
            "sesion": "persistente"}


@app.get('/live',tags=['Sistema'],summary='Proceso de la API activo, sin consultar BD')
def live() -> dict:
    return {'estado':'ok','version':app.version}


@app.get('/ready',tags=['Sistema'],summary='Conexión y esquema mínimo disponibles')
def ready() -> dict:
    try:
        with engine.connect() as connection:
            connection.execute(text('SELECT u.rol_id, u.credenciales_version, s.id FROM usuario u LEFT JOIN seguridad.sesion s ON s.usuario_id=u.id LIMIT 1'))
            if settings.oidc_issuer:
                connection.execute(text('SELECT estado_hash FROM seguridad.oidc_transaccion LIMIT 1'))
                connection.execute(text('SELECT usuario_id FROM seguridad.identidad_oidc LIMIT 1'))
            if settings.pdf_bucket:
                connection.execute(text('SELECT estado FROM procesamiento_pdf LIMIT 1'))
    except Exception:
        raise ServicioNoDisponible('La conexión o el esquema de PostgreSQL aún no están disponibles.')
    return {'estado':'ok'}
