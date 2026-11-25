"""Inicio, consulta y cierre de sesiones persistentes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response, Request
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.orm import Session

import httpx
from fastapi.responses import RedirectResponse

from ..auth import oidc, sesion
from ..core.config import settings
from ..core.db import get_db
from ..core.errores import ErrorNegocio, SinSesion, ServicioNoDisponible
from ..auth.passwords import verify_password
from ..models import Eps, Usuario
from ..schemas.salidas import Sesion

router = APIRouter(prefix="/api/sesion", tags=["Sesión"])
auth_router = APIRouter(prefix="/api/auth", tags=["OIDC"])


@auth_router.get("/login")
def login_oidc(db: Session = Depends(get_db)):
    respuesta = RedirectResponse("/", status_code=303, headers={"Cache-Control":"no-store"})
    oidc.iniciar(db, respuesta)
    return respuesta


@auth_router.get("/callback")
def callback_oidc(request: Request, state: str = "", code: str = "", db: Session = Depends(get_db)):
    respuesta = RedirectResponse("/", status_code=303, headers={"Cache-Control":"no-store",
                                                                "Referrer-Policy":"no-referrer"})
    respuesta.delete_cookie(oidc.TRANSACCION, path=oidc.CALLBACK, secure=True, httponly=True)
    try:
        usuario = oidc.procesar(db, state, request.cookies.get(oidc.TRANSACCION, ""), code)
    except ErrorNegocio:
        respuesta.headers["location"] = "/?acceso=fallido"
    else:
        sesion.cerrar(respuesta, request, db)
        sesion.abrir(respuesta, usuario, db)
        respuesta.headers["location"] = "/eps/tramites" if usuario.perfil == "eps" else "/sunass/expedientes"
    return respuesta


class Credenciales(BaseModel):
    model_config=ConfigDict(extra='forbid')
    usuario_id: str = Field(min_length=1,max_length=80)
    password: str = Field(min_length=1,max_length=256)


@router.post('', response_model=Sesion, summary='Iniciar sesión con credenciales provisionadas')
def autenticar(datos: Credenciales, respuesta: Response, db: Session = Depends(get_db)) -> dict:
    if settings.oidc_issuer or settings.portal_origin:
        raise SinSesion('Utiliza el ingreso institucional.')
    if len(settings.secret_key)<32:
        raise ServicioNoDisponible('Configura SECRET_KEY con al menos 32 caracteres.')
    u = db.get(Usuario,datos.usuario_id)
    if u is None or not u.activo or sesion.ROLES.get(u.rol_id) != u.perfil or not verify_password(datos.password,u.password_hash):
        raise SinSesion('Credenciales no válidas.')
    sesion.abrir(respuesta,u,db)
    return _vista(db,u)


def _vista(db: Session, u: Usuario) -> dict:
    eps = db.get(Eps, u.eps_id) if u.eps_id else None
    return {"rol_id":u.rol_id, "permisos":sesion.cargar(db,u.rol_id), "usuario_id": u.id, "nombre": u.nombre_visible, "perfil": u.perfil, "eps_id": u.eps_id,
            "eps": eps.nombre if eps else None, "simulado": False}


@router.get("", response_model=Sesion, summary="Sesión actual")
def actual(respuesta: Response, u: Usuario = Depends(sesion.usuario_actual), db: Session = Depends(get_db)) -> dict:
    respuesta.headers["Cache-Control"] = "no-store"
    return _vista(db, u)


@router.delete("", summary="Cerrar sesión", status_code=204)
def salir(respuesta: Response, request: Request, db: Session = Depends(get_db)) -> Response:
    sesion.cerrar(respuesta,request,db)
    if settings.oidc_issuer:
        try:
            destino = oidc.destino_logout()
            if destino:
                respuesta.headers["X-Logout-URL"] = destino
        except (httpx.HTTPError, ErrorNegocio, ValueError, TypeError, KeyError):
            pass  # La sesión local ya quedó revocada.
    respuesta.status_code = 204
    return respuesta
