"""Non-destructive cold-reference audits and versioned, read-back recovery kits."""
import hashlib
import json
import os
from pathlib import Path
import re
import uuid
from vault import VaultError, now, save_json
from verify_kit import verify

RUNTIME = ('vault.py', 'cold.py', 'pins.py', 'recovery.py', 'verify_kit.py',
           'provenance.py', 'queue_store.py', 'tier_queue.py', 'requests_worker.py',
           'scheduled.py', 'anubis_backup.py', 'lock_recovery.py', 'health.py',
           'dashboard.py', 'dashboard.html', 'scrub.py', 'drill.py', 'bench.py', 'bench.html')
HEX64 = re.compile(r'^[0-9a-f]{64}$')

def read_items(folder):
    records, issues = {}, []
    for file in sorted(folder.glob('*.json')):
        try:
            item = json.loads(file.read_text())
            if (not isinstance(item, dict) or item.get('id') != file.stem
                    or not HEX64.fullmatch(str(item.get('snapshot', '')))
                    or not HEX64.fullmatch(str(item.get('content_manifest_sha256', '')))
                    or not Path(item.get('path', '')).is_absolute()):
                raise ValueError('Invalid identity, snapshot, manifest digest or absolute path')
            records[file.stem] = item
        except (OSError, ValueError, TypeError) as error:
            issues.append({'record': str(file), 'error': str(error)})
    return records, issues

def audit(vault, online=False):
    # This lock is cooperative. The audit does not hash source trees or delete anything.
    with vault.locked():
        local, issues = read_items(vault.state / 'items')
        regrown = []
        for identity, item in local.items():
            path = Path(item['path'])
            if item.get('state') in ('verified-removal-intent', 'verified-removal-pending', 'recovery-required'):
                issues.append({'item': identity, 'error': 'Interrupted retirement needs review; preserve quarantine.'})
            quarantine = Path(item['quarantine']) if item.get('quarantine') else None
            if quarantine is not None and (quarantine.exists() or quarantine.is_symlink()):
                issues.append({'item': identity, 'error': 'Quarantine still exists; preserve it until complete recovery is verified.'})
            if item.get('state') == 'offloaded' and (path.exists() or path.is_symlink()):
                regrown.append({'item': identity, 'path': str(path), 'action': 'Do not reuse old receipt for deletion; restore elsewhere if needed.'})
        refs = sorted({item['snapshot'] for item in local.values()})
        if online:
            vault.online()
            remote, remote_issues = read_items(vault.root / 'Recovery/items')
            issues.extend(remote_issues)
            for identity in sorted(local.keys() | remote.keys()):
                if local.get(identity) != remote.get(identity):
                    issues.append({'item': identity, 'error': 'Local/iPad receipt missing or different; reconcile without overwriting either blindly.'})
            snapshots = {s['id']: s for s in json.loads(vault.run('snapshots', '--json', capture=True))}
            for identity, item in {**remote, **local}.items():
                snap = snapshots.get(item['snapshot'])
                if not snap:
                    issues.append({'item': identity, 'snapshot': item['snapshot'], 'error': 'Referenced snapshot is missing.'})
                elif item.get('tag') not in snap.get('tags', []) or item['path'] not in snap.get('paths', []):
                    issues.append({'item': identity, 'error': 'Snapshot tag or root does not match cold receipt.'})
            refs = sorted({item['snapshot'] for item in [*local.values(), *remote.values()]})
        result = {'state': 'needs-attention' if issues else 'passed', 'time': now(),
                  'mode': 'online-reference-check' if online else 'local-record-check',
                  'items_checked': len(local), 'issues': issues, 'regrown_paths': regrown,
                  'protected_cold_snapshots': refs,
                  'boundary': 'Metadata/reference audit only, not a data scrub or restore. No pruning authorized.'}
        save_json(vault.state / 'recovery-audit.json', result)
        if online:
            vault.online()
            save_json(vault.root / 'Recovery/recovery-audit.json', result)
        return result


def export_kit(vault):
    vault.online()
    with vault.locked():
        device = vault.mount.stat().st_dev
        source = Path(__file__).resolve().parent
        home = Path(vault.cfg['home'])
        files = {}
        for name in RUNTIME:
            files['Tools/' + name] = (source / name).read_bytes()
        for name in ('README.md', 'ANUBIS-COVERAGE.md', 'RECOVERY-BOOTSTRAP.md', 'render_whitepaper.py'):
            files['Tools/' + name] = (source / name).read_bytes()
        files['Tools/BENCH.md'] = (source / 'docs/BENCH.md').read_bytes()
        for file in sorted((home / '.config/systemd/user').glob('project-vault-*')):
            if file.is_file():
                files['Services/' + file.name] = file.read_bytes()
        for name in ('ipad-storage.service',):
            file = home / '.config/systemd/user' / name
            if file.is_file(): files['Services/' + name] = file.read_bytes()
        for file in sorted((home / 'Documents').glob('DUAT-Vault-Architecture-White-Paper.*')):
            if file.suffix in ('.md', '.html') and file.is_file():
                files['Documents/' + file.name] = file.read_bytes()
        for name in ('pinned-paths.json', 'project-health.json', 'scrub.json', 'restore-drill.json', 'recovery-audit.json'):
            file = vault.state / name
            if file.exists(): files['State/' + name] = file.read_bytes()
        for file in sorted((vault.state / 'items').glob('*.json')):
            files['State/items/' + file.name] = file.read_bytes()
        for file in sorted((vault.state / 'provenance').glob('*.json')):
            files['State/provenance/' + file.name] = file.read_bytes()
        files['configuration.json'] = (json.dumps(vault.cfg, indent=2) + '\n').encode()
        hashes = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
        # Content-addressed export avoids identical copies. State changes produce new editions.
        content_hash = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
        root = vault.root / 'Recovery'
        pointer = root / 'latest-kit.json'
        if pointer.exists():
            previous = json.loads(pointer.read_text())
            old = root / 'Kits' / previous.get('id', '')
            if old.parent == root / 'Kits' and previous.get('content_sha256') == content_hash:
                if verify(old)['state'] == 'passed':
                    return {'state': 'unchanged', 'id': previous['id'], 'path': str(old)}
        identity = uuid.uuid4().hex
        target = root / 'Kits' / identity
        target.mkdir(parents=True, exist_ok=False)
        for name, data in files.items():
            file = target / name
            file.parent.mkdir(parents=True, exist_ok=True)
            with file.open('xb') as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
        manifest = {'schema': 1, 'id': identity, 'created': now(), 'files': hashes,
                    'boundary': 'Read-back hash verification; no authenticity or power-loss durability claim.'}
        save_json(target / 'manifest.json', manifest)
        result = verify(target)
        if result['state'] != 'passed':
            raise VaultError('Recovery kit read-back failed; previous published kit retained.')
        vault.online()
        if vault.mount.stat().st_dev != device:
            raise VaultError('Mount changed during recovery export; previous published kit retained.')
        pointer_value = {'id': identity, 'created': manifest['created'], 'content_sha256': content_hash,
                         'manifest_sha256': hashlib.sha256((target / 'manifest.json').read_bytes()).hexdigest()}
        save_json(pointer, pointer_value)
        if json.loads(pointer.read_text()) != pointer_value:
            raise VaultError('Recovery kit pointer read-back failed.')
        result.update(path=str(target), time=now())
        save_json(vault.state / 'recovery-kit.json', result)
        return result
