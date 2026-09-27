import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from vault import Vault, VaultError
import cold

class ColdTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir='/tmp'); self.h=Path(self.tmp.name)
  self.src=self.h/'Projects/project/output'; self.src.mkdir(parents=True)
  (self.src/'proof.txt').write_text('evidence that must survive')
  (self.src/'run').write_text('executable bytes'); (self.src/'run').chmod(0o755)
  (self.src/'link').symlink_to('proof.txt')
  (self.src/'empty').mkdir()
  self.c=self.h/'config.json'; self.c.write_text(json.dumps(dict(home=str(self.h),state=str(self.h/'state'),mount=str(self.h/'device'),root=str(self.h/'device/TryOmarchy'),vault_id='test',require_ifuse_mount=False,reserve_bytes=0,local_reserve_bytes=0,project_roots=[],additional_paths=[])))
  self.v=Vault(self.c); self.v.initialize()
 def tearDown(self):
  self.v.db.close(); self.tmp.cleanup()
 def test_offload_and_get_exact(self):
  original=cold.inventory(self.src)
  entry=cold.put(self.v,self.src,True)
  self.assertFalse(self.src.exists()); self.assertEqual(entry['state'],'offloaded')
  self.assertTrue(self.src.with_name('output.ipad.json').exists())
  cold.get(self.v,entry['id'])
  self.assertEqual(cold.inventory(self.src),original)
  with self.assertRaises(VaultError): cold.get(self.v,entry['id'])
 def test_failure_retains_source(self):
  with patch.object(self.v,'run',side_effect=VaultError('connection failure')):
   with self.assertRaises(VaultError): cold.put(self.v,self.src,True)
  self.assertTrue((self.src/'proof.txt').exists())
 def test_source_change_during_verification_prevents_offload(self):
  real=self.v.run
  def change(*args,**kwargs):
   result=real(*args,**kwargs)
   if args[0]=='restore': (self.src/'proof.txt').write_text('changed while verifying')
   return result
  with patch.object(self.v,'run',side_effect=change):
   with self.assertRaises(VaultError): cold.put(self.v,self.src,True)
  self.assertEqual((self.src/'proof.txt').read_text(),'changed while verifying')
 def test_pin_blocks_eviction(self):
  (self.v.state/'pinned-paths.json').write_text(json.dumps([str(self.src)]))
  with self.assertRaises(VaultError): cold.put(self.v,self.src,True)
  self.assertTrue(self.src.exists())
 def test_pin_added_during_restore_blocks_eviction(self):
  real=self.v.run
  def pin(*args,**kwargs):
   result=real(*args,**kwargs)
   if args[0]=='restore':
    (self.v.state/'pinned-paths.json').write_text(json.dumps([str(self.src)]))
   return result
  with patch.object(self.v,'run',side_effect=pin):
   with self.assertRaises(VaultError):cold.put(self.v,self.src,True)
  self.assertTrue(self.src.exists())
 def test_interrupted_restore_resumes_snapshot(self):
  real=self.v.run
  def fail(*args,**kwargs):
   if args[0]=='restore':raise VaultError('interrupted restore')
   return real(*args,**kwargs)
  with patch.object(self.v,'run',side_effect=fail):
   with self.assertRaises(VaultError):cold.put(self.v,self.src,True)
  jobs=list((self.v.state/'cold-jobs').glob('*/job.json'))
  snapshot=json.loads(jobs[0].read_text())['snapshot']
  item=cold.put(self.v,self.src,True)
  self.assertEqual(item['snapshot'],snapshot)
  cold.get(self.v,item['id'])
  self.assertTrue((self.src/'proof.txt').exists())
 def test_whole_scope_drill_and_reserve(self):
  from drill import drill
  from vault import save_json
  from types import SimpleNamespace
  original=cold.inventory(self.src)
  item=cold.put(self.v,self.src)
  save_json(self.v.state/'project-health.json',{'anubis-complete-scope':{'state':'passed','snapshot':item['snapshot']}})
  with patch('drill.shutil.disk_usage',return_value=SimpleNamespace(free=0)):
   self.assertEqual(drill(self.v)['state'],'waiting')
  self.assertEqual(drill(self.v)['state'],'passed')
  self.assertEqual(cold.inventory(self.src),original)
  self.assertFalse(list(self.v.state.glob('scope-drill-*')))
 def test_active_and_symlink_rejected(self):
  with (self.src/'proof.txt').open() as f:
   # Own-process handles are excluded; test detection via a distinct process.
   import subprocess
   p=subprocess.Popen(['sleep','30'],cwd=self.src)
   try:
    with self.assertRaises(VaultError): cold.put(self.v,self.src,True)
   finally: p.terminate();p.wait()
  link=self.src.parent/'alias';link.symlink_to(self.src)
  with self.assertRaises(VaultError): cold.put(self.v,link,True)

if __name__=='__main__': unittest.main()
