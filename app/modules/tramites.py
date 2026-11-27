"""Reglas del negocio: vista SUNASS del expediente, acciones permitidas y transiciones.

Cada actuación se guarda junto con el nuevo estado en una sola transacción. La versión del trámite
evita aplicar dos veces una respuesta o perder cambios simultáneos (409).
"""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import date, datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from ..core.errores import AccesoDenegado, Conflicto, DatosInvalidos, NoEncontrado
from ..models import Actuacion, Alerta, DocumentoRecibido, Documento, Fragmento, Eps, Tramite, Usuario
from ..models.seguridad import Asignacion
from ..repositories import tramites as repo
from ..schemas.comun import Actor
from . import plazos
from ..auth.permisos import ACCIONES, exigir

# Pasos de cada procedimiento según los flujogramas del anexo del expediente.
PASOS: dict[str, list[tuple[str, str]]] = {
    "CPI": [("Solicitud", "EPS · Mesa de Partes"), ("Deriva a SRT", "DRE · meta 1 DH"), ("Asigna equipo", "SRT"),
            ("Verifica requisitos TUPA", "Equipo SRT"), ("Evalúa información", "Equipo SRT"),
            ("Informe y proyecto de resolución", "Equipo SRT"), ("Firma SRT y memo a GG", "SRT y DRE"),
            ("Resolución", "GG eleva · CD aprueba")],
    "UFI": [("Solicitud", "EPS · Mesa de Partes"), ("Deriva a SRT", "DRE · meta 1 DH"), ("Asigna equipo", "SRT"),
            ("Verifica requisitos TUPA", "Equipo SRT"), ("Evalúa información", "Equipo SRT"),
            ("Informe único", "SRT visa · OAJ y DRE firman"), ("Memo a GG", "DRE"),
            ("Eleva al CD", "Gerencia General"), ("Resolución", "Consejo Directivo")],
    "RP": [("Inicio", "EPS, DRE y SRT · máx. 30 DH"), ("Evaluación", "Equipo SRT · máx. 60 DH"),
           ("Difusión aprobada", "GG eleva · CD aprueba"), ("Audiencia pública", "Dirección de Usuarios · máx. 30 DH"),
           ("Comentarios", "EPS e interesados · hasta 15 DH"), ("Informe, estudio y proyecto final", "Equipo SRT"),
           ("Firma SRT y memo a GG", "SRT y DRE"), ("Resolución tarifaria", "GG eleva · CD aprueba")],
}
ENCABEZADO_FLUJO = {
    "CPI": "Flujograma · Cambio al programa de inversiones · Art. 93 RGT",
    "UFI": "Flujograma · Uso excepcional del fondo de inversiones · Art. 89 RGT",
    "RP": "Flujograma · Revisión periódica (estudio tarifario) · Arts. 45-49 RGT",
}
NOTA_FLUJO = {
    "CPI": "Plazo máximo: 30 días hábiles (Art. 93 RGT). Metas internas del anexo: subsanación TUPA máx. 2 DH · "
           "información adicional hasta 10 DH · evaluación en SRT 24 DH · firma y decisión (DRE, GG y CD) 5 DH. "
           "Si no subsana, se cierra el procedimiento.",
    "UFI": "Plazo máximo: 30 días hábiles (Art. 89 RGT). Metas internas del anexo: subsanación TUPA máx. 2 DH · "
           "información adicional hasta 10 DH · evaluación 24 DH · firma y decisión 5 DH. El informe es único: "
           "SRT visa, OAJ y DRE firman.",
    "RP": "Metas por etapa del flujograma: inicio 30 DH · evaluación 60 DH · difusión 45 DH desde el día siguiente "
          "de la publicación en El Peruano · aprobación 60 DH.",
}
ESTADOS = {"en_evaluacion", "requiere_respuesta", "requiere_subsanacion", "en_consulta", "autorizado",
           "no_autorizado", "concluido"}
FINALES = {"autorizado", "no_autorizado", "concluido"}
TEXTO_ESTADO = {"en_evaluacion": "En evaluación", "requiere_respuesta": "Requiere respuesta de la EPS",
                "requiere_subsanacion": "Requiere subsanación", "en_consulta": "En consulta pública",
                "autorizado": "Autorizado", "no_autorizado": "No autorizado", "concluido": "Concluido"}
