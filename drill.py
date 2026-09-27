#!/usr/bin/env python3
"""Restore an entire successful Anubis scope into disposable local scratch."""
import json
from pathlib import Path
import shutil
import tempfile
from vault import Vault, VaultError, save_json, now
from health import read_json

def drill(v):
    scope = read_json(v.state/'project-health.json', {}).get('anubis-complete-scope', {})
    snapshot = scope.get('snapshot') if scope.get('state') == 'passed' else scope.get('last_success')
    if not snapshot:
        return {'state': 'waiting', 'time': now(), 'reason': 'No successful scoped snapshot recorded yet.'}
    v.online()
    with v.locked():
        stats = json.loads(v.run('stats', snapshot, '--mode', 'restore-size', '--json', capture=True))
        needed = stats['total_size']
        free = shutil.disk_usage(v.state).free
        reserve = v.cfg.get('local_reserve_bytes', 10000000000)
        if needed + reserve > free:
            return {'state': 'waiting', 'time': now(), 'snapshot': snapshot,
                    'reason': 'Whole scope does not fit while preserving local working reserve.',
                    'restore_bytes': needed, 'local_free_bytes': free}
        # Never substitute sampling when the requested whole scope will not fit.
        with tempfile.TemporaryDirectory(prefix='scope-drill-', dir=v.state) as scratch:
            v.run('restore', snapshot, '--target', str(Path(scratch)/'tree'), '--verify', '--sparse')
        return {'state': 'passed', 'time': now(), 'snapshot': snapshot,
                'method': 'Entire anubis-complete-scope snapshot restored with restic --verify',
                'boundary': 'Selected snapshot files only; separately offloaded cold items are not automatically restored. Does not prove application consistency, rebuildability, or an independent device copy.'}

def main():
    v = Vault(Path.home()/'.config/project-vault/config.json')
    try:
        result = drill(v)
    except (VaultError, OSError) as e:
        waiting = getattr(e, 'exit_code', None) == 11 or any(x in str(e) for x in ('offline', 'Another vault', 'queued until'))
        result = {'state': 'waiting' if waiting else 'failed', 'time': now(), 'reason': str(e)}
    save_json(v.state/'restore-drill.json', result)
    try:
        v.online()
        save_json(v.root/'Recovery/restore-drill.json', result)
    except (VaultError, OSError):
        pass
    print(json.dumps(result, indent=2))

if __name__ == '__main__': main()
