"""Plazos documentados. No usa feriados ni fechas de demostración."""
from datetime import date
from .reloj import calcular as calcular_documentado

ETAPA_RP = {1:'inicio',2:'evaluacion',3:'evaluacion',4:'difusion',5:'difusion',6:'aprobacion',7:'aprobacion',8:'aprobacion'}
MESES = ['ene','feb','mar','abr','may','jun','jul','ago','set','oct','nov','dic']


def fecha_corta(d: date) -> str:
    return f'{d.day} {MESES[d.month-1]}'


def calcular(db, tramite, hoy):
    etapa=ETAPA_RP.get(tramite.paso_actual) if tramite.procedimiento=='RP' else None
    return calcular_documentado(db,tramite,hoy,etapa)


def texto_chip(plazo):
    if plazo['validacion']!='validado': return 'Plazo pendiente de validación'
    return f"{plazo['situacion'].replace('_',' ')} · {plazo['dias_usados']} de {plazo['dias_totales']} días hábiles"


def dias_habiles(desde, hasta):
    # Los consumidores no deben generar un conteo sin calendario acreditado.
    return None


def plazos_del_expediente(ficha_agente):
    return [{**p,'estado':'pendiente_de_validacion','motivo':'Requiere regla y calendario acreditados.'}
            for p in (ficha_agente or {}).get('plazos',[])]
