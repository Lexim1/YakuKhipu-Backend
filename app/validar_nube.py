"""Prueba conexiones reales desde el contenedor desplegado en Railway.

Ejecutar: python -m app.validar_nube
No imprime credenciales, datos de expedientes ni respuestas del modelo.
"""
from __future__ import annotations

import asyncio
import json
import secrets
import sys
from urllib.parse import urlsplit

import httpx
from sqlalchemy import text

from .agent import llm
from .core.config import settings
from .core.db import engine
from .modules.archivos_pdf import cliente


def configuracion() -> None:
    obligatorias = (
        "database_url", "secret_key", "portal_origin", "frontend_origin",
        "oidc_issuer", "oidc_client_id", "oidc_client_secret",
        "pdf_bucket", "pdf_endpoint", "pdf_access_key", "pdf_secret_key",
        "llm_base_url", "llm_api_key", "llm_model",
    )
    faltantes = [nombre.upper() for nombre in obligatorias if not getattr(settings, nombre)]
    if faltantes:
        raise ValueError("Faltan variables: " + ", ".join(faltantes))
    if not settings.cookie_secure or not settings.llm_enabled or len(settings.secret_key) < 32:
        raise ValueError("Se requieren COOKIE_SECURE=true, LLM_ENABLED=true y SECRET_KEY de 32+ caracteres.")
    if settings.portal_origin.rstrip("/") != settings.frontend_origin.rstrip("/"):
        raise ValueError("PORTAL_ORIGIN y FRONTEND_ORIGIN deben coincidir en este despliegue BFF.")
    for nombre in ("portal_origin", "oidc_issuer", "pdf_endpoint", "llm_base_url"):
        if urlsplit(getattr(settings, nombre)).scheme != "https":
            raise ValueError(f"{nombre.upper()} debe usar HTTPS.")
    if settings.fecha_demo is not None:
        raise ValueError("FECHA_DEMO debe estar vacía en la validación de nube.")


def postgres() -> None:
    with engine.connect() as conexion:
        conexion.execute(text("SELECT id, rol_id FROM usuario LIMIT 1")).all()
        conexion.execute(text("SELECT estado_hash FROM seguridad.oidc_transaccion LIMIT 1")).all()
        conexion.execute(text("SELECT usuario_id FROM seguridad.identidad_oidc LIMIT 1")).all()
        conexion.execute(text("SELECT estado FROM procesamiento_pdf LIMIT 1")).all()
        conexion.execute(text("SELECT estado FROM propuesta_agente LIMIT 1")).all()


def keycloak() -> None:
    with httpx.Client(timeout=12) as http:
        respuesta = http.get(settings.oidc_issuer.rstrip("/") + "/.well-known/openid-configuration")
        respuesta.raise_for_status()
        datos = respuesta.json()
        if datos.get("issuer") != settings.oidc_issuer:
            raise ValueError("El issuer publicado por Keycloak no coincide con OIDC_ISSUER.")
        for nombre in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
            if urlsplit(datos.get(nombre, "")).scheme != "https":
                raise ValueError(f"Keycloak no publicó un {nombre} HTTPS.")
        claves = http.get(datos["jwks_uri"])
        claves.raise_for_status()
        if not any(k.get("kty") == "RSA" and k.get("use", "sig") == "sig"
                   for k in claves.json().get("keys", [])):
            raise ValueError("Keycloak no publicó claves RSA para validar tokens.")
        # Un código inventado debe ser rechazado como invalid_grant DESPUÉS de autenticar al cliente.
        prueba = http.post(datos["token_endpoint"],
                           auth=(settings.oidc_client_id, settings.oidc_client_secret),
                           data={"grant_type": "authorization_code", "code": "validacion-sin-sesion",
                                 "redirect_uri": settings.portal_origin.rstrip("/") + "/api/auth/callback",
                                 "code_verifier": "validacion-sin-sesion-123456789012345678901234567890123456"})
        try:
            error = prueba.json().get("error")
        except (ValueError, AttributeError):
            error = None
        if prueba.status_code != 400 or error != "invalid_grant":
            raise ValueError("Keycloak no aceptó las credenciales del cliente OIDC o su configuración.")


def bucket() -> None:
    s3 = cliente()
    clave = "validacion/" + secrets.token_hex(16) + ".txt"
    contenido = b"YakuKhipu: prueba de almacenamiento privado\n"
    creado = False
    try:
        s3.put_object(Bucket=settings.pdf_bucket, Key=clave, Body=contenido,
                      ContentType="text/plain")
        creado = True
        objeto = s3.get_object(Bucket=settings.pdf_bucket, Key=clave)
        try:
            if objeto["Body"].read() != contenido:
                raise ValueError("La lectura del bucket no coincide con la escritura.")
        finally:
            objeto["Body"].close()
    finally:
        if creado:
            s3.delete_object(Bucket=settings.pdf_bucket, Key=clave)


async def agente() -> None:
    respuesta, _ = await llm.completar([
        {"role": "user", "content": "Responde solo con la palabra OK."}
    ])
    if not respuesta.strip():
        raise ValueError("El proveedor del agente devolvió una respuesta vacía.")


def main() -> int:
    comprobaciones = (("configuracion", configuracion), ("postgres", postgres),
                     ("keycloak", keycloak), ("bucket", bucket),
                     ("agente", lambda: asyncio.run(agente())))
    correcto = True
    for nombre, funcion in comprobaciones:
        try:
            funcion()
        except Exception as exc:
            correcto = False
            print(json.dumps({"servicio": nombre, "estado": "fallo",
                              "tipo": type(exc).__name__}, ensure_ascii=False))
        else:
            print(json.dumps({"servicio": nombre, "estado": "ok"}, ensure_ascii=False))
    return 0 if correcto else 1


if __name__ == "__main__":
    sys.exit(main())
