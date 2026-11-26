"""OmniRoute y worker PDF/agente en un único servicio Railway supervisado."""
from __future__ import annotations
import json,logging,os,signal,subprocess,sys,threading,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import httpx

LOG=logging.getLogger('yakukhipu.worker_runtime')
KEY_FILE='yakukhipu-inference-key.json'

def private_json(path:Path,data:dict):
 temporary=path.with_suffix('.tmp')
 with temporary.open('w',encoding='utf-8') as f:
  if os.name=='posix':os.fchmod(f.fileno(),0o600)
  json.dump(data,f)
 temporary.replace(path)

def configure_gateway(base:str,directory:Path,management_key:str,providers:list[dict],combo:dict)->str:
 """Configura solo recursos del proyecto; reinicios conservan la clave de inferencia."""
 headers={'Authorization':'Bearer '+management_key,'Origin':base}
 with httpx.Client(base_url=base,headers=headers,timeout=120,trust_env=False) as client:
  def request(method,path,**kwargs):
   response=client.request(method,path,**kwargs)
   if response.is_error:raise RuntimeError(f'OmniRoute {method} {path}: HTTP {response.status_code}')
   return response.json() if response.content else None
  connections=request('GET','/api/providers')['connections'];mapping={};allowed=[];usable=0
  for source in providers:
   existing=next((p for p in connections if p['provider']==source['provider'] and p['name']==source['name']),None)
   if existing is None:
    body={k:v for k,v in source.items() if k!='sourceId'}
    result=request('POST','/api/providers',json=body)
    existing=result.get('connection',result)
   mapping[source['sourceId']]=existing['id'];allowed.append(existing['id'])
   # El alta empieza inactiva; comprobar credenciales antes de anunciar disponibilidad.
   tested=request('POST',f"/api/providers/{existing['id']}/test",json={})
   refreshed=request('GET','/api/providers')['connections']
   active=next((p for p in refreshed if p['id']==existing['id']),{})
   if active.get('isActive'):usable+=1
  if not usable:raise RuntimeError('Ningún proveedor LLM superó la comprobación de conexión')
  prepared=json.loads(json.dumps(combo))
  for model in prepared['models']:
   if model.get('connectionId') in mapping:model['connectionId']=mapping[model['connectionId']]
  combos=request('GET','/api/combos')['combos']
  existing=next((c for c in combos if c['name']==prepared['name']),None)
  if existing is None:request('POST','/api/combos',json=prepared)
  keyfile=directory/KEY_FILE
  if keyfile.exists():return json.loads(keyfile.read_text(encoding='utf-8'))['key']
  result=request('POST','/api/keys',json={'name':'YakuKhipu apps','scopes':['read','write'],'allowedCombos':['yakukhipu'],'allowedConnections':allowed,'noLog':True})
  private_json(keyfile,{'key':result['key'],'id':result['id']})
  return result['key']

def prepare_directory(directory:Path):
 directory.mkdir(parents=True,exist_ok=True)
 if os.name=='posix' and os.getuid()==0:
  import pwd
  user=pwd.getpwnam('yakukhipu')
  os.chown(directory,user.pw_uid,user.pw_gid)
  os.setgroups([]);os.setgid(user.pw_gid);os.setuid(user.pw_uid)
 directory.chmod(0o700)

def terminate(process:subprocess.Popen|None,timeout:int):
 if process is None or process.poll() is not None:return
 process.terminate()
 try:process.wait(timeout=timeout)
 except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)

