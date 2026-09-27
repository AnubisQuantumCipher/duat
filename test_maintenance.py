import fcntl
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import Mock, patch
from cold import cargo_build_guard
from lock_recovery import recover
from vault import VaultError

class MaintenanceTests(unittest.TestCase):
 def test_cargo_lock_blocks_cleanup(self):
  with tempfile.TemporaryDirectory() as tmp:
   profile=Path(tmp)/'debug';profile.mkdir()
   cache=profile/'incremental';cache.mkdir()
   lockpath=profile/'.cargo-lock';lockpath.touch()
   with lockpath.open('r+b') as held:
    fcntl.flock(held,fcntl.LOCK_EX|fcntl.LOCK_NB)
    with self.assertRaises(VaultError):
     with cargo_build_guard(cache):pass
   with cargo_build_guard(cache):self.assertTrue(cache.exists())
 def test_only_dead_local_owner_unlocked(self):
  v=Mock();v.run.side_effect=['a'*64+'\n',json.dumps({'hostname':socket.gethostname(),'pid':123}),None]
  with patch('lock_recovery.os.kill',side_effect=ProcessLookupError):
   self.assertEqual(recover(v),['a'*64])
  self.assertIn(unittest.mock.call('unlock'),v.run.call_args_list)
 def test_live_or_foreign_owner_not_unlocked(self):
  for host in (socket.gethostname(),'foreign-owner'):
   v=Mock();v.run.side_effect=['a'*64+'\n',json.dumps({'hostname':host,'pid':123})]
   with patch('lock_recovery.os.kill'):
    with self.assertRaises(VaultError):recover(v)
   self.assertNotIn(unittest.mock.call('unlock'),v.run.call_args_list)
