from test_api_actores import entorno
import app.main as main


def test_live_no_requiere_bd_y_ready_informa_caida(entorno):
    def falla(): raise OSError('Conexión no configurada')
    entorno.monkeypatch.setattr(main.engine,'connect',falla)
    assert entorno.client.get('/live').status_code==200
    assert entorno.client.get('/health').json()['estado']=='degradado'
    assert entorno.client.get('/ready').status_code==503


def test_health_informa_modo_de_ingreso_y_carga_pdf(entorno):
    entorno.monkeypatch.setattr(main.settings, 'oidc_issuer', '')
    entorno.monkeypatch.setattr(main.settings, 'portal_origin', '')
    entorno.monkeypatch.setattr(main.settings, 'pdf_bucket', '')
    datos = entorno.client.get('/health').json()
    assert datos['ingreso'] == 'clave' and datos['carga_pdf'] == 'deshabilitada'
    entorno.monkeypatch.setattr(main.settings, 'oidc_issuer', 'https://identidad.example/realms/yakukhipu')
    entorno.monkeypatch.setattr(main.settings, 'pdf_bucket', 'documentos')
    datos = entorno.client.get('/health').json()
    assert datos['ingreso'] == 'oidc' and datos['carga_pdf'] == 'habilitada'
    assert 'identidad.example' not in str(datos)