TIPOS_SEMILLA = {"hito"}  # actuaciones cargadas desde los documentos; ya forman parte de la presentación


# ---------------------------------------------------------------- lectura

def _eps(db: Session, t: Tramite) -> Eps:
    return getattr(db,'info',{}).get('eps_cache',{}).get(t.eps_id) or db.get(Eps, t.eps_id)


def resumen(db: Session, t: Tramite, hoy: date) -> dict:
    p = plazos.calcular(db, t, hoy)
    if t.estado in FINALES: p={**p,'situacion':'concluido'}
    eps = _eps(db, t)
    cache=getattr(db,'info',{}).get('referencias')
    referencia=cache.get(t.id) if cache is not None else None
    if cache is None and hasattr(db,'info'):
        referencia=db.execute(text("""SELECT coalesce(p.id_expediente,r.datos->>'referencia',r.datos->>'expediente')
            FROM registro_fuente r LEFT JOIN procedimiento_fuente p ON p.tramite_id=r.canonical_id WHERE r.canonical_id=:id"""),{'id':t.id}).scalar()
    return {"id": t.id, "referencia":referencia, "estado":t.estado,"procedimiento": t.procedimiento, "eps": eps.nombre, "tamano_eps": eps.tamano or "Mediana",
            "etapa": t.etapa, "responsable": t.responsable or "Sin asignar",
            "plazo": {k: p[k] for k in ("situacion", "dias_usados", "dias_totales", "etapa")},
            "simulado": t.simulado}


def _actuaciones(db: Session, t: Tramite, nuevas: bool = False) -> list[Actuacion]:
    consulta = select(Actuacion).where(Actuacion.tramite_id == t.id).order_by(Actuacion.id)
    lista = list(db.scalars(consulta))
    return [a for a in lista if a.tipo not in TIPOS_SEMILLA] if nuevas else lista


def flujo(t: Tramite, base: dict | None, p: dict) -> dict:
    if t.procedimiento not in PASOS:
        return {"encabezado": t.procedimiento, "titulo": t.etapa, "chip": plazos.texto_chip(p),
                "pasos": [], "nota": "Procedimiento conservado del dataset. Flujo operativo aún no configurado."}
    pasos = PASOS[t.procedimiento]
    actual = min(max(t.paso_actual, 1), len(pasos)) - 1
    semilla = (base or {}).get("pasos") or []
    misma_posicion = (base or {}).get("_paso") == t.paso_actual
    salida = []
    for i, (titulo, detalle) in enumerate(pasos):
        estado = "hecho" if i < actual or t.estado in FINALES else "actual" if i == actual else "pendiente"
        nota = "✓ Hecho" if estado == "hecho" else "Aquí está" if estado == "actual" else "Pendiente"
        if misma_posicion and i < len(semilla):
            detalle, nota = semilla[i]["detalle"], semilla[i]["nota"]
        salida.append({"titulo": titulo, "detalle": detalle, "estado": estado, "nota": nota})
    texto_situacion = {"en_plazo": "en plazo", "por_vencer": "por vencer", "vencido": "vencido",
                       "concluido": "concluido", "pendiente_de_validacion": "pendiente de validación"}[p["situacion"]]
    if t.estado in FINALES:
        titulo, chip = f"Procedimiento {TEXTO_ESTADO[t.estado].lower()}", plazos.texto_chip(p)
    else:
        titulo = (base or {}).get("titulo") if misma_posicion else None
        titulo = titulo or f"Paso {actual + 1} de {len(pasos)} · Lo tiene {t.responsable or 'sin asignar'}"
        chip = plazos.texto_chip(p)
    return {"encabezado": ENCABEZADO_FLUJO[t.procedimiento], "titulo": titulo, "chip": chip,
            "pasos": salida, "nota": (base or {}).get("nota") or NOTA_FLUJO[t.procedimiento]}


