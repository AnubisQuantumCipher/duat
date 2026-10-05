#!/usr/bin/env python3
"""Independent project scopes: a failed scope never erases another scope's status."""
import fcntl
import json
from pathlib import Path
import subprocess
from vault import Vault,VaultError,save_json,now
from health import read_json


def main():
 h=Path.home();v=Vault(h/'.config/project-vault/config.json')
 with (v.state/'scheduler.lock').open('a') as scheduler:
  try:fcntl.flock(scheduler,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:return
  try:
   v.online()
   with v.locked():
    if (v.repo/'config').exists():
     from lock_recovery import recover
     recover(v)
  except (VaultError,OSError) as e:print('BACKUP DEFERRED: '+str(e),flush=True);return
  v.initialize()
  health_file=v.state/'project-health.json';health=read_json(health_file,{})
  # Anubis retains the established extended scope, including caches, identities and worktrees.
  scopes=[('Anubis','anubis-complete-scope',None)]
  for base in v.cfg['project_roots']:
   base=Path(base)
   if base.name=='Projects':
    for p in sorted(base.iterdir()):
     if p.name in ('anubis','anubis-lang','anubis-desktop'):continue
     scopes.append((p.name,'project-'+p.name,[str(p)]))
   elif base.name=='Work' and v.cfg.get('work_partial_policy'):
    scopes.append(('Work readable partial','project-Work-readable-partial',[str(base)]))
   else:scopes.append((base.name,'project-'+base.name,[str(base)]))
  failures=[]
  for name,tag,paths in scopes:
   try:
    v.online()
    partial_manifest=None
    if tag=='project-Work-readable-partial':
     from work_partial import prepare
     if health.get('project-Work',{}).get('state')!='incomplete':
      raise VaultError('Original broad Work scope is not recorded INCOMPLETE')
     paths,partial_manifest=prepare(v.config_path,Path(paths[0]),
                                    Path(v.cfg['work_partial_policy']))
     save_json(v.state/'work-partial-scheduled-plan.json',partial_manifest)
    if name=='Anubis':
     from anubis_backup import backup_anubis
     snap=backup_anubis()
    else:
     scoped=Vault(h/'.config/project-vault/config.json')
     scoped.cfg.update(project_roots=[],additional_paths=paths,snapshot_tag=tag)
     try:
      snap=scoped.backup()
      if partial_manifest is not None:
       from work_partial import check_saved_map
       check_saved_map(scoped,snap,partial_manifest)
       partial_manifest.update(state='PASS_PARTIAL_SCOPE',snapshot=snap)
       save_json(v.state/'work-partial-scheduled-plan.json',partial_manifest)
       ipad_manifest=scoped.root/'Recovery/Partial-Scopes'/(snap+'.scheduled-manifest.json')
       save_json(ipad_manifest,partial_manifest)
       if json.loads(ipad_manifest.read_text())!=partial_manifest:
        raise VaultError('Partial Work iPad manifest readback differs')
     finally:scoped.db.close()
    health[tag]={'name':name,'state':'passed','snapshot':snap,'updated':now(),
                 'verification':('partial declared scope; snapshot and repository metadata checked; no scheduled full restore'
                                 if partial_manifest is not None else
                                 'snapshot saved and repository metadata checked')}
   except (VaultError,OSError) as e:
    message=str(e)
    if 'Another vault' in message or 'Another repository' in message or 'offline' in message or getattr(e,'exit_code',None)==11:
     print('BACKUP DEFERRED: '+message,flush=True);break
    previous=health.get(tag,{})
    health[tag]={'name':name,'state':'incomplete' if getattr(e,'exit_code',None)==3 else 'failed',
                 'error':message,'updated':now(),'last_success':previous.get('snapshot') or previous.get('last_success')}
    failures.append(name)
    print('SCOPE INCOMPLETE: '+name+': '+message,flush=True)
   finally:save_json(health_file,health)
  try:
   v.online();save_json(v.root/'Recovery/project-health.json',health)
  except (VaultError,OSError):pass
  # Publish fresh recovery tooling and audit cold references without pruning.
  try:
   from recovery import audit, export_kit
   report=audit(v, online=True)
   export_kit(v)
   if report['state']!='passed':
    print('RECOVERY AUDIT NEEDS ATTENTION: inspect recovery-audit.json',flush=True)
  except (VaultError,OSError,ValueError) as e:
   waiting=getattr(e,'exit_code',None)==11 or any(x in str(e) for x in ('offline','Another vault','queued until'))
   print(('RECOVERY MAINTENANCE DEFERRED: ' if waiting else 'RECOVERY MAINTENANCE FAILED: ')+str(e),flush=True)
   save_json(v.state/'recovery-maintenance.json',{'state':'waiting' if waiting else 'failed','time':now(),'reason':str(e)})
  else:
   save_json(v.state/'recovery-maintenance.json',{'state':'passed' if report['state']=='passed' else 'needs-attention','time':now()})
  if failures:subprocess.run(['notify-send','Project Vault: incomplete project backups',', '.join(failures)+' — other project scopes were processed independently.'],check=False)

if __name__=='__main__':main()
