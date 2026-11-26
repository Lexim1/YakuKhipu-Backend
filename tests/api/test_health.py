from test_api_actores import entorno
import app.main as main


def test_live_no_requiere_bd_y_ready_informa_caida(entorno):
    def falla(): raise OSError('Conexión no configurada')
    entorno.monkeypatch.setattr(main.engine,'connect',falla)
    assert entorno.client.get('/live').status_code==200
    assert entorno.client.get('/health').json()['estado']=='degradado'
    assert entorno.client.get('/ready').status_code==503
