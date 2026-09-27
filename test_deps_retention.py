import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from vault import Vault,VaultError
import cold

class RetentionTests(unittest.TestCase):
 def test_offload_retains_executable_and_so_but_frees_objects(self):
  with tempfile.TemporaryDirectory() as tmp:
   home=Path(tmp);deps=home/'Projects/example/target/debug/deps';deps.mkdir(parents=True)
   (deps.parent/'.cargo-lock').touch()
   (deps/'compiler').write_text('unique compiler');(deps/'compiler').chmod(0o755)
   (deps/'libmacro.so').write_text('shared object')
   (deps/'libpart.rlib').write_text('reproducible archive')
   (deps/'proof.json').write_text('unique receipt')
   config=home/'config.json';config.write_text(json.dumps(dict(home=str(home),state=str(home/'state'),mount=str(home/'device'),root=str(home/'device/TryOmarchy'),vault_id='test',require_ifuse_mount=False,reserve_bytes=0,local_reserve_bytes=0,project_roots=[],additional_paths=[])))
   v=Vault(config)
   try:
    v.initialize();before=cold.inventory(deps)
    item=cold.put(v,deps,True,retain_binaries=True)
    retained=Path(item['retained_local']['path'])
    self.assertFalse(deps.exists());self.assertTrue((retained/'compiler').exists());self.assertTrue((retained/'libmacro.so').exists());self.assertTrue((retained/'proof.json').exists());self.assertFalse((retained/'libpart.rlib').exists())
    self.assertIn(str(retained),json.loads((v.state/'pinned-paths.json').read_text()))
    cold.get(v,item['id'])
    self.assertEqual(cold.inventory(deps),before)
    with self.assertRaises(VaultError):cold.put(v,retained,True)
   finally:v.db.close()
 def test_generated_cache_uses_existing_mutex_protocol(self):
  with tempfile.TemporaryDirectory() as tmp:
   profile=Path(tmp)/'anubis-run-cargo-target-audited-crypto-v3/release';profile.mkdir(parents=True)
   mutex=profile.parent/'.anubis-build-mutex'
   with cold.cargo_build_guard(profile):
    self.assertTrue((mutex/'owner').read_text().startswith('pid='))
    with self.assertRaises(VaultError):
     with cold.cargo_build_guard(profile):pass
   self.assertFalse(mutex.exists())
   mutex.mkdir();(mutex/'owner').write_text('pid=999999999\n')
   with self.assertRaises(VaultError):
    with cold.cargo_build_guard(profile):pass
   self.assertTrue(mutex.exists())
 def test_deps_profile_lock_is_required(self):
  with tempfile.TemporaryDirectory() as tmp:
   deps=Path(tmp)/'debug/deps';deps.mkdir(parents=True)
   with self.assertRaises(VaultError):
    with cold.cargo_build_guard(deps):pass

if __name__=='__main__':unittest.main()
