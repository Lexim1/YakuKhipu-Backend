"""Entradas de las operaciones que cambian datos. Las salidas siguen los tipos del frontend
(frontend/src/types/*.ts) y se documentan con ejemplos en /docs."""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, ConfigDict, model_validator


class Entrada(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)


class NuevaActuacion(Entrada):
    """POST /api/tramites/{id}/eventos."""
    tipo: Literal["avanzar_paso", "registrar_informe", "requerir_informacion", "requerir_subsanacion", "verificar_respuesta", "resolver", "cerrar_expediente", "confirmar_vinculo", "validar_expediente"]
    titulo: str | None = Field(default=None, max_length=200)
    detalle: str | None = Field(default=None, max_length=2000)
    documento_id: str | None = Field(default=None, max_length=120)
    fecha_acreditada: date | None = None
    version: int = Field(ge=1, description="Versión observada por el frontend; si cambió responde 409")
    plazo_dias: int | None = Field(default=None, ge=1, le=60, description="Solo para requerir_informacion")
    requisitos: list[str] | None = None
    resultado: Literal["autorizado", "no_autorizado"] | None = None
    alcance_autorizacion: Literal['total', 'parcial'] | None = None
    estado_validado: Literal['en_evaluacion','autorizado','no_autorizado','concluido'] | None = None
    paso_validado: int | None = Field(default=None,ge=1,le=9)


class ConfirmarVinculo(Entrada):
    documento: str = Field(max_length=120)
    decision: Literal["confirmar"] = "confirmar"
    version: int = Field(ge=1)


class NuevaRespuestaEps(Entrada):
    """POST /api/eps/tramites/{id}/respuestas."""
    documento: str | None = Field(default=None, min_length=2, max_length=120, description='ID de un documento incorporado y visible para la EPS')
    referencia_presentada: str | None = Field(default=None, min_length=2, max_length=120, description='Número del oficio presentado, pendiente de incorporación y verificación')
    fecha_presentacion: date
    cargo: str | None = Field(default=None, max_length=120)
    canal: str = Field(min_length=2, max_length=120)
    version: int = Field(ge=1)

    @model_validator(mode='after')
    def identificar_presentacion(self):
        if not self.documento and not self.referencia_presentada:
            raise ValueError('Indica el documento incorporado o la referencia presentada por Mesa de Partes.')
        return self


class Incorporacion(Entrada):
    documento_id: str = Field(min_length=3,max_length=120)
    tramite_id: str = Field(min_length=3,max_length=80)
    tipo_actuacion: str = Field(min_length=2,max_length=80)
    asignado_a: str | None = Field(default=None,min_length=2,max_length=120)
    avisar: bool = False
    version: int = Field(ge=1)


class NuevoExpedienteRecepcion(Entrada):
    documento_id: str = Field(min_length=3, max_length=120)
    procedimiento: Literal["CPI", "UFI", "RP"]
    fecha_ingreso: date
    asignado_a: str | None = Field(default=None, min_length=2, max_length=80)


class RevisionVisibilidad(Entrada):
    visibilidad: Literal['interna', 'partes']
    motivo: str = Field(min_length=3, max_length=1000)
    version: int = Field(ge=1)
