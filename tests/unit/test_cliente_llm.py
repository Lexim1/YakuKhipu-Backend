import asyncio
import httpx
import pytest
from app.agent import llm
from app.core.config import settings


@pytest.mark.parametrize('codigo,respuesta,exito,llamadas',[
    (200,{'choices':[{'message':{'content':'respuesta'}}]},True,1),
    (200,{'choices':None},False,2),
    (200,{'choices':[{'message':{'content':''}}]},False,2),
    (200,{'choices':[{'message':{'content':{'objeto':'no textual'}}}]},False,2),
    (401,{'error':'clave-privada'},False,1),
    (429,{'error':'cuota'},False,2),
    (503,{'error':'proveedor'},False,2),
])
def test_transporte_llm_sin_red(monkeypatch,codigo,respuesta,exito,llamadas):
    real_client=httpx.AsyncClient
    requests=[]
    def handler(request):
        requests.append(request)
        return httpx.Response(codigo,json=respuesta)
    monkeypatch.setattr(settings,'llm_enabled',True)
    monkeypatch.setattr(llm.httpx,'AsyncClient',lambda **kwargs:real_client(transport=httpx.MockTransport(handler),**kwargs))
    if exito:
        assert asyncio.run(llm.completar([{'role':'user','content':'Consulta aislada'}]))[0]=='respuesta'
    else:
        with pytest.raises(llm.ModeloNoDisponible) as error:
            asyncio.run(llm.completar([{'role':'user','content':'Consulta aislada'}]))
        assert 'clave-privada' not in str(error.value)
    assert len(requests)==llamadas


def test_modelo_deshabilitado_no_realiza_http(monkeypatch):
    monkeypatch.setattr(settings,'llm_enabled',False)
    with pytest.raises(llm.ModeloNoDisponible): asyncio.run(llm.completar([]))


def test_openrouter_gratis_sin_razonamiento(monkeypatch):
    real_client=httpx.AsyncClient
    requests=[]
    def handler(request):
        requests.append(request)
        return httpx.Response(200,json={'choices':[{'message':{'content':'{"respuesta":"ok"}'}}]})
    monkeypatch.setattr(settings,'llm_enabled',True)
    monkeypatch.setattr(settings,'llm_base_url','https://openrouter.ai/api/v1')
    monkeypatch.setattr(settings,'llm_model','nvidia/nemotron-3-ultra-550b-a55b:free')
    monkeypatch.setattr(settings,'llm_reasoning_effort','none')
    monkeypatch.setattr(llm.httpx,'AsyncClient',lambda **kwargs:real_client(transport=httpx.MockTransport(handler),**kwargs))
    asyncio.run(llm.completar([{'role':'user','content':'pregunta'}]))
    assert requests[0].content
    import json
    data=json.loads(requests[0].content)
    assert data['reasoning']=={'enabled':False}
    assert data['model'].endswith(':free')
