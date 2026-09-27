"""Explicit cold storage with verified recovery and a small persistent item index."""
import ctypes
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import uuid
from vault import VaultError, now, save_json


def rename_new(source, target):
    libc = ctypes.CDLL(None, use_errno=True)
    result = libc.renameat2(-100, os.fsencode(source), -100, os.fsencode(target), 1)
    if result:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), str(target))


def inventory(root):
    records = {}
    stack = [Path(root)]
    while stack:
        p = stack.pop()
        s = p.lstat()
        rel = str(p.relative_to(root))
        attrs = {n: os.getxattr(p, n, follow_symlinks=False).hex()
                 for n in os.listxattr(p, follow_symlinks=False)}
        item = {'mode': stat.S_IMODE(s.st_mode), 'uid': s.st_uid, 'gid': s.st_gid, 'xattrs': attrs}
        if stat.S_ISLNK(s.st_mode):
            item.update(kind='symlink', target=os.readlink(p))
        elif stat.S_ISDIR(s.st_mode):
            item['kind'] = 'directory'
            stack.extend(sorted(p.iterdir(), reverse=True))
        elif stat.S_ISREG(s.st_mode):
            digest = hashlib.sha256()
            with p.open('rb') as f:
                for block in iter(lambda: f.read(1048576), b''):
                    digest.update(block)
            end = p.lstat()
            if (s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns) != (end.st_ino,end.st_size,end.st_mtime_ns,end.st_ctime_ns):
                raise VaultError('File changed during inspection: ' + str(p))
            item.update(kind='file', size=s.st_size, sha256=digest.hexdigest(), mtime_ns=s.st_mtime_ns)
        else:
            raise VaultError('Special file cannot be offloaded: ' + str(p))
        records[rel] = item
    return records


def active_users(root):
    if os.geteuid() != 0:
        check = subprocess.run(['sudo', '-n', '/usr/bin/python3', str(Path(__file__).resolve()), '--scan', str(root)],
                               capture_output=True, text=True)
        if check.returncode:
            raise VaultError('Cannot complete read-only process inspection: ' + check.stderr.strip())
        return json.loads(check.stdout)
    owner = Path(root).stat().st_uid
    root = str(root)
    hits = []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name) == os.getpid():
            continue
        try:
            if proc.stat().st_uid not in (owner, 0):
                continue
            links = [proc / 'cwd', proc / 'exe'] + list((proc / 'fd').iterdir())
            for p in links:
                try:
                    target = os.readlink(p).removesuffix(' (deleted)')
                except FileNotFoundError:
                    continue
                if target == root or target.startswith(root + '/'):
                    hits.append(proc.name)
                    break
            maps = (proc / 'maps').read_text(errors='replace')
            if root + '/' in maps:
                hits.append(proc.name)
        except FileNotFoundError:
            continue
        except PermissionError:
            # A living same-user process that cannot be inspected makes eviction unsafe.
            if proc.exists():
                raise VaultError('Cannot inspect same-user process ' + proc.name)
    return sorted(set(hits))


def items(vault):
    folder = vault.state / 'items'
    if not folder.exists(): return []
    return [json.loads(p.read_text()) for p in sorted(folder.glob('*.json'))]


def record(vault, item):
    save_json(vault.state / 'items' / (item['id'] + '.json'), item)
    remote = vault.root / 'Recovery/items' / (item['id'] + '.json')
    save_json(remote, item)
    if json.loads(remote.read_text()) != item:
        raise VaultError('iPad recovery receipt read-back differs; refusing to proceed.')