def _siguiente_generico(t: Tramite) -> dict:
    if t.estado in FINALES:
        return {"titulo": "Seguimiento de la ejecución", "detalle": "El procedimiento concluyó. Falta el reporte de "
                "ejecución de la EPS.", "responsable": None, "boton": "Ver alertas de plazo", "accion": "alertas",
                "urgente": False}
    if t.estado in {"requiere_respuesta", "requiere_subsanacion"}:
        return {"titulo": "Esperar la respuesta de la EPS", "detalle": "La EPS tiene un requerimiento pendiente.",
                "responsable": "EPS", "boton": "Ver alertas de plazo", "accion": "alertas", "urgente": False}
    return {"titulo": f"Continuar: {t.etapa}", "detalle": "Registra la actuación con su documento de sustento.",
            "responsable": t.responsable, "boton": "Registrar actuación", "accion": "registrar", "urgente": False}


def _historial(actuaciones: list[Actuacion]) -> list[dict]:
    return [{"fecha_texto": plazos.fecha_corta(a.fecha_acreditada) if a.fecha_acreditada else 'Fecha por acreditar', "titulo": a.titulo,
             "detalle": a.detalle or "", "actual": i == len(actuaciones) - 1} for i, a in enumerate(actuaciones)]


def _hito(a: Actuacion) -> dict:
    por_verificar = not a.verificada
    return {"id": f"a{a.id}", "fecha_texto": plazos.fecha_corta(a.fecha_acreditada) if a.fecha_acreditada else 'Fecha por acreditar',
            "titulo": a.titulo, "detalle": a.detalle or "",
            "chip": {"texto": "Por verificar" if por_verificar else "Registrado", "tono": "aviso" if por_verificar else "ok"},
            "fuente": a.documento_id, "validar": False}


def expediente(db: Session, t: Tramite, hoy: date) -> dict:
    """Ficha interna para SUNASS. Los plazos y el flujograma se calculan; el resto viene de la base."""
    from .datos import proyeccion
    base = proyeccion(db, t)
    p = plazos.calcular(db, t, hoy)
    nuevas = _actuaciones(db, t, nuevas=True)
    salida = {
        **resumen(db, t, hoy),
        "tema": base.get("tema") or t.titulo,
        "chip_plazo": plazos.texto_chip(p),
        "flujo": flujo(t, base.get("flujo"), p),
        "siguiente": base.get("siguiente") or _siguiente_generico(t),
        "linea_tiempo": base.get("linea_tiempo"),
        "resumen": base.get("resumen"),
        "comparador": base.get("comparador"),
        "plazos": base.get("plazos"),
        "impacto": base.get("impacto"),
        "vinculo": base.get("vinculo"),
        "historial": base.get("historial"),
        "estado": t.estado,
        "version": t.version,
        "plazo_detalle": p,
        "documentos": base.get("documentos", []),
    }
    if _presentacion_pendiente(db,t):
        salida['siguiente']={'titulo':'Verificar la respuesta de la EPS','detalle':'Confirma la recepción y el contenido del documento.',
                             'responsable':t.responsable,'boton':'Verificar respuesta','accion':'verificar_respuesta','urgente':True}
    if salida["linea_tiempo"] is not None:
        salida["linea_tiempo"] = [h for h in salida["linea_tiempo"] if h.get("fecha_texto") != "Próximo"] + \
            [_hito(a) for a in nuevas] + [h for h in salida["linea_tiempo"] if h.get("fecha_texto") == "Próximo"]
    elif salida["historial"] is not None:
        salida["historial"] = [{**h, "actual": False} for h in salida["historial"]] + _historial(nuevas) \
            if nuevas else salida["historial"]
    else:
        salida["historial"] = _historial(_actuaciones(db, t))
    return salida


def eventos(db: Session, t: Tramite) -> list[dict]:
    return [{"id": a.id, "tipo": a.tipo, "titulo": a.titulo, "detalle": a.detalle, "actor": a.actor,
             "fecha": a.fecha_acreditada.isoformat() if a.fecha_acreditada else None,
             "fecha_por_validar": a.fecha_por_validar, "documento_id": a.documento_id, "fuente": a.fuente,
             "verificada": a.verificada, "estado_destino": a.estado_destino} for a in _actuaciones(db, t)]


# ---------------------------------------------------------------- acciones y transiciones

