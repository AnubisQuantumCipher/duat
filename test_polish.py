import concurrent.futures
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from vault import Vault, VaultError, save_json
from pins import set_pin, locked
from recovery import audit, export_kit
from verify_kit import verify
from scrub import scrub

class PolishTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.home=Path(self.tmp.name)
  config={'home':str(self.home),'state':str(self.home/'state'),'mount':str(self.home/'device'),
          'root':str(self.home/'device/TryOmarchy'),'vault_id':'fixture','require_ifuse_mount':False,
          'reserve_bytes':0,'local_reserve_bytes':0,'project_roots':[],'additional_paths':[]}
  file=self.home/'config.json';file.write_text(json.dumps(config));self.v=Vault(file)
 def tearDown(self):
  self.v.db.close();self.tmp.cleanup()
 def test_concurrent_json_writes_remain_complete(self):
  file=self.home/'shared.json'
  def write(i):save_json(file,{'writer':i,'payload':str(i)*10000})
  with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:list(pool.map(write,range(50)))
  final=json.loads(file.read_text());self.assertEqual(final['payload'],str(final['writer'])*10000)
  self.assertFalse(list(self.home.glob('.*.new')))
 def test_failed_json_encode_preserves_previous_file(self):
  file=self.home/'record.json';save_json(file,{'old':True})
  with self.assertRaises(TypeError):save_json(file,{'unsupported':object()})
  self.assertEqual(json.loads(file.read_text()),{'old':True})
 def test_concurrent_pins_not_lost(self):
  paths=[str(self.home/'Work'/str(i)) for i in range(20)]
  with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:list(pool.map(lambda p:set_pin(self.v,p),paths))
  self.assertEqual(set(json.loads((self.v.state/'pinned-paths.json').read_text())),set(paths))
 def test_pin_waits_for_final_retirement_lock(self):
  with locked(self.v.state):
   pool=concurrent.futures.ThreadPoolExecutor(max_workers=1);future=pool.submit(set_pin,self.v,self.home/'Work/current')
   with self.assertRaises(concurrent.futures.TimeoutError):future.result(timeout=.1)
  self.assertIn('pin',future.result(timeout=5));pool.shutdown()
 def test_scrub_deferred_preserves_last_success_separately(self):
  save_json(self.v.state/'scrub.json',{'state':'passed','time':'prior-success'})
  with patch.object(self.v,'online',side_effect=VaultError('iPad is offline')):result=scrub(self.v)
  self.assertEqual(result['state'],'waiting');self.assertEqual(result['last_success'],'prior-success')
  self.assertNotEqual(result['time'],'prior-success')
 def test_exit11_scrub_is_waiting(self):
  e=VaultError('repository locked');e.exit_code=11
  with patch.object(self.v,'online'),patch.object(self.v,'run',side_effect=e):result=scrub(self.v)
  self.assertEqual(result['state'],'waiting')
 def test_kit_roundtrip_tamper_and_failure_keep_previous_pointer(self):
  self.v.initialize();result=export_kit(self.v);folder=Path(result['path'])
  self.assertEqual(verify(folder)['state'],'passed');self.assertEqual(export_kit(self.v)['state'],'unchanged')
  pointer=self.v.root/'Recovery/latest-kit.json';previous=pointer.read_bytes()
  (folder/'Tools/vault.py').write_text('broken');self.assertEqual(verify(folder)['state'],'failed')
  with patch('recovery.verify',return_value={'state':'failed'}):
   with self.assertRaises(VaultError):export_kit(self.v)
  self.assertEqual(pointer.read_bytes(),previous)
  repaired=export_kit(self.v);self.assertNotEqual(repaired['path'],str(folder))
  self.assertEqual(verify(Path(repaired['path']))['state'],'passed')
 def test_online_audit_detects_missing_snapshot_and_remote_receipt(self):
  self.v.initialize();item={'id':'example','snapshot':'a'*64,'content_manifest_sha256':'b'*64,
    'tag':'cold-example','path':str(self.home/'Work/retired'),'state':'offloaded'}
  save_json(self.v.state/'items/example.json',item)
  with patch.object(self.v,'run',return_value='[]'):result=audit(self.v,True)
  self.assertEqual(result['state'],'needs-attention')
  self.assertTrue(any('snapshot is missing' in x['error'] for x in result['issues']))
  self.assertTrue(any('receipt missing' in x['error'] for x in result['issues']))
  save_json(self.v.root/'Recovery/items/example.json',item)
  snap={'id':item['snapshot'],'tags':[item['tag']],'paths':[item['path']]}
  with patch.object(self.v,'run',return_value=json.dumps([snap])):result=audit(self.v,True)
  self.assertEqual(result['state'],'passed')
 def test_recovery_required_and_bad_record_are_visible(self):
  item={'id':'example','snapshot':'a'*64,'content_manifest_sha256':'b'*64,
    'path':str(self.home/'Work/retired'),'state':'recovery-required'}
  save_json(self.v.state/'items/example.json',item);(self.v.state/'items/bad.json').write_text('{')
  result=audit(self.v);self.assertEqual(result['state'],'needs-attention');self.assertEqual(len(result['issues']),2)

if __name__=='__main__':unittest.main()
