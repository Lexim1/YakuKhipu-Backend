from types import SimpleNamespace

import pytest

from app import validar_nube


@pytest.mark.parametrize('url,permitido', [
    ('https://openrouter.ai/api/v1', True),
    ('http://worker.railway.internal:20128/v1', True),
    ('http://127.0.0.1:20128/v1', True),
    ('http://openrouter.ai/api/v1', False),
    ('http://worker.railway.internal.example.com:20128/v1', False),
    ('http://worker.railway.internal:80/v1', False),
    ('http://usuario:clave@worker.railway.internal:20128/v1', False),
    ('http://127.0.0.2:20128/v1', False),
])
def test_llm_solo_https_o_gateway_privado(monkeypatch, url, permitido):
    config = SimpleNamespace(
        database_url='postgresql://test', secret_key='x'*40,
        portal_origin='https://portal.example', frontend_origin='https://portal.example',
        oidc_issuer='https://keycloak.example/realms/test', oidc_client_id='test',
        oidc_client_secret='test', pdf_bucket='test', pdf_endpoint='https://s3.example',
        pdf_access_key='test', pdf_secret_key='test', llm_base_url=url,
        llm_api_key='test', llm_model='yakukhipu', llm_enabled=True,
        cookie_secure=True, fecha_demo=None,
    )
    monkeypatch.setattr(validar_nube, 'settings', config)
    if permitido:
        validar_nube.configuracion()
    else:
        with pytest.raises(ValueError, match='LLM_BASE_URL'):
            validar_nube.configuracion()