def validate_path(vault, path):
    path = Path(path).expanduser().absolute()
    home = Path(vault.cfg['home'])
    allowed = [home / name for name in ('Projects', 'Work', '.cache')]
    if not any(path != base and path.is_relative_to(base) for base in allowed):
        raise VaultError('Offload an explicit child of Projects, Work or .cache.')
    if path.resolve() != path or path.is_symlink() or not path.is_dir():
        raise VaultError('Offload requires an existing real directory without symlink components.')
    if '.git' in path.parts or (path / '.git').exists():
        raise VaultError('Repository/worktree roots stay local; offload inactive data or build subdirectories.')
    if any(p.name == '.git' for p in path.rglob('.git')):
        raise VaultError('Nested Git metadata found; keep this checkout locally.')
    pins = vault.state / 'pinned-paths.json'
    for original in json.loads(pins.read_text()) if pins.exists() else []:
        p = Path(original)
        if path == p or path.is_relative_to(p) or p.is_relative_to(path):
            raise VaultError('Path overlaps a locally pinned working set: ' + original)
    return path


@contextlib.contextmanager
def generated_run_guard(path):
    """Use Anubis's existing external build mutex for its generated release cache."""
    mutex = path.parent / '.anubis-build-mutex'
    try:
        mutex.mkdir()
    except FileExistsError:
        raise VaultError('Anubis generated-run cache is in use; existing build mutex retained.')
    identity = mutex.stat().st_ino
    owner = mutex / 'owner'
    try:
        owner.write_text('pid=' + str(os.getpid()) + '\n')
        yield
    finally:
        # Remove only our unchanged ownership record and empty lock directory.
        if mutex.exists() and not mutex.is_symlink() and mutex.stat().st_ino == identity:
            if owner.is_file() and owner.read_text() == 'pid=' + str(os.getpid()) + '\n':
                owner.unlink()
                mutex.rmdir()


@contextlib.contextmanager
def cargo_build_guard(path):
    """Serialize cache offload using the owning workflow's existing locks."""
    if path.name == 'release' and path.parent.name == 'anubis-run-cargo-target-audited-crypto-v3':
        with generated_run_guard(path):
            yield
        return
    if path.name not in ('incremental', 'deps') or path.parent.name not in ('debug', 'release'):
        yield
        return
    lockpath = path.parent / '.cargo-lock'
    if not lockpath.is_file() or lockpath.is_symlink():
        raise VaultError('Missing Cargo profile lock; Cargo cache offload requires review.')
    with lockpath.open('r+b') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise VaultError('Cargo build directory is in use; cache retained.')
        yield


