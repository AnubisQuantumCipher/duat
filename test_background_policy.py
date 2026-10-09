import fcntl
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import background_policy
import recovery
import scheduled
import tier_queue


class BackgroundPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / 'state'
        self.state.mkdir()
        self.proc = self.root / 'proc'
        self.proc.mkdir()
        self.window = self.root / 'window.json'
        self.window.write_text(json.dumps({'status': 'released'}))
        self.config = {'state': str(self.state), 'background_policy': {
            'coordination_files': [str(self.window)]}}

    def decision(self):
        return background_policy.assess(self.config, proc_root=self.proc)

    def test_released_window_allows_without_retaining_vault_lock(self):
        self.assertTrue(self.decision()['allowed'])
        with (self.state / 'operation.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def test_reserved_unknown_missing_and_malformed_window_defer(self):
        for record in ({'status': 'reserved'}, {'status': 'running'}, {}, []):
            self.window.write_text(json.dumps(record))
            self.assertFalse(self.decision()['allowed'])
        self.window.write_text('{')
        self.assertFalse(self.decision()['allowed'])
        self.window.unlink()
        self.assertFalse(self.decision()['allowed'])

    def test_compiler_deferred_but_agent_process_is_not_a_build(self):
        process = self.proc / '101'
        process.mkdir()
        for name in ('gnatprove', 'gprbuild', 'gnat2why', 'rustc'):
            (process / 'comm').write_text(name + '\n')
            self.assertFalse(self.decision()['allowed'])
            self.assertEqual(self.decision()['command'], name)
        (process / 'comm').write_text('omp\n')
        self.assertTrue(self.decision()['allowed'])

    def test_retrieval_pending_has_priority_and_receipt_is_unchanged(self):
        folder = self.state / 'requests'
        folder.mkdir()
        path = folder / 'request.json'
        for state in ('queued', 'waiting', 'running'):
            path.write_text(json.dumps({'state': state, 'item': 'untouched'}))
            before = path.read_bytes()
            self.assertFalse(self.decision()['allowed'])
            self.assertEqual(path.read_bytes(), before)
        path.write_text(json.dumps({'state': 'done'}))
        self.assertTrue(self.decision()['allowed'])

    def test_busy_vault_never_unlocks_or_replaces_other_owner(self):
        path = self.state / 'operation.lock'
        with path.open('a') as owner:
            fcntl.flock(owner, fcntl.LOCK_EX)
            inode = path.stat().st_ino
            self.assertFalse(self.decision()['allowed'])
            self.assertEqual(path.stat().st_ino, inode)
            with path.open('a') as competitor:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(competitor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.assertTrue(self.decision()['allowed'])

    def test_missing_unknown_and_malformed_request_state_defer(self):
        folder = self.state / 'requests'
        folder.mkdir()
        path = folder / 'request.json'
        for record in ({}, {'state': 'unknown'}, {'state': None}, [], 'invalid'):
            path.write_text(json.dumps(record))
            self.assertFalse(self.decision()['allowed'])
        path.write_text('{')
        self.assertFalse(self.decision()['allowed'])
        path.write_text(json.dumps({'state': 'failed'}))
        self.assertTrue(self.decision()['allowed'])

    def test_dangling_retrieval_directory_symlink_defers(self):
        (self.state / 'requests').symlink_to(self.root / 'missing-retrievals')
        self.assertFalse(self.decision()['allowed'])

    @unittest.skipIf(os.geteuid() == 0, 'Root bypasses this filesystem permission check')
    def test_unreadable_retrieval_directory_defers(self):
        folder = self.state / 'requests'
        folder.mkdir()
        (folder / 'queued.json').write_text(json.dumps({'state': 'queued'}))
        folder.chmod(0)
        try:
            self.assertFalse(self.decision()['allowed'])
        finally:
            folder.chmod(0o700)

    def test_scheduler_defers_before_any_repository_action(self):
        vault = Mock(state=self.state)
        with patch.object(scheduled, 'Vault', return_value=vault), \
             patch.object(scheduled, 'permit', return_value=False) as permit:
            scheduled.main()
        permit.assert_called_once_with(vault, 'backup')
        vault.online.assert_not_called()
        vault.initialize.assert_not_called()
        vault.backup.assert_not_called()

    def test_tier_defers_without_rewriting_queue_or_offloading(self):
        vault = SimpleNamespace(state=self.state)
        with patch.object(tier_queue, 'Vault', return_value=vault), \
             patch.object(tier_queue, 'permit', return_value=False), \
             patch.object(tier_queue, 'edit') as edit, \
             patch.object(tier_queue, 'put') as put:
            tier_queue.main()
        edit.assert_not_called()
        put.assert_not_called()

    def test_recovery_kit_carries_new_runtime_dependency(self):
        self.assertIn('background_policy.py', recovery.RUNTIME)


if __name__ == '__main__':
    unittest.main()
