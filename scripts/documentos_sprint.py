"""Separación conservadora de páginas identificadas y continuaciones del material ficticio."""
import re
from collections import defaultdict

def agrupar_documentos(reader):
    grupos=defaultdict(list);actual=None
    for index,page in enumerate(reader.pages):
        if index==0:continue  # Portada con el índice de todos los documentos.
        texto=page.extract_text() or ''
        match=re.search(r'\bDOC-\d{6}\b',texto)
        if match:
            actual=match[0]
        elif not actual or not re.match(r'^\s*(?:\d+\.\s*)?(?:Conclusi[oó]n|An[aá]lisis|Sentido propuesto)\b',texto,re.I):
            raise ValueError(f'Página {index+1} sin identificador ni continuación reconocible; requiere revisión.')
        grupos[actual].append((page,texto,index+1))
    return dict(grupos)
