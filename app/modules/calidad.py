"""Alertas reproducibles sobre registros del dataset, pendientes de verificación."""
import hashlib
import json
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from sqlalchemy import text


def numero(valor):
    if valor is None or valor == "":
        return None
    try:
        n = Decimal(str(valor))
        return n if n.is_finite() else None
    except InvalidOperation:
        return None


def detectar(ejecuciones, fondos, cuarentenas):
    hallazgos = []
    por_proyecto = defaultdict(list)

    def agregar(tipo, eps, detalle, regla, fuentes):
        clave = json.dumps([tipo, eps, detalle, fuentes], ensure_ascii=False)
        hallazgos.append(dict(id="calidad-" + hashlib.sha256(clave.encode()).hexdigest()[:24],
                              tipo=tipo, eps_id=eps, detalle=detalle, regla=regla,
                              fuentes=fuentes))

    ultimo = max((r["anio_trimestre"] for r in ejecuciones), default=None)
    for r in ejecuciones:
        por_proyecto[(r["eps_id"], r["cod_proyecto"])].append(r)
    for (eps, proyecto), rows in por_proyecto.items():
        rows.sort(key=lambda r: r["anio_trimestre"])
        if ultimo and rows[-1]["anio_trimestre"] != ultimo and rows[-1]["estado"] not in {"concluido", "culminado", "cancelado"}:
            agregar("reporte_faltante", eps, f"{proyecto}: falta el reporte de {ultimo}.",
                    "Proyecto con reportes previos no concluido y sin registro en el último trimestre disponible. Verificar obligación y fecha de corte.",
                    [rows[-1]["canonical_id"]])
        vistos = set()
        previa = None
        for r in rows:
            periodo = r["anio_trimestre"]
            if periodo in vistos:
                agregar("dato_duplicado", eps, f"{proyecto}: registros repetidos en {periodo}.",
                        "Mismo proyecto, EPS y trimestre.", [r["canonical_id"]])
                previa = None
                continue
            vistos.add(periodo)
            avance = numero(r.get("avance_fisico_acumulado_pct"))
            if previa is not None and avance is not None and avance < previa[0]:
                agregar("avance_inconsistente", eps,
                        f"{proyecto}: el avance acumulado pasó de {previa[0]} % a {avance} % en {periodo}.",
                        "Un avance físico acumulado menor al anterior requiere sustento de rectificación.",
                        [previa[1], r["canonical_id"]])
            if avance is not None:
                previa = (avance, r["canonical_id"])
    depositos = defaultdict(list)
    for r in fondos:
        eps, periodo = r["eps_id"], r["anio_mes"]
        valores = [numero(r.get(k)) for k in ("saldo_inicial", "deposito_efectuado", "intereses",
                                              "uso_ejecutado", "uso_excepcional", "saldo_final")]
        if all(v is not None for v in valores):
            inicial, deposito, interes, uso, excepcional, final = valores
            esperado = inicial + deposito + interes - uso - excepcional
            diferencia = final - esperado
            if abs(diferencia) > Decimal("0.01"):
                agregar("saldo_inconsistente", eps,
                        f"{periodo} ({r['tipo_fondo']}): diferencia de S/ {diferencia:.2f} respecto al saldo calculado.",
                        "Saldo inicial + depósito efectuado + intereses − uso ejecutado − uso excepcional. Verificar ajustes contables.",
                        [r["canonical_id"]])
        programado, efectuado = numero(r.get("deposito_programado")), numero(r.get("deposito_efectuado"))
        if programado is not None and efectuado is not None and programado > 0 and efectuado < programado:
            depositos[(eps, r["tipo_fondo"])].append((r, efectuado, programado))
    for (eps, fondo), rows in depositos.items():
        rows.sort(key=lambda item: item[0]["anio_mes"])
        ultimo_registro, efectuado, programado = rows[-1]
        graves = sum(efectuado < programado / 2 for _, efectuado, programado in rows)
        agregar("deposito_insuficiente", eps,
                f"{fondo}: {len(rows)} registros mensuales con depósito menor al programado, "
                f"{graves} por debajo del 50 %. Último: {ultimo_registro['anio_mes']}, "
                f"S/ {efectuado:.2f} de S/ {programado:.2f}.",
                "Depósito efectuado menor al programado; resumen por EPS y fondo. "
                "Verificar sustento y cierre del mes. Se citan hasta los últimos cinco registros; "
                "el histórico completo está en los registros fuente de ds05.",
                [r["canonical_id"] for r, _, _ in rows[-5:]])
    for r in cuarentenas:
        datos = r["datos"]
        if isinstance(datos, str):
            datos = json.loads(datos)
        if ":fila:" in r["source_record_id"]:
            eps = r.get("eps_id")
            if eps:
                agregar("dato_duplicado", eps,
                        f"{datos.get('cod_proyecto', 'Registro')}: duplicado en cuarentena, fila {r['source_record_id'].rsplit(':fila:', 1)[-1]}.",
                        "El importador separó las filas con la misma clave. Requiere revisión antes de incorporarlas.",
                        [r["canonical_id"]])
    return hallazgos


def listar(db, tramites):
    por_eps = {}
    for tramite in sorted(tramites, key=lambda t: t.estado in {"concluido", "autorizado", "no_autorizado"}):
        por_eps.setdefault(tramite.eps_id, tramite)
    if not por_eps:
        return []
    parametros = {"eps": list(por_eps)}
    nombres = dict(db.execute(text("SELECT id,nombre FROM eps WHERE id=ANY(:eps)"), parametros).all())
    ejecuciones = db.execute(text("""
        SELECT * FROM ejecucion_inversion WHERE eps_id=ANY(:eps)
        AND canonical_id IN (SELECT canonical_id FROM registro_fuente WHERE presente)
    """), parametros).mappings().all()
    fondos = db.execute(text("""
        SELECT * FROM fondo_inversion WHERE eps_id=ANY(:eps)
        AND canonical_id IN (SELECT canonical_id FROM registro_fuente WHERE presente)
    """), parametros).mappings().all()
    cuarentenas = db.execute(text("""
        SELECT r.canonical_id,r.source_record_id,r.datos,e.id AS eps_id
        FROM registro_fuente r
        JOIN fuente f ON f.id=r.fuente_id
        JOIN catalogo_eps c ON c.cod_eps=r.datos->>'cod_eps'
        JOIN eps e ON e.id=c.eps_id
        WHERE r.presente AND r.source_record_id LIKE '%:fila:%'
        AND f.source_file='ds04_ejecucion_inversiones.csv' AND e.id=ANY(:eps)
    """), parametros).mappings().all()
    salida = []
    for hallazgo in detectar(ejecuciones, fondos, cuarentenas):
        t = por_eps[hallazgo.pop("eps_id")]
        fuentes = hallazgo.pop("fuentes")
        salida.append({**hallazgo, "titulo": f"Revisión de datos: {nombres[t.eps_id]}",
                       "fuente": ", ".join(fuentes), "accion": "Revisar contexto de EPS",
                       "destino": {"tipo": "expediente", "id": t.id, "pestana": "comparador"}})
    return salida
