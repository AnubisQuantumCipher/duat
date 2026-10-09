import contextlib
import fcntl
import io
import select
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import vault


class WaitLockTests(unittest.TestCase):
    def test_waiter_acquires_and_keeps_exclusion_until_context_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            v = object.__new__(vault.Vault)
            v.state = Path(directory)
            with (v.state / 'operation.lock').open('a') as holder:
                fcntl.flock(holder, fcntl.LOCK_EX)
                with self.assertRaisesRegex(vault.VaultError, 'Another vault operation'):
                    with v.locked():
                        self.fail('Default busy path entered the critical section')
                code = '''from pathlib import Path
import sys
from vault import Vault
v = object.__new__(Vault)
v.state = Path(sys.argv[1])
print('ready', flush=True)
with v.locked(wait=True):
    print('acquired', flush=True)
    input()
print('released', flush=True)
'''
                child = subprocess.Popen([sys.executable, '-u', '-c', code, directory],
                    cwd=Path(__file__).parent, stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                try:
                    self.assertTrue(select.select([child.stdout], [], [], 5)[0])
                    self.assertEqual(child.stdout.readline().strip(), 'ready')
                    self.assertFalse(select.select([child.stdout], [], [], 0.2)[0])
                    self.assertIsNone(child.poll())
                    fcntl.flock(holder, fcntl.LOCK_UN)
                    self.assertTrue(select.select([child.stdout], [], [], 5)[0])
                    self.assertEqual(child.stdout.readline().strip(), 'acquired')
                    with self.assertRaisesRegex(vault.VaultError, 'Another vault operation'):
                        with v.locked():
                            self.fail('Concurrent owner entered while waiter held the lock')
                    stdout, stderr = child.communicate('\n', timeout=5)
                    self.assertEqual(child.returncode, 0, stderr)
                    self.assertEqual(stdout.strip(), 'released')
                    with v.locked():
                        pass
                finally:
                    if child.poll() is None:
                        child.kill()
                        child.communicate()

    def test_wait_can_be_cancelled_without_removing_or_unlocking_holder(self):
        with tempfile.TemporaryDirectory() as directory:
            v = object.__new__(vault.Vault)
            v.state = Path(directory)
            with v.locked():
                inode = (v.state / 'operation.lock').stat().st_ino
                code = '''from pathlib import Path
import sys
from vault import Vault
v = object.__new__(Vault)
v.state = Path(sys.argv[1])
print('ready', flush=True)
with v.locked(wait=True):
    print('unexpected acquisition', flush=True)
'''
                child = subprocess.Popen([sys.executable, '-u', '-c', code, directory],
                    cwd=Path(__file__).parent, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, text=True)
                try:
                    self.assertTrue(select.select([child.stdout], [], [], 5)[0])
                    self.assertEqual(child.stdout.readline().strip(), 'ready')
                    self.assertFalse(select.select([child.stdout], [], [], 0.2)[0])
                    child.send_signal(signal.SIGINT)
                    stdout, _ = child.communicate(timeout=5)
                    self.assertNotEqual(child.returncode, 0)
                    self.assertNotIn('unexpected acquisition', stdout)
                    self.assertEqual((v.state / 'operation.lock').stat().st_ino, inode)
                    with self.assertRaises(vault.VaultError):
                        with v.locked():
                            self.fail('Cancellation released a different owner lock')
                finally:
                    if child.poll() is None:
                        child.kill()
                        child.communicate()

    def test_wait_flag_requires_online_before_opening_config(self):
        with patch.object(sys, 'argv', ['project-vault', '--config', '/nonexistent',
                                      'find', 'marker', '--wait-lock']), \
             patch.object(vault, 'Vault') as constructor, \
             contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as result:
                vault.main()
            self.assertEqual(result.exception.code, 2)
            constructor.assert_not_called()

    def _run_cli(self, *, wait, changed_identity=False):
        events = []
        class FakeVault:
            @contextlib.contextmanager
            def locked(self, *, wait=False):
                events.append(('locked', wait))
                try:
                    yield
                finally:
                    events.append('released')

            def online(self):
                if changed_identity and any(isinstance(e, tuple) for e in events):
                    raise vault.VaultError('Vault identity does not match')
                events.append('online')

            def run(self, *args, **kwargs):
                events.append(('run', args, kwargs))
                return '[]'

        argv = ['project-vault', 'find', '*/initialized.json', '--online']
        if wait:
            argv.append('--wait-lock')
        with patch.object(sys, 'argv', argv), \
             patch.object(vault, 'Vault', return_value=FakeVault()), \
             contextlib.redirect_stdout(io.StringIO()):
            if changed_identity:
                with self.assertRaisesRegex(vault.VaultError, 'identity'):
                    vault.main()
            else:
                vault.main()
        return events

    def test_device_revalidation_precedes_repository_access_under_waited_lock(self):
        self.assertEqual(self._run_cli(wait=True), [
            'online', ('locked', True), 'online',
            ('run', ('find', '--json', '--', '*/initialized.json'), {'capture': True}),
            'released'])

    def test_changed_device_after_wait_refuses_without_repository_access(self):
        self.assertEqual(self._run_cli(wait=True, changed_identity=True), [
            'online', ('locked', True), 'released'])

    def test_default_find_retains_nonblocking_behavior(self):
        self.assertEqual(self._run_cli(wait=False), [
            'online', ('locked', False),
            ('run', ('find', '--json', '--', '*/initialized.json'), {'capture': True}),
            'released'])


if __name__ == '__main__':
    unittest.main()
