"""Ingreso de tres procedimientos con PostgreSQL real y rollback."""
import os
import uuid
from datetime import date
import pytest


@pytest.mark.parametrize("procedimiento", ["CPI", "UFI", "RP"])
@pytest.mark.parametrize('asignar_al_registrar', [True, False])
def test_ingreso_derivacion_y_citas(procedimiento, asignar_al_registrar, monkeypatch):
    from sqlalchemy import create_engine, text, select
    from sqlalchemy.orm import Session
    from fastapi.testclient import TestClient
    from fastapi import Response
    from http.cookies import SimpleCookie
    from app.core.db import get_db
    from app.main import app
    from app.core.config import settings
    monkeypatch.setattr(settings, "secret_key", "clave-integracion-ingresos-aislada-de-32-caracteres")
    monkeypatch.setattr(settings, "portal_origin", "https://test.local")
    from app.auth import sesion
    from app.models import Usuario
    from app.models.seguridad import Asignacion
    from app.modules.operaciones import recibir_documento
    from app.modules.fuentes import FuentesBD

    url = os.environ.get("VERIFY_DATABASE_URL")
    if not url:
        pytest.skip("Requiere la copia PostgreSQL local")
    engine = create_engine(url)
    with engine.connect() as connection:
        tx = connection.begin()
        db = Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
        app.dependency_overrides[get_db] = lambda: db
        try:
            uid = "test-ingreso-" + uuid.uuid4().hex[:12]
            db.add(Usuario(id=uid, nombre_visible="Analista de prueba", perfil="sunass",
                           rol_id="analista_srt", activo=True, credenciales_version=1))
            coordinacion = db.scalars(select(Usuario).where(Usuario.rol_id == "coordinacion_dre")).first()
            eps_id = db.execute(text("SELECT id FROM eps ORDER BY id LIMIT 1")).scalar_one()
            db.commit()
            db.execute(text("SET LOCAL ROLE yakukhipu_final_api"))
            actor = sesion.actor_de(coordinacion, db)
            documento = recibir_documento(db, actor, dict(titulo="Ingreso de prueba",
                referencia=uid, fecha_documento=date(2026, 1, 1), eps_id=eps_id,
                texto="Documento recibido: el proyecto contempla 120 medidores.", simulado=True), date.today(), uid)
            with TestClient(app, base_url="https://test.local", headers={"Origin": "https://test.local"}) as client:
                cuerpo = dict(documento_id=documento["id"], procedimiento=procedimiento,
                              fecha_ingreso="2026-01-02")
                if asignar_al_registrar:
                    cuerpo['asignado_a'] = uid
                assert client.post("/api/recepcion/expedientes", json=cuerpo).status_code == 401
                response = Response()
                sesion.abrir(response, coordinacion, db)
                cookie = SimpleCookie()
                cookie.load(response.headers["set-cookie"])
                client.cookies.set(sesion.COOKIE, cookie[sesion.COOKIE].value)
                assert client.get("/api/recepcion/catalogos").status_code == 200
                assert client.post("/api/recepcion/expedientes", json={**cuerpo, "procedimiento": "OTRO"}).status_code == 422
                respuesta = client.post("/api/recepcion/expedientes", json=cuerpo)
                assert respuesta.status_code == 201, respuesta.text
                nuevo = respuesta.json()
                ficha = client.get('/api/tramites/'+nuevo['tramite_id']).json()
                assert ficha['simulado'] is True and ficha['flujo']['pasos'][0]['estado']=='actual'
                if not asignar_al_registrar:
                    assert not db.scalars(select(Asignacion).where(Asignacion.tramite_id==nuevo['tramite_id'])).first()
                    asignacion = client.post('/api/tramites/'+nuevo['tramite_id']+'/asignaciones', json={
                        'usuario_id':uid, 'motivo':'Derivación posterior por Coordinación', 'version':nuevo['version']})
                    assert asignacion.status_code == 201, asignacion.text
            assert db.scalars(select(Asignacion).where(Asignacion.usuario_id == uid, Asignacion.fin.is_(None))).first()
            analista = db.get(Usuario, uid)
            actor_analista = sesion.actor_de(analista, db)
            assert FuentesBD(db).listar_fuentes(actor_analista, nuevo["tramite_id"])
            with TestClient(app, base_url="https://test.local") as client:
                response = Response()
                sesion.abrir(response, analista, db)
                cookie = SimpleCookie()
                cookie.load(response.headers["set-cookie"])
                client.cookies.set(sesion.COOKIE, cookie[sesion.COOKIE].value)
                listado = client.get("/api/tramites")
                assert listado.status_code == 200, listado.text
                assert nuevo["tramite_id"] in {t["id"] for t in listado.json()["items"]}
                ficha = client.get("/api/tramites/" + nuevo["tramite_id"])
                assert ficha.status_code == 200, ficha.text
                assert client.put('/api/tramites/'+nuevo['tramite_id']+'/documentos/'+documento['id']+'/visibilidad',
                    json={'visibilidad':'partes','motivo':'Intento de analista sin permiso','version':ficha.json()['version']},
                    headers={'Origin':'https://test.local'}).status_code==403
                assert client.post("/api/recepcion/expedientes", json=dict(documento_id=documento["id"],
                    procedimiento=procedimiento, fecha_ingreso="2026-01-02", asignado_a=uid),
                    headers={"Origin": "https://test.local"}).status_code == 403
                alertas = client.get("/api/alertas")
                assert alertas.status_code == 200, alertas.text
        finally:
            app.dependency_overrides.pop(get_db, None)
            db.close()
            tx.rollback()
    engine.dispose()
