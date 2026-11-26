from test_api_actores import entorno
from app.core.config import settings


def test_protecciones_en_exito_y_denegacion(entorno):
    entorno.monkeypatch.setattr(settings, "cookie_secure", True)
    entorno.monkeypatch.setattr(settings, "portal_origin", "https://portal.example")
    for ruta, codigo in (("/live", 200), ("/api/tramites", 401)):
        r = entorno.client.get(ruta)
        assert r.status_code == codigo
        assert r.headers["X-Content-Type-Options"] == "nosniff"
        assert r.headers["X-Frame-Options"] == "DENY"
        assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
        assert r.headers["Strict-Transport-Security"] == "max-age=31536000"
    r = entorno.client.post("/api/recepcion/expedientes", json={}, headers={"Origin": "https://otro.example"})
    assert r.status_code == 403
    assert r.headers["Cache-Control"] == "no-store"
    assert "nosniff" == r.headers["X-Content-Type-Options"]


def test_no_hsts_en_desarrollo_y_swagger_funcional(entorno):
    entorno.monkeypatch.setattr(settings, "cookie_secure", False)
    assert "Strict-Transport-Security" not in entorno.client.get("/live").headers
    r = entorno.client.get("/docs")
    assert r.status_code == 200
    assert "https://cdn.jsdelivr.net" in r.headers["Content-Security-Policy"]
