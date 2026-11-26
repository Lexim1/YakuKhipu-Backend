"""Flujo real sobre SQL instalado. Los INSERT de prueba se revierten al finalizar."""
import os
import uuid
import pytest

def test_login_asignacion_ambitos_y_logout_postgres(monkeypatch):
    url = os.environ.get('VERIFY_DATABASE_URL')
    if not url:
        pytest.skip('Configura VERIFY_DATABASE_URL para integración PostgreSQL.')
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session
    from fastapi.testclient import TestClient
    from fastapi import Response
    from http.cookies import SimpleCookie
    from app.auth import sesion
    from app.models import Usuario
    from app.main import app
    from app.core.db import get_db
    from app.core.config import settings

    engine = create_engine(url.replace('postgresql://','postgresql+psycopg://',1),connect_args={'connect_timeout':5})
    with engine.connect() as connection:
        transaction = connection.begin()
        db = Session(bind=connection,join_transaction_mode='create_savepoint',expire_on_commit=False)
        prefix = 'test-'+uuid.uuid4().hex[:12]
        rows = db.execute(text('SELECT id,eps_id,version FROM v_expedientes_portal ORDER BY id LIMIT 2')).all()
        assert len(rows) == 2
        tid, eid, version = rows[0]
        ids = {}
        for role in ('analista_srt','coordinacion_dre','jefatura_dre','eps'):
            ids[role] = prefix+'-'+role
            db.execute(text('INSERT INTO usuario(id,nombre_visible,perfil,eps_id,rol_id) VALUES (:id,:nombre,:perfil,:eps,:rol)'),
                {'id':ids[role],'nombre':ids[role],'perfil':'eps' if role=='eps' else 'sunass','eps':eid if role=='eps' else None,'rol':role})
        db.commit()
        # Las peticiones usan el rol técnico sin privilegios de administración.
        db.execute(text('SET LOCAL ROLE yakukhipu_final_api'))
        monkeypatch.setattr(settings,'secret_key','clave-integracion-aislada-de-al-menos-32-caracteres')
        app.dependency_overrides[get_db] = lambda: db
        try:
            with TestClient(app) as client:
                def login(role):
                    respuesta = Response()
                    sesion.abrir(respuesta,db.get(Usuario,ids[role]),db)
                    cookie = SimpleCookie(); cookie.load(respuesta.headers['set-cookie'])
                    client.cookies.set(sesion.COOKIE,cookie[sesion.COOKIE].value)
                    r = client.get('/api/sesion')
                    assert r.status_code == 200, r.text
                    assert r.json()['rol_id'] == role
                login('analista_srt')
                assert client.get('/api/tramites/'+tid).status_code == 404
                login('coordinacion_dre')
                result = client.post('/api/tramites/'+tid+'/asignaciones',json={
                    'usuario_id':ids['analista_srt'],'version':version,'motivo':'Asignación de integración'})
                assert result.status_code == 201, result.text
                assert client.post('/api/tramites/'+tid+'/eventos',json={'tipo':'validar_expediente','version':result.json()['version']}).status_code == 403
                login('analista_srt')
                assert client.get('/api/tramites/'+tid).status_code == 200
                assert client.get('/api/tramites/'+tid+'/eventos').status_code == 200
                assert client.get('/api/tramites/'+rows[1].id).status_code == 404
                assert client.get('/api/recepcion').status_code == 403
                copied = client.cookies.get('yakukhipu_sesion')
                assert client.delete('/api/sesion').status_code == 204
                client.cookies.set('yakukhipu_sesion',copied)
                assert client.get('/api/sesion').status_code == 401
                login('jefatura_dre')
                assert client.get('/api/tramites/'+rows[1].id).status_code == 200
                login('eps')
                listing = client.get('/api/eps/tramites')
                assert listing.status_code == 200, listing.text
                assert all(db.execute(text('SELECT eps_id FROM tramite WHERE id=:id'),{'id':t['id']}).scalar() == eid for t in listing.json()['items'])
        finally:
            app.dependency_overrides.clear()
            db.close()
            transaction.rollback()
    engine.dispose()
