"""Read-only dashboard data. No repository unlocks, pruning or file traversal."""
from collections import Counter
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess

HOME=Path.home()
STATE=HOME/'.local/state/project-vault'

def read_json(path, default=None):
    try: return json.loads(Path(path).read_text())
    except (OSError,ValueError): return default

def alive(pid):
    return bool(pid and Path('/proc',str(pid)).exists())

def status():
    disk=shutil.disk_usage(HOME)
    mounted=any(line.split()[1:3]==[str(HOME/'iPad'),'fuse.ifuse'] for line in Path('/proc/mounts').read_text().splitlines())
    queue=read_json(STATE/'offload-queue.json',[])
    cold=[]
    for p in sorted((STATE/'items').glob('*.json')):
        item=read_json(p)
        if item:
            item['local_exists']=Path(item['path']).exists()
            cold.append(item)
    operation=read_json(STATE/'operation.json',{})
    if operation.get('state')=='running' and not alive(operation.get('owner_pid')):
        operation['state']='interrupted'
    phase=read_json(STATE/'cold-operation.json',{})
    if phase.get('state')=='running' and not alive(phase.get('pid')):phase['state']='interrupted'
    projects=read_json(STATE/'project-health.json',{})
    result={'observed_at':dt.datetime.now(dt.timezone.utc).isoformat(),
        'local':dict(total=disk.total,used=disk.used,free=disk.free),'ipad_connected':mounted,
        'queue':queue,'queue_counts':dict(Counter(x['state'] for x in queue)),
        'items':cold,'operation':operation,'cold_operation':phase,'projects':projects,
        'paused':(STATE/'offload-paused').exists(),
        'catalog_bytes':(STATE/'catalog.sqlite').stat().st_size if (STATE/'catalog.sqlite').exists() else 0,
        'pins':read_json(STATE/'pinned-paths.json',[]),
        'jobs':[read_json(p,{}) for p in sorted((STATE/'requests').glob('*.json'))],
        'anubis_recovery':read_json(STATE/'anubis-recovery-check.json'),
        'scrub':read_json(STATE/'scrub.json')}
    result['restore_drill'] = read_json(STATE/'restore-drill.json')
    result['recovery_audit'] = read_json(STATE/'recovery-audit.json')
    result['recovery_kit'] = read_json(STATE/'recovery-kit.json')
    result['recovery_maintenance'] = read_json(STATE/'recovery-maintenance.json')
    return result

if __name__=='__main__': print(json.dumps(status(),indent=2))
