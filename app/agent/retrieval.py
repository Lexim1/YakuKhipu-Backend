"""Recuperación de fragmentos (BM25 sobre el texto por página, solo dentro del trámite autorizado)."""
from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter

PALABRAS_VACIAS = set("""
a al algo ante con contra cual cuales cuando de del desde donde dos el ella ellas ellos en entre es esa
ese eso esta este esto estos fue ha han hay la las le les lo los mas me mi mis muy no nos o para pero
por que se sea ser si sin sobre su sus tambien te tiene un una uno unos y ya yo cual cuanto cuantos
como qué cómo cuál quien quién dónde donde sabe sabemos dime dice
""".split())


ESPACIOS = str.maketrans({" ": " ", " ": " ", " ": " ", "‑": "-", "‐": "-"})


def normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto.translate(ESPACIOS).lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def tokens(texto: str) -> list[str]:
    t = normalizar(texto)
    t = re.sub(r"(\d)[ .](?=\d{3}\b)", r"\1", t)  # 19 935 / 19.935 → 19935
    palabras = [w for w in re.findall(r"[a-z0-9]+", t) if w not in PALABRAS_VACIAS and len(w) > 1]
    # Flexiones frecuentes en preguntas de expedientes; conserva códigos y cifras intactos.
    familias = {'solicit':'solicitud','autoriz':'autorizacion','ejecut':'ejecucion',
                'resoluc':'resolucion','aprob':'aprobacion','archiv':'archivo',
                'asign':'asignacion','subsan':'subsanacion'}
    return [next((canon for prefijo,canon in familias.items() if w.startswith(prefijo)),w) for w in palabras]


def buscar(consulta: str, fragmentos: list[dict], k: int = 5) -> list[tuple[float, dict]]:
    """BM25 clásico. Los números y códigos de documento pesan el doble."""
    if not fragmentos:
        return []
    docs = [tokens(f["texto"] + " " + f["titulo"]) for f in fragmentos]
    n, prom = len(docs), sum(len(d) for d in docs) / len(docs)
    df = Counter(w for d in docs for w in set(d))
    q = tokens(consulta)
    resultados = []
    for frag, d in zip(fragmentos, docs):
        tf, puntaje = Counter(d), 0.0
        for w in q:
            if w not in tf:
                continue
            idf = math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
            peso = 2.0 if any(ch.isdigit() for ch in w) else 1.0
            puntaje += peso * idf * tf[w] * 2.2 / (tf[w] + 1.2 * (0.25 + 0.75 * len(d) / prom))
        if puntaje > 0:
            resultados.append((puntaje, frag))
    resultados.sort(key=lambda x: -x[0])
    return resultados[:k]


def umbral(cantidad_paginas: int, configurado: float) -> float:
    """BM25 depende del corpus: una coincidencia única en una sola página vale
    log(4/3), por debajo del umbral histórico 1.5. Acotar por la mitad del IDF
    máximo conserva esa evidencia sin admitir resultados con puntaje cero.
    El puntaje mide coincidencia léxica; no certifica que una respuesta sea cierta.
    """
    n = max(1,cantidad_paginas)
    return min(configurado,0.5*math.log(1+(n-0.5)/1.5))


def extracto(texto: str, consulta: str, largo: int = 2600) -> str:
    """Ventana del texto alrededor de las palabras de la consulta (para no mandar páginas enteras)."""
    norm = normalizar(texto)
    pos = [norm.find(w) for w in tokens(consulta) if w in norm]
    centro = min(pos) if pos else 0
    ini = max(0, centro - largo // 3)
    return " ".join(texto[ini: ini + largo].split())
