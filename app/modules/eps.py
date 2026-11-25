"""Vista EPS: sus trámites, su siguiente acción y el informe de su presentación.

La EPS informa que presentó; SUNASS verifica la incorporación en una actuación posterior.
"""
from __future__ import annotations

import copy
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.errores import Conflicto, DatosInvalidos
from ..models import Actuacion, Documento, Eps, Tramite
from ..repositories import tramites as repo
from ..schemas.comun import Actor
from . import plazos
from ..auth.permisos import exigir
from .tramites import FINALES, TEXTO_ESTADO, _guardar, _nueva, huella_peticion

ESTADO_CORTO = {"requiere_respuesta": "Requiere respuesta", "requiere_subsanacion": "Requiere subsanación",
                "en_evaluacion": "En evaluación"}
ESTADO_EPS = {"en_evaluacion": "en_evaluacion", "requiere_respuesta": "requiere_respuesta",
              "requiere_subsanacion": "requiere_subsanacion", "en_consulta": "en_consulta",
              "autorizado": "autorizado", "no_autorizado": "no_autorizado", "concluido": "concluido"}


def _ficha_generica(db: Session, t: Tramite) -> dict:
    """Ficha de un trámite sin presentación EPS cargada: se arma con sus columnas y documentos."""
    eps = db.get(Eps, t.eps_id)
    docs = db.scalars(select(Documento).where(Documento.tramite_id == t.id,
                                              Documento.visibilidad.in_(repo.VISIBLES["eps"]))
                      .order_by(Documento.id)).all()
    acts = db.scalars(select(Actuacion).where(Actuacion.tramite_id == t.id).order_by(Actuacion.id)).all()
    acts = [a for a in acts if a.documento_id in {d.id for d in docs}]
    seguimiento = [{"titulo": a.titulo, "fecha_texto": plazos.fecha_corta(a.fecha_acreditada) if a.fecha_acreditada
                    else "Fecha por validar", "estado": "hecho"} for a in acts]
    if t.estado not in FINALES:
        seguimiento.append({"titulo": t.etapa, "fecha_texto": "En curso", "estado": "actual"})
    concluido = t.estado in FINALES
    return {"id": t.id, "eps": eps.nombre, "procedimiento": t.procedimiento, "titulo": t.titulo,
            "estado": ESTADO_EPS.get(t.estado, "en_evaluacion"), "estado_texto": TEXTO_ESTADO.get(t.estado, t.estado),
            "resumen": "El procedimiento concluyó." if concluido else "Sunass está evaluando. No tienes tareas pendientes.",
            "simulado": t.simulado, "siguiente_accion": None,
            "aviso": {"tipo": "concluido", "titulo": "Trámite concluido", "etiqueta": "Trámite concluido",
                      "texto": "Revisa la resolución en tus documentos.", "enlace": None} if concluido else None,
            "documentos": [{"id": d.id, "titulo": d.titulo, "pagina": 1} for d in docs],
            "seguimiento": seguimiento, "respuesta_informada": None}


def ficha(db: Session, t: Tramite, hoy: date) -> dict:
    f = copy.deepcopy(t.ficha_eps) if t.ficha_eps else _ficha_generica(db, t)
    f["eps"] = db.get(Eps, t.eps_id).nombre
    f['documentos']=[{'id':d.id,'titulo':d.titulo,'pagina':1} for d in repo.documentos_visibles(db,Actor(perfil='eps',eps_id=t.eps_id,permisos=["expediente.consultar"]),t.id)]
    f.pop("detalle_lista", None)
    accion = f.get("siguiente_accion")
    if accion and accion.get("fecha_limite"):  # los días restantes se calculan hoy, no se guardan
        accion["dias_restantes"] = plazos.dias_habiles(hoy, date.fromisoformat(accion["fecha_limite"]))
    f["version"] = t.version
    return f


def resumen(db: Session, t: Tramite, hoy: date) -> dict:
    f = ficha(db, t, hoy)
    accion = f.get("siguiente_accion")
    respuesta = f.get("respuesta_informada")
    respuesta = respuesta if respuesta and not respuesta.get("verificada") else None
    detalle = (t.ficha_eps or {}).get("detalle_lista") or f["estado_texto"].lower()
    return {
        "id": f["id"], "eps": f["eps"], "procedimiento": f["procedimiento"], "titulo": f["titulo"],
        "estado": f["estado"], "estado_texto": ESTADO_CORTO.get(f["estado"], f["estado_texto"]),
        "detalle": "Sunass evalúa tu respuesta" if respuesta else detalle, "simulado": f["simulado"],
        "pendiente": {"titulo": accion["titulo"], "fecha_texto": accion["fecha_texto"],
                      "fecha_detalle": accion["fecha_detalle"], "dias_restantes": accion["dias_restantes"],
                      "listos": sum(r["preparado"] for r in accion["requisitos"]),
                      "total": len(accion["requisitos"])} if accion else None,
        "respuesta": {"documento": respuesta["documento"], "fecha_texto": respuesta["fecha_texto"]} if respuesta else None,
    }


