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
