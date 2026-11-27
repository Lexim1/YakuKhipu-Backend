"""Sugerencia documental conservadora, sin inferencia ni transiciones automáticas."""
import re
import unicodedata


def sugerir(texto):
    normal = ''.join(c for c in unicodedata.normalize('NFKD', texto) if not unicodedata.combining(c)).lower()
    normal = re.sub(r'\s+', ' ', normal)
    patrones = {
        'UFI': r'\bufi\s*-\s*\d{4}|uso excepcional (?:del?\s+)?fondo',
        'CPI': r'\bcpi\s*-\s*\d{4}|cambio (?:al|del|de) programa de inversiones',
        'RP': r'\brp\s*-\s*\d{4}|revision periodica',
    }
    encontrados = [(codigo, re.search(patron, normal)) for codigo, patron in patrones.items()]
    encontrados = [(codigo, m) for codigo, m in encontrados if m]
    if len(encontrados) != 1:
        return None
    codigo, coincidencia = encontrados[0]
    return {'procedimiento': codigo, 'evidencia': normal[max(0, coincidencia.start()-50):coincidencia.end()+100],
            'metodo': 'coincidencia_documental', 'requiere_confirmacion': True}