def _presentacion_pendiente(db: Session, t: Tramite) -> Actuacion | None:
    consulta = select(Actuacion).where(Actuacion.tramite_id == t.id, Actuacion.tipo == "informar_presentacion",
                                       Actuacion.verificada.is_(False))
    return db.scalars(consulta).first()


def acciones(db: Session, actor: Actor, t: Tramite) -> list[dict]:
    return [a for a in _acciones_estado(db, actor, t) if _puede_registrar(actor, t, a["tipo"])]


def _puede_registrar(actor: Actor, t: Tramite, tipo: str) -> bool:
    # El analista documenta la evaluación interna; derivaciones, firmas y resoluciones
    # externas siguen siendo actuaciones de Coordinación/Jefatura DRE.
    if tipo == 'avanzar_paso' and 'acto_externo.registrar' in actor.permisos:
        return True
    internos = {'CPI': {4, 5, 6}, 'UFI': {4, 5}, 'RP': {2, 6, 7}}
    if tipo == 'avanzar_paso' and t.paso_actual + 1 in internos.get(t.procedimiento, set()):
        return 'evaluacion.validar' in actor.permisos
    return ACCIONES.get(tipo) in actor.permisos


def _acciones_estado(db: Session, actor: Actor, t: Tramite) -> list[dict]:
    """Acciones que este usuario puede registrar ahora, según el estado y el paso."""
    if t.etapa == 'Estado documental pendiente de validación' and actor.perfil=='sunass':
        return [{'tipo':'validar_expediente','texto':'Validar estado con evidencia documental','requiere_documento':True}]
    if t.estado in FINALES or t.procedimiento not in PASOS:
        return []
    if actor.perfil == "eps":
        ficha = t.ficha_eps or {}
        return [{"tipo": "informar_presentacion", "texto": "Informar que presentaste tu respuesta",
                 "requiere_documento": True}] if ficha.get("siguiente_accion") else []
    lista = []
    if (t.presentacion or {}).get("vinculo"):
        lista.append({"tipo": "confirmar_vinculo", "texto": "Confirmar el vínculo propuesto", "requiere_documento": False})
    pendiente = _presentacion_pendiente(db, t)
    if pendiente:
        lista.append({"tipo": "verificar_respuesta", "texto": "Verificar la respuesta de la EPS",
                      "requiere_documento": not bool(pendiente.documento_id)})
        return lista
    if t.estado in {"en_evaluacion","en_consulta"}:
        if t.paso_actual < len(PASOS[t.procedimiento]):
            siguiente = PASOS[t.procedimiento][t.paso_actual][0]
            lista.append({"tipo": "avanzar_paso", "texto": f"Pasar a «{siguiente}»", "requiere_documento": True})
        else:
            lista.append({"tipo": "resolver", "texto": "Registrar la resolución", "requiere_documento": True})
        lista.append({"tipo": "requerir_informacion", "texto": "Requerir información a la EPS",
                      "requiere_documento": True})
        lista.append({'tipo':'requerir_subsanacion','texto':'Solicitar subsanación','requiere_documento':True})
    return lista


def _repetida(db: Session, t: Tramite, clave: str | None) -> Actuacion | None:
    if not clave:
        return None
    return db.scalars(select(Actuacion).where(Actuacion.tramite_id == t.id,
                                              Actuacion.clave_idempotencia == clave)).first()


def huella_peticion(datos):
    return hashlib.sha256(json.dumps(datos,sort_keys=True,default=str,ensure_ascii=False).encode()).hexdigest()


def _guardar(db: Session, t: Tramite, actuacion: Actuacion) -> None:
    t.version += 1
    db.add(actuacion)
    try:
        db.commit()
    except (StaleDataError, IntegrityError) as e:
        db.rollback()
        raise Conflicto("El trámite cambió mientras trabajabas. Actualiza la página.") from e
    db.refresh(t)


def _nueva(t: Tramite, actor: Actor, tipo: str, titulo: str, datos: dict, destino: str | None = None,
           paso: int | None = None, verificada: bool = True, clave: str | None = None) -> Actuacion:
    return Actuacion(tramite_id=t.id, tipo=tipo, titulo=titulo, detalle=datos.get("detalle"),
                     fecha_acreditada=datos.get("fecha_acreditada"), documento_id=datos.get("documento_id"),
                     usuario_id=actor.usuario_id, actor="EPS" if actor.perfil == "eps" else "SUNASS",
                     estado_origen=t.estado, estado_destino=destino or t.estado, paso_origen=t.paso_actual,
                     paso_destino=paso or t.paso_actual, verificada=verificada, clave_idempotencia=clave)