def put(vault, original, offload=False, retain_binaries=False):
    vault.online()
    device = vault.mount.stat().st_dev
    def connected():
        vault.online()
        if vault.mount.stat().st_dev != device:
            raise VaultError('iPad connection changed during transfer; source retained, retry after reconnection.')
    path = validate_path(vault, original)
    if retain_binaries and (path.name != 'deps' or path.parent.name not in ('debug', 'release')):
        raise VaultError('Binary retention applies only to reviewed Cargo profile/deps directories.')
    with vault.locked(), cargo_build_guard(path):
        local_free_before = shutil.disk_usage(vault.state).free
        if active_users(path):
            raise VaultError('Directory is in use; leave it local: ' + str(path))
        print('Inspecting source content: ' + str(path), flush=True)
        before = inventory(path)
        needed = sum(x.get('size', 0) for x in before.values())
        if shutil.disk_usage(vault.state).free < needed + vault.cfg.get('local_reserve_bytes', 10000000000):
            raise VaultError('Insufficient local space for a full recovery comparison.')
        if shutil.disk_usage(vault.root).free < needed + vault.cfg['reserve_bytes']:
            raise VaultError('Insufficient iPad reserve for this conservative admission check.')
        digest = hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest()
        job_dir = vault.state / 'cold-jobs' / hashlib.sha256(str(path).encode()).hexdigest()
        job_dir.mkdir(parents=True, exist_ok=True)
        job_file = job_dir / 'job.json'
        job = json.loads(job_file.read_text()) if job_file.exists() else {}
        # Resume only the same source content. Staging is generated restore data, never originals.
        if job.get('manifest') != digest or job.get('complete'):
            if (job_dir / 'tree').exists(): shutil.rmtree(job_dir / 'tree')
            job = {'id': uuid.uuid4().hex, 'path': str(path), 'manifest': digest, 'started': now()}
            save_json(job_file, job)
        identity = job['id']
        tag = 'cold-' + identity
        if retain_binaries:
            # Retain every file except non-executable Rust object/metadata archives.
            # Preserve names and metadata using same-filesystem hard links; source stays intact.
            if any('/' in name or data['kind'] != 'file' for name, data in before.items() if name != '.'):
                raise VaultError('Cargo deps retention requires a flat regular-file directory; review other contents.')
            retained = path.parent / ('vault-retained-binaries-' + identity)
            if retained.is_symlink():
                raise VaultError('Retained binary destination is a symlink.')
            retained.mkdir(exist_ok=True)
            keep = {name: data for name, data in before.items() if name != '.' and
                    not (Path(name).suffix in ('.rlib', '.rmeta', '.o') and not data['mode'] & 0o111)}
            for name in keep:
                target = retained / name
                if not (target.exists() or target.is_symlink()):
                    os.link(path / name, target, follow_symlinks=False)
            actual = inventory(retained)
            if {k: value for k, value in actual.items() if k != '.'} != keep:
                raise VaultError('Retained binaries differ from source; original deps remain local.')
            from pins import set_pin
            set_pin(vault, retained)
            job['retained_local'] = {'path': str(retained), 'files': sorted(keep),
                                    'manifest_sha256': hashlib.sha256(json.dumps(keep, sort_keys=True).encode()).hexdigest(),
                                    'policy': 'All entries except non-executable .rlib/.rmeta/.o retained as local hard links.'}
            save_json(job_file, job)
        if not job.get('snapshot'):
            vault.run('backup', '--tag', tag, '--', str(path))
            connected()
            snapshots = json.loads(vault.run('snapshots', '--tag', tag, '--json', capture=True))
            if len(snapshots) != 1:
                raise VaultError('Expected one uniquely tagged snapshot.')
            job['snapshot'] = snapshots[0]['id']
            save_json(job_file, job)
        snapshot = job['snapshot']
        print('Restoring the entire candidate and comparing content and metadata', flush=True)
        save_json(vault.state / 'cold-operation.json', {'path': str(path), 'phase': 'restore and compare', 'state': 'running', 'pid': os.getpid(), 'started': now()})
        restore_root = job_dir / 'tree'
        try:
            vault.run('restore', snapshot, '--target', str(restore_root), '--overwrite', 'if-changed', '--verify', '--sparse')
        except VaultError:
            connected()
            raise
        restored = restore_root / str(path).lstrip('/')
        if inventory(restored) != before or inventory(path) != before:
            raise VaultError('Source/restored content or metadata differs; nothing offloaded.')
        connected()
        shutil.rmtree(restore_root)
        item = {'id': identity, 'path': str(path), 'snapshot': snapshot, 'tag': tag,
                'time': now(), 'state': 'backed-up-local', 'bytes': needed,
                'verification': 'full candidate restore, SHA256 and metadata comparison',
                'content_manifest_sha256': hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest(),
                'single_device_archive_when_offloaded': True}
        from provenance import lookup
        item['provenance'] = lookup(vault, path)
        if job.get('retained_local'):
            item['retained_local'] = job['retained_local']
        item['local_free_before'] = local_free_before
        record(vault, item)
        if not offload:
            job['complete'] = True; save_json(job_file, job)
            save_json(vault.state / 'cold-operation.json', {'state': 'passed', 'path': str(path), 'finished': now()})
            return item
        if active_users(path):
            raise VaultError('Directory became active; source retained.')
        from pins import locked as pins_locked
        with pins_locked(vault.state):
            validate_path(vault, path)  # Pins may have changed during the transfer.
            quarantine = path.with_name('.' + path.name + '.vault-retiring-' + identity)
            item.update(state='verified-removal-intent', quarantine=str(quarantine))
            record(vault, item)  # Durable recovery identity before changing the original name.
            rename_new(path, quarantine)
            deleting = False
            try:
                if path.exists() or path.is_symlink() or active_users(quarantine) or inventory(quarantine) != before:
                    raise VaultError('Directory changed or became active; eviction aborted.')
                item.update(state='verified-removal-pending', quarantine=str(quarantine))
                record(vault, item)
                connected()
                # The explicit renamed directory was fully recovered and compared above.
                deleting = True
                shutil.rmtree(quarantine)
            except BaseException:
                if not deleting and quarantine.exists() and not (path.exists() or path.is_symlink()):
                    rename_new(quarantine, path)
                item.update(state='recovery-required' if deleting else 'backed-up-local',
                            recovery_instruction='Preserve remaining quarantine; get this item --to a new local path for a complete verified restore.')
                save_json(vault.state / 'items' / (identity + '.json'), item)
                raise
        item.update(state='offloaded', time=now(), local_free_after=shutil.disk_usage(vault.state).free,
                    reclaim_verification={'original_path_absent': not (path.exists() or path.is_symlink()),
                                          'quarantine_absent': not (quarantine.exists() or quarantine.is_symlink()),
                                          'verification_scratch_absent': not (restore_root.exists() or restore_root.is_symlink()),
                                          'free_space_boundary': 'Filesystem free space sampled before and after; concurrent workloads can also change it.'})
        item['reclaim_verification']['filesystem_free_space_increased'] = item['local_free_after'] > local_free_before
        record(vault, item)
        save_json(path.with_name(path.name + '.ipad.json'), item)
        vault.event('offloaded', item)
        job['complete'] = True; save_json(job_file, job)
        save_json(vault.state / 'cold-operation.json', {'state': 'passed', 'path': str(path), 'finished': now()})
        with (vault.state / 'offloads.jsonl').open('a') as journal:
            journal.write(json.dumps(item) + '\n')
            journal.flush()
            os.fsync(journal.fileno())
        return item


