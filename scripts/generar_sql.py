"""Genera SQL desde fuentes locales. No abre conexiones ni ejecuta SQL.

python -m scripts.generar_sql --datasets RUTA --casos RUTA --salida sql/local
Los SQL contienen datos y texto documental: mantener fuera del repositorio público.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import logging
import re
import zipfile
from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

logging.getLogger('pypdf').setLevel(logging.ERROR)
ROOT = Path(__file__).resolve().parents[1]
TABLES = {
 'ds01_catalogo_eps': ('catalogo_eps', ('cod_eps',)),
 'ds01_localidades_eps': ('localidad_eps', ('cod_eps','localidad','ubigeo')),
 'ds02_procedimientos': ('procedimiento_fuente', ('id_expediente',)),
 'ds02_hitos_procedimientos': ('hito', ('id_expediente','nro_hito')),
 'ds03_programa_inversiones': ('programa_inversion', ('cod_eps','periodo_regulatorio','cod_proyecto','anio')),
 'ds04_ejecucion_inversiones': ('ejecucion_inversion', ('cod_eps','cod_proyecto','anio_trimestre')),
 'ds05_fondo_inversiones_reservas': ('fondo_inversion', ('cod_eps','anio_mes','tipo_fondo')),
 'ds06_estados_financieros': ('estado_financiero', ('cod_eps','anio')),
 'ds07_metas_gestion': ('meta_gestion', ('cod_eps','periodo_regulatorio','cod_meta','nivel','localidad','anio')),
 'ds08_inversiones_mef': ('inversion_mef', ('cui',)),
 'ds09_ipm': ('ipm', ('anio_mes',)),
}
PROCS = {'cambio_programa_inversiones':'CPI','uso_excepcional_fondo':'UFI','revision_periodica':'RP',
         'reajuste_ipm':'IPM','reporte_periodico':'RPI','verificacion_incremento':'VIN'}
CASES = {
 'EPS TACNA S.A. - modificación del PI': ('CPI','013-2026-SUNASS-DRE-PI','EPS TACNA S.A.'),
 'EPSSMU uso excepcional del FI': ('UFI','004-2025-SUNASS-DRT-FI','EPSSMU S.A.'),
 'Emapa Pasco - Revisión Periódica': ('RP','EMAPA-PASCO-RP-2024','EMAPA PASCO S.A.'),
}


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def identity(namespace: str, key: str) -> str:
    return namespace + ':' + sha(key.encode())[:32]


def dump(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',',':'),default=str)


def literal(value) -> str:
    if value is None: return 'NULL'
    if isinstance(value, bool): return 'TRUE' if value else 'FALSE'
    if isinstance(value, (int, Decimal)): return str(value)
    return "'" + str(value).replace('\x00','').replace("'", "''") + "'"


def insert(table: str, values: dict, key='id', preserve=(), where_update=None) -> str:
    columns = list(values)
    updates = [f'{c}=EXCLUDED.{c}' for c in columns if c != key and c not in preserve]
    return (f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join(literal(values[c]) for c in columns)}) "
            f"ON CONFLICT ({key}) DO " + ('UPDATE SET '+','.join(updates) + (f' WHERE {where_update}' if where_update else '') if updates else 'NOTHING')+';\n')


def read_rows(path: Path):
    content = path.read_bytes()
    if content[:2] == b'PK':
        from openpyxl import load_workbook
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        rows = list(workbook.active.values)
        workbook.close()
        return [dict(zip(rows[0], r)) for r in rows[1:] if any(v is not None for v in r)]
    return list(csv.DictReader(io.StringIO(content.decode('utf-8-sig'))))


def coltype(name: str) -> str:
    if name.startswith('fecha_'): return 'date'
    if name in {'es_sede','cuenta_plazo','condiciona_incremento'}: return 'boolean'
    if name in {'anio','anio_regulatorio','nro_hito','n_localidades','plazo_etapa_dh','plazo_referencial_dh',
                'plazo_maximo_dh','dias_suspension_dh','dias_habiles_sunass','periodo_regulatorio_inicio','periodo_regulatorio_fin'} or name.startswith(('poblacion_','conexiones_')): return 'integer'
    if name.startswith(('monto_','avance_','ejecucion_','porcentaje_','ingresos_','saldo_','deposito_','uso_',
                        'costo_','gastos_','resultado_','efectivo_','cuentas_','activo_','pasivo_','facturacion_',
                        'margen_','relacion_','liquidez_','morosidad_','eficiencia_','valor_','cumplimiento_',
                        'variacion_','indice_','devengado_','pim_')) or name in {'intereses','patrimonio','recaudacion','endeudamiento','costo_actualizado'}: return 'numeric'
    return 'text'


def typed(name: str, value):
    if value is None or value == '': return None
    kind = coltype(name)
    if kind == 'date': return date.fromisoformat(str(value)).isoformat()
    if kind == 'boolean':
        if str(value).lower() not in ('true','false'): raise ValueError(f'booleano inválido: {value}')
        return str(value).lower() == 'true'
    if kind in ('numeric','integer'):
        number = Decimal(str(value))
        if not number.is_finite(): raise ValueError('número no finito')
        if kind == 'integer' and number != number.to_integral_value(): raise ValueError('entero no válido')
        return int(number) if kind == 'integer' else number
    return str(value)


class Exporter:
    def __init__(self, datasets: Path, casos: Path, salida: Path):
        self.datasets, self.casos, self.salida = datasets, casos, salida
        self.files = sorted([*datasets.glob('*'), *casos.glob('*.zip')])
        self.manifest = {p.name:sha(p.read_bytes()) for p in self.files if p.is_file()}
        self.lote = sha(dump(self.manifest).encode())
        self.errors, self.counts, self.mapping = [], {}, {}
        self.data, self.docs, self.ddl = [], [], []
        self.eps, self.tramites, self.project_keys = {}, {}, set()

    def error(self, file, record, code, detail):
        self.errors.append({'archivo':file,'registro':record,'codigo':code,'detalle':detail})

    def source(self, filename, kind, content, output):
        fid = identity(kind,filename)
        output.append(insert('fuente',dict(id=fid,source_type=kind,source_file=filename,source_hash=sha(content))))
        output.append(f'UPDATE registro_fuente SET presente=false WHERE fuente_id={literal(fid)};\n')
        return fid

    def record(self, fid, key, row, namespace, output):
        rid = identity(namespace,key)
        output.append(insert('registro_fuente',dict(canonical_id=rid,fuente_id=fid,source_record_id=key,
                       source_hash=sha(dump(row).encode()),lote_id=self.lote,datos=dump(row),presente=True),key='canonical_id'))
        output.append(f"INSERT INTO registro_revision(canonical_id,source_hash,lote_id,datos) VALUES ({literal(rid)},{literal(sha(dump(row).encode()))},{literal(self.lote)},{literal(dump(row))}) ON CONFLICT DO NOTHING;\n")
        return rid

    def datasets_sql(self):
        files = {p.stem:p for p in self.datasets.iterdir() if p.stem in TABLES}
        missing = set(TABLES)-files.keys()
        if missing: raise ValueError(f'Faltan fuentes requeridas: {sorted(missing)}')
        # Catálogo y procedimientos primero; luego hitos y tablas de contexto.
        for stem in sorted(files, key=lambda s:(s != 'ds01_catalogo_eps',s != 'ds02_procedimientos',s)):
            path = files[stem]
            rows = read_rows(path)
            if not rows: raise ValueError(f'Archivo sin filas: {path.name}')
            table, keys = TABLES[stem]
            columns = list(rows[0])
            if any(not re.fullmatch('[a-z][a-z0-9_]*', c) for c in columns): raise ValueError('Encabezados no válidos')
            if set(keys)-set(columns): raise ValueError(f'Llaves faltantes en {path.name}')
            extra = ', eps_id varchar(80) REFERENCES eps(id)' if 'cod_eps' in columns else ''
            if 'id_expediente' in columns: extra += ', tramite_id varchar(80) REFERENCES tramite(id)'
            definitions = ','.join(f'{c} {coltype(c)}' for c in columns)
            self.ddl.append(f'CREATE TABLE {table} (canonical_id text PRIMARY KEY REFERENCES registro_fuente(canonical_id),{definitions}{extra});\n')
            self.mapping[path.name] = {'tabla':table,'llave':keys,'columnas':{c:coltype(c) for c in columns}}
            fid = self.source(path.name,'dataset',path.read_bytes(),self.data)
            seen = set()
            repetitions = Counter(dump([r.get(k) for k in keys]) for r in rows)
            imported = 0
            for pos,row in enumerate(rows,2):
                key = dump([row.get(k) for k in keys])
                if repetitions[key]>1:
                    # Todas las variantes quedan en cuarentena; no se elige una por orden del archivo.
                    self.record(fid,key+':fila:'+str(pos),row,'cuarentena',self.data)
                    self.error(path.name,str(pos),'duplicado_en_cuarentena',key); continue
                seen.add(key)
                try: values = {c:typed(c,row.get(c)) for c in columns}
                except (ValueError,InvalidOperation) as e:
                    self.error(path.name,str(pos),'tipo_invalido',str(e)); continue
                if 'cod_eps' in row and stem != 'ds01_catalogo_eps' and row['cod_eps'] not in self.eps:
                    self.error(path.name,str(pos),'eps_inexistente',row['cod_eps']); continue
                if stem=='ds02_hitos_procedimientos' and row['id_expediente'] not in self.tramites:
                    self.error(path.name,str(pos),'expediente_inexistente',row['id_expediente']); continue
                if stem=='ds04_ejecucion_inversiones' and (row['cod_eps'],row['cod_proyecto']) not in self.project_keys:
                    self.record(fid,key,row,'cuarentena',self.data)
                    self.error(path.name,str(pos),'proyecto_inexistente',row['cod_proyecto']); continue
                rid = self.record(fid,key,row,table,self.data)
                if stem=='ds01_catalogo_eps':
                    eid = identity('dataset-eps',row['cod_eps'])
                    self.record(fid,row['cod_eps'],row,'dataset-eps',self.data)
                    self.eps[row['cod_eps']] = eid
                    self.data.append(insert('eps',dict(id=eid,nombre=row['nombre_eps'],region=row['departamento'],tamano=row['tamano'],simulado=True)))
                if 'cod_eps' in row: values['eps_id'] = self.eps[row['cod_eps']]
                if stem=='ds02_procedimientos':
                    tid = identity('dataset-exp',row['id_expediente'])
                    self.record(fid,row['id_expediente'],row,'dataset-exp',self.data)
                    self.tramites[row['id_expediente']] = tid
                    estado = ('no_autorizado' if row['resultado']=='denegado' else 'concluido') if row['estado'] in ('concluido','archivado') else 'en_evaluacion'
                    self.data.append(insert('tramite',dict(id=tid,procedimiento=PROCS[row['tipo_procedimiento']],eps_id=values['eps_id'],
                        titulo=row['motivo'] or row['tipo_procedimiento'],estado=estado,paso_actual=1,etapa=row['etapa_actual'] or 'Por validar',
                        responsable=row['responsable_actual'] or None,fecha_inicio=values['fecha_inicio'],fecha_fin=values['fecha_conclusion'],simulado=True),
                        where_update='tramite.version=1'))
                if 'id_expediente' in row: values['tramite_id'] = self.tramites.get(row['id_expediente'])
                if stem=='ds03_programa_inversiones':
                    self.project_keys.add((row['cod_eps'],row['cod_proyecto']))
                    self.data.append(f"INSERT INTO proyecto_inversion(eps_id,cod_proyecto) VALUES ({literal(values['eps_id'])},{literal(row['cod_proyecto'])}) ON CONFLICT DO NOTHING;\n")
                self.data.append(insert(table,dict(canonical_id=rid,**values),key='canonical_id'))
                imported += 1
            self.counts[path.name] = {'filas':len(rows),'cargadas':imported}
            print(f'{path.name}: {imported}/{len(rows)} filas operativas',flush=True)

    def documents_sql(self):
        from pypdf import PdfReader
        for archive in sorted(self.casos.glob('*.zip')):
            with zipfile.ZipFile(archive) as z:
                for folder,(proc,exp,eps_name) in CASES.items():
                    members = [n for n in z.namelist() if n.startswith(folder+'/') and n.lower().endswith('.pdf')]
                    if not members: continue
                    fid = self.source(archive.name,'caso_real',archive.read_bytes(),self.docs)
                    eid = self.record(fid,eps_name,{'nombre':eps_name},'real-eps',self.docs)
                    self.docs.append(insert('eps',dict(id=eid,nombre=eps_name,simulado=False)))
                    tid = self.record(fid,exp,{'expediente':exp,'procedimiento':proc},'real-exp',self.docs)
                    # El estado no se deduce del nombre del PDF. Se valida humanamente.
                    self.docs.append(insert('tramite',dict(id=tid,procedimiento=proc,eps_id=eid,titulo=folder,estado='en_evaluacion',
                        paso_actual=1,etapa='Estado documental pendiente de validación',simulado=False,huella_fuentes=self.manifest[archive.name]),
                        where_update='tramite.version=1'))
                    pages_total, ocr = 0, 0
                    for name in sorted(members):
                        raw = z.read(name)
                        try: pages = PdfReader(io.BytesIO(raw)).pages
                        except Exception as exc:
                            self.error(archive.name,name,'pdf_ilegible',str(exc)); continue
                        did = self.record(fid,name,{'zip':archive.name,'miembro':name,'sha256':sha(raw)},'real-doc',self.docs)
                        self.docs.append(insert('documento',dict(id=did,tramite_id=tid,titulo=Path(name).stem,referencia=Path(name).stem,
                            visibilidad='interna',archivo=archive.name+'::'+name,paginas=len(pages),simulado=False),preserve=('visibilidad',)))
                        # Candidatos del nombre/carpeta; no se consideran actos acreditados.
                        number = re.search(r'\d{2,5}[- ]20\d{2}',Path(name).stem)
                        first_page = pages[0].extract_text() or ''
                        header_date = re.search(r'(\d{1,2})\s+de\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|setiembre|septiembre|octubre|noviembre|diciembre)\s+de\s+(20\d{2})', first_page[:1500], re.I)
                        candidate_date=None
                        if header_date:
                            months={'enero':1,'febrero':2,'marzo':3,'abril':4,'mayo':5,'junio':6,'julio':7,'agosto':8,'setiembre':9,'septiembre':9,'octubre':10,'noviembre':11,'diciembre':12}
                            try: candidate_date=date(int(header_date[3]),months[header_date[2].lower()],int(header_date[1])).isoformat()
                            except ValueError: pass
                        self.docs.append(insert('metadato_documental',dict(documento_id=did,
                            numero_candidato=number.group() if number else None,fecha_candidata=candidate_date,
                            actor_candidato=None,etapa_carpeta=Path(name).parent.name,
                            metodo='Nombre, carpeta y fecha textual del encabezado; requiere validación humana'),key='documento_id',preserve=('actor_candidato',)))
                        for i,page in enumerate(pages,1):
                            try: text = page.extract_text() or ''
                            except Exception: text = ''
                            needs_ocr = len(text.strip())<80
                            ocr += needs_ocr
                            # Texto se guarda localmente; no se envía a IA externa durante la carga.
                            self.docs.append(insert('fragmento',dict(id=f'{did}-p{i}',documento_id=did,tramite_id=tid,pagina_pdf=i,
                                texto=text,requiere_ocr=needs_ocr,metadatos=dump({'sha256_pdf':sha(raw),'etapa_carpeta':str(Path(name).parent)}))))
                        pages_total += len(pages)
                    self.counts[archive.name] = {'pdf':len(members),'paginas':pages_total,'paginas_ocr':ocr}
                    print(f'{archive.name}: {len(members)} PDF, {pages_total} páginas',flush=True)
                    self.error(archive.name,exp,'revision_documental','Validar estado, fechas, número de documento, actor, relaciones y visibilidad antes de operar/publicar.')

    def run(self):
        self.salida.mkdir(parents=True,exist_ok=True)
        self.datasets_sql()
        self.documents_sql()
        self.source('diccionario_variables.xlsx','dataset',(self.datasets/'diccionario_variables.xlsx').read_bytes(),self.data)
        lote = insert('lote_importacion',dict(id=self.lote,manifiesto=dump(self.manifest)))
        for filename, content in [('01_dataset_schema.sql',self.ddl),('04_dataset_inserts.sql',[lote,*self.data]),('05_real_cases_inserts.sql',[lote,*self.docs])]:
            (self.salida/filename).write_text("SET standard_conforming_strings=on;\nBEGIN;\n"+''.join(content)+'COMMIT;\n',encoding='utf-8')
        errors = [lote]
        for e in self.errors:
            errors.append(insert('error_calidad_datos',dict(id=sha(dump(e).encode()),lote_id=self.lote,registro_id=e['registro'],codigo=e['codigo'],detalle=dump(e))))
        (self.salida/'08_calidad.sql').write_text('BEGIN;\n'+''.join(errors)+'COMMIT;\n',encoding='utf-8')
        report = {'lote':self.lote,'archivos':self.manifest,'conteos':self.counts,'errores':self.errors,
                  'faltantes':['DS10','DS11'],'mapeo':self.mapping,
                  'politica':'Dataset de muestra; nunca equiparado a datos oficiales. SQL local contiene texto documental.'}
        (self.salida/'manifiesto.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'lote':self.lote,'conteos':self.counts,'incidencias':len(self.errors)},ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--datasets',type=Path,required=True)
    parser.add_argument('--casos',type=Path,required=True)
    parser.add_argument('--salida',type=Path,default=ROOT/'sql'/'local')
    args = parser.parse_args()
    Exporter(args.datasets,args.casos,args.salida).run()


if __name__ == '__main__': main()
