#!/usr/bin/env python3
from pathlib import Path
import tempfile
from vault import Vault, save_json, now


def backup_anubis():
    home = Path.home()
    vault = Vault(home / '.config/project-vault/config.json')
    vault.cfg['snapshot_tag'] = 'anubis-complete-scope'
    vault.cfg['additional_paths'] += [str(home / 'Projects/anubis-lang'), str(home / 'Projects/anubis'), str(home / 'Projects/anubis-desktop')]
    vault.cfg['project_roots'] = [str(home / 'Work')]
    print('ANUBIS: backing up full Anubis scope separately from unrelated projects', flush=True)
    snapshot = vault.backup()
    receipt = vault.state / 'anubis-recovery-check.json'
    if not receipt.exists():
        with vault.locked():
            vault.run('check', '--read-data')
        sample = str(home / 'Projects/anubis-lang/Cargo.toml')
        with tempfile.TemporaryDirectory(prefix='anubis-restore-', dir=vault.state) as temporary:
            vault.restore(snapshot, sample, Path(temporary) / 'restore')
        record = {'time': now(), 'snapshot': snapshot, 'scope': 'anubis-complete-scope',
                  'full_repository_read': 'passed', 'verified_sample_restore': sample,
                  'boundary': 'Live filesystem backup, not an atomic application snapshot or full disaster-recovery test'}
        save_json(receipt, record)
        save_json(vault.root / 'Recovery/anubis-recovery-check.json', record)
    print('ANUBIS: backup saved; initial recovery check available', flush=True)
    return snapshot

if __name__ == '__main__':
    backup_anubis()
