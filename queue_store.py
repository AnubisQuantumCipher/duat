"""Short locked queue edits, independently of the long-running worker."""
import contextlib
import fcntl
import json
from pathlib import Path
import uuid
from vault import save_json,VaultError,now

@contextlib.contextmanager
def edit(state):
    with (state/'queue-edit.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        path=state/'offload-queue.json'
        entries=json.loads(path.read_text()) if path.exists() else []
        for entry in entries:entry.setdefault('id',uuid.uuid4().hex)
        yield entries
        save_json(path,entries)

def enqueue(vault,path):
    from cold import validate_path
    path=validate_path(vault,path)
    st=path.stat()
    with edit(vault.state) as entries:
        for e in entries:
            if e['path']==str(path) and e['state'] in ('queued','waiting','running'):
                return e
        entry={'id':uuid.uuid4().hex,'path':str(path),'identity':[st.st_dev,st.st_ino],
               'state':'queued','classification':'explicit enrollment','enrolled':now()}
        entries.append(entry)
    return entry

def update(state_dir,identity,**changes):
    with edit(state_dir) as entries:
        for entry in entries:
            if entry['id']==identity:entry.update(changes);return
        raise VaultError('Queue item disappeared during operation')

def cancel(state,identity):
    with edit(state) as entries:
        for e in entries:
            if e['id']==identity:
                if e['state']=='running':raise VaultError('Current transfer continues; pause stops after it completes.')
                e['state']='cancelled';return
        raise VaultError('Unknown queue item')
