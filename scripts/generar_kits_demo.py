"""Kits por expediente desde los originales del sprint; nunca fabrica solicitudes o resoluciones.

Uso: python -m scripts.generar_kits_demo --datasets RUTA --actualizacion RUTA --salida RUTA
--transcribir-hitos requiere reportlab (solo para esta utilidad local, no para el servidor).
"""
import argparse, csv, hashlib, io, json, re, zipfile
from collections import Counter, defaultdict
from pathlib import Path
from xml.sax.saxutils import escape
from pypdf import PdfReader, PdfWriter
from scripts.importar_d3 import merge_rows, UPDATES, KEYS
from scripts.generar_sql import identity, PROCS
from scripts.documentos_sprint import agrupar_documentos

PASOS={
 'CPI':['Solicitud','Deriva a SRT','Asigna equipo','Verifica requisitos TUPA','Evalúa información','Informe y proyecto de resolución','Firma SRT y memo a GG','Resolución'],
 'UFI':['Solicitud','Deriva a SRT','Asigna equipo','Verifica requisitos TUPA','Evalúa información','Informe único','Memo a GG','Eleva al CD','Resolución'],
 'RP':['Inicio','Evaluación','Difusión aprobada','Audiencia pública','Comentarios','Informe, estudio y proyecto final','Firma SRT y memo a GG','Resolución tarifaria'],
}
SUPLEMENTOS={'verificacion_tupa','evaluacion','evaluacion_requisitos','firma_informe','visado_informe','firma_informe_dre','firma_informe_oaj','elevacion_cd','firma_informe_inicio','firma_informe_difusion','firma_informe_final','elevacion_cd_difusion','elevacion_cd_final'}

def cargar(path):
 with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def sha(blob):return hashlib.sha256(blob).hexdigest()
def escribir_csv(path,rows,columns=None):
 if columns is None:columns=list(rows[0]) if rows else []
 with path.open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=columns);w.writeheader();w.writerows(rows)
def pdf_extraido(pages,path):
 w=PdfWriter()
 for page,_,_ in pages:w.add_page(page)
 stream=io.BytesIO();w.write(stream);raw=stream.getvalue();path.write_bytes(raw)
 assert [p.extract_text() for p in PdfReader(io.BytesIO(raw)).pages]==[t for _,t,_ in pages]
 return sha(raw)
def transcribir(act,path,case):
 from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer
 from reportlab.lib.styles import getSampleStyleSheet
 from reportlab.lib.pagesizes import A4
 styles=getSampleStyleSheet();styles['BodyText'].fontSize=10;styles['BodyText'].leading=15
 paragraphs=[('Registro de hito DS10','Title'),(case+' · FICTICIO','Heading2'),
  ('Transcripción del dataset de práctica. No es un documento original firmado, una solicitud ni una resolución.','BodyText'),
  (act['id_actuacion']+' · '+(act['fecha_actuacion'] or 'Fecha no acreditada'),'Heading2'),
  (act['descripcion'],'BodyText'),(act['area']+' · '+act['responsable'],'BodyText'),
  ('Fuente: ds10_bitacora_actuaciones.csv y su actualización al 20/11/2026; fila '+act['id_actuacion']+'.','BodyText')]
 story=[]
 for text,style in paragraphs:story.extend([Paragraph(escape(text),styles[style]),Spacer(1,12)])
 SimpleDocTemplate(str(path),pagesize=A4,rightMargin=42,leftMargin=42,topMargin=42,bottomMargin=42).build(story)