def registrar(db: Session, actor: Actor, tramite_id: str, datos: dict, clave: str | None, hoy: date) -> dict:
    """POST /api/tramites/{id}/eventos. Aplica una transición permitida y devuelve el expediente actualizado."""
    t = repo.obtener_tramite(db, actor, tramite_id, bloquear=True)
    if not _puede_registrar(actor, t, datos["tipo"]):
        raise AccesoDenegado('No tienes permiso para esta actuación.')
    previa=_repetida(db,t,clave)
    if previa:
        if previa.peticion_hash!=huella_peticion(datos):
            raise Conflicto('La clave de idempotencia ya corresponde a otra petición.')
        return expediente(db, t, hoy)
    if datos.get("version") is not None and datos["version"] != t.version:
        raise Conflicto("El trámite cambió mientras trabajabas. Actualiza la página.")
    tipo = datos["tipo"]
    permitidas = {a["tipo"]: a for a in acciones(db, actor, t)}
    if tipo not in permitidas:
        raise Conflicto("Esa acción no está permitida en el estado actual del trámite.")
    if permitidas[tipo]["requiere_documento"] and not datos.get("documento_id"):
        raise DatosInvalidos("Esta actuación necesita su documento de sustento.")
    if permitidas[tipo]['requiere_documento'] and not datos.get('fecha_acreditada'):
        raise DatosInvalidos('Indica la fecha acreditada en el documento de sustento.')
    if datos.get("documento_id"):
        doc = repo.obtener_documento(db, actor, datos["documento_id"])
        if doc.tramite_id != t.id:
            raise DatosInvalidos("El documento pertenece a otro expediente.")
    if datos.get("fecha_acreditada") and datos["fecha_acreditada"] > hoy:
        raise DatosInvalidos("La fecha acreditada no puede ser futura.")
    presentacion = copy.deepcopy(t.presentacion) if t.presentacion else None
    fecha = datos.get("fecha_acreditada") or hoy

    if tipo == 'validar_expediente':
        estado = datos.get('estado_validado')
        paso = datos.get('paso_validado')
        if not estado or not paso or paso>len(PASOS[t.procedimiento]) or not datos.get('fecha_acreditada'):
            raise DatosInvalidos('Indica estado, paso y fecha acreditada en el documento.')
        if estado in FINALES and paso!=len(PASOS[t.procedimiento]):
            raise DatosInvalidos('Un estado final debe corresponder al último paso del procedimiento.')
        act = _nueva(t, actor, tipo, 'Estado validado con documento', datos, destino=estado, paso=paso, clave=clave)
        t.estado,t.paso_actual,t.etapa = estado,paso,PASOS[t.procedimiento][paso-1][0]
        t.responsable = None if estado in FINALES else PASOS[t.procedimiento][paso-1][1]
        if estado in FINALES: t.fecha_fin=fecha
    elif tipo == "avanzar_paso":
        nuevo = t.paso_actual + 1
        titulo, responsable = PASOS[t.procedimiento][nuevo - 1]
        act = _nueva(t, actor, tipo, datos.get("titulo") or f"Pasa a «{titulo}»", datos, paso=nuevo, clave=clave)
        if t.procedimiento == "RP" and plazos.ETAPA_RP[nuevo] != plazos.ETAPA_RP[t.paso_actual]:
            t.fecha_inicio_etapa = fecha
        t.paso_actual, t.etapa, t.responsable = nuevo, titulo, responsable.split(" · ")[0]
        t.estado='en_consulta' if t.procedimiento=='RP' and nuevo in (4,5) else 'en_evaluacion'
        act.estado_destino=t.estado
        if presentacion:
            presentacion["siguiente"] = None
    elif tipo == "resolver":
        resultado = datos.get("resultado")
        if resultado not in {"autorizado", "no_autorizado"}:
            raise DatosInvalidos("El resultado debe ser autorizado o no_autorizado.")
        act = _nueva(t, actor, tipo, datos.get("titulo") or f"Resolución: {TEXTO_ESTADO[resultado].lower()}", datos,
                     destino=resultado, clave=clave)
        t.estado, t.fecha_fin, t.responsable = resultado, fecha, None
        if presentacion:
            presentacion["siguiente"] = None
        _ficha_eps_cierre(t, resultado, fecha)
    elif tipo in {"requerir_informacion","requerir_subsanacion"}:
        if datos.get('plazo_dias') is None:
            raise DatosInvalidos('Indica el plazo expresamente señalado en el oficio.')
        dias = int(datos['plazo_dias'])
        act = _nueva(t, actor, tipo, datos.get("titulo") or ('Requerimiento de subsanación' if tipo=='requerir_subsanacion' else 'Requerimiento de información'), datos,
                     destino="requiere_respuesta", clave=clave)
        t.estado = "requiere_respuesta"
        if tipo=='requerir_subsanacion':
            t.estado='requiere_subsanacion'
            act.estado_destino=t.estado
        _ficha_eps_requerimiento(t, datos, fecha, dias, hoy)
        if tipo=='requerir_subsanacion':
            t.ficha_eps={**t.ficha_eps,'estado':t.estado,'siguiente_accion':{**t.ficha_eps['siguiente_accion'],'etiqueta':'Subsanación'}}
        if presentacion:
            presentacion["siguiente"] = None
    elif tipo == "verificar_respuesta":
        pendiente = _presentacion_pendiente(db, t)
        if not pendiente.documento_id:
            pendiente.documento_id = datos['documento_id']
        pendiente.verificada = True
        act = _nueva(t, actor, tipo, datos.get("titulo") or "SUNASS verifica la respuesta de la EPS", datos, clave=clave)
        if t.ficha_eps and t.ficha_eps.get("respuesta_informada"):
            ficha = copy.deepcopy(t.ficha_eps)
            ficha["respuesta_informada"]["verificada"] = True
            t.ficha_eps = ficha
        if presentacion:
            presentacion["siguiente"] = None
    elif tipo == "confirmar_vinculo":
        act = _nueva(t, actor, tipo, "Vínculo confirmado", datos,
                     clave=clave)
        presentacion = _aplicar_vinculo(presentacion)
    else:  # pragma: no cover - acciones() ya lo filtró
        raise DatosInvalidos("Acción desconocida.")
    if presentacion is not None:
        t.presentacion = presentacion
    act.peticion_hash=huella_peticion(datos)
    _guardar(db, t, act)
    return expediente(db, t, hoy)


