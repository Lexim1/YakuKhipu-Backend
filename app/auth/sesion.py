"""Sesiones opacas revocables en PostgreSQL, transportadas en cookie HttpOnly firmada."""
from __future__ import annotations

import hashlib
import hmac
import time
import uuid
import secrets
from datetime import datetime, timedelta, timezone
from ..models.seguridad import SesionPersistente
from ..auth.permisos import ROLES, cargar

from fastapi import Depends, Request, Response,Security
from fastapi.security import APIKeyCookie
from sqlalchemy.orm import Session

from ..models import Usuario
from ..schemas.comun import Actor
from ..core.config import settings
from ..core.db import get_db
from ..core.errores import AccesoDenegado, SinSesion

COOKIE = "yakukhipu_sesion"
cookie_auth=APIKeyCookie(name=COOKIE,auto_error=False,description='Cookie HttpOnly obtenida en POST /api/sesion')


def _firma(valor: str) -> str:
    return hmac.new(settings.secret_key.encode(), valor.encode(), hashlib.sha256).hexdigest()[:32]


def abrir(respuesta: Response, usuario: Usuario, db: Session) -> None:
    ahora = datetime.now(timezone.utc)
    token = secrets.token_urlsafe(32)
    sid = str(uuid.uuid4())
    db.add(SesionPersistente(id=sid, usuario_id=usuario.id, refresh_hash=hashlib.sha256(token.encode()).hexdigest(),
        credenciales_version=usuario.credenciales_version, creada=ahora, vence=ahora+timedelta(hours=8), revocada_en=None))
    db.commit()
    value = f"{sid}.{token}.{int(time.time())+8*3600}"
    respuesta.set_cookie(COOKIE, f"{value}.{_firma(value)}", httponly=True, samesite="lax",
                         max_age=8 * 3600, secure=settings.cookie_secure)


def cerrar(respuesta: Response, request: Request, db: Session) -> None:
    value = request.cookies.get(COOKIE, "")
    if len(value)>512 or not value.isascii():
        value = ""
    signed, _, firma = value.rpartition(".")
    sid = signed.split(".")[0] if hmac.compare_digest(firma, _firma(signed)) else ""
    try:
        uuid.UUID(sid)
    except ValueError:
        sid = None
    registro = db.get(SesionPersistente, sid) if sid else None
    if registro:
        registro.revocada_en = datetime.now(timezone.utc)
        registro.motivo_revocacion = "Cierre de sesión"
        db.commit()
    respuesta.delete_cookie(COOKIE)


def usuario_actual(request: Request, db: Session = Depends(get_db),cookie: str | None=Security(cookie_auth)) -> Usuario:
    if len(settings.secret_key)<32:
        raise SinSesion('La sesión requiere una SECRET_KEY de al menos 32 caracteres.')
    valor = cookie or ''
    if len(valor)>512 or not valor.isascii():
        raise SinSesion('Inicia sesión para continuar.')
    signed, _, firma = valor.rpartition(".")
    identity, _, expires = signed.rpartition('.')
    sid, _, token = identity.partition(".")
    if not sid or not token or len(expires)>12 or not expires.isdigit() or int(expires)<time.time() or not hmac.compare_digest(firma, _firma(signed)):
        raise SinSesion("Inicia sesión para continuar.")
    try:
        uuid.UUID(sid)
    except ValueError:
        raise SinSesion("Inicia sesión para continuar.")
    registro = db.get(SesionPersistente, sid)
    ahora = datetime.now(timezone.utc)
    if (registro is None or registro.revocada_en is not None or registro.vence <= ahora
            or not hmac.compare_digest(registro.refresh_hash, hashlib.sha256(token.encode()).hexdigest())):
        raise SinSesion("Tu sesión ya no es válida.")
    usuario = db.get(Usuario, registro.usuario_id)
    if (usuario is None or not usuario.activo or usuario.credenciales_version != registro.credenciales_version
            or ROLES.get(usuario.rol_id) != usuario.perfil):
        raise SinSesion("Tu sesión ya no es válida.")
    return usuario


def actor_de(usuario: Usuario, db: Session) -> Actor:
    return Actor(perfil=usuario.perfil, eps_id=usuario.eps_id, usuario_id=usuario.id,
                 rol_id=usuario.rol_id, permisos=cargar(db, usuario.rol_id))


def actor_institucional(usuario: Usuario = Depends(usuario_actual), db: Session = Depends(get_db)) -> Actor:
    return actor_de(usuario, db)


def actor_sunass(actor: Actor = Depends(actor_institucional)) -> Actor:
    if actor.perfil != "sunass":
        raise AccesoDenegado("Esta sección es solo para el personal de SUNASS.")
    return actor


def actor_eps(actor: Actor = Depends(actor_institucional)) -> Actor:
    if actor.perfil != "eps" or not actor.eps_id:
        raise AccesoDenegado("Esta sección es solo para las empresas prestadoras.")
    return actor


ACTOR_PUBLICO = Actor(perfil="publico")


def visitante(request: Request, response: Response) -> Actor:
    from ..core.errores import ServicioNoDisponible
    if len(settings.secret_key)<32:
        raise ServicioNoDisponible('La sesión del asistente ciudadano no está configurada.')
    cookie=request.cookies.get('yakukhipu_visitante','')
    if len(cookie)>512 or not cookie.isascii():
        cookie = ''
    signed,_,signature=cookie.rpartition('.')
    identifier,_,expires=signed.rpartition('.')
    valido=bool(identifier and len(expires)<=12 and expires.isdigit() and int(expires)>time.time() and hmac.compare_digest(signature,_firma('publico:'+signed)))
    if not valido:
        identifier=str(uuid.uuid4())
        signed=f'{identifier}.{int(time.time())+8*3600}'
        response.set_cookie('yakukhipu_visitante',f'{signed}.{_firma("publico:"+signed)}',httponly=True,samesite='lax',max_age=8*3600,secure=settings.cookie_secure)
        request.state.visitante_cookies=response.headers.getlist('set-cookie')
    return Actor(perfil='publico',visitante_id=identifier)