def main()->int:
 logging.basicConfig(level=logging.INFO,format='%(levelname)s %(name)s %(message)s')
 directory=Path(os.environ.get('DATA_DIR','/omniroute-data'));prepare_directory(directory)
 management=os.environ['OMNIROUTE_API_KEY'];port=int(os.environ.get('OMNIROUTE_PORT','20128'))
 base=f'http://127.0.0.1:{port}'
 providers=json.loads(os.environ['YAKUKHIPU_OMNI_PROVIDERS']);combo=json.loads(os.environ['YAKUKHIPU_OMNI_COMBO'])
 stopped=threading.Event();ready=threading.Event();node=None;worker=None
 for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,lambda *_:stopped.set())
 class Health(BaseHTTPRequestHandler):
  def do_GET(self):
   healthy=ready.is_set() and node is not None and node.poll() is None and worker is not None and worker.poll() is None
   if self.path not in ('/health/live','/health/ready'):self.send_error(404);return
   if healthy and self.path=='/health/ready':
    try:
     with httpx.Client(timeout=3,trust_env=False) as c:healthy=c.get(base+'/api/monitoring/health',headers={'Authorization':'Bearer '+management}).status_code==200
    except httpx.HTTPError:healthy=False
   status=200 if self.path=='/health/live' or healthy else 503
   body=json.dumps({'estado':'ok' if status==200 else 'iniciando','omniroute':node is not None and node.poll() is None,'worker':worker is not None and worker.poll() is None}).encode()
   self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
  def log_message(self,*_):pass
 server=ThreadingHTTPServer(('0.0.0.0',int(os.environ.get('PORT','20127'))),Health)
 threading.Thread(target=server.serve_forever,daemon=True).start()
 try:
  node_env=os.environ.copy()
  for key in ['DATABASE_URL','PDF_ACCESS_KEY','PDF_SECRET_KEY','YAKUKHIPU_OMNI_PROVIDERS','YAKUKHIPU_OMNI_COMBO','LLM_API_KEY']:node_env.pop(key,None)
  node_env.update(PORT=str(port),DASHBOARD_PORT=str(port),HOSTNAME='::',OMNIROUTE_SERVER_HOST='::',NODE_ENV='production',NEXT_TELEMETRY_DISABLED='1',REQUIRE_API_KEY='true',OMNIROUTE_HEADLESS='1',NODE_OPTIONS='--max-old-space-size='+os.environ.get('OMNIROUTE_MEMORY_MB','320'))
  entry=Path(os.environ.get('OMNIROUTE_SERVER_ENTRY','/opt/omniroute/node_modules/omniroute/dist/server-ws.mjs'))
  node=subprocess.Popen([os.environ.get('OMNIROUTE_NODE','node'),str(entry)],cwd=entry.parent,env=node_env)
  deadline=time.monotonic()+240
  while time.monotonic()<deadline and not stopped.is_set():
   if node.poll() is not None:raise RuntimeError('OmniRoute terminó durante el arranque')
   try:
    with httpx.Client(timeout=4,trust_env=False) as c:r=c.get(base+'/api/monitoring/health',headers={'Authorization':'Bearer '+management})
    if r.status_code==200:break
   except httpx.HTTPError:pass
   stopped.wait(2)
  else:raise RuntimeError('OmniRoute no alcanzó disponibilidad')
  inference=configure_gateway(base,directory,management,providers,combo)
  worker_env=os.environ.copy();worker_env.update(LLM_BASE_URL=base+'/v1',LLM_API_KEY=inference,LLM_MODEL='yakukhipu',LLM_ENABLED='true')
  for key in ['YAKUKHIPU_OMNI_PROVIDERS','OMNIROUTE_API_KEY','INITIAL_PASSWORD','STORAGE_ENCRYPTION_KEY','JWT_SECRET','API_KEY_SECRET']:worker_env.pop(key,None)
  worker=subprocess.Popen([sys.executable,'-m','app.worker_pdf'],env=worker_env)
  ready.set();LOG.info('OmniRoute y worker listos; combo yakukhipu configurado')
  while not stopped.wait(1):
   if node.poll() is not None or worker.poll() is not None:raise RuntimeError('Terminó un proceso supervisado')
  return 0
 except Exception as exc:
  LOG.error('No se pudo iniciar el servicio combinado: %s',type(exc).__name__)
  return 1
 finally:
  ready.clear();terminate(worker,10);terminate(node,40);server.shutdown()

if __name__=='__main__':raise SystemExit(main())