def listar(db: Session, actor: Actor, hoy: date) -> list[dict]:
    return [resumen(db, t, hoy) for t in repo.listar_tramites(db, actor)]


def informar_respuesta(db: Session, actor: Actor, tramite_id: str, datos: dict, clave: str | None, hoy: date) -> dict:
    """La EPS informa que presentó su respuesta. Repetir el mismo envío (misma clave) devuelve el mismo resultado."""
    exigir(actor, "eps.respuesta_informar")
    t = repo.obtener_tramite(db, actor, tramite_id, bloquear=True)
    previa=db.scalars(select(Actuacion).where(Actuacion.tramite_id==t.id,Actuacion.clave_idempotencia==clave)).first() if clave else None
    if previa:
        if previa.peticion_hash!=huella_peticion(datos):
            raise Conflicto('La clave de idempotencia ya corresponde a otra petición.')
        return ficha(db, t, hoy)
    if datos.get('version')!=t.version:
        raise Conflicto('El trámite cambió. Actualiza antes de informar la respuesta.')
    if t.estado in FINALES:
        raise Conflicto('El trámite ya concluyó.')
    f = copy.deepcopy(t.ficha_eps) if t.ficha_eps else None
    if not f or not f.get("siguiente_accion"):
        raise Conflicto("Esta respuesta ya fue informada. Revisa el seguimiento del trámite.")
    presentado = datos["fecha_presentacion"]
    doc = repo.obtener_documento(db, actor, datos["documento"])
    if doc.tramite_id != t.id:
        raise DatosInvalidos("El documento pertenece a otro expediente.")
    if presentado > hoy:
        raise DatosInvalidos("La fecha de presentación no puede ser futura.")
    accion = f["siguiente_accion"]
    fecha_texto = plazos.fecha_corta(presentado)
    pedido = next((i for i, p in enumerate(f["seguimiento"]) if p["estado"] == "actual"), None)
    anteriores = f["seguimiento"][:pedido] if pedido is not None else [p for p in f["seguimiento"] if p["estado"] == "hecho"]
    verbo = "Subsanaste" if accion.get("etiqueta") == "Subsanación" else "Respondiste"
    f.update({
        "estado": "en_evaluacion", "estado_texto": "Sunass evalúa tu respuesta",
        "resumen": "Sunass está evaluando tu respuesta. Por ahora no tienes ninguna tarea pendiente.",
        "siguiente_accion": None, "aviso": None,
        "respuesta_informada": {"documento": datos["documento"], "fecha_presentacion": presentado.isoformat(),
                                "fecha_texto": fecha_texto, "canal": datos["canal"], "cargo": datos.get("cargo"),
                                "verificada": False},
        "seguimiento": anteriores + [
            {"titulo": f"{verbo} con el {datos['documento']}", "fecha_texto": fecha_texto, "estado": "hecho"},
            {"titulo": "Sunass evalúa tu respuesta", "fecha_texto": "Hoy", "estado": "actual"},
            {"titulo": "Decisión del Consejo Directivo", "fecha_texto": "Te avisaremos cuando se publique",
             "estado": "pendiente"}],
    })
    act = _nueva(t, actor, "informar_presentacion", f"La EPS informa su respuesta: {datos['documento']}",
                 {"detalle": f"Presentada por {datos['canal']} · cargo {datos.get('cargo') or 'sin adjuntar'}",
                  "fecha_acreditada": presentado, "documento_id": datos["documento"]},
                 destino="en_evaluacion", verificada=False, clave=clave)
    t.estado, t.ficha_eps = "en_evaluacion", f
    act.peticion_hash=huella_peticion(datos)
    if t.presentacion:
        p = copy.deepcopy(t.presentacion)
        p["siguiente"] = {"titulo": "Verificar la respuesta de la EPS",
                          "detalle": f"La EPS informó el {datos['documento']} ({fecha_texto}). Confirma que llegó por "
                                     "Mesa de Partes antes de incorporarlo.",
                          "responsable": t.responsable, "boton": "Ver alertas de plazo", "accion": "alertas",
                          "urgente": True}
        t.presentacion = p
    _guardar(db, t, act)
    return ficha(db, t, hoy)
