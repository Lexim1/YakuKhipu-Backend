"""Cliente OIDC confidencial y transacciones de inicio de un solo uso."""
import base64
import hashlib
import secrets
from urllib.parse import urlencode, urlsplit

import httpx
import jwt
from sqlalchemy import text

from ..core.config import settings
from ..core.errores import ServicioNoDisponible, SinSesion
from ..models import Usuario
from .sesion import ROLES

TRANSACCION = "yakukhipu_oidc"
CALLBACK = "/api/auth/callback"


def huella(valor):
    return hashlib.sha256(valor.encode()).hexdigest()


def cliente_configurado():
    if not (settings.cookie_secure and len(settings.secret_key) >= 32
            and settings.oidc_client_id and settings.oidc_client_secret):
        raise ServicioNoDisponible("El inicio de sesión OIDC no está configurado.")
    for url in (settings.oidc_issuer, settings.portal_origin):
        segura(url)
    origen = urlsplit(settings.portal_origin)
    if origen.path not in ('', '/') or origen.query or origen.fragment:
        raise ServicioNoDisponible("Configura PORTAL_ORIGIN como un origen HTTPS.")


def segura(url):
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.fragment:
        raise ServicioNoDisponible("La configuración OIDC requiere direcciones HTTPS válidas.")
    return url


def metadata(http):
    issuer = settings.oidc_issuer
    response = http.get(issuer.rstrip("/") + "/.well-known/openid-configuration")
    response.raise_for_status()
    data = response.json()
    if data["issuer"] != issuer:
        raise ValueError("Emisor inesperado")
    return data


def iniciar(db, respuesta):
    cliente_configurado()
    state, navegador, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(4))
    try:
        with httpx.Client(timeout=8) as http:
            endpoint = segura(metadata(http)["authorization_endpoint"])
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise ServicioNoDisponible("El proveedor de acceso no está disponible.") from None
    db.execute(text("DELETE FROM seguridad.oidc_transaccion WHERE vence <= now()"))
    db.execute(text("""INSERT INTO seguridad.oidc_transaccion (estado_hash, navegador_hash, nonce, verifier)
        VALUES (:estado, :navegador, :nonce, :verifier)"""),
        dict(estado=huella(state), navegador=huella(navegador), nonce=nonce, verifier=verifier))
    db.commit()
    respuesta.set_cookie(TRANSACCION, navegador, max_age=600, httponly=True, secure=True,
                         samesite="lax", path=CALLBACK)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    query = urlencode(dict(client_id=settings.oidc_client_id, response_type="code",
                           scope="openid", redirect_uri=settings.portal_origin.rstrip("/") + CALLBACK,
                           state=state, nonce=nonce, code_challenge=challenge, code_challenge_method="S256"))
    respuesta.headers["location"] = endpoint + "?" + query


def procesar(db, state, navegador, code):
    cliente_configurado()
    if not (state and navegador and code and len(state) <= 100 and len(navegador) <= 100 and len(code) <= 4096):
        raise SinSesion("No se pudo completar el inicio de sesión.")
    fila = db.execute(text("""DELETE FROM seguridad.oidc_transaccion
        WHERE estado_hash=:estado AND navegador_hash=:navegador AND vence>now()
        RETURNING nonce, verifier"""), dict(estado=huella(state), navegador=huella(navegador))).one_or_none()
    db.commit()
    if not fila:
        raise SinSesion("El inicio de sesión venció. Vuelve a intentarlo.")
    try:
        with httpx.Client(timeout=8) as http:
            data = metadata(http)
            response = http.post(segura(data["token_endpoint"]), auth=(settings.oidc_client_id,
                                 settings.oidc_client_secret), data=dict(grant_type="authorization_code",
                                 code=code, redirect_uri=settings.portal_origin.rstrip("/") + CALLBACK,
                                 code_verifier=fila.verifier))
            response.raise_for_status()
            token = response.json()["id_token"]
            response = http.get(segura(data["jwks_uri"]))
            response.raise_for_status()
            claims = validar(token, response.json(), fila.nonce)
    except httpx.HTTPError:
        raise ServicioNoDisponible("No se pudo contactar al proveedor de acceso.") from None
    except (jwt.PyJWTError, ValueError, KeyError, TypeError):
        raise SinSesion("El proveedor no devolvió una identidad válida.") from None
    uid = db.execute(text("""SELECT usuario_id FROM seguridad.identidad_oidc
        WHERE issuer=:issuer AND subject=:subject"""), dict(issuer=claims["iss"], subject=claims["sub"])).scalar()
    usuario = db.get(Usuario, uid) if uid else None
    if not usuario or not usuario.activo or ROLES.get(usuario.rol_id) != usuario.perfil:
        raise SinSesion("Tu cuenta todavía no está habilitada en YakuKhipu.")
    return usuario


def validar(token, jwks, nonce):
    header = jwt.get_unverified_header(token)
    kid = header.get("kid")
    claves = [k for k in jwks["keys"] if kid and k.get("kid") == kid
              and k.get("kty") == "RSA" and k.get("use", "sig") == "sig"
              and k.get("alg", "RS256") == "RS256"]
    if len(claves) != 1:
        raise ValueError("Clave de firma desconocida")
    claims = jwt.decode(token, jwt.PyJWK.from_dict(claves[0], algorithm="RS256").key,
                        algorithms=["RS256"], audience=settings.oidc_client_id, issuer=settings.oidc_issuer,
                        options={"require": ["exp", "iat", "iss", "aud", "sub", "nonce"]}, leeway=30)
    multiple = isinstance(claims["aud"], list) and len(claims["aud"]) > 1
    if (claims["nonce"] != nonce or not claims["sub"] or
            ((multiple or "azp" in claims) and claims.get("azp") != settings.oidc_client_id)):
        raise ValueError("Identidad no vinculada a esta transacción")
    return claims


def destino_logout():
    cliente_configurado()
    with httpx.Client(timeout=5) as http:
        endpoint = metadata(http).get("end_session_endpoint")
    if not endpoint:
        return None
    return segura(endpoint) + "?" + urlencode(dict(client_id=settings.oidc_client_id,
                          post_logout_redirect_uri=settings.portal_origin.rstrip("/") + "/"))
