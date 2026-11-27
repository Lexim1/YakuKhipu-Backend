"""Localiza fuentes dentro del ámbito autorizado, sin inferencia ni conversaciones."""
from urllib.parse import quote

from sqlalchemy import text

from ..agent import retrieval
from ..auth.permisos import exigir
from ..models import Eps
from ..repositories import tramites as repo
from .documentos import enlace

INTENCION = set('busca buscar busco ubica ubicar localizar encuentra encontrar donde esta estan expediente expedientes documento documentos menciona mencionan necesito quiero saber favor por tiene lleva atiende cargo encargado'.split())


def palabras(consulta):
    return list(dict.fromkeys(w for w in retrieval.tokens(consulta) if w not in INTENCION))[:12]


def buscar(db, actor, consulta, limite=5):
    exigir(actor, 'agente.consultar')
    terms = palabras(consulta)
    salida = {'items': [], 'limite': limite, 'parcial': False, 'sin_inferencia': True,
              'nota': 'Coincidencias en registros y fuentes autorizadas. Abre el expediente para analizar su contenido.'}
    if not terms:
        return salida
    casos = repo.listar_tramites(db,actor)
    if not casos:
        return salida
    ids = [t.id for t in casos]
    refs = db.info.get('referencias',{})
    eps = db.info.get('eps_cache',{})
    responsables = {}
    if actor.perfil == 'sunass':
        responsables = dict(db.execute(text('''SELECT a.tramite_id,u.nombre_visible
            FROM asignacion_tramite a JOIN usuario u ON u.id=a.usuario_id
            WHERE a.fin IS NULL AND a.tramite_id=ANY(:ids)'''), {'ids':ids}).all())
    por_id = {}
    for t in casos:
        empresa = eps.get(t.eps_id) or db.get(Eps,t.eps_id)
        por_id[t.id] = {'tramite_id':t.id,'referencia':refs.get(t.id) or t.id,
            'titulo':t.titulo,'eps':empresa.nombre,'procedimiento':t.procedimiento,
            'estado':t.estado,'etapa':t.etapa,'responsable':t.responsable if actor.perfil=='sunass' else None,
            'analista':responsables.get(t.id),
            'enlace_expediente':('/sunass/expedientes/' if actor.perfil=='sunass' else '/eps/tramites/')+quote(t.id,safe=''),
            'fuentes':[]}
    metadatos = [{'texto':' '.join(str(r[k] or '') for k in ('tramite_id','referencia','titulo','eps','procedimiento','etapa','analista')),
                  'titulo':'','tramite_id':tid} for tid,r in por_id.items()]
    scores = {r['tramite_id']:score for score,r in retrieval.buscar(' '.join(terms),metadatos,len(casos))}
    # La consulta tsquery se construye solo con tokens alfanuméricos normalizados.
    # Los IDs autorizados y la visibilidad se aplican ANTES de recuperar texto.
    query = '|'.join(terms)
    params = {'ids':ids,'visibilidades':list(repo.VISIBLES[actor.perfil]),'q':query}
    paginas = list(db.execute(text('''SELECT f.tramite_id,f.documento_id,f.id AS fragmento_id,
        f.pagina_pdf,f.texto,d.titulo,
        ts_rank_cd(to_tsvector('spanish',coalesce(f.texto,'')),to_tsquery('spanish',:q)) AS rango
        FROM fragmento f JOIN documento d ON d.id=f.documento_id AND d.tramite_id=f.tramite_id
        JOIN registro_fuente r ON r.canonical_id=d.id AND r.presente
        WHERE f.tramite_id=ANY(:ids) AND d.visibilidad=ANY(:visibilidades) AND NOT f.requiere_ocr
        AND to_tsvector('spanish',coalesce(f.texto,'')) @@ to_tsquery('spanish',:q)
        ORDER BY rango DESC,f.id LIMIT 80'''),params).mappings())
    indices = list(db.execute(text('''SELECT d.tramite_id,d.id AS documento_id,d.titulo,
        ts_rank_cd(to_tsvector('spanish',coalesce(d.titulo,'')||' '||coalesce(d.referencia,'')),to_tsquery('spanish',:q)) AS rango
        FROM documento d JOIN registro_fuente r ON r.canonical_id=d.id AND r.presente
        WHERE d.tramite_id=ANY(:ids) AND d.visibilidad=ANY(:visibilidades)
        AND to_tsvector('spanish',coalesce(d.titulo,'')||' '||coalesce(d.referencia,'')) @@ to_tsquery('spanish',:q)
        ORDER BY rango DESC,d.id LIMIT 80'''),params).mappings())
    usados = set()
    for row in paginas+indices:
        tid,did=row['tramite_id'],row['documento_id']
        scores[tid] = max(scores.get(tid,0),1+float(row['rango']))
        if (tid,did) in usados or len(por_id[tid]['fuentes'])>=2:
            continue
        usados.add((tid,did))
        es_pagina = 'pagina_pdf' in row
        pagina = row['pagina_pdf'] if es_pagina else None
        por_id[tid]['fuentes'].append({'documento_id':did,'titulo':row['titulo'],
            'fragmento_id':row['fragmento_id'] if es_pagina else 'indice:'+did,'pagina_pdf':pagina,
            'extracto':retrieval.extracto(row['texto'],consulta,900)[:600] if es_pagina else 'Coincidencia en el título o número del documento; no se utilizó texto de una página.',
            'enlace':enlace(did,pagina,False),'tipo':'texto' if es_pagina else 'indice'})
    orden = sorted(scores,key=lambda tid:(-scores[tid],por_id[tid]['referencia'],tid))
    salida['items'] = [por_id[tid] for tid in orden[:limite]]
    salida['parcial'] = len(orden)>limite or len(paginas)==80 or len(indices)==80
    return salida
