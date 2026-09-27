#!/usr/bin/env python3
"""Loopback-only control surface for explicit storage actions."""
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from pathlib import Path
import json
import os
import secrets
import subprocess
import uuid
import bench
from health import status,STATE,read_json
from vault import Vault,VaultError,save_json,now
from queue_store import enqueue,cancel

PORT=8767
TOKEN=secrets.token_urlsafe(32)
CONFIG=Path.home()/'.config/project-vault/config.json'
ALLOWED_HOSTS={f'127.0.0.1:{PORT}',f'localhost:{PORT}'}

def start(unit):
 subprocess.run(['systemctl','--user','start','--no-block',unit],check=True,capture_output=True,text=True)

class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def send(self,code,body,kind='application/json'):
  if kind=='application/json':body=json.dumps(body).encode()
  elif isinstance(body,str):body=body.encode()
  self.send_response(code);self.send_header('Content-Type',kind);self.send_header('Cache-Control','no-store')
  self.send_header('X-Content-Type-Options','nosniff');self.send_header('X-Frame-Options','DENY')
  self.send_header('Referrer-Policy','no-referrer');self.send_header('Content-Length',str(len(body)))
  self.end_headers();self.wfile.write(body)
 def authorized_host(self):return self.headers.get('Host') in ALLOWED_HOSTS
 def do_GET(self):
  if not self.authorized_host():return self.send(403,{'error':'Local access only'})
  if self.path=='/':
   html=Path(__file__).with_name('dashboard.html').read_text().replace('__TOKEN__',TOKEN)
   return self.send(200,html,'text/html; charset=utf-8')
  if self.path=='/bench':
   page=Path(__file__).with_name('bench.html').read_text().replace('__TOKEN__',TOKEN)
   return self.send(200,page,'text/html; charset=utf-8')
  if self.path=='/api/bench':
   try:return self.send(200,bench.overview(STATE,CONFIG))
   except (VaultError,OSError,ValueError):return self.send(503,{'error':'Benchmark state unavailable'})
  if self.path.startswith('/api/bench/'):
   parts=self.path.split('/')
   if len(parts)!=5 or parts[4] not in ('report.json','samples.csv','card.html'):
    return self.send(404,{'error':'Unknown benchmark export'})
   try:
    report=bench.read_report(STATE,parts[3])
    if parts[4]=='report.json':return self.send(200,report)
    if report['state'] not in bench.TERMINAL:return self.send(409,{'error':'Wait for the run to end before exporting'})
    path=bench.runs_root(STATE)/parts[3]/parts[4]
    if path.is_symlink():raise VaultError('Invalid export')
    content=path.read_bytes()
   except (VaultError,OSError):return self.send(404,{'error':'Export unavailable'})
   return self.send(200,content,'text/csv; charset=utf-8' if parts[4]=='samples.csv' else 'text/html; charset=utf-8')
  if self.path=='/api/status':return self.send(200,status())
  return self.send(404,{'error':'Not found'})
 def do_POST(self):
  if not self.authorized_host() or self.headers.get('Origin')!='http://'+self.headers.get('Host','') or not secrets.compare_digest(self.headers.get('X-Vault-Token',''),TOKEN):
   return self.send(403,{'error':'Invalid local action token or origin'})
  if self.path!='/api/action':return self.send(404,{'error':'Not found'})
  v=None
  try:
   length=int(self.headers.get('Content-Length','0'))
   if length<=0 or length>8192:raise VaultError('Invalid request size')
   data=json.loads(self.rfile.read(length))
   if not isinstance(data,dict):raise VaultError('Expected an action object')
   action=data.get('action')
   if action=='bench-start':
    options=bench.validate_options(data.get('size_mib',16),data.get('files',8),data.get('pattern','incompressible'))
    identity=bench.reserve_request(CONFIG,options,detached=True)
    result={'message':'Synthetic benchmark requested. It will refuse if storage is offline, busy, or below reserve.','id':identity}
   elif action=='bench-cancel':result=bench.cancel_run(STATE,data.get('id'))
   elif action=='pause':(STATE/'offload-paused').touch();result={'message':'Offload will pause after the current folder finishes.'}
   elif action=='resume':
    (STATE/'offload-paused').unlink(missing_ok=True);start('project-vault-tier.service');result={'message':'Offload queue resumed.'}
   elif action=='backup':start('project-vault-backup.service');result={'message':'Backup requested. It waits if storage is busy.'}
   elif action=='get':
    item=next((x for x in status()['items'] if x['id']==data.get('item')),None)
    if not item:raise VaultError('Unknown saved folder')
    if item['local_exists']:raise VaultError('Folder already exists locally. No overwrite allowed.')
    requests=STATE/'requests';requests.mkdir(exist_ok=True)
    for p in requests.glob('*.json'):
     existing=read_json(p,{})
     if existing.get('item')==item['id'] and existing.get('state') in ('queued','waiting','running'):raise VaultError('This retrieval is already queued.')
    identity=uuid.uuid4().hex
    save_json(requests/(identity+'.json'),{'id':identity,'item':item['id'],'path':item['path'],'state':'queued','created':now()})
    start('project-vault-requests.service');result={'message':'Retrieval queued. Existing transfers finish first.'}
   elif action=='queue':
    if not isinstance(data.get('path'),str):raise VaultError('Enter an exact directory path')
    v=Vault(Path.home()/'.config/project-vault/config.json');entry=enqueue(v,data['path'])
    start('project-vault-tier.service');result={'message':'Folder enrolled for verified offload.','item':entry}
   elif action=='cancel':cancel(STATE,data.get('item'));result={'message':'Queued offload cancelled.'}
   else:raise VaultError('Unknown action')
   return self.send(200,result)
  except (ValueError,OSError,VaultError,subprocess.SubprocessError) as e:return self.send(400,{'error':str(e)})
  finally:
   if v is not None:v.db.close()

if __name__=='__main__':
 STATE.mkdir(parents=True,exist_ok=True)
 ThreadingHTTPServer(('127.0.0.1',PORT),Handler).serve_forever()
