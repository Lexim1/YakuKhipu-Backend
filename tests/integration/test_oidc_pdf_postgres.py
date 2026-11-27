"""Valida el callback OIDC y el flujo documental con SQL real y servicios externos simulados."""
import json
import asyncio
import os
import re
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app import worker_pdf
from app.modules import propuestas
from app.agent import llm
from app.auth import oidc
from app.core.config import settings
from app.core.db import get_db
from app.main import app
from app.modules import archivos_pdf
from app.modules.fuentes import FuentesBD
from app.schemas.comun import Actor


def test_oidc_y_pdf_en_expediente_postgres(monkeypatch):
    url = os.environ.get("VERIFY_DATABASE_URL")
    if not url:
        pytest.skip("Configura VERIFY_DATABASE_URL para integración PostgreSQL.")
    engine = create_engine(url.replace("postgresql://", "postgresql+psycopg://", 1))
    origen = "https://portal.example"
    issuer = "https://identidad.example/realms/yaku"
    cliente = "portal"
    for clave, valor in dict(portal_origin=origen, oidc_issuer=issuer, oidc_client_id=cliente,
                             oidc_client_secret="secreto-aislado", cookie_secure=True,
                             secret_key="clave-de-integracion-aislada-de-32-caracteres").items():
        monkeypatch.setattr(settings, clave, valor)

    privada = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    publica = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(privada.public_key()))
    publica["kid"] = "validacion"
    transaccion = {}

    def proveedor(request):
        from datetime import datetime, timezone
        if request.url.path.endswith("openid-configuration"):
            return httpx.Response(200, json={"issuer": issuer, "authorization_endpoint": issuer + "/login",
                "token_endpoint": issuer + "/token", "jwks_uri": issuer + "/jwks",
                "end_session_endpoint": issuer + "/logout"})
        if request.url.path.endswith("/jwks"):
            return httpx.Response(200, json={"keys": [publica]})
        assert request.url.path.endswith("/token")
        datos = parse_qs(request.content.decode())
        verifier = datos["code_verifier"][0]
        import base64
        import hashlib
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        assert challenge == transaccion["code_challenge"][0]
        ahora = int(datetime.now(timezone.utc).timestamp())
        token = jwt.encode({"iss": issuer, "sub": "coordinacion-prueba", "aud": cliente, "iat": ahora,
                            "exp": ahora + 120, "nonce": transaccion["nonce"][0]},
                           privada, algorithm="RS256", headers={"kid": "validacion"})
        return httpx.Response(200, json={"id_token": token, "access_token": "solo-en-proveedor"})

    monkeypatch.setattr(oidc, "httpx", SimpleNamespace(HTTPError=httpx.HTTPError,
        Client=lambda **kw: httpx.Client(transport=httpx.MockTransport(proveedor), **kw)))
    monkeypatch.setattr(archivos_pdf, "cliente", lambda: SimpleNamespace(put_object=lambda **kw: None))

    async def modelo(mensajes):
        cita = re.search(r"\[(F\d+)\] Oficio de prueba · página 2", mensajes[-1]["content"])
        assert cita
        return json.dumps({"respuesta":f"La página identifica una abrazadera volcánica tricapa [{cita[1]}].",
                           "citas":[cita[1]], "advertencias":[]}), "modelo-de-prueba"

    monkeypatch.setattr(llm, "completar", modelo)

    with engine.connect() as conexion:
        tx = conexion.begin()
        with Session(bind=conexion, join_transaction_mode="create_savepoint", expire_on_commit=False) as db:
            tramite, eps, version = db.execute(text("""SELECT id,eps_id,version FROM v_expedientes_portal
                WHERE estado='en_evaluacion' ORDER BY id LIMIT 1""")).one()
            db.execute(text("""INSERT INTO usuario(id,nombre_visible,perfil,rol_id)
                VALUES ('test-pdf-oidc','Coordinación de prueba','sunass','coordinacion_dre')"""))
            db.execute(text("""INSERT INTO usuario(id,nombre_visible,perfil,rol_id)
                VALUES ('test-jefatura-pdf','Jefatura de prueba','sunass','jefatura_dre')"""))
            db.execute(text("""INSERT INTO seguridad.identidad_oidc(issuer,subject,usuario_id)
                VALUES (:issuer,'coordinacion-prueba','test-pdf-oidc')"""), {"issuer": issuer})
            db.commit()
            db.execute(text("SET LOCAL ROLE yakukhipu_final_api"))
            app.dependency_overrides[get_db] = lambda: db
            try:
                with TestClient(app, base_url=origen, follow_redirects=False) as web:
                    entrada = web.get("/api/auth/login")
                    assert entrada.status_code == 303
                    transaccion.update(parse_qs(urlsplit(entrada.headers["location"]).query))
                    assert transaccion["code_challenge_method"] == ["S256"]
                    cookie = web.cookies.get(oidc.TRANSACCION)
                    callback = f"/api/auth/callback?state={transaccion['state'][0]}&code=prueba"
                    assert web.get(callback).headers["location"] == "/sunass/expedientes"
                    assert web.get("/api/sesion").json()["rol_id"] == "coordinacion_dre"
                    web.cookies.set(oidc.TRANSACCION, cookie, path=oidc.CALLBACK)
                    assert web.get(callback).headers["location"] == "/?acceso=fallido"
                    assert web.delete("/api/sesion").status_code == 403
                    cabeceras = {"Origin": origen}
                    respuesta = web.post("/api/recepcion/pdf", headers=cabeceras,
                        data={"titulo":"Oficio de prueba", "referencia":"Prueba 123", "eps_id":eps,
                              "fecha_documento":str(settings.hoy())},
                        files={"archivo":("prueba.pdf", b"%PDF-1.4\n", "application/pdf")})
                    assert respuesta.status_code == 202, respuesta.text
                    documento = respuesta.json()["id"]
                    datos = {"documento_id":documento, "tramite_id":tramite, "version":version,
                             "tipo_actuacion":"Recepción de PDF"}
                    url_incorporar = "/api/recepcion/incorporaciones"
                    assert web.post(url_incorporar, headers=cabeceras, json=datos).status_code == 409
                    assert worker_pdf.tomar(db)["recepcion_id"] == documento
                    assert worker_pdf.tomar(db) is None
                    db.execute(text("""UPDATE procesamiento_pdf SET estado='listo', paginas=CAST(:paginas AS jsonb)
                          WHERE recepcion_id=:id"""), {"id":documento, "paginas":json.dumps([
                             {"texto":"Página digital", "origen":"texto_pdf"},
                             {"texto":"El documento identifica una abrazadera volcánica tricapa.", "origen":"ocr"}])})
                    db.commit()
                    incorporado = web.post(url_incorporar, headers=cabeceras, json=datos)
                    assert incorporado.status_code == 204, incorporado.text
                    pendiente = web.get(f"/api/tramites/{tramite}/propuestas")
                    assert pendiente.status_code == 200
                    assert pendiente.json()["items"][0]["estado"] == "pendiente"
                    # Aislar esta cola de otros ingresos existentes en QA. El
                    # cambio pertenece a la transacción de prueba y se revierte.
                    db.execute(text("UPDATE propuesta_agente SET estado='fallida' WHERE documento_id<>:id AND estado IN ('pendiente','procesando')"), {'id': documento})
                    trabajo = propuestas.tomar(db)
                    assert trabajo["documento_id"] == documento
                    monkeypatch.setattr(propuestas, "SesionDB", lambda: Session(bind=conexion,
                        join_transaction_mode="create_savepoint", expire_on_commit=False))
                    estado, texto, fuentes, advertencias, modelo = asyncio.run(propuestas.procesar(trabajo))
                    assert estado == "lista" and texto and fuentes[0]["pagina_pdf"] == 2
                    db.execute(text("""UPDATE propuesta_agente SET estado=:estado, propuesta=:propuesta,
                        fuentes=CAST(:fuentes AS jsonb) WHERE documento_id=:documento"""),
                        {"estado":estado, "propuesta":texto, "fuentes":json.dumps(fuentes), "documento":documento})
                    db.commit()
                    assert web.post(f"/api/tramites/{tramite}/propuestas/{documento}/revision",
                                    headers=cabeceras, json={"decision":"aceptada","motivo":"Evidencia revisada"}).status_code == 403
                    jefatura = Actor(perfil="sunass", rol_id="jefatura_dre", usuario_id="test-jefatura-pdf",
                                     permisos=["expediente.consultar", "evaluacion.validar"])
                    assert propuestas.revisar(db, jefatura, tramite, documento, "aceptada",
                                               "Hallazgo contrastado con el expediente") == "aceptada"
                    assert db.execute(text("""SELECT revisada_por FROM propuesta_agente
                        WHERE documento_id=:id"""), {"id": documento}).scalar() == "test-jefatura-pdf"
                    referencia = f"/api/documentos/{documento}/contenido?pagina=2"
                    assert web.get(referencia).json()["paginas"][0]["pagina_pdf"] == 2
                    actor = Actor(perfil="sunass", rol_id="coordinacion_dre", usuario_id="test-pdf-oidc",
                                  permisos=["expediente.consultar"])
                    citas = FuentesBD(db).listar_fuentes(actor, tramite)
                    assert any(f["documento_id"] == documento and f["pagina_pdf"] == 2 for f in citas)
                    chat = web.post("/api/agente/chat", headers=cabeceras,
                                     json={"tramite_id":tramite, "pregunta":"¿Qué dice sobre la abrazadera volcánica tricapa?"})
                    assert chat.status_code == 200, chat.text
                    assert any(f["documento_id"] == documento and f["pagina_pdf"] == 2
                               for f in chat.json()["fuentes"])
                    parte = Actor(perfil="eps", rol_id="eps", eps_id=eps, permisos=["expediente.consultar"])
                    assert not any(f["documento_id"] == documento for f in FuentesBD(db).listar_fuentes(parte, tramite))
                    salida = web.delete("/api/sesion", headers=cabeceras)
                    assert salida.status_code == 204 and "post_logout_redirect_uri=" in salida.headers["X-Logout-URL"]
                    assert web.get(referencia).status_code == 401
            finally:
                app.dependency_overrides.pop(get_db, None)
        tx.rollback()
    engine.dispose()
