"""Registro operativo y publicación explícita; nunca publica durante una importación."""
import hashlib
import json
import uuid
from sqlalchemy import select,text
from ..models import DocumentoRecibido,Documento,Publicacion,Eps
from ..repositories import tramites as repo
from ..core.errores import DatosInvalidos,Conflicto
from .tramites import FINALES,_nueva,_guardar
from .publico import proyectar
from ..auth.permisos import exigir


def recibir_documento(db,actor,datos,hoy,clave,pdf=None):
    exigir(actor, "recepcion.gestionar")
    if datos['fecha_documento']>hoy: raise DatosInvalidos('La fecha del documento no puede ser futura.')
    if db.get(Eps,datos['eps_id']) is None: raise DatosInvalidos('La EPS indicada no existe.')
    rid='sistema-doc:'+hashlib.sha256(f'{actor.usuario_id}:{clave}'.encode()).hexdigest()[:32]
    payload={**datos,'fecha_documento':datos['fecha_documento'].isoformat(),'id':rid,'registrado_por':actor.usuario_id}
    if pdf:
        payload["tiene_pdf"] = True
    serial=json.dumps(payload,ensure_ascii=False,sort_keys=True)
    previa=db.get(DocumentoRecibido,rid)
    if previa:
        if previa.datos!=payload: raise Conflicto('La clave de idempotencia ya corresponde a otro documento.')
        return {k:v for k,v in payload.items() if k!='texto'}
    digest=pdf["sha256"] if pdf else hashlib.sha256(serial.encode()).hexdigest()
    # Solo DML: conserva la procedencia de lo registrado manualmente.
    db.execute(text("INSERT INTO fuente(id,source_type,source_file,source_hash) VALUES (:id,'sistema','api/recepcion',:hash)"),{'id':rid,'hash':digest})
    db.execute(text('INSERT INTO lote_importacion(id,manifiesto) VALUES (:id,CAST(:datos AS jsonb))'),{'id':rid,'datos':serial})
    db.execute(text('''INSERT INTO registro_fuente(canonical_id,fuente_id,source_record_id,source_hash,lote_id,datos)
        VALUES (:id,:id,:id,:hash,:id,CAST(:datos AS jsonb))'''),{'id':rid,'hash':digest,'datos':serial})
    db.add(DocumentoRecibido(id=rid,datos=payload))
    if pdf:
        db.flush()
        db.execute(text("""INSERT INTO procesamiento_pdf (recepcion_id, clave, sha256, bytes)
            VALUES (:id,:clave,:sha256,:bytes)"""), {"id":rid, **pdf})
    db.commit()
    return {k:v for k,v in payload.items() if k!='texto'}


def publicar_decision(db,actor,tramite_id,datos,hoy):
    exigir(actor, "publicacion.gestionar")
    t=repo.obtener_tramite(db,actor,tramite_id,bloquear=True)
    if t.version!=datos['version']: raise Conflicto('El expediente cambió. Actualiza antes de publicar.')
    if t.estado not in FINALES: raise Conflicto('La decisión debe estar registrada antes de publicarla.')
    selected=[]
    for did in dict.fromkeys(datos['documentos_publicos']):
        doc=repo.obtener_documento(db,actor,did)
        if doc.tramite_id!=t.id: raise DatosInvalidos('Un documento seleccionado pertenece a otro expediente.')
        selected.append(doc)
    # La selección explícita de SUNASS acredita la revisión de visibilidad.
    for doc in db.scalars(select(Documento).where(Documento.tramite_id==t.id)):
        if doc.visibilidad=='publica' and doc.id not in datos['documentos_publicos']: doc.visibilidad='interna'
    for doc in selected: doc.visibilidad='publica'
    pub=db.scalars(select(Publicacion).where(Publicacion.tramite_id==t.id)).first()
    if pub is None:
        pub=Publicacion(id='decision-'+hashlib.sha256(t.id.encode()).hexdigest()[:24],tramite_id=t.id)
        db.add(pub)
    pub.resumen={'id':pub.id,'eps':db.get(Eps,t.eps_id).nombre,'localidad':datos['localidad'],
        'procedimiento':t.procedimiento,'titulo':datos['titulo'],'resumen_ciudadano':datos['resumen_ciudadano'],
        'estado_publico':'decision_publicada','simulado':t.simulado,'fecha_actualizacion':hoy.isoformat(),
        'documentos':[{'id':d.id,'titulo':d.titulo} for d in selected]}
    pub.ficha=None
    pub.publicada=True
    t.publicable=True
    act=_nueva(t,actor,'publicar','SUNASS publica una decisión revisada',{'documento_id':selected[0].id,'fecha_acreditada':hoy})
    _guardar(db,t,act)
    return proyectar(pub)


def retirar_publicacion(db,actor,tramite_id):
    exigir(actor, "publicacion.gestionar")
    t=repo.obtener_tramite(db,actor,tramite_id,bloquear=True)
    pub=db.scalars(select(Publicacion).where(Publicacion.tramite_id==t.id)).first()
    if pub: pub.publicada=False
    t.publicable=False
    _guardar(db,t,_nueva(t,actor,'retirar_publicacion','SUNASS retira la publicación',{}))
