import asyncio

import pytest

from app import validar_nube


@pytest.mark.parametrize("respuesta,correcta", [
    ('{"respuesta":"OK","citas":[],"advertencias":[]}', True),
    ("Respuesta arbitraria no vacía", False),
    ('{"respuesta":"ERROR","citas":[],"advertencias":[]}', False),
    ('{"respuesta":"OK","citas":"sin formato","advertencias":[]}', False),
])
def test_control_agente_valida_contenido_y_formato(monkeypatch, respuesta, correcta):
    async def completar(mensajes):
        return respuesta, "modelo-control"

    monkeypatch.setattr(validar_nube.llm, "completar", completar)
    if correcta:
        asyncio.run(validar_nube.agente())
    else:
        with pytest.raises(ValueError):
            asyncio.run(validar_nube.agente())


@pytest.mark.parametrize("url", [
    "https://openrouter.ai/api/v1",
    "http://worker.railway.internal:20128/v1",
    "http://127.0.0.1:20128/v1",
])
def test_gateway_externo_seguro_o_privado(url):
    validar_nube.validar_url_llm(url)


@pytest.mark.parametrize("url", [
    "http://openrouter.ai/api/v1",
    "http://worker.railway.internal.ejemplo.com:20128/v1",
    "http://worker.railway.internal:8080/v1",
    "https://usuario:secreto@openrouter.ai/api/v1",
])
def test_gateway_no_admite_http_publico_ni_credenciales_en_url(url):
    with pytest.raises(ValueError):
        validar_nube.validar_url_llm(url)
