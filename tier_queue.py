#!/usr/bin/env python3
"""Drain explicitly enrolled folders, yielding to retrieval and pause requests."""
import fcntl
import json
import os
from pathlib import Path
from vault import Vault, VaultError, now, save_json
from cold import put, items
from queue_store import edit,update


def main():
    v=Vault(Path.home()/'.config/project-vault/config.json')
    with (v.state/'tier-queue.lock').open('a') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return
        attempted=set()
        while True:
            if (v.state/'offload-paused').exists():print('PAUSED after completed item',flush=True);return
            for p in (v.state/'requests').glob('*.json'):
                request=json.loads(p.read_text())
                if request['state'] in ('queued','waiting','running'):
                    print('YIELDING to requested retrieval',flush=True);return
            try:v.online()
            except (VaultError,OSError) as e:print('WAITING FOR IPAD: '+str(e),flush=True);return
            with edit(v.state) as entries:
                for e in entries:
                    if e['state']=='running':e['state']='waiting'
                    if e['state']=='needs-review' and e.get('error','').startswith('iPad connection changed during transfer;'):e['state']='waiting'
                entry=next((dict(e) for e in entries if e['state'] in ('queued','waiting') and e['id'] not in attempted),None)
            if entry is None:return
            identity=entry['id'];attempted.add(identity);p=Path(entry['path'])
            if not p.exists():
                known=[x for x in items(v) if x['path']==str(p) and x['state']=='offloaded']
                update(v.state,identity,state='done' if known else 'needs-review');continue
            st=p.lstat()
            from provenance import lookup
            if lookup(v,p).get('state') == 'unrecorded':
                update(v.state,identity,state='needs-review',error='Record source commit, toolchain and rebuild command before automated offload; original retained.')
                continue
            if [st.st_dev,st.st_ino]!=entry['identity']:
                update(v.state,identity,state='needs-review',error='Path identity changed since enrollment');continue
            update(v.state,identity,state='running',started=now(),pid=os.getpid())
            try:
                result=put(v,p,offload=True)
                update(v.state,identity,state='done',item=result['id'],finished=now(),error=None)
                print('OFFLOADED: '+str(p),flush=True)
            except (VaultError,OSError) as e:
                message=str(e)
                waiting=getattr(e,'exit_code',None)==11 or any(x in message for x in ('offline','Another vault','in use','became active','queued until','Insufficient','iPad connection changed'))
                update(v.state,identity,state='waiting' if waiting else 'needs-review',error=message)
                save_json(v.state/'cold-operation.json',{'state':'waiting' if waiting else 'failed','path':str(p),'error':message,'finished':now()})
                print('OFFLOAD DEFERRED: '+str(p)+': '+message,flush=True)
                if not waiting:
                    import subprocess
                    subprocess.run(['notify-send','Project Vault needs attention',str(p)+': inspect its receipt and any quarantine before cleanup. '+message],check=False)
                if getattr(e,'exit_code',None)==11 or any(x in message for x in ('offline','Another vault','connection changed')):return

if __name__=='__main__':main()
