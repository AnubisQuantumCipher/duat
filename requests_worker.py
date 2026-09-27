#!/usr/bin/env python3
"""Persistent user-requested retrievals; never deletes existing destinations."""
import fcntl
import json
from pathlib import Path
import subprocess
from vault import Vault,VaultError,save_json,now
from cold import get

def main():
 v=Vault(Path.home()/'.config/project-vault/config.json')
 with (v.state/'requests.lock').open('a') as lock:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:return
  for p in sorted((v.state/'requests').glob('*.json')):
   job=json.loads(p.read_text())
   if job['state'] not in ('queued','waiting','running'):continue
   job.update(state='running',updated=now());save_json(p,job)
   try:
    result=get(v,job['item'])
    job.update(state='done',result=result,finished=now())
    subprocess.run(['notify-send','Folder restored',result['restored']],check=False)
   except (VaultError,OSError) as e:
    message=str(e)
    waiting=getattr(e,'exit_code',None)==11 or any(x in message for x in ('offline','Another vault','queued until','Insufficient'))
    job.update(state='waiting' if waiting else 'failed',error=message,updated=now())
   save_json(p,job)

if __name__=='__main__':main()
