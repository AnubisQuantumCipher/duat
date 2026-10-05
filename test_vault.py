import importlib.util
import json
import os
from pathlib import Path
import tempfile
import subprocess
import unittest

spec = importlib.util.spec_from_file_location('vault', Path(__file__).with_name('vault.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class VaultTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='project-vault-test-')
        self.base = Path(self.temp.name)
        self.sources = self.base / 'Projects'
        project = self.sources / 'example'
        project.mkdir(parents=True)
        (project / 'proof.txt').write_text('unique project evidence\n')
        (project / 'run.sh').write_text('#!/bin/sh\necho ok\n')
        (project / 'run.sh').chmod(0o755)
        (project / 'evidence-link').symlink_to('proof.txt')
        self.mount = self.base / 'device'
        self.mount.mkdir()
        self.config = self.base / 'config.json'
        self.cfg = dict(state=str(self.base / 'state'), mount=str(self.mount),
            root=str(self.mount / 'TryOmarchy'), home=str(self.base),
            project_roots=[str(self.sources)], additional_paths=[],
            require_ifuse_mount=False, reserve_bytes=0, vault_id='test-vault')
        self.config.write_text(json.dumps(self.cfg))
        self.vault = module.Vault(self.config)

    def tearDown(self):
        self.vault.db.close()
        self.temp.cleanup()

    def test_existing_catalog_can_open_during_writer_transaction(self):
        self.vault.db.execute('INSERT INTO events VALUES(?,?,?)', ('test','writer','{}'))
        second = module.Vault(self.config)
        second.db.close()
        self.vault.db.rollback()

    def test_unchanged_sources_receive_snapshot_for_new_scope(self):
        self.vault.initialize()
        self.vault.cfg['snapshot_tag'] = 'first-scope'
        first = self.vault.backup()
        self.vault.cfg['snapshot_tag'] = 'second-scope'
        second = self.vault.backup()
        self.assertIsInstance(second, str)
        self.assertNotEqual(first, second)
        snapshots = json.loads(self.vault.run('snapshots', '--tag', 'second-scope', '--json', capture=True))
        self.assertEqual([x['id'] for x in snapshots], [second])
        # A skipped backup must still resolve the existing tagged snapshot.
        from unittest.mock import patch
        run = self.vault.run
        def skipped(*args, **kwargs):
            return None if args[0] == 'backup' else run(*args, **kwargs)
        with patch.object(self.vault, 'run', side_effect=skipped):
            self.assertEqual(self.vault.backup(), second)

    def test_backup_offline_catalog_restore_and_tamper(self):
        self.vault.initialize()
        self.vault.backup()
        snapshot = self.vault.latest()
        matches = self.vault.search('proof.txt')['results']
        self.assertEqual(matches[0]['path'], str(self.sources / 'example/proof.txt'))
        repo = self.vault.repo
        offline = repo.with_name('disconnected-repository')
        repo.rename(offline)
        self.assertTrue(self.vault.search('proof.txt')['results'])
        offline.rename(repo)
        target = self.base / 'restored'
        self.vault.restore(snapshot, str(self.sources / 'example'), target)
        restored = target / str(self.sources / 'example').lstrip('/')
        self.assertEqual((restored / 'proof.txt').read_bytes(), (self.sources / 'example/proof.txt').read_bytes())
        self.assertTrue((restored / 'evidence-link').is_symlink())
        self.assertTrue(os.access(restored / 'run.sh', os.X_OK))
        with self.assertRaises(module.VaultError):
            self.vault.restore(snapshot, str(self.sources / 'example'), target)
        self.vault.run('check', '--read-data')
        pack = next(p for p in (repo / 'data').rglob('*') if p.is_file())
        pack.chmod(0o600)
        with pack.open('r+b') as file:
            file.write(b'CORRUPTED')
        with self.assertRaises(module.VaultError):
            self.vault.run('check', '--read-data', capture=True)

    def test_offline_guard_does_not_create_local_destination(self):
        self.vault.cfg['require_ifuse_mount'] = True
        with self.assertRaises(module.VaultError):
            self.vault.initialize()
        self.assertFalse(self.vault.root.exists())

    def test_symlink_project_target_included_and_identity_checked(self):
        live = self.base / 'example-app/current'
        live.mkdir(parents=True)
        (live / 'source.anb').write_text('source')
        (self.sources / 'linked-project').symlink_to(live)
        roots, mapping = self.vault.sources()
        self.assertIn(str(live), roots)
        self.assertTrue(any(x['symlink'] for x in mapping))
        self.vault.initialize()
        (self.vault.root / '.vault-id').write_text('wrong-device')
        with self.assertRaises(module.VaultError):
            self.vault.online()

    def test_external_source_requires_explicit_allowed_root(self):
        with tempfile.TemporaryDirectory(prefix='vault-external-') as outside:
            source = Path(outside) / 'project'
            source.mkdir()
            (source / 'evidence.txt').write_text('retained source')
            (self.sources / 'external-project').symlink_to(source)
            with self.assertRaises(module.VaultError):
                self.vault.sources()
            self.vault.cfg['allowed_external_roots'] = [str(Path(outside))]
            roots, mapping = self.vault.sources()
            self.assertIn(str(source), roots)
            self.assertTrue(any(row['stored_path'] == str(source) for row in mapping))
            self.vault.cfg['allowed_external_roots'] = [str(Path(outside) / 'other')]
            with self.assertRaises(module.VaultError):
                self.vault.sources()

    def test_external_worktree_and_common_git_are_discovered(self):
        project = self.sources / 'example'
        def git(*args):
            subprocess.run(['git', '-C', str(project), *args], check=True, capture_output=True)
        git('init')
        git('add', '.')
        git('-c', 'user.name=Vault Test', '-c', 'user.email=test@localhost', 'commit', '-m', 'fixture')
        external = self.base / 'cache/linked'
        git('worktree', 'add', '-b', 'fixture', str(external))
        (external / 'uncommitted.txt').write_text('unique worktree data')
        roots, records = self.vault.sources()
        self.assertIn(str(external), roots)
        self.assertTrue(any(x.get('kind') == 'shared-git-metadata' for x in records))


if __name__ == '__main__':
    unittest.main()