def _aplicar_vinculo(p: dict) -> dict:
    p["vinculo"] = None
    if p.get("linea_tiempo"):
        for h in p["linea_tiempo"]:
            if h.get("validar"):
                h["validar"], h["chip"] = False, {"texto": "Vínculo confirmado", "tono": "ok"}
    p["siguiente"] = p.pop("siguiente_tras_vinculo", None)
    return p


def _ficha_eps_requerimiento(t: Tramite, datos: dict, fecha: date, dias: int, hoy: date) -> None:
    ficha = copy.deepcopy(t.ficha_eps) if t.ficha_eps else None
    if ficha is None:
        ficha = {"id": t.id, "procedimiento": t.procedimiento, "titulo": t.titulo,
                 "simulado": t.simulado, "seguimiento": [], "documentos": []}
    # Fecha del oficio no acredita notificación; no inventar vencimiento.
    limite = None
    requisitos = [{"id": f"r{i}", "texto": r, "preparado": False} for i, r in enumerate(datos.get("requisitos") or [], 1)]
    ficha.update({
        "estado": "requiere_respuesta", "estado_texto": "Necesitamos tu respuesta",
        "resumen": datos.get("detalle") or "Sunass necesita información adicional para evaluar tu solicitud.",
        "aviso": None, "respuesta_informada": None,
        "siguiente_accion": {
            "tipo": "informar_presentacion", "etiqueta": "Respuesta",
            "titulo": f"Responde el {datos.get('documento_id')}", "texto": "Preparar respuesta",
            "instrucciones": None if requisitos else datos.get("detalle"),
            "canal": "Mesa de Partes Virtual de Sunass", "fecha_limite": None,
            "fecha_texto": 'Por validar', "fecha_detalle": f"{dias} días hábiles; falta acreditar la notificación y el calendario",
            "dias_restantes": None, "fuente_documento_id": datos.get("documento_id"),
            "requisitos": requisitos,
        },
    })
    seguimiento = [{**s, "estado": "hecho"} if s["estado"] == "actual" else s for s in ficha.get("seguimiento", [])
                   if s["estado"] != "pendiente"]
    ficha["seguimiento"] = seguimiento + [
        {"titulo": "Sunass te pidió información", "fecha_texto": plazos.fecha_corta(fecha), "estado": "hecho"},
        {"titulo": f"Tu respuesta al {datos.get('documento_id')}", "fecha_texto": 'Vencimiento pendiente de validación',
         "estado": "actual"},
        {"titulo": "Decisión del Consejo Directivo", "fecha_texto": "Te avisaremos cuando se publique",
         "estado": "pendiente"}]
    t.ficha_eps = ficha


