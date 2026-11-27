import pytest
from app.modules.clasificacion_recepcion import sugerir


@pytest.mark.parametrize('texto,esperado', [
    ('Solicitud de uso excepcional del fondo de inversiones', 'UFI'),
    ('Expediente UFI-2024-0001', 'UFI'),
    ('Cambio al programa de inversiones', 'CPI'),
    ('Revisión periódica del estudio tarifario', 'RP'),
    ('Oficio sin procedimiento identificado', None),
    ('Comparación CPI-2024-0002 con UFI-2024-0001', None),
    ('Solicitud de revisión tarifaria incremental RTI-2024-0001', None),
])
def test_sugerencia_documental_sin_inventar_procedimiento(texto, esperado):
    resultado = sugerir(texto)
    assert (resultado['procedimiento'] if resultado else None) == esperado
    if resultado:
        assert resultado['requiere_confirmacion'] is True
        assert resultado['evidencia']
