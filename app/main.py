"""Aplicación FastAPI. Arranca aunque el proveedor de IA esté deshabilitado (LLM_ENABLED=false)."""
from __future__ import annotations


from asyncio import Semaphore
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
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

_cargas_pdf = Semaphore(2)


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
        if _cargas_pdf.locked():
            return JSONResponse({"detail":"Hay dos PDF en carga. Intenta otra vez en unos segundos.",
                                 "codigo":"cargas_ocupadas"}, status_code=429, headers={"Retry-After": "5"})
        async with _cargas_pdf:
            return await call_next(request)
    return await call_next(request)


@app.get("/health", tags=["Sistema"])
def health() -> dict:
    try:
        with engine.connect() as c:
            c.execute(text("select 1"))
        base = "ok"
    except Exception:  # noqa: BLE001 - el chequeo informa, no falla
        base = "sin_conexion"
    # «ingreso» y «carga_pdf» informan el acceso OIDC y la carga de PDF sin revelar secretos.
    return {"estado": "ok" if base=='ok' else 'degradado', "base_de_datos": base, "asistente": "habilitado" if settings.llm_enabled else "deshabilitado",
            "sesion": "persistente", "ingreso": "oidc",
            "carga_pdf": "habilitada" if settings.pdf_bucket else "deshabilitada"}


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


# Railway sirve React y la API desde el mismo origen. Fuera de la imagen web,
# por ejemplo en pruebas unitarias, la API puede arrancar sin los archivos.
frontend_dist = Path(__file__).resolve().parent.parent / "frontend_dist"
if frontend_dist.is_dir():
    app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="frontend-assets")

    @app.get("/{ruta:path}", include_in_schema=False)
    def frontend(ruta: str):
        if ruta == "api" or ruta.startswith("api/"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        archivo = (frontend_dist / ruta).resolve()
        if archivo.is_relative_to(frontend_dist) and archivo.is_file():
            return FileResponse(archivo)
        if "." in Path(ruta).name:
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        return FileResponse(frontend_dist / "index.html")
