"""Importación D3 idempotente. No invoca IA ni publica/asigna expedientes.

Genera SQL y un manifiesto por defecto. --aplicar requiere D3_DATABASE_URL;
--subir-pdf requiere además las variables PDF_* del bucket privado de destino.
"""
from __future__ import annotations
import argparse,csv,io,json,os,re,tempfile,zipfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from pypdf import PdfReader,PdfWriter
from scripts.generar_sql import Exporter,TABLES,CASES,identity,insert,literal,dump,sha,read_rows
from scripts.documentos_sprint import agrupar_documentos

UPDATES={
 'ds02_procedimientos':'ds02_procedimientos_actualizados',
 'ds02_hitos_procedimientos':'ds02_hitos_nuevos_o_actualizados',
 'ds04_ejecucion_inversiones':'ds04_ejecucion_2026T3',
 'ds05_fondo_inversiones_reservas':'ds05_fondos_hasta_2026-10',
 'ds10_bitacora_actuaciones':'ds10_actuaciones_nuevas_o_actualizadas',
 'ds11_indice_documentos':'ds11_documentos_nuevos',
}
KEYS={**{stem:spec[1] for stem,spec in TABLES.items()},
      'ds10_bitacora_actuaciones':('id_actuacion',),'ds11_indice_documentos':('id_documento',)}

def merge_rows(base,patch,keys):
    """La actualización reemplaza la clave completa; duplicados del mismo archivo se conservan para cuarentena."""
    groups={}
    for row in base:groups.setdefault(tuple(row.get(k) for k in keys),[]).append(row)
    updated={}
    for row in patch:updated.setdefault(tuple(row.get(k) for k in keys),[]).append(row)
    groups.update(updated)
    return [row for rows in groups.values() for row in rows]

