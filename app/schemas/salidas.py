"""Contratos JSON publicados en OpenAPI para las tres vistas del portal."""
from datetime import date
from typing import Any, Literal
from pydantic import BaseModel, Field, ConfigDict


class Sesion(BaseModel):
    rol_id: Literal['analista_srt','coordinacion_dre','jefatura_dre','eps']
    permisos: list[str]
    usuario_id: str
    nombre: str
    perfil: Literal['sunass','eps']
    eps_id: str | None
    eps: str | None
    simulado: bool


class Plazo(BaseModel):
    situacion: str
    dias_usados: int | None
    dias_totales: int | None
    etapa: str | None


class ResumenTramite(BaseModel):
    id: str
    referencia: str | None = None
    estado: str | None = None
    procedimiento: str
    eps: str
    tamano_eps: str
    etapa: str
    responsable: str
    plazo: Plazo
    simulado: bool


class Expediente(ResumenTramite):
    tema: str
    chip_plazo: str
    flujo: dict[str,Any]
    siguiente: dict[str,Any]
    linea_tiempo: list[dict[str,Any]] | None
    resumen: dict[str,Any] | None
    comparador: dict[str,Any] | None
    plazos: dict[str,Any] | list[dict[str,Any]] | None
    impacto: dict[str,Any] | None
    vinculo: dict[str,Any] | None
    historial: list[dict[str,Any]] | None
    estado: str
    version: int
    plazo_detalle: dict[str,Any]
    documentos: list[dict[str,Any]]


class FichaEps(BaseModel):
    id: str
    eps: str
    procedimiento: str
    titulo: str
    estado: str
    estado_texto: str
    resumen: str
    simulado: bool
    siguiente_accion: dict[str,Any] | None
    aviso: dict[str,Any] | None = None
    documentos: list[dict[str,Any]] = Field(default_factory=list)
    seguimiento: list[dict[str,Any]] = Field(default_factory=list)
    respuesta_informada: dict[str,Any] | None = None
    version: int


class ResumenEps(BaseModel):
    id: str
    eps: str
    procedimiento: str
    titulo: str
    estado: str
    estado_texto: str
    detalle: str
    simulado: bool
    pendiente: dict[str,Any] | None
    respuesta: dict[str,Any] | None


class DocumentoPublico(BaseModel):
    id: str
    titulo: str


class DecisionPublica(BaseModel):
    # Lista de campos pública: descarta notas internas y rutas de archivo.
    id: str
    eps: str
    localidad: str
    procedimiento: str
    titulo: str
    resumen_ciudadano: str
    estado_publico: str = 'decision_publicada'
    cifra: str | None = None
    nota_estado: str | None = None
    fecha_actualizacion: date | None = None
    simulado: bool = False
    documentos: list[DocumentoPublico] = Field(default_factory=list)


class DocumentoContenido(BaseModel):
    id: str
    titulo: str
    referencia: str | None
    visibilidad: Literal['interna','partes','publica']
    estado_validacion: str
    simulado: bool
    pdf_disponible: bool
    paginas: list[dict[str,Any]]


class FichaDecisionPublica(DecisionPublica):
    """Solo proyección aprobada. No consulta montos ni documentos internos por defecto."""
    solicitado: dict[str,Any] | None = None
    autorizado: dict[str,Any] | None = None
    ejecutado: dict[str,Any] | None = None
    impacto: list[dict[str,Any]] = Field(default_factory=list)
    fuentes: list[dict[str,Any]] = Field(default_factory=list)
    consulta: dict[str,Any] | None = None


class Accion(BaseModel):
    tipo: str
    texto: str
    requiere_documento: bool


class Evento(BaseModel):
    id: int
    tipo: str
    titulo: str
    detalle: str | None = None
    actor: str | None = None
    fecha: date | None
    fecha_por_validar: bool
    documento_id: str | None
    fuente: str | None
    verificada: bool
    estado_destino: str


class EstadoPDF(BaseModel):
    estado: str
    error: str | None = None
    paginas: int | None = None


class Recepcion(BaseModel):
    id: str
    titulo: str
    referencia: str
    fecha_documento: date
    eps_id: str
    registrado_por: str
    procesamiento_pdf: EstadoPDF | None = None


class Flujo(BaseModel):
    encabezado: str
    titulo: str
    chip: str
    pasos: list[dict[str,str]]
    nota: str


class Alerta(BaseModel):
    id: str
    tipo: str
    titulo: str
    detalle: str
    regla: str | None = None
    fuente: str | None = None
    destino: dict[str,str] | None = None
    accion: str | None = None


class PublicarDecision(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    version: int = Field(ge=1)
    titulo: str = Field(min_length=3,max_length=200)
    resumen_ciudadano: str = Field(min_length=10,max_length=3000)
    localidad: str = Field(min_length=2,max_length=120)
    documentos_publicos: list[str] = Field(min_length=1,max_length=50)


class NuevaRecepcion(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    titulo: str = Field(min_length=3,max_length=200)
    referencia: str = Field(min_length=2,max_length=120)
    fecha_documento: date
    eps_id: str = Field(min_length=3,max_length=80)
    texto: str = Field(min_length=1,max_length=100000)
