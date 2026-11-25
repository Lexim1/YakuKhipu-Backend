"""Implementación de FuentesAgente con PostgreSQL. Reutiliza los filtros de acceso del repositorio."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from ..agent.fuentes import SinAcceso
from ..core.config import settings
from ..core.errores import NoEncontrado
from ..models import Actuacion, Documento, Eps, RespuestaCache, Tramite,Publicacion
from ..repositories import tramites as repo
from ..schemas.comun import Actor
from . import plazos
from .tramites import PASOS, TEXTO_ESTADO

CAMPOS_PUBLICOS = ("procedimiento", "procedimiento_nombre", "norma", "eps", "region", "titulo", "estado",
                   "resumen_ciudadano", "cifras", "simulado")


class FuentesBD:
    def __init__(self, db: Session, hoy: date | None = None):
        self.db = db
        self.hoy = hoy or settings.hoy()

    # -- lectura autorizada -------------------------------------------------
    def _tramite(self, actor: Actor, tramite_id: str) -> Tramite:
        try:
            return repo.obtener_tramite(self.db, actor, tramite_id)
        except NoEncontrado as e:
            raise SinAcceso("El trámite no existe o no tienes acceso.") from e

    def consultar_tramite(self, actor: Actor, tramite_id: str) -> dict:
        t = self._tramite(actor, tramite_id)
        if actor.perfil=='publico':
            from .publico import proyectar
            pub=self.db.scalars(select(Publicacion).where(Publicacion.tramite_id==t.id)).first()
            return {'id':t.id,**proyectar(pub)}
        eps = self.db.get(Eps, t.eps_id)
        extra = t.ficha_agente or {}
        pasos = PASOS.get(t.procedimiento, [(t.etapa, t.responsable)])
        ficha = {
            "id": t.id, "procedimiento": t.procedimiento,
            "procedimiento_nombre": extra.get("procedimiento_nombre"), "norma": extra.get("norma"),
            "eps": eps.nombre, "region": eps.region, "titulo": t.titulo,
            "estado": TEXTO_ESTADO.get(t.estado, t.estado),
            "paso_actual": f"{min(t.paso_actual, len(pasos))} de {len(pasos)} · {t.etapa}",
            "responsable_actual": t.responsable or "Ninguno",
            # Los casos con ficha documentada usan datos reales aunque su pantalla sea de demostración.
            "simulado": t.simulado,
            "resumen_ciudadano": extra.get("resumen_ciudadano"),
            "cifras": extra.get("cifras") or self._cifras_presentacion(t),
            "eventos": self._eventos(t, actor),
        }
        row=self.db.execute(text('SELECT canonical_id,base_normativa,monto_solicitado,monto_aprobado FROM procedimiento_fuente WHERE tramite_id=:id'),{'id':t.id}).mappings().first()
        if row:
            ficha['norma']=row['base_normativa']
            ficha['cifras']=[{'concepto':label,'tipo':kind,'valor':str(row[column]) if row[column] is not None else None,'fuente':row['canonical_id']}
                for label,kind,column in [('Monto solicitado','solicitado','monto_solicitado'),('Monto aprobado','autorizado','monto_aprobado')]]
        if actor.perfil == "sunass" and t.presentacion and t.presentacion.get("siguiente"):
            s = t.presentacion["siguiente"]
            ficha["siguiente_actuacion"] = {"titulo": s.get("titulo"), "detalle": s.get("detalle")}
        if actor.perfil == "eps" and t.ficha_eps:
            accion = t.ficha_eps.get("siguiente_accion")
            ficha["tu_siguiente_accion"] = None if not accion else {
                "titulo": accion["titulo"], "canal": accion["canal"], "fecha_limite": accion.get("fecha_limite"),
                "requisitos": [r["texto"] + (" (listo)" if r["preparado"] else " (falta)") for r in accion["requisitos"]],
                "instrucciones": accion.get("instrucciones")}
            ficha["respuesta_informada"] = t.ficha_eps.get("respuesta_informada")
        if actor.perfil == "publico":
            ficha = {k: ficha[k] for k in ("id", *CAMPOS_PUBLICOS) if k in ficha}
            ficha["cifras"] = [c for c in ficha.get("cifras") or [] if c.get("tipo") in
                               {"solicitado", "autorizado", "ejecutado"}]
        return ficha

    def _cifras_presentacion(self, t: Tramite) -> list[dict]:
        comparador = (t.presentacion or {}).get("comparador")
        if not comparador:
            return []
        cifras = [{"concepto": v["titulo"], "tipo": "solicitado", "valor": v["valor"],
                   "fuente": v["fuente"] if not v.get("sin_documento") else f"{v['fuente']} (sin documento)"}
                  for v in comparador.get("versiones", [])]
        return cifras + [{"concepto": "Ejecutado", "tipo": "ejecutado", "valor": None, "fuente": None}]

    def _eventos(self, t: Tramite, actor: Actor) -> list[dict]:
        acts = self.db.scalars(select(Actuacion).where(Actuacion.tramite_id == t.id).order_by(Actuacion.id))
        eventos = []
        for a in acts:
            if actor.perfil == "publico":
                continue
            if actor.perfil == 'eps':
                doc = self.db.get(Documento,a.documento_id) if a.documento_id else None
                if not doc or doc.visibilidad not in repo.VISIBLES['eps']:
                    continue
            eventos.append({"fecha": a.fecha_acreditada.isoformat() if a.fecha_acreditada else None,
                            "fecha_estado": "por_validar" if a.fecha_por_validar or not a.fecha_acreditada else "documento",
                            "hito": a.titulo + (f" — {a.detalle}" if a.detalle and actor.perfil=='sunass' else ""), "actor": a.actor,
                            "fuente": a.fuente or a.documento_id,
                            **({"verificada_por_sunass": False} if not a.verificada else {})})
        return eventos

    def consultar_plazo(self, actor: Actor, tramite_id: str) -> list[dict]:
        t = self._tramite(actor, tramite_id)
        if actor.perfil == "publico":
            return []
        p = plazos.calcular(self.db, t, self.hoy)
        salida = [{"capa": "procedimiento" if t.procedimiento != "RP" else f"etapa {p['etapa']}",
                   "regla": p["regla"], "fuente": p["fuente"], "dias_habiles_usados": p["dias_usados"],
                   "dias_habiles_totales": p["dias_totales"], "situacion": p["situacion"],
                   "fecha_limite": p["fecha_limite"], "estado": p["validacion"], "motivo": p["motivo"],
                   "calculado_al": self.hoy.isoformat()}]
        salida += plazos.plazos_del_expediente(t.ficha_agente)
        accion = (t.ficha_eps or {}).get("siguiente_accion")
        if accion and accion.get("fecha_limite"):
            limite = date.fromisoformat(accion["fecha_limite"])
            salida.append({"capa": "requerimiento a la EPS", "regla": accion.get("fecha_detalle"),
                           "fuente": accion.get("fuente_documento_id"), "fecha_limite": limite.isoformat(),
                           "dias_habiles_restantes": plazos.dias_habiles(self.hoy, limite),
                           "estado": "pendiente_de_validacion",
                           "motivo": "La fecha límite depende de la notificación acreditada del oficio."})
        return salida

    def listar_fuentes(self, actor: Actor, tramite_id: str) -> list[dict]:
        self._tramite(actor, tramite_id)
        frags = repo.fragmentos_visibles(self.db, actor, tramite_id)
        docs = {d.id: d for d in self.db.scalars(select(Documento).where(Documento.tramite_id == tramite_id))}
        return [{"documento_id": f.documento_id, "titulo": docs[f.documento_id].titulo, "fragmento_id": f.id,
                 "pagina_pdf": f.pagina_pdf, "texto": f.texto} for f in frags]

    def consultar_caso_publico(self, caso_id: str) -> dict:
        try:
            pub = repo.publicacion(self.db, caso_id)
        except NoEncontrado as e:
            raise SinAcceso("No encontramos esa decisión publicada.") from e
        return self.consultar_tramite(Actor(perfil="publico"), pub.tramite_id)

    def listar_fuentes_publicas(self, caso_id: str) -> list[dict]:
        try:
            pub = repo.publicacion(self.db, caso_id)
        except NoEncontrado as e:
            raise SinAcceso("No encontramos esa decisión publicada.") from e
        return self.listar_fuentes(Actor(perfil="publico"), pub.tramite_id)

    # -- caché ----------------------------------------------------------------
    def version(self, tramite_id: str) -> str:
        t = self.db.get(Tramite, tramite_id)
        docs=list(self.db.execute(select(Documento.id,Documento.visibilidad,Documento.estado_validacion).where(Documento.tramite_id==tramite_id).order_by(Documento.id)).all())
        pub=self.db.scalars(select(Publicacion).where(Publicacion.tramite_id==tramite_id)).first()
        base = json.dumps([t.version, t.huella_fuentes, t.estado, t.paso_actual, self.hoy.isoformat(),
                          [tuple(d) for d in docs],[pub.publicada,pub.resumen,pub.ficha] if pub else None],default=str,sort_keys=True) if t else "-"
        return hashlib.sha256(base.encode()).hexdigest()[:16]

    def cache_obtener(self, clave: str) -> dict | None:
        item = self.db.get(RespuestaCache, clave)
        if item is None:
            return None
        guardado = item.guardado if item.guardado.tzinfo else item.guardado.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - guardado > timedelta(hours=settings.cache_horas):
            return None
        return item.salida

    def cache_guardar(self, clave: str, tramite_id: str, salida: dict) -> None:
        limite = datetime.now(timezone.utc) - timedelta(hours=settings.cache_horas)
        self.db.execute(delete(RespuestaCache).where(RespuestaCache.guardado < limite))
        self.db.merge(RespuestaCache(clave=clave, tramite_id=tramite_id, salida=salida,
                                     guardado=datetime.now(timezone.utc)))
        self.db.commit()