def _ficha_eps_cierre(t: Tramite, resultado: str, fecha: date) -> None:
    if not t.ficha_eps:
        return
    ficha = copy.deepcopy(t.ficha_eps)
    ficha.update({"estado": resultado, "estado_texto": TEXTO_ESTADO[resultado], "siguiente_accion": None,
                  "resumen": f"El Consejo Directivo resolvió tu solicitud el {plazos.fecha_corta(fecha)}."})
    ficha["seguimiento"] = [{**s, "estado": "hecho"} for s in ficha.get("seguimiento", [])]
    t.ficha_eps = ficha


# ---------------------------------------------------------------- recepción y alertas

def listar_recepcion(db: Session) -> list[dict]:
    from .archivos_pdf import estado
    salida = []
    consulta = select(DocumentoRecibido).where(DocumentoRecibido.incorporado_a.is_(None)).order_by(DocumentoRecibido.id)
    for recibido in db.scalars(consulta):
        item = {k:v for k,v in recibido.datos.items() if k not in ('texto', 'tiene_pdf')}
        if recibido.datos.get("tiene_pdf"):
            trabajo = estado(db, recibido.id)
            if trabajo:
                item["procesamiento_pdf"] = trabajo
        salida.append(item)
    return salida


def cambiar_asignacion(db: Session, actor: Actor, t: Tramite, usuario_id: str, motivo: str) -> bool:
    exigir(actor, "asignacion.gestionar")
    usuario = db.get(Usuario, usuario_id)
    if usuario is None or not usuario.activo or usuario.rol_id != "analista_srt":
        raise DatosInvalidos("La asignación requiere un Analista SRT activo.")
    anterior = db.scalars(select(Asignacion).where(
        Asignacion.tramite_id == t.id, Asignacion.fin.is_(None),
    )).first()
    if anterior and anterior.usuario_id == usuario.id:
        return False
    ahora = datetime.now(timezone.utc)
    if anterior:
        anterior.fin = ahora
        db.flush()
    db.add(Asignacion(tramite_id=t.id, usuario_id=usuario.id, asignado_por=actor.usuario_id,
                      inicio=ahora, fin=None, motivo=motivo))
    t.responsable = usuario.nombre_visible
    return True


def recepcion_pendiente(db: Session, actor: Actor, documento_id: str) -> DocumentoRecibido:
    exigir(actor, "recepcion.gestionar")
    recibido = db.get(DocumentoRecibido, documento_id, with_for_update=True)
    if recibido is None or recibido.incorporado_a:
        raise NoEncontrado("El documento ya fue incorporado o no existe.")
    return recibido


def incorporar(db: Session, actor: Actor, datos: dict, hoy: date) -> None:
    recibido = recepcion_pendiente(db, actor, datos["documento_id"])
    t = repo.obtener_tramite(db, actor, datos["tramite_id"], bloquear=True)
    if t.estado in FINALES:
        raise Conflicto("El trámite ya concluyó.")
    if datos['version']!=t.version:
        raise Conflicto('El trámite cambió. Actualiza antes de incorporar el documento.')
    if recibido.datos.get('eps_id')!=t.eps_id:
        raise DatosInvalidos('El documento recibido corresponde a otra EPS.')
    incorporar_en_tramite(db, actor, recibido, t, datos["tipo_actuacion"], datos.get("asignado_a"))