def get(vault, key, destination=None):
    vault.online()
    found = [x for x in items(vault) if x['id'] == key or x['path'] == str(Path(key).expanduser().absolute())]
    if not found: raise VaultError('No cold-storage record for this item.')
    item = sorted(found, key=lambda x:x['time'])[-1]
    target = Path(destination or item['path']).expanduser().absolute()
    if not target.is_relative_to(Path(vault.cfg['home'])) or target.resolve().is_relative_to(vault.mount.resolve()):
        raise VaultError('Restore must be inside local home, outside iPad.')
    if target.exists() or target.is_symlink(): raise VaultError('Restore destination already exists; refusing overwrite.')
    if target.parent.resolve() != target.parent:
        raise VaultError('Restore parent has symlink components.')
    with vault.locked():
        if shutil.disk_usage(vault.state).free < item['bytes'] + vault.cfg.get('local_reserve_bytes', 10000000000):
            raise VaultError('Insufficient space for retrieval while retaining local reserve.')
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.vault-get-', dir=target.parent) as temporary:
            restore_root = Path(temporary) / 'tree'
            vault.run('restore', item['snapshot'], '--target', str(restore_root), '--verify', '--sparse')
            restored = restore_root / item['path'].lstrip('/')
            actual = hashlib.sha256(json.dumps(inventory(restored), sort_keys=True).encode()).hexdigest()
            if actual != item['content_manifest_sha256']:
                raise VaultError('Retrieved content/metadata differs from offload receipt.')
            rename_new(restored, target)
        item.update(last_restored_to=str(target), last_restored_at=now())
        if str(target) == item['path']: item['state'] = 'restored-local'
        record(vault, item)
        return {'restored': str(target), 'snapshot': item['snapshot']}


if __name__ == '__main__':
    import sys
    if len(sys.argv) != 3 or sys.argv[1] != '--scan':
        raise SystemExit('Only the read-only process scan is exposed here.')
    print(json.dumps(active_users(Path(sys.argv[2]))))
