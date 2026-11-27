"""Protecciones HTTP del portal y sus respuestas de error."""
from .config import settings


def aplicar(respuesta, ruta="/"):
    scripts = "'self'"
    estilos = "'self' 'unsafe-inline'"
    fuentes = "'self'"
    if ruta in {"/docs", "/redoc"}:
        # Las interfaces de documentación de FastAPI usan este CDN y su arranque inline.
        scripts += " https://cdn.jsdelivr.net 'unsafe-inline'"
        estilos += " https://cdn.jsdelivr.net https://fonts.googleapis.com"
        fuentes += " https://fonts.gstatic.com"
    respuesta.headers.setdefault("Content-Security-Policy", "default-src 'self'; "
        f"script-src {scripts}; style-src {estilos}; font-src {fuentes}; "
        "img-src 'self' data: blob: https://fastapi.tiangolo.com; connect-src 'self'; "
        "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'")
    respuesta.headers.setdefault("X-Content-Type-Options", "nosniff")
    respuesta.headers.setdefault("X-Frame-Options", "DENY")
    respuesta.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    respuesta.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()")
    if settings.cookie_secure and settings.portal_origin.startswith("https://"):
        respuesta.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    if ruta.startswith("/api/"):
        respuesta.headers.setdefault("Cache-Control", "no-store")
    return respuesta