class Importer(Exporter):
    def __init__(self,root,updates,merged,output,subir_pdf=False,casos=None):
        self.root,self.updates,self.origins=root,updates,{}
        manifest={}
        for stem,keys in KEYS.items():
            path=root/(stem+'.csv');base=read_rows(path);patch=[]
            manifest[path.name]=sha(path.read_bytes())
            for row in base:self.origins[(stem,tuple(row.get(k) for k in keys))]=path.name
            if updates and stem in UPDATES:
                change=updates/(UPDATES[stem]+'.csv');patch=read_rows(change)
                manifest[str(change.relative_to(root)) if change.is_relative_to(root) else change.name]=sha(change.read_bytes())
                for row in patch:self.origins[(stem,tuple(row.get(k) for k in keys))]=change.name
            rows=merge_rows(base,patch,keys)
            with (merged/path.name).open('w',encoding='utf-8',newline='') as f:
                writer=csv.DictWriter(f,fieldnames=list(base[0]));writer.writeheader();writer.writerows(rows)
        super().__init__(merged,merged,output)
        for pdf in sorted((root/'expedientes_ficticios').glob('*.pdf')):manifest[str(pdf.relative_to(root))]=sha(pdf.read_bytes())
        self.archives=sorted(casos.glob('*.zip')) if casos else []
        for archive in self.archives:manifest[archive.name]=sha(archive.read_bytes())
        self.extracted=[]
        if casos:
            for folder in CASES:
                for path in sorted((casos/folder).rglob('*.pdf')):
                    self.extracted.append(path)
                    manifest['casos/'+path.relative_to(casos).as_posix()]=sha(path.read_bytes())
        self.casos_root=casos
        self.manifest=manifest;self.lote=sha(dump(manifest).encode());self.subir_pdf=subir_pdf
        self.pdf_count=0;self.indexed_docs=0;self.acts=0
        self.uploads={}
        self.pool=ThreadPoolExecutor(max_workers=4) if subir_pdf else None
        if subir_pdf:
            from app.modules.archivos_pdf import cliente
            from app.core.config import settings
            self.storage,self.bucket=cliente(),settings.pdf_bucket

    def record(self,fid,key,row,namespace,output):
        enriched=dict(row)
        for stem,keys in KEYS.items():
            if fid==identity('dataset',stem+'.csv'):
                enriched['_origen_archivo']=self.origins.get((stem,tuple(row.get(k) for k in keys)),stem+'.csv')
                break
        return super().record(fid,key,enriched,namespace,output)

    def upload(self,raw):
        key='fuentes/d3/'+sha(raw)+'.pdf'
        if self.subir_pdf and key not in self.uploads:
            self.uploads[key]=self.pool.submit(self.upload_one,key,raw)
        return 'bucket:'+key if self.subir_pdf else None

    def upload_one(self,key,raw):
        from botocore.exceptions import ClientError
        try:
            obj=self.storage.head_object(Bucket=self.bucket,Key=key)
            if obj['ContentLength']==len(raw):return
        except ClientError as exc:
            if str(exc.response.get('Error',{}).get('Code')) not in ('404','NoSuchKey','NotFound'):raise
        # Clave dirigida por contenido, máximo cuatro transferencias concurrentes.
        self.storage.put_object(Bucket=self.bucket,Key=key,Body=raw,ContentType='application/pdf',Metadata={'sha256':sha(raw)})

    def documents_sql(self):
        rows=read_rows(self.datasets/'ds11_indice_documentos.csv');by_id={};duplicates=set()
        for row in rows:
            did=row['id_documento']
            if did in by_id:duplicates.add(did)
            by_id[did]=row
        fid=self.source('ds11_indice_documentos.csv','dataset',(self.datasets/'ds11_indice_documentos.csv').read_bytes(),self.data)
        self.doc_ids={}
        for source,row in by_id.items():
            if source in duplicates:
                self.error('ds11_indice_documentos.csv',source,'duplicado_en_cuarentena','ID documental repetido');continue
            tid=self.tramites.get(row['id_expediente'])
            if not tid:
                self.error('ds11_indice_documentos.csv',source,'expediente_inexistente',row['id_expediente']);continue
            did=self.record(fid,source,row,'dataset-doc',self.data);self.doc_ids[source]=did
            # El nivel del dataset no equivale a la aprobación de una publicación del portal.
            access='partes' if row['nivel_acceso']=='restringido_partes' else 'interna'
            self.data.append(insert('documento',dict(id=did,tramite_id=tid,titulo=row['asunto'][:200] or row['tipo_documento'],
                referencia=row['numero_documento'][:120] or None,visibilidad=access,simulado=True),preserve=('visibilidad',)))
            self.data.append(insert('metadato_documental',dict(documento_id=did,numero_candidato=row['numero_documento'] or None,
                fecha_candidata=row['fecha_documento'] or None,actor_candidato=row['emisor'],etapa_carpeta=row['tipo_documento'],
                metodo='Índice DS11 de muestra. Vínculo sia.example es referencial; no se descarga como PDF.'),key='documento_id',preserve=('validado',)))
            self.indexed_docs+=1
        # Cada PDF de práctica agrupa varios documentos. Separar por ID para no exponer páginas de otro documento.
        for path in sorted((self.root/'expedientes_ficticios').glob('*.pdf')):
            raw=path.read_bytes();reader=PdfReader(io.BytesIO(raw));groups={}
            for source,pages in agrupar_documentos(reader).items():
                if source not in self.doc_ids:continue
                if by_id[source]['id_expediente']!=path.stem:
                    self.error(path.name,source,'documento_de_otro_expediente',source);continue
                groups[source]=pages
            for source,pages in groups.items():
                did=self.doc_ids[source];row=by_id[source];writer=PdfWriter()
                for page,_,_ in pages:writer.add_page(page)
                stream=io.BytesIO();writer.write(stream);blob=stream.getvalue()
                # Sin bucket, la copia separada se puede servir desde DOCUMENTOS_DIR de QA.
                relative='d3/'+sha(blob)+'.pdf';target=self.salida/'documentos'/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(blob)
                archive=self.upload(blob) or relative
                self.data.append(f'UPDATE documento SET archivo={literal(archive)},paginas={len(pages)} WHERE id={literal(did)};\n')
                self.data.append(f'DELETE FROM fragmento WHERE documento_id={literal(did)} AND pagina_pdf>{len(pages)};\n')
                for page_no,(_,text,original_page) in enumerate(pages,1):
                    self.data.append(insert('fragmento',dict(id=f'{did}-p{page_no}',documento_id=did,
                        tramite_id=self.tramites[row['id_expediente']],pagina_pdf=page_no,texto=text,
                        requiere_ocr=not bool(text.strip()),metadatos=dump({'archivo_fuente':path.name,'pagina_origen':original_page,'sha256_pdf':sha(blob),'tipo':'documento_ficticio','texto_corto':len(text.strip())<80}))))
                self.pdf_count+=1
        self.counts['ds11_indice_documentos.csv']={'filas':len(rows),'cargadas':self.indexed_docs,'documentos_con_pdf':self.pdf_count}

    def actions_sql(self):
        path=self.datasets/'ds10_bitacora_actuaciones.csv';fid=self.source(path.name,'dataset',path.read_bytes(),self.data)
        rows=read_rows(path);counts=defaultdict(int)
        for row in rows:counts[row['id_actuacion']]+=1
        for row in rows:
            key=row['id_actuacion'];tid=self.tramites.get(row['id_expediente'])
            if counts[key]!=1 or not tid:
                self.error(path.name,key,'actuacion_no_importable','ID repetido o expediente ausente');continue
            rid=self.record(fid,key,row,'actuacion-fuente',self.data)
            values=dict(tramite_id=tid,tipo='dataset',titulo=row['tipo_actuacion'].replace('_',' '),detalle=row['descripcion'],
                fecha_acreditada=row['fecha_actuacion'] or None,fecha_por_validar=True,actor=row['responsable'],fuente=rid,
                estado_origen='en_evaluacion',estado_destino='en_evaluacion',paso_origen=1,paso_destino=1,
                verificada=False,clave_idempotencia='d3:'+key)
            columns=list(values);updates=','.join(f'{k}=EXCLUDED.{k}' for k in columns if k not in ('tramite_id','clave_idempotencia'))
            self.data.append(f"INSERT INTO actuacion ({','.join(columns)}) VALUES ({','.join(literal(values[k]) for k in columns)}) ON CONFLICT (tramite_id,clave_idempotencia) DO UPDATE SET {updates};\n")
            self.acts+=1
        self.counts[path.name]={'filas':len(rows),'cargadas':self.acts}

    def legacy_pdf_sql(self):
        """Transportar los PDF reales ya indexados, conservando estado y visibilidad."""
        files={}
        for archive in self.archives:
            with zipfile.ZipFile(archive) as z:
                for name in sorted(z.namelist()):
                    if not name.lower().endswith('.pdf') or not any(name.startswith(folder+'/') for folder in CASES):continue
                    files[name]=z.read(name)
        for path in self.extracted:
            name=path.relative_to(self.casos_root).as_posix();blob=path.read_bytes()
            if name in files and files[name]!=blob:raise ValueError(f'Dos versiones PDF distintas para {name}')
            files[name]=blob
        for name,blob in files.items():
            if not blob.startswith(b'%PDF-'):raise ValueError(f'Contenido PDF inválido: {name}')
            did=identity('real-doc',name)
            relative='d3/'+sha(blob)+'.pdf';target=self.salida/'documentos'/relative
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(blob)
            location=self.upload(blob) or relative
            self.data.append(f"UPDATE documento SET archivo={literal(location)} WHERE id={literal(did)} AND EXISTS (SELECT 1 FROM registro_fuente r WHERE r.canonical_id=documento.id AND r.datos->>'sha256'={literal(sha(blob))});\n")
        self.counts['pdf_casos_reales']={'pdf_disponibles':len(files)}

    def run(self):
        self.salida.mkdir(parents=True,exist_ok=True);self.datasets_sql();self.documents_sql();self.actions_sql();self.legacy_pdf_sql()
        if self.pool:
            try:
                for future in self.uploads.values():future.result()
            finally:self.pool.shutdown(wait=True,cancel_futures=True)
        self.data.append(f"UPDATE tramite SET huella_fuentes={literal(self.lote)},actualizado=now() WHERE id LIKE 'dataset-exp:%' AND huella_fuentes<>{literal(self.lote)};\n")
        # No se desasignan usuarios, no se alteran roles, ni se publica material por importar un CSV.
        header=insert('lote_importacion',dict(id=self.lote,manifiesto=dump(self.manifest)))
        errors=[insert('error_calidad_datos',dict(id=sha(dump(e).encode()),lote_id=self.lote,registro_id=e['registro'],codigo=e['codigo'],detalle=dump(e))) for e in self.errors]
        sql='SET standard_conforming_strings=on;\nBEGIN;\n'+header+''.join(self.data+errors)+'COMMIT;\n'
        (self.salida/'importacion_d3.sql').write_text(sql,encoding='utf-8')
        report={'lote':self.lote,'archivos':self.manifest,'conteos':self.counts,'incidencias':self.errors,'corte_datos':'2026-11-20' if self.updates else 'sprint','ia_solicitudes':0}
        (self.salida/'manifiesto.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        return report

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--datasets',type=Path,required=True)
    parser.add_argument('--actualizacion',type=Path)
    parser.add_argument('--salida',type=Path,required=True)
    parser.add_argument('--casos',type=Path,help='Carpeta con ZIP o subcarpetas extraídas de los tres casos ya indexados en el dump final')
    parser.add_argument('--aplicar',action='store_true')
    parser.add_argument('--subir-pdf',action='store_true')
    args=parser.parse_args()
    if args.aplicar and not os.environ.get('D3_DATABASE_URL'):parser.error('--aplicar requiere D3_DATABASE_URL explícita')
    with tempfile.TemporaryDirectory() as temp:
        importer=Importer(args.datasets,args.actualizacion,Path(temp),args.salida,args.subir_pdf,args.casos);report=importer.run()
    if args.aplicar:
        import psycopg
        with psycopg.connect(os.environ['D3_DATABASE_URL'].replace('postgresql+psycopg://','postgresql://')) as conn:
            conn.execute((args.salida/'importacion_d3.sql').read_text(encoding='utf-8'),prepare=False)
    print(json.dumps({'lote':report['lote'],'conteos':report['conteos'],'incidencias':len(report['incidencias']),'aplicado':args.aplicar,'ia_solicitudes':0},ensure_ascii=False))

if __name__=='__main__':main()
