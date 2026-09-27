"""Explicit origin records for artifacts; never infer original build flags from names."""
import json
from pathlib import Path
import subprocess
import hashlib
from vault import save_json,VaultError,now

def register(vault,path,repository,rebuild,toolchain):
 path=Path(path).expanduser().resolve();repo=Path(repository).expanduser().resolve()
 if not rebuild.strip() or not toolchain.strip():raise VaultError('Record the rebuild command and pinned toolchain.')
 result=subprocess.run(['git','-C',str(repo),'rev-parse','HEAD'],capture_output=True,text=True,check=True)
 dirty=subprocess.run(['git','-C',str(repo),'status','--porcelain'],capture_output=True,text=True,check=True)
 value={'path':str(path),'repository':str(repo),'source_commit':result.stdout.strip(),
        'working_tree_dirty':bool(dirty.stdout),'rebuild_command':rebuild,'toolchain':toolchain,
        'recorded':now(),'boundary':'Operator-supplied build recipe and current source identity; this is not a demonstrated rebuild.'}
 if dirty.stdout:value['source_warning']='Uncommitted source changes require their own snapshot; commit identity alone is insufficient.'
 dest=vault.state/'provenance'/ (hashlib.sha256(str(path).encode()).hexdigest()+'.json')
 save_json(dest,value);return value

def lookup(vault,path):
 p=vault.state/'provenance'/(hashlib.sha256(str(path).encode()).hexdigest()+'.json')
 return json.loads(p.read_text()) if p.exists() else {'state':'unrecorded','boundary':'No original rebuild recipe or toolchain claim has been established.'}
