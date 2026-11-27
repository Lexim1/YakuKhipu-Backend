"""Propuestas del agente por documento, pendientes de revisión humana."""
import json
import logging

from sqlalchemy import text

from ..agent import graph
from ..auth.permisos import exigir
from ..core.config import settings
from ..core.db import SesionDB
from ..core.errores import Conflicto
from ..models import Fragmento
from sqlalchemy import select
from ..repositories import tramites as repo
from ..schemas.comun import Actor
from .fuentes import FuentesBD

LOG = logging.getLogger(__name__)


def listar(db, actor, tramite_id):
    exigir(actor, "agente.consultar")
    repo.obtener_tramite(db, actor, tramite_id)
    filas = db.execute(text("""SELECT documento_id, estado, propuesta, fuentes, advertencias,
        modelo, error, revisada_por, revision_motivo, revisada_en
        FROM propuesta_agente WHERE tramite_id=:id ORDER BY creada DESC"""), {"id":tramite_id}).mappings()
    return [dict(fila) for fila in filas]


def revisar(db, actor, tramite_id, documento_id, decision, motivo):
    exigir(actor, "evaluacion.validar")
    repo.obtener_tramite(db, actor, tramite_id)
    if decision not in ("aceptada", "rechazada"):
        raise Conflicto("La decisión de revisión no es válida.")
    fila = db.execute(text("""UPDATE propuesta_agente SET estado=:estado, revisada_por=:usuario,
        revision_motivo=:motivo, revisada_en=now(), actualizada=now()
        WHERE tramite_id=:tramite AND documento_id=:documento AND estado='lista'
        RETURNING documento_id"""), {"estado":decision, "usuario":actor.usuario_id, "motivo":motivo,
                                      "tramite":tramite_id, "documento":documento_id}).first()
    if not fila:
        raise Conflicto("La propuesta ya fue revisada o aún no está lista.")
    db.commit()
    return decision


def tomar(db):
    db.execute(text("""UPDATE propuesta_agente SET estado='fallida', error='Se agotaron los intentos.'
        WHERE estado='procesando' AND intentos>=3 AND tomada<now()-interval '5 minutes'"""))
    fila = db.execute(text("""WITH siguiente AS (
        SELECT documento_id FROM propuesta_agente WHERE intentos<3 AND
        (estado='pendiente' OR (estado='procesando' AND tomada<now()-interval '5 minutes'))
        ORDER BY creada LIMIT 1 FOR UPDATE SKIP LOCKED
    ) UPDATE propuesta_agente p SET estado='procesando', tomada=now(), intentos=intentos+1, actualizada=now()
        FROM siguiente WHERE p.documento_id=siguiente.documento_id
        RETURNING p.documento_id, p.tramite_id, p.intentos""")).mappings().one_or_none()
    db.commit()
    return fila


class FuentesDocumento(FuentesBD):
    def __init__(self, db, documento_id):
        super().__init__(db)
        self.documento_id = documento_id

    def listar_fuentes(self, actor, tramite_id):
        return [f for f in super().listar_fuentes(actor, tramite_id)
                if f["documento_id"] == self.documento_id]

    def version(self, tramite_id):
        return super().version(tramite_id) + ":" + self.documento_id


async def procesar(trabajo):
    with SesionDB() as db:
        actor = Actor(perfil="sunass", rol_id="coordinacion_dre", permisos=[
            "expediente.consultar", "agente.consultar"])
        fuente = FuentesDocumento(db, trabajo["documento_id"])
        fragmentos = db.scalars(select(Fragmento).where(
            Fragmento.documento_id == trabajo["documento_id"],
            Fragmento.requiere_ocr.is_(False)).order_by(Fragmento.pagina_pdf).limit(3)).all()
        if not fragmentos:
            return "sin_evidencia", None, [], ["El documento no contiene texto legible."], None
        terminos = " ".join(f.texto[:250] for f in fragmentos)
        pregunta = ("Analiza el documento recién incorporado. Para este procedimiento identifica "
                    "hallazgos relevantes, datos que faltan por verificar y un siguiente paso sugerido. "
                    "Cita páginas del documento. Presenta la propuesta como pendiente de validación humana. "
                    f"Pasajes del documento para localizar evidencia: {terminos}")
        resultado = await graph.preguntar(fuente, actor, trabajo["tramite_id"], pregunta)
        if resultado.estado == "no_disponible" or (resultado.estado == "ok" and not resultado.modelo):
            raise RuntimeError("El modelo no respondió.")
        if resultado.estado != "ok" or not any(f.documento_id == trabajo["documento_id"] for f in resultado.fuentes):
            return "sin_evidencia", None, [], resultado.advertencias, resultado.modelo
        fuentes = [f.model_dump() for f in resultado.fuentes if f.documento_id == trabajo["documento_id"]]
        return "lista", resultado.respuesta, fuentes, resultado.advertencias, resultado.modelo


async def ciclo():
    if not settings.llm_enabled:
        return False
    with SesionDB() as db:
        trabajo = tomar(db)
    if not trabajo:
        return False
    try:
        estado, propuesta, fuentes, advertencias, modelo = await procesar(trabajo)
        error = None
    except Exception as exc:
        LOG.warning("Análisis automático fallido para %s: %s", trabajo["documento_id"], type(exc).__name__)
        estado = "pendiente" if trabajo["intentos"] < 3 else "fallida"
        propuesta, fuentes, advertencias, modelo = None, [], [], None
        error = "No se pudo analizar el documento. Reintenta cuando el agente esté disponible."
    with SesionDB.begin() as db:
        db.execute(text("""UPDATE propuesta_agente SET estado=:estado, propuesta=:propuesta,
            fuentes=CAST(:fuentes AS jsonb), advertencias=CAST(:advertencias AS jsonb),
            modelo=:modelo, error=:error, actualizada=now()
            WHERE documento_id=:documento AND estado='procesando' AND intentos=:intentos"""),
            {"estado":estado, "propuesta":propuesta, "fuentes":json.dumps(fuentes),
             "advertencias":json.dumps(advertencias), "modelo":modelo, "error":error,
             "documento":trabajo["documento_id"], "intentos":trabajo["intentos"]})
    return True
