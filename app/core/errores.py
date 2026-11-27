"""Errores del negocio con su código HTTP. Los routers no arman mensajes a mano."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm.exc import StaleDataError
import logging


class ErrorNegocio(Exception):
    estado = 400
    codigo = "error"

    def __init__(self, mensaje: str, **datos):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.datos = datos


class SinSesion(ErrorNegocio):
    estado, codigo = 401, "sin_sesion"


class AccesoDenegado(ErrorNegocio):
    estado, codigo = 403, "acceso_denegado"


class NoEncontrado(ErrorNegocio):
    """También se usa cuando el recurso existe pero el perfil no puede saberlo (política 404)."""
    estado, codigo = 404, "no_encontrado"


class Conflicto(ErrorNegocio):
    estado, codigo = 409, "conflicto"


class DatosInvalidos(ErrorNegocio):
    estado, codigo = 422, "datos_invalidos"


class ServicioNoDisponible(ErrorNegocio):
    estado, codigo = 503, "no_disponible"


class DemasiadasConsultas(ErrorNegocio):
    estado, codigo = 429, "demasiadas_consultas"


def registrar(app: FastAPI) -> None:
    @app.exception_handler(ErrorNegocio)
    async def _negocio(request: Request, e: ErrorNegocio) -> JSONResponse:
        response=JSONResponse(status_code=e.estado, content={"detail": e.mensaje, "codigo": e.codigo, **e.datos},
                            headers={"Retry-After":"60"} if e.estado==429 else None)
        for cookie in getattr(request.state,'visitante_cookies',[]): response.headers.append('set-cookie',cookie)
        return response

    @app.exception_handler(RequestValidationError)
    async def _validacion(_: Request, e: RequestValidationError) -> JSONResponse:
        campos = ", ".join(".".join(str(p) for p in err["loc"][1:]) or "cuerpo" for err in e.errors())
        return JSONResponse(status_code=422, content={"detail": f"Datos no válidos: {campos}.",
                                                      "codigo": "datos_invalidos"})

    @app.exception_handler(HTTPException)
    async def _http(_: Request, e: HTTPException):
        return JSONResponse(status_code=e.status_code,content={"detail": str(e.detail),
            "codigo": {404:'no_encontrado',405:'metodo_no_permitido'}.get(e.status_code,'error_http')},headers=e.headers)

    @app.exception_handler(SQLAlchemyError)
    async def _base(_: Request, e: SQLAlchemyError):
        conflict=isinstance(e,(IntegrityError,StaleDataError))
        logging.getLogger(__name__).error('Error de persistencia: %s',type(e).__name__)
        return JSONResponse(status_code=409 if conflict else 503,content={
            'detail':'Los datos cambiaron o no cumplen las restricciones.' if conflict else 'La base de datos no está disponible. Intenta nuevamente.',
            'codigo':'conflicto' if conflict else 'no_disponible'})

    @app.exception_handler(Exception)
    async def _inesperado(request: Request, e: Exception):
        logging.getLogger(__name__).error('Error no controlado en %s: %s',request.url.path,type(e).__name__)
        from .config import settings
        headers={}
        if request.headers.get('origin')==settings.frontend_origin:
            headers={'Access-Control-Allow-Origin':settings.frontend_origin,'Access-Control-Allow-Credentials':'true','Vary':'Origin'}
        from .cabeceras import aplicar
        return aplicar(JSONResponse(status_code=500,content={'detail':'Ocurrió un error interno. Intenta nuevamente.','codigo':'error_interno'},headers=headers),request.url.path)
