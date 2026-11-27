import json,os,uuid
from datetime import datetime,timezone
import pytest

def test_busqueda_y_carga_con_sql_real_permiso_y_rollback(monkeypatch):
    url=os.environ.get('VERIFY_DATABASE_URL')
    if not url:pytest.skip('Requiere copia PostgreSQL local')
    from sqlalchemy import create_engine,text,select
    from sqlalchemy.orm import Session
    from app.models import Usuario,Tramite,Documento,Fragmento
    from app.models.seguridad import Asignacion
    from app.modules.operaciones import registrar_procedencia
    from app.modules import busqueda_agente,carga_analistas
    from app.auth.sesion import actor_de
    from app.agent import llm
    async def no_llm(*a,**kw):raise AssertionError('No se permite inferencia')
    monkeypatch.setattr(llm,'completar',no_llm)
    engine=create_engine(url.replace('postgresql://','postgresql+psycopg://',1))
    prefix='busq-'+uuid.uuid4().hex[:12]
    with engine.connect() as connection:
        tx=connection.begin()
        db=Session(bind=connection,join_transaction_mode='create_savepoint',expire_on_commit=False)
        try:
            eps=list(db.execute(text('SELECT id FROM eps ORDER BY id LIMIT 2')).scalars())
            assert len(eps)==2
            users={}
            for key,role in [('a','analista_srt'),('b','analista_srt'),('c','analista_srt'),('coor','coordinacion_dre'),('eps','eps')]:
                user=Usuario(id=prefix+'-'+key,nombre_visible='Prueba '+key,perfil='eps' if role=='eps' else 'sunass',rol_id=role,eps_id=eps[0] if role=='eps' else None,activo=True,credenciales_version=1)
                db.add(user);users[key]=user
            db.add(Usuario(id=prefix+'-inactivo',nombre_visible='Inactivo',perfil='sunass',rol_id='analista_srt',activo=False,credenciales_version=1))
            cases=[]
            for i in range(5):
                tid=prefix+'-caso-'+str(i);cases.append(tid)
                registrar_procedencia(db,tid,'a'*64,json.dumps({'referencia':'EXP-PRUEBA-'+str(i)}))
                db.add(Tramite(id=tid,eps_id=eps[1] if i==2 else eps[0],procedimiento='CPI',titulo='Proyecto sintético '+str(i),estado='concluido' if i==3 else 'en_evaluacion',paso_actual=1,etapa='Solicitud',version=1,simulado=True,publicable=False,huella_fuentes='test'))
            db.flush()
            for i,key in [(0,'a'),(1,'b'),(2,'b'),(3,'b')]:
                db.add(Asignacion(tramite_id=cases[i],usuario_id=users[key].id,asignado_por=users['coor'].id,inicio=datetime.now(timezone.utc)))
            db.add(Asignacion(tramite_id=cases[4],usuario_id=users['b'].id,asignado_por=users['coor'].id,inicio=datetime.now(timezone.utc),fin=datetime.now(timezone.utc)))
            data=[(0,'partes','Proyecto de abrazaderas volcánicas tricapa.','Oficio 76321',False),(0,'interna','reservadohiperion solo para SUNASS.','Interno',False),(2,'partes','Abrazaderas volcánicas de otra empresa.','Ajeno',False),(0,'partes','ocrhiperion pendiente de leer.','Escaneo',True),(0,'partes',None,'Índice Oficio 98765',False)]
            for i,(case,vis,body,title,ocr) in enumerate(data):
                did=prefix+'-doc-'+str(i);registrar_procedencia(db,did,'b'*64,'{}')
                db.add(Documento(id=did,tramite_id=cases[case],titulo=title,referencia=title,visibilidad=vis,simulado=True,estado_validacion='por_validar',paginas=1))
                if body:db.add(Fragmento(id=did+'-p1',documento_id=did,tramite_id=cases[case],pagina_pdf=1,texto=body,requiere_ocr=ocr))
            db.commit();connection.execute(text('SET LOCAL ROLE yakukhipu_final_api'))
            coordinator=actor_de(users['coor'],db);company=actor_de(users['eps'],db);analyst=actor_de(users['a'],db)
            cargas={r['id']:r for r in carga_analistas.consultar(db,coordinator)}
            assert cargas[users['a'].id]['carga_activa']==1
            assert cargas[users['b'].id]['carga_activa']==2
            assert cargas[users['c'].id]['carga_activa']==0 and cargas[users['c'].id]['recomendado']
            assert prefix+'-inactivo' not in cargas
            found=busqueda_agente.buscar(db,company,'Busca abrazaderas volcánicas',20)
            assert cases[0] in {r['tramite_id'] for r in found['items']}
            assert cases[2] not in {r['tramite_id'] for r in found['items']}
            assert all(r['analista'] is None and r['responsable'] is None for r in found['items'])
            assert any(f['pagina_pdf']==1 and f['documento_id']==prefix+'-doc-0' for r in found['items'] for f in r['fuentes'])
            assert busqueda_agente.buscar(db,company,'reservadohiperion')['items']==[]
            assert busqueda_agente.buscar(db,coordinator,'reservadohiperion')['items']
            assert busqueda_agente.buscar(db,coordinator,'ocrhiperion')['items']==[]
            assert cases[2] not in {r['tramite_id'] for r in busqueda_agente.buscar(db,analyst,'abrazaderas')['items']}
            index=busqueda_agente.buscar(db,company,'Oficio 98765',20)
            assert any(f['documento_id']==prefix+'-doc-4' and f['tipo']=='indice' and f['pagina_pdf'] is None for r in index['items'] for f in r['fuentes'])
            db.execute(text('UPDATE registro_fuente SET presente=false WHERE canonical_id=:id'),{'id':prefix+'-doc-1'});db.flush()
            assert busqueda_agente.buscar(db,coordinator,'reservadohiperion')['items']==[]
        finally:db.close();tx.rollback()
    engine.dispose()