def rol(tipo):
 if tipo in ('subsanacion_ep','informacion_ep','comentarios'):return 'EPS; Coordinación incorpora; analista verifica'
 if tipo=='solicitud':return 'EPS de origen; Jefatura registra ingreso'
 if tipo=='asignacion':return 'Coordinación asigna al analista'
 if tipo in ('verificacion_tupa','evaluacion','evaluacion_requisitos','informe','proyecto_estudio','evaluacion_comentarios'):return 'Analista'
 if tipo.startswith('oficio_'):return 'Analista registra requerimiento con oficio compartido por Coordinación'
 return 'Jefatura o Coordinación registra el acto externo acreditado'

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--datasets',type=Path,required=True);ap.add_argument('--actualizacion',type=Path);ap.add_argument('--salida',type=Path,required=True);ap.add_argument('--transcribir-hitos',action='store_true');ap.add_argument('--portal-origin',default='');a=ap.parse_args()
 a.salida.mkdir(parents=True,exist_ok=True)
 sources={};tables={}
 for stem in ['ds01_catalogo_eps','ds02_procedimientos','ds02_hitos_procedimientos','ds10_bitacora_actuaciones','ds11_indice_documentos']:
  p=a.datasets/(stem+'.csv');rows=cargar(p);sources[str(p)]=sha(p.read_bytes())
  if a.actualizacion and stem in UPDATES:
   p=a.actualizacion/(UPDATES[stem]+'.csv');rows=merge_rows(rows,cargar(p),KEYS[stem]);sources[str(p)]=sha(p.read_bytes())
  tables[stem]=rows
 eps={r['cod_eps']:r for r in tables['ds01_catalogo_eps']}
 cases={r['id_expediente']:r for r in tables['ds02_procedimientos']}
 assert len(cases)==len(tables['ds02_procedimientos'])
 docs={r['id_documento']:r for r in tables['ds11_indice_documentos']}
 case_docs=defaultdict(list);acts=defaultdict(list);hitos=defaultdict(list)
 for d in docs.values():case_docs[d['id_expediente']].append(d)
 for r in tables['ds10_bitacora_actuaciones']:acts[r['id_expediente']].append(r)
 for r in tables['ds02_hitos_procedimientos']:hitos[r['id_expediente']].append(r)
 available=defaultdict(dict);packet_meta={}
 for p in sorted((a.datasets/'expedientes_ficticios').glob('*.pdf')):
  if 'Solicitud_UFI_SIMULADO'.casefold() in p.name.casefold():continue
  reader=PdfReader(p);sources[str(p)]=sha(p.read_bytes());groups=agrupar_documentos(reader)
  for did in groups:
   d=docs[did]
   if d['id_expediente']!=p.stem:raise ValueError('Documento de otro expediente: '+did)
  available[p.stem]=dict(groups);packet_meta[p.stem]={'archivo':str(p),'sha256':sha(p.read_bytes()),'paginas':len(reader.pages)}
 catalog=[];index=['# Kits de demostración del dataset','',
  'Los PDF iniciales son extractos de los originales entregados. Se excluye Solicitud_UFI_SIMULADO. Las transcripciones DS10 están identificadas y no sustituyen documentos firmados.',
  '', 'Estos kits son para iniciar expedientes NUEVOS desde Recepción. No aplican estados históricos a esos expedientes ni avanzan automáticamente actuaciones.', '',
  '| Procedimiento | Expediente | EPS | Estado de la fuente | PDF entregados | Guía |','|---|---|---|---|---|---|']
 for cid,row in sorted(cases.items()):
  proc=PROCS[row['tipo_procedimiento']];folder=a.salida/proc/cid;folder.mkdir(parents=True,exist_ok=True)
  ad=sorted(acts[cid],key=lambda x:int(x['nro_hito']));cd=sorted(case_docs[cid],key=lambda x:(x['fecha_documento'],x['id_documento']))
  provided=available.get(cid,{});operativo=proc in PASOS;errors=[];files={}
  for n,d in enumerate(cd,1):
   if d['fecha_documento'] and row['fecha_inicio'] and d['fecha_documento']<row['fecha_inicio']:errors.append(d['id_documento']+': fecha documental anterior al inicio; revisar fuente, no corregirla para forzar el avance.')
   if d['id_documento'] not in provided:continue
   rel=Path('documentos')/(f'{n:02d}_'+d['id_documento']+'_'+d['tipo_documento'][:26]+'.pdf');target=folder/rel;target.parent.mkdir(exist_ok=True)
   digest=pdf_extraido(provided[d['id_documento']],target)
   files[d['id_documento']]={'archivo':rel.as_posix(),'fecha':d['fecha_documento'],'referencia':d['numero_documento'],'tipo':d['tipo_documento'],'paginas_original':[x[2] for x in provided[d['id_documento']]],'sha256':digest,'visibilidad_fuente':d['nivel_acceso']}
  initial=[x for x in ad if x['tipo_actuacion']=='solicitud']
  initial_ids={x['id_actuacion'] for x in initial}
  first=[d for d in cd if d['id_actuacion'] in initial_ids and d['id_documento'] in provided]
  initial_pdf=None
  if first:
   pages=sorted([page for d in first for page in provided[d['id_documento']]],key=lambda x:x[2])
   initial_pdf='01-Solicitud-y-anexos.pdf';pdf_extraido(pages,folder/initial_pdf)
  supports={}
  if a.transcribir_hitos and provided:
   for act in ad:
    if act['tipo_actuacion'] not in SUPLEMENTOS:continue
    if any(d['id_actuacion']==act['id_actuacion'] and d['id_documento'] in provided for d in cd):continue
    rel=Path('hitos_ds10')/(act['id_actuacion']+'.pdf');(folder/rel).parent.mkdir(exist_ok=True)
    transcribir(act,folder/rel,cid);supports[act['id_actuacion']]=rel.as_posix()
  final_pdf=[d for d in cd if d['id_documento'] in provided and d['numero_documento']==row['documento_final'] and row['documento_final']]
  if row['estado'] in ('concluido','archivado') and not final_pdf:errors.append('El dataset registra cierre, pero el PDF final no está entregado. El kit no fabrica una resolución para completar la demostración.')
  for act in ad:
   if act['fecha_actuacion'] and row['fecha_inicio'] and act['fecha_actuacion']<row['fecha_inicio']:errors.append(act['id_actuacion']+': fecha de actuación anterior al ingreso.')
  manifest={'expediente':cid,'tipo':row['tipo_procedimiento'],'codigo_portal':proc,'eps':eps[row['cod_eps']]['nombre_eps'],'cod_eps':row['cod_eps'],'corte':'2026-11-20' if a.actualizacion else 'sprint','estado_fuente':row['estado'],'resultado_fuente':row['resultado'],'estado_nuevo_expediente':'Solicitud o Inicio; solo avanza con actuaciones confirmadas','datos':row,'original':packet_meta.get(cid),'documentos':files,'solicitud_inicial':initial_pdf,'hitos_transcritos':supports,'pdf_faltantes':[d['id_documento'] for d in cd if d['id_documento'] not in provided],'observaciones':errors,'soporte_operativo_portal':operativo,'simulado':True,'excluido':'Solicitud_UFI_SIMULADO'}
  (folder/'manifiesto.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
  escribir_csv(folder/'indice_documentos.csv',cd,list(tables['ds11_indice_documentos'][0]))
  escribir_csv(folder/'actuaciones_fuente.csv',ad,list(tables['ds10_bitacora_actuaciones'][0]))
  guide=[f'# {cid} · {manifest["eps"]}','',f'Procedimiento: {row["tipo_procedimiento"]}. Corte de datos: {manifest["corte"]}. Material ficticio de práctica.', '',
   f'Estado en la fuente: **{row["estado"]}**. Resultado: {row["resultado"] or "sin pronunciamiento registrado"}. Este dato no cambia el estado del expediente nuevo que vas a registrar.', '',
   f'Portal: {a.portal_origin or "la URL configurada de tu entorno local o Railway"}. Inicia sesión con Jefatura, Coordinación, analista asignado o la cuenta EPS que corresponda a **{row["cod_eps"]}**. Usa sesiones separadas. No se incluyen contraseñas en este kit.', '']
  if initial_pdf and operativo:
   guide += [f'## Inicio desde cero\n\n1. Jefatura abre Recepción y sube **{initial_pdf}**. La solicitud es un extracto del PDF original, sin texto redactado nuevamente.',
    f'2. Selecciona {manifest["eps"]}, referencia original con un sufijo DEMO nuevo, fecha **{initial[0]["fecha_actuacion"] or row["fecha_inicio"]}** y material ficticio de práctica. Espera PDF listo.',
    f'3. Registra expediente nuevo **{proc}**, fecha de ingreso acreditada, sin asignación inicial. Anota el ID {proc}-MP-… y utiliza ese mismo ID durante todo el recorrido.',
    '4. Coordinación asigna un analista revisando carga. Jefatura y Coordinación incorporan después cada documento al mismo expediente, cuando llegue su actuación. No subas al inicio todo el expediente con su resolución.',
    '5. En Documentos incorporados revisa acceso EPS para solicitud, oficios dirigidos a la EPS, su respuesta y documento final. Proveídos e informes permanecen internos salvo revisión expresa.',
    '6. El analista registra evaluación, requerimientos y verificación. EPS informa su presentación; Coordinación incorpora la respuesta recibida y el analista verifica esa respuesta, sin reutilizar el oficio del requerimiento.','', '## Etapas del portal','']
   for n,paso in enumerate(PASOS[proc],1):guide.append(f'{n}. {paso}.')
   guide += ['', 'Los hitos DS10 son más detallados que estas etapas: **un hito DS10 no equivale a avanzar un paso del portal**. Conserva las firmas y derivaciones como respaldo y registra el avance solo al acreditar su etapa.',
    '', 'El analista usa Registrar informe de evaluación para dejar el informe sin atribuirse la firma externa. Jefatura/Coordinación registran el pronunciamiento acreditado. Autorización parcial se selecciona expresamente; el monto solicitado no se convierte en monto aprobado.',
    '', 'Si el resultado es archivo por no subsanar, utiliza el oficio de archivo y Cerrar y archivar con documento; no registres una autorización ni inventes una RCD. Si falta el PDF de cierre, detén allí la reconstrucción.',
    '', '## Actuaciones y soportes','', '| Hito | Fecha | Rol / operación | Fuente disponible |','|---|---|---|---|']
   for act in ad:
    linked=[files[d['id_documento']]['archivo'] for d in cd if d['id_actuacion']==act['id_actuacion'] and d['id_documento'] in files]
    if act['id_actuacion'] in supports:linked.append(supports[act['id_actuacion']]+' (transcripción DS10)')
    guide.append(f'| {act["nro_hito"]}: {act["descripcion"].replace("|","/")} | {act["fecha_actuacion"] or "Sin fecha acreditada"} | {rol(act["tipo_actuacion"])} | {", ".join(linked) or "Índice DS10; no se entregó PDF propio"} |')
  elif operativo:guide += ['## Documento inicial no entregado','', 'Este expediente tiene registros e índice, pero no una solicitud PDF entregada en el material. El kit permite revisar su información; no contiene una solicitud generada. Para iniciar el flujo necesitas obtener el original por el canal correspondiente.']
  else:guide += ['## Consulta documental y financiera','', 'RPI (reporte periódico), IPM/RTI (reajuste) y VIN/VCI (verificación) se conservan como fuentes de contexto financiero. Los flujos operativos del portal son CPI, UFI y RP. No registres este material como otro procedimiento para forzar un recorrido. Revisa sus datos y alertas en Ficha 360 / Finanzas / Reportes, según tu ámbito.']
  guide += ['', '## Documentos entregados','']+[f'- {did}: [{m["referencia"] or m["tipo"]}]({m["archivo"]}), fecha {m["fecha"]}, páginas {m["paginas_original"]} del original.' for did,m in files.items()]
  guide += ['', '## Controles y límites','', 'Los PDF bajo hitos_ds10 son transcripciones rotuladas, sin firmas. Los enlaces sia.example de DS11 son referencias de muestra, no descargas. No hay inferencia automática ni estados concluidos aplicados por abrir este kit. Los plazos requieren la fecha de notificación y calendario acreditados; copia los días del oficio, sin inventar vencimientos.']
  if errors:guide+=['','## Incidencias de la fuente','']+['- '+e for e in errors]
  (folder/'00-LEEME.md').write_text('\n'.join(guide)+'\n',encoding='utf-8')
  ready='Solicitud PDF disponible' if initial_pdf and operativo else 'Consulta documental' if provided else 'Sin PDF entregado'
  catalog.append({'procedimiento':proc,'expediente':cid,'eps':manifest['eps'],'cod_eps':row['cod_eps'],'estado_fuente':row['estado'],'resultado_fuente':row['resultado'],'pdf_entregados':len(files),'solicitud_pdf':bool(initial_pdf),'pdf_cierre':bool(final_pdf),'modalidad':ready,'incidencias':len(errors),'carpeta':folder.relative_to(a.salida).as_posix()})
  if provided:index.append(f'| {proc} | {cid} | {manifest["eps"]} | {row["estado"]} | {len(files)} | [{ready}]({folder.relative_to(a.salida).as_posix()}/00-LEEME.md) |')
 assert sum(len(x) for x in available.values())==130
 escribir_csv(a.salida/'catalogo_solicitudes.csv',catalog)
 summary={'expedientes':len(catalog),'tipos':dict(Counter(x['procedimiento'] for x in catalog)),'kits_con_pdf':sum(x['pdf_entregados']>0 for x in catalog),'documentos_originales_separados':sum(x['pdf_entregados'] for x in catalog),'solicitudes_pdf':sum(x['solicitud_pdf'] for x in catalog),'sin_pdf_entregado':sum(not x['pdf_entregados'] for x in catalog),'fuentes':sources,'excluido':'Solicitud_UFI_SIMULADO'}
 (a.salida/'resumen.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
 index += ['', 'El catálogo CSV incluye todos los expedientes, también los que solo tienen metadatos. Los estados mostrados pertenecen al dataset histórico; los expedientes nuevos comienzan desde su ingreso.']
 (a.salida/'00-INDICE.md').write_text('\n'.join(index)+'\n',encoding='utf-8')
 for proc in summary['tipos']:
  with zipfile.ZipFile(a.salida.parent/f'Kit-{proc}-solicitudes.zip','w',compression=zipfile.ZIP_DEFLATED) as z:
   for path in sorted((a.salida/proc).rglob('*')):
    if path.is_file():z.write(path,path.relative_to(a.salida))
   z.write(a.salida/'00-INDICE.md','00-INDICE.md')
 with zipfile.ZipFile(a.salida.parent/'Kits-todas-las-solicitudes.zip','w',compression=zipfile.ZIP_DEFLATED) as z:
  for path in sorted(a.salida.rglob('*')):
   if path.is_file():z.write(path,path.relative_to(a.salida))
 print(json.dumps({k:v for k,v in summary.items() if k!='fuentes'},ensure_ascii=False))

if __name__=='__main__':main()
