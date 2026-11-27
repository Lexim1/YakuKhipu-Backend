"""Flujo del agente (LangGraph).

autorizar → buscar_cache → recuperar → (sin_fuentes | generar → comprobar) → entregar

- Los datos llegan por `FuentesAgente` (config["configurable"]["fuentes"]), que ya aplica los permisos.
- La memoria de la conversación (últimos turnos) la carga el router desde PostgreSQL.
- Solo `generar` es asíncrono: los nodos de lectura son síncronos y LangGraph los ejecuta en un hilo.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from ..core.config import settings
from . import cache, llm, prompts, retrieval
from .fuentes import FuentesAgente, SinAcceso
from ..schemas.agente import Fuente, Respuesta
from ..schemas.comun import Actor

PALABRAS_FICHA = ("estado", "paso", "etapa", "plazo", "dias", "responsable", "quien", "tiene", "cifra", "autoriz",
                  "solicit", "ejecut", "instal", "resumen", "monto", "cuanto", "cuando", "fecha", "siguiente",
                  "resolucion", "decidio", "aprob", "medidor", "fondo", "falta", "historial", "documento",
                  "presentar", "requisito", "debo", "revisar", "pendiente", "vence")
ETIQUETA = re.compile(r"^(F\d+|FICHA|PLAZOS)$")


class Estado(TypedDict, total=False):
    actor: dict
    tramite_id: str
    pregunta: str
    historial: list[dict]
    ficha: dict
    plazos: list[dict]
    fragmentos: list[dict]
    salida: dict
    inicio: float
    cache_clave: str


def _fuentes(config: RunnableConfig) -> FuentesAgente:
    return config["configurable"]["fuentes"]


def autorizar(estado: Estado, config: RunnableConfig) -> dict:
    actor = Actor(**estado["actor"])
    f = _fuentes(config)
    try:
        ficha = f.consultar_tramite(actor, estado["tramite_id"])
        plazos = f.consultar_plazo(actor, estado["tramite_id"])
    except SinAcceso as e:
        return {"salida": Respuesta(estado="denegado", respuesta=str(e)).model_dump()}
    return {"ficha": ficha, "plazos": plazos, "inicio": time.time()}


def tras_autorizar(estado: Estado) -> str:
    return "entregar" if estado.get("salida") else "buscar_cache"


def buscar_cache(estado: Estado, config: RunnableConfig) -> dict:
    """Se consulta DESPUÉS de autorizar: la caché nunca salta el control de acceso."""
    f = _fuentes(config)
    historial = estado.get("historial") or []
    ultimo = json.dumps(historial,ensure_ascii=False,sort_keys=True)
    snapshot=json.dumps([estado.get('ficha'),estado.get('plazos')],sort_keys=True,default=str,ensure_ascii=False)
    version = "agente-20261126:" + settings.llm_model + ":" + f.version(estado["tramite_id"])
    k = cache.clave(estado["actor"], estado["tramite_id"], version+snapshot, estado["pregunta"], ultimo)
    guardada = f.cache_obtener(k) if settings.cache_activa else None
    if guardada:
        return {"cache_clave": k, "salida": {**guardada, "desde_cache": True}}
    return {"cache_clave": k}


def tras_cache(estado: Estado) -> str:
    return "entregar" if estado.get("salida") else "recuperar"


def recuperar(estado: Estado, config: RunnableConfig) -> dict:
    actor = Actor(**estado["actor"])
    consulta = estado["pregunta"]
    historial = estado.get("historial") or []
    if historial and len(retrieval.tokens(consulta)) < 6:  # pregunta de seguimiento: suma el contexto previo
        consulta = historial[-1]["pregunta"] + " " + consulta
    candidatos = _fuentes(config).listar_fuentes(actor, estado["tramite_id"])
    hallados = [{"puntaje": p, **fr} for p, fr in retrieval.buscar(consulta, candidatos, settings.max_fragmentos)
                if p >= settings.min_puntaje]
    for h in hallados:
        h["extracto"] = retrieval.extracto(h["texto"], consulta)
    return {"fragmentos": hallados}


def elegir_salida(estado: Estado) -> str:
    if estado.get("fragmentos"):
        return "generar"
    texto = estado["pregunta"] + " " + " ".join(h["pregunta"] for h in (estado.get("historial") or [])[-1:])
    return "generar" if any(p in retrieval.normalizar(texto) for p in PALABRAS_FICHA) else "sin_fuentes"


def sin_fuentes(_: Estado) -> dict:
    return {"salida": Respuesta(
        estado="sin_fuentes",
        respuesta="No está en el expediente: no encontré documentos ni datos del trámite que respondan esa pregunta.",
        advertencias=["Reformula la pregunta o revisa si el documento fue incorporado al expediente."],
    ).model_dump()}


def _mensajes(estado: Estado, aviso: str | None = None) -> list[dict]:
    actor = Actor(**estado["actor"])
    etiquetados = [(f"F{i}", f, f["extracto"]) for i, f in enumerate(estado.get("fragmentos") or [], start=1)]
    sistema = prompts.SISTEMA.format(perfil=actor.perfil, tono=prompts.TONOS[actor.perfil])
    msgs = [{"role": "system", "content": sistema}]
    for turno in (estado.get("historial") or [])[-settings.turnos_memoria:]:
        msgs += [{"role": "user", "content": turno["pregunta"]}, {"role": "assistant", "content": turno["respuesta"]}]
    contenido = f"{prompts.armar_contexto(estado['ficha'], estado.get('plazos') or [], etiquetados)}\n\n" \
                f"PREGUNTA: {estado['pregunta']}"
    if aviso:
        contenido += f"\n\nCORRIGE: {aviso}"
    msgs.append({"role": "user", "content": contenido})
    return msgs


def _parsear(texto: str) -> dict | None:
    texto = texto.translate(retrieval.ESPACIOS)
    decoder = json.JSONDecoder(strict=False)
    for inicio in re.finditer(r"\{", texto):
        try:
            d, _ = decoder.raw_decode(texto[inicio.start():])
        except json.JSONDecodeError:
            continue
        if not isinstance(d, dict) or not isinstance(d.get("respuesta"), str) or not 0 < len(d["respuesta"].strip()) <= 8000:
            continue
        if any(not isinstance(d.get(k, []), list) or any(not isinstance(x, str) for x in d.get(k, []))
               for k in ("citas", "advertencias")):
            continue
        d["citas"] = [c.strip().strip("[]").upper() for c in d.get("citas", [])]
        return d
    return None


def _numeros(texto: str) -> set[str]:
    texto=re.sub(r'\[[^\]]+\]','',texto)
    t = re.sub(r"(\d)[ .,](?=\d{3}\b)", r"\1", texto.translate(retrieval.ESPACIOS))
    return set(re.findall(r"\d+", t))


def _citas_en_texto(texto: str) -> set[str]:
    """Etiquetas citadas, también agrupadas: [F1, F2] o [FICHA, PLAZOS]."""
    citas = set()
    for grupo in re.findall(r"\[([^\]]+)\]", texto):
        for parte in grupo.split(","):
            if ETIQUETA.match(parte.strip()):
                citas.add(parte.strip())
    return citas


def _problemas(estado: Estado, salida: dict) -> list[str]:
    n = len(estado.get("fragmentos") or [])
    validas = {f"F{i}" for i in range(1, n + 1)} | {"FICHA", "PLAZOS"}
    citadas = _citas_en_texto(salida["respuesta"]) | {str(c) for c in (salida.get("citas") or []) if ETIQUETA.match(str(c))}
    problemas = [f"citaste {c}, que no existe" for c in sorted(citadas - validas)]
    if not citadas:
        problemas.append('la respuesta no incluye citas verificables')
    if 'PLAZOS' in citadas and not estado.get('plazos'):
        problemas.append('no hay plazos disponibles para este perfil')
    evidencia=[]
    if 'FICHA' in citadas: evidencia.append(json.dumps(estado['ficha'],ensure_ascii=False,default=str))
    if 'PLAZOS' in citadas: evidencia.append(json.dumps(estado.get('plazos') or [],default=str))
    for i,fragmento in enumerate(estado.get('fragmentos') or [],1):
        if f'F{i}' in citadas: evidencia.append(fragmento['texto'])
    contexto=' '.join(evidencia)
    sin_sustento = _numeros(salida["respuesta"]) - _numeros(contexto)
    if sin_sustento:
        problemas.append("estas cifras no aparecen en las fuentes: " + ", ".join(sorted(sin_sustento)))
    return problemas


def extractos_de_respaldo(estado: Estado, aviso: str) -> dict | None:
    fragmentos = (estado.get("fragmentos") or [])[:3]
    if not fragmentos:
        return None
    fuentes = [Fuente(documento_id=f["documento_id"], titulo=f["titulo"], fragmento_id=f["fragmento_id"],
                      pagina_pdf=f["pagina_pdf"], extracto=f["extracto"][:300]) for f in fragmentos]
    respuesta = "Encontré estos extractos en los documentos del expediente:\n\n" + "\n\n".join(
        f"«{f.extracto}» — {f.titulo}, pág. {f.pagina_pdf}" if f.pagina_pdf else f"«{f.extracto}» — {f.titulo}"
        for f in fuentes
    )
    return {"salida": Respuesta(estado="ok", respuesta=respuesta, fuentes=fuentes,
                                advertencias=[aviso]).model_dump() | {"_verificada": False}}


async def generar(estado: Estado) -> dict:
    try:
        async with asyncio.timeout(35):
            texto, modelo = await llm.completar(_mensajes(estado))
            salida = _parsear(texto)
            problemas = ["no devolviste el JSON pedido"] if salida is None else _problemas(estado, salida)
            if problemas:
                texto, modelo = await llm.completar(_mensajes(estado, aviso="; ".join(problemas) + ". Usa solo las fuentes."))
                salida = _parsear(texto)
    except (llm.ModeloNoDisponible, TimeoutError):
        respaldo = extractos_de_respaldo(estado, "El modelo no respondió. Estos son extractos del documento, sin análisis generado.")
        if respaldo:
            return respaldo
        return {"salida": Respuesta(estado="no_disponible",
                                    respuesta="El asistente no está disponible ahora. Puedes seguir consultando el trámite.").model_dump()}
    if salida is None:
        respaldo = extractos_de_respaldo(estado, "El formato de la respuesta del modelo no se pudo verificar.")
        if respaldo:
            return respaldo
        return {"salida": Respuesta(estado="no_disponible",
                                    respuesta="No pude generar una respuesta verificable. Intenta de nuevo.",
                                    advertencias=["El modelo no devolvió una respuesta con el formato pedido."]
                                    ).model_dump()}
    return {"salida": {"_borrador": salida, "modelo": modelo}}


def comprobar(estado: Estado) -> dict:
    s = estado["salida"]
    if "_borrador" not in s:
        return {}
    borrador, frags = s["_borrador"], estado.get("fragmentos") or []
    advertencias = [a for a in (borrador.get("advertencias") or []) if isinstance(a, str)]
    problemas = _problemas(estado, borrador)
    if problemas:
        respaldo = extractos_de_respaldo(estado, "Se descartó la respuesta del modelo porque sus citas no se pudieron verificar.")
        if respaldo:
            return respaldo
        return {'salida':Respuesta(estado='sin_fuentes',respuesta='No pude verificar esa respuesta con las fuentes disponibles.',
                advertencias=['La respuesta del modelo fue descartada: '+ '; '.join(problemas)]).model_dump()}
    citadas = {c for c in _citas_en_texto(borrador["respuesta"]) | {str(c) for c in (borrador.get("citas") or [])}
               if re.match(r"^F\d+$", c)}
    fuentes = []
    for c in sorted(citadas, key=lambda x: int(x[1:])):
        i = int(c[1:]) - 1
        if 0 <= i < len(frags):
            f = frags[i]
            fuentes.append(Fuente(documento_id=f["documento_id"], titulo=f["titulo"], fragmento_id=f["fragmento_id"],
                                  pagina_pdf=f["pagina_pdf"], extracto=f["extracto"][:300]))
    nombres = {f"F{i}": f"{f['titulo']}, p. {f['pagina_pdf']}" for i, f in enumerate(frags, start=1)}
    nombres |= {"FICHA": "ficha del trámite", "PLAZOS": "plazos calculados"}

    def _renombrar(m: re.Match) -> str:
        partes = [p.strip() for p in m.group(1).split(",")]
        if all(ETIQUETA.match(p) for p in partes):
            return "[" + "; ".join(nombres.get(p, p) for p in partes) + "]"
        return m.group(0)

    texto = re.sub(r"\[([^\]]+)\]", _renombrar, borrador["respuesta"])
    # Con problemas se entrega con la advertencia visible y NO se guarda en caché (ver entregar).
    return {"salida": Respuesta(estado="ok", respuesta=texto, fuentes=fuentes, advertencias=advertencias,
                                modelo=s.get("modelo")).model_dump() | {"_verificada": not problemas}}


def entregar(estado: Estado, config: RunnableConfig) -> dict:
    s = dict(estado["salida"])
    verificada = s.pop("_verificada", True)
    if estado.get("inicio"):
        s["duracion_ms"] = int((time.time() - estado["inicio"]) * 1000)
    if (settings.cache_activa and s["estado"] == "ok" and verificada and not s.get("desde_cache")
            and estado.get("cache_clave")):
        _fuentes(config).cache_guardar(estado["cache_clave"], estado["tramite_id"],
                                       {k: v for k, v in s.items() if k != "duracion_ms"})
    return {"salida": s}


def construir() -> Any:
    g = StateGraph(Estado)
    for nombre, fn in [("autorizar", autorizar), ("buscar_cache", buscar_cache), ("recuperar", recuperar),
                       ("sin_fuentes", sin_fuentes), ("generar", generar), ("comprobar", comprobar),
                       ("entregar", entregar)]:
        g.add_node(nombre, fn)
    g.add_edge(START, "autorizar")
    g.add_conditional_edges("autorizar", tras_autorizar, {"buscar_cache": "buscar_cache", "entregar": "entregar"})
    g.add_conditional_edges("buscar_cache", tras_cache, {"recuperar": "recuperar", "entregar": "entregar"})
    g.add_conditional_edges("recuperar", elegir_salida, {"generar": "generar", "sin_fuentes": "sin_fuentes"})
    g.add_edge("generar", "comprobar")
    g.add_edge("comprobar", "entregar")
    g.add_edge("sin_fuentes", "entregar")
    g.add_edge("entregar", END)
    return g.compile()


grafo = construir()


async def preguntar(fuentes: FuentesAgente, actor: Actor, tramite_id: str, pregunta: str,
                    historial: list[dict] | None = None) -> Respuesta:
    r = await grafo.ainvoke({"actor": actor.model_dump(), "tramite_id": tramite_id, "pregunta": pregunta,
                             "historial": historial or [], "salida": {}},
                            config={"configurable": {"fuentes": fuentes}})
    return Respuesta(**r["salida"])
