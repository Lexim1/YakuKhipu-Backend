from app.modules.calidad import detectar


def test_cinco_hallazgos_con_datos_y_nulos():
    ejecuciones = [
        dict(eps_id="eps", cod_proyecto="P1", anio_trimestre="2026-T1", estado="en_ejecucion",
             avance_fisico_acumulado_pct=96.8, canonical_id="e1"),
        dict(eps_id="eps", cod_proyecto="P1", anio_trimestre="2026-T2", estado="en_ejecucion",
             avance_fisico_acumulado_pct=10, canonical_id="e2"),
        dict(eps_id="eps", cod_proyecto="P2", anio_trimestre="2026-T1", estado="en_ejecucion",
             avance_fisico_acumulado_pct=None, canonical_id="e3"),
    ]
    fondos = [dict(eps_id="eps", anio_mes="2026-01", tipo_fondo="inversiones",
                    saldo_inicial=100, deposito_efectuado=10, intereses=0, uso_ejecutado=0,
                    uso_excepcional=0, saldo_final=25110, deposito_programado=30, canonical_id="f1")]
    duplicados = [dict(eps_id="eps", canonical_id="dup", source_record_id="P1:fila:2",
                       datos={"cod_proyecto": "P1"})]
    hallazgos = detectar(ejecuciones, fondos, duplicados)
    assert {h["tipo"] for h in hallazgos} == {
        "reporte_faltante", "avance_inconsistente", "dato_duplicado",
        "saldo_inconsistente", "deposito_insuficiente",
    }
    assert all(h["fuentes"] for h in hallazgos)
    fondos[0]["saldo_final"] = None
    assert not any(h["tipo"] == "saldo_inconsistente" for h in detectar([], fondos, []))
