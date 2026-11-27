"""Consultas con el filtro de acceso aplicado. Ningún otro módulo lee trámites o documentos sin pasar por aquí.

Política de acceso:
- SUNASS ve todos los trámites y documentos.
- Una EPS solo ve sus trámites, y en ellos los documentos «partes» y «publica». Un trámite de otra EPS
  responde 404, igual que uno inexistente, para no revelar que existe.
- Ciudadanía solo ve trámites con publicación activa y documentos «publica».
"""
from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..core.errores import NoEncontrado
from ..models import Documento, Fragmento, Publicacion, Tramite, Eps
from ..schemas.comun import Actor
from ..models.seguridad import Asignacion
from ..auth.permisos import exigir

PROCEDIMIENTOS = ("CPI", "UFI", "RP")

VISIBLES = {"sunass": {"interna", "partes", "publica"}, "eps": {"partes", "publica"}, "publico": {"publica"}}


def obtener_tramite(db: Session, actor: Actor, tramite_id: str, bloquear: bool = False) -> Tramite:
    consulta = select(Tramite).where(Tramite.id == tramite_id,
        text('tramite.id IN (SELECT canonical_id FROM registro_fuente WHERE presente)'))
    if bloquear:
        consulta = consulta.with_for_update()
    t = db.scalars(consulta).first()
    if t is None or t.procedimiento not in PROCEDIMIENTOS or not puede_ver(db, actor, t):
        raise NoEncontrado("El trámite no existe o no tienes acceso.")
    return t


def puede_ver(db: Session, actor: Actor, t: Tramite) -> bool:
    if actor.perfil != "publico" and "expediente.consultar" not in actor.permisos:
        return False
    if t.procedimiento not in PROCEDIMIENTOS:
        return False
    if actor.perfil == "sunass":
        if actor.rol_id in ("coordinacion_dre", "jefatura_dre"):
            return True
        if actor.rol_id != "analista_srt":
            return False
        return db.scalars(select(Asignacion).where(Asignacion.tramite_id == t.id,
            Asignacion.usuario_id == actor.usuario_id, Asignacion.fin.is_(None))).first() is not None
    if actor.perfil == "eps":
        return actor.eps_id is not None and t.eps_id == actor.eps_id
    pub = db.scalars(select(Publicacion).where(Publicacion.tramite_id == t.id)).first()
    return bool(t.publicable and pub and pub.publicada)


def listar_tramites(db: Session, actor: Actor) -> list[Tramite]:
    consulta = select(Tramite).where(Tramite.procedimiento.in_(PROCEDIMIENTOS),text('tramite.id IN (SELECT canonical_id FROM registro_fuente WHERE presente)')).order_by(Tramite.id)
    if actor.perfil != 'publico' and 'expediente.consultar' not in actor.permisos:
        return []
    if actor.perfil == "eps":
        consulta = consulta.where(Tramite.eps_id == actor.eps_id)
    elif actor.perfil == 'sunass':
        if actor.rol_id == 'analista_srt':
            asignados=list(db.scalars(select(Asignacion.tramite_id).where(Asignacion.usuario_id==actor.usuario_id,Asignacion.fin.is_(None))))
            consulta=consulta.where(Tramite.id.in_(asignados))
        elif actor.rol_id not in ('coordinacion_dre','jefatura_dre'):
            return []
    elif actor.perfil == "publico":
        consulta = consulta.join(Publicacion, Publicacion.tramite_id == Tramite.id).where(
            Publicacion.publicada.is_(True), Tramite.publicable.is_(True))
    rows=[t for t in db.scalars(consulta) if puede_ver(db, actor, t)] if actor.perfil=='publico' else list(db.scalars(consulta))
    if rows and hasattr(db,'info'):
        db.info['referencias']=dict(db.execute(text("""SELECT r.canonical_id,coalesce(p.id_expediente,r.datos->>'referencia',r.datos->>'expediente')
            FROM registro_fuente r LEFT JOIN procedimiento_fuente p ON p.tramite_id=r.canonical_id WHERE r.canonical_id=ANY(:ids)"""),{'ids':[t.id for t in rows]}).all())
        db.info['eps_cache']={e.id:e for e in db.scalars(select(Eps).where(Eps.id.in_({t.eps_id for t in rows})))}
    return rows


def obtener_documento(db: Session, actor: Actor, documento_id: str) -> Documento:
    doc = db.get(Documento, documento_id)
    if doc is None or doc.visibilidad not in VISIBLES[actor.perfil]:
        raise NoEncontrado("El documento no existe o no tienes acceso.")
    if not db.execute(text('SELECT presente FROM registro_fuente WHERE canonical_id=:id'),{'id':doc.id}).scalar():
        raise NoEncontrado('El documento no existe o no tienes acceso.')
    obtener_tramite(db, actor, doc.tramite_id)  # también exige acceso al trámite
    return doc


def documentos_visibles(db: Session,actor: Actor,tramite_id: str) -> list[Documento]:
    obtener_tramite(db,actor,tramite_id)
    return list(db.scalars(select(Documento).where(Documento.tramite_id==tramite_id,
        Documento.visibilidad.in_(VISIBLES[actor.perfil]),
        text('documento.id IN (SELECT canonical_id FROM registro_fuente WHERE presente)')).order_by(Documento.id)))


def fragmentos_visibles(db: Session, actor: Actor, tramite_id: str) -> list[Fragmento]:
    """Fragmentos con texto útil que este actor puede leer. Se filtra ANTES de llegar al agente."""
    obtener_tramite(db,actor,tramite_id)
    consulta = (select(Fragmento).join(Documento, Documento.id == Fragmento.documento_id)
                .where(Fragmento.tramite_id == tramite_id, Fragmento.requiere_ocr.is_(False),
                       Documento.visibilidad.in_(VISIBLES[actor.perfil]),
                       text('documento.id IN (SELECT canonical_id FROM registro_fuente WHERE presente)'))
                .order_by(Fragmento.documento_id, Fragmento.pagina_pdf))
    return list(db.scalars(consulta))


def publicacion(db: Session, caso_id: str) -> Publicacion:
    pub = db.get(Publicacion, caso_id)
    if pub is None or not pub.publicada:
        raise NoEncontrado("No encontramos esa decisión publicada.")
    t = db.get(Tramite, pub.tramite_id)
    activo = db.execute(text('SELECT presente FROM registro_fuente WHERE canonical_id=:id'),{'id':pub.tramite_id}).scalar()
    if t is None or t.procedimiento not in PROCEDIMIENTOS or not t.publicable or not activo:
        raise NoEncontrado("No encontramos esa decisión publicada.")
    return pub