def incorporar_en_tramite(db: Session, actor: Actor, recibido: DocumentoRecibido, t: Tramite,
                          motivo: str, analista_id: str | None, fecha_ingreso: date | None = None) -> None:
    tiene_pdf = recibido.datos.get("tiene_pdf", False)
    paginas = [{"texto": recibido.datos["texto"], "origen": "texto_registrado_mesa_partes"}]
    if tiene_pdf:
        from .archivos_pdf import estado
        trabajo = estado(db, recibido.id, incluir_texto=True)
        if not trabajo or trabajo["estado"] != "listo":
            raise Conflicto("El PDF debe terminar de procesarse antes de incorporarlo.")
        paginas = trabajo["paginas"]
    doc=Documento(id=recibido.id,tramite_id=t.id,titulo=recibido.datos['titulo'],referencia=recibido.datos['referencia'],
                  visibilidad='interna' if tiene_pdf else 'partes', estado_validacion='por_validar',simulado=False,
                  paginas=len(paginas), archivo="bucket:original" if tiene_pdf else None)
    db.add(doc)
    db.flush()
    for numero, pagina in enumerate(paginas, 1):
        db.add(Fragmento(id=f'{doc.id}-p{numero}', documento_id=doc.id, tramite_id=t.id, pagina_pdf=numero,
                        texto=pagina["texto"], requiere_ocr=not bool(pagina["texto"]),
                        metadatos={"origen": pagina["origen"]}))
    recibido.incorporado_a = t.id
    if tiene_pdf:
        db.flush()
        db.execute(text("""INSERT INTO propuesta_agente(documento_id,tramite_id)
            VALUES (:documento,:tramite)"""), {"documento":doc.id,"tramite":t.id})
    if fecha_ingreso:
        db.add(_nueva(t, actor, "recepcion_mesa_partes", "Ingreso registrado por Mesa de Partes",
                      {"detalle": doc.referencia, "fecha_acreditada": fecha_ingreso, "documento_id": doc.id}))
    act = _nueva(t, actor, "incorporar_documento", f"Se incorpora {recibido.datos.get('titulo', 'un documento')}",
                 {"detalle": motivo,
                  "fecha_acreditada": date.fromisoformat(recibido.datos['fecha_documento']), "documento_id": recibido.id})
    if analista_id and cambiar_asignacion(db, actor, t, analista_id, motivo):
        db.add(_nueva(t, actor, "asignar", "Asignación de expediente", {"detalle": motivo, "documento_id": doc.id}))
    _guardar(db, t, act)


def listar_alertas(db: Session, hoy: date, actor: Actor) -> list[dict]:
    """Alertas registradas y, además, las de plazo que el sistema calcula hoy."""
    registradas = [a for a in db.scalars(select(Alerta).where(Alerta.atendida.is_(False)).order_by(Alerta.id))]
    visibles = {t.id for t in repo.listar_tramites(db, actor)}
    salida = [a.datos for a in registradas if a.tramite_id in visibles]
    cubiertas = {(a.tramite_id, a.datos.get("tipo")) for a in registradas}
    for t in repo.listar_tramites(db, actor):
        if t.estado in FINALES:
            continue
        p = plazos.calcular(db, t, hoy)
        if p["validacion"] == "validado" and p["situacion"] in {"vencido", "por_vencer"} and (t.id, p["situacion"]) not in cubiertas:
            exceso = p["dias_usados"] - p["dias_totales"]
            detalle = (f"Superó el plazo por {exceso} días hábiles." if exceso > 0 else
                       f"Quedan {-exceso} días hábiles.")
            salida.append({"id": f"calc-{t.id}", "tipo": p["situacion"],
                           "titulo": f"{t.id} · {'vencido' if exceso > 0 else 'por vencer'}", "detalle": detalle,
                           "regla": p["regla"] or "", "fuente": p["fuente"] or "",
                           "destino": {"tipo": "expediente", "id": t.id, "pestana": "plazos"},
                           "accion": "Abrir expediente"})
    from .calidad import listar
    salida.extend(listar(db, repo.listar_tramites(db, actor)))
    return salida
