from types import SimpleNamespace
import pytest
from scripts.documentos_sprint import agrupar_documentos

def lector(*textos):
    return SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda t=t:t) for t in textos])

def test_continuacion_conclusion_se_conserva_sin_adjuntar_portada_ni_otro_documento():
    grupos=agrupar_documentos(lector('Índice DOC-000001 DOC-000002','DOC-000001\nInforme','3. Conclusión\nSentido propuesto: aprobado.','DOC-000002\nMemorándum'))
    assert [p[2] for p in grupos['DOC-000001']]==[2,3]
    assert [p[2] for p in grupos['DOC-000002']]==[4]
    assert 'aprobado' in grupos['DOC-000001'][1][1]

def test_pagina_no_identificada_no_se_atribuye_silenciosamente_a_un_documento():
    with pytest.raises(ValueError,match='requiere revisión'):
        agrupar_documentos(lector('Índice','DOC-000001\nOficio','Contenido sin identificador ni continuidad verificable'))
