#!/usr/bin/env python3
"""Managed backups and explicit verified offload/retrieval for iPad storage."""
import argparse
import contextlib
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid
import tempfile
import errno


class VaultError(Exception):
    pass


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Unique temporary names prevent concurrent writers from replacing each other's files.
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '.', suffix='.new', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'w') as output:
            output.write(json.dumps(value, indent=2) + '\n')
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            try:
                os.fsync(directory)
            except OSError as error:
                # Some app/FUSE filesystems do not implement directory fsync.
                # Other I/O failures remain visible. This is not a power-loss guarantee.
                if error.errno not in (errno.EINVAL, errno.ENOTSUP, errno.EOPNOTSUPP):
                    raise
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)



class Vault:
    def __init__(self, config):
        self.config_path = Path(config)
        self.cfg = json.loads(self.config_path.read_text())
        self.state = Path(self.cfg['state'])
        self.state.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.mount = Path(self.cfg['mount'])
        self.root = Path(self.cfg['root'])
        self.repo = self.root / 'Repository'
        self.password = self.state / 'repository-password'
        self.db = sqlite3.connect(self.state / 'catalog.sqlite')
        schema = {row[0] for row in self.db.execute('SELECT name FROM sqlite_master')}
        if not {'snapshots', 'files', 'files_path', 'events'}.issubset(schema):
            self.db.executescript('''
          CREATE TABLE IF NOT EXISTS snapshots(id TEXT PRIMARY KEY, time TEXT, metadata TEXT);
          CREATE TABLE IF NOT EXISTS files(snapshot TEXT, path TEXT, type TEXT, size INTEGER, mtime TEXT,
            PRIMARY KEY(snapshot,path));
          CREATE INDEX IF NOT EXISTS files_path ON files(path);
          CREATE TABLE IF NOT EXISTS events(time TEXT, action TEXT, detail TEXT);
            ''')

    def event(self, action, detail):
        self.db.execute('INSERT INTO events VALUES(?,?,?)', (now(), action, json.dumps(detail)))
        self.db.commit()

    def legacy_active(self):
        scripts = set(self.cfg.get('wait_for_scripts', []))
        for process in Path('/proc').iterdir():
            if not process.name.isdigit():
                continue
            try:
                arguments = (process / 'cmdline').read_bytes().decode(errors='replace').split('\0')
            except OSError:
                continue
            if len(arguments) > 1 and Path(arguments[0]).name.startswith('python') and arguments[1] in scripts:
                return True
        return False

    def online(self, initialize=False):
        if self.cfg.get('require_ifuse_mount', True):
            found = False
            for line in Path('/proc/mounts').read_text().splitlines():
                fields = line.split()
                if len(fields) >= 3 and fields[1] == str(self.mount) and fields[2] == 'fuse.ifuse':
                    found = True
            if not found:
                raise VaultError('iPad is offline. Refusing to write into the underlying local directory.')
        if self.legacy_active():
            raise VaultError('The initial archive transfer is active; repository operations are queued until it finishes.')
        if not self.root.is_relative_to(self.mount):
            raise VaultError('Vault root must be inside the configured iPad mount.')
        if not initialize:
            marker = self.root / '.vault-id'
            if not marker.is_file() or marker.read_text().strip() != self.cfg['vault_id']:
                raise VaultError('Vault identity does not match; refusing repository access.')

    @contextlib.contextmanager
    def locked(self):
        with (self.state / 'operation.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise VaultError('Another vault operation is running.')
            yield

    def command(self, *args):
        return ['restic', '--repo', str(self.repo), '--password-file', str(self.password),
                '--cache-dir', str(self.state / 'restic-cache'), *args]

    def run(self, *args, capture=False):
        operation = {'started': now(), 'phase': args[0], 'arguments': list(args[1:]),
                     'owner_pid': os.getpid(), 'state': 'running'}
        process = subprocess.Popen(self.command(*args), stdout=subprocess.PIPE if capture else None,
                                   stderr=subprocess.PIPE if capture else None, text=True)
        operation['pid'] = process.pid
        output = error = None
        try:
            while True:
                operation['updated'] = now()
                try:
                    operation['process_io'] = dict(line.split(': ', 1) for line in Path(f'/proc/{process.pid}/io').read_text().splitlines())
                except OSError: pass
                save_json(self.state / 'operation.json', operation)
                try:
                    output, error = process.communicate(timeout=5)
                    break
                except subprocess.TimeoutExpired: continue
        except BaseException:
            process.terminate()
            process.wait()
            raise
        operation.update(state='passed' if process.returncode == 0 else 'failed', exit_code=process.returncode, finished=now())
        save_json(self.state / 'operation.json', operation)
        if process.returncode:
            failure = VaultError(f'restic {args[0]} failed with exit status {process.returncode}. ' + (error if capture else 'See the operation log.'))
            failure.exit_code = process.returncode
            raise failure
        return output if capture else None

    def initialize(self):
        self.online(initialize=True)
        with self.locked():
            self.root.mkdir(parents=True, exist_ok=True)
            marker = self.root / '.vault-id'
            if marker.exists() and marker.read_text().strip() != self.cfg['vault_id']:
                raise VaultError('An unrelated vault already occupies this destination.')
            if not self.password.exists():
                if (self.repo / 'config').exists():
                    raise VaultError('Repository already exists but its local password is missing. Recover the key first.')
                descriptor = os.open(self.password, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, 'w') as key:
                    key.write(secrets.token_urlsafe(48) + '\n')
            marker.write_text(self.cfg['vault_id'] + '\n')
            if not (self.repo / 'config').exists():
                self.run('init')
            recovery = self.root / 'Recovery'
            recovery.mkdir(exist_ok=True)
            # The operator's iPad holds recovery material so losing the VM does not strand backups.
            # Do not claim confidentiality from someone with access to the whole Documents app.
            keycopy = recovery / 'repository-password'
            if keycopy.exists() and keycopy.read_bytes() != self.password.read_bytes():
                raise VaultError('Recovery key differs; refusing to overwrite it.')
            if not keycopy.exists():
                with keycopy.open('xb') as output:
                    output.write(self.password.read_bytes())
            (recovery / 'README.txt').write_text(
                'PROJECT VAULT RECOVERY\n\n'
                'Repository is ../Repository. The adjacent repository-password opens it.\n'
                'Keep this password private. It is deliberately included on your iPad for recovery;\n'
                'someone who can access this entire folder can decrypt the backups.\n'
                'On another machine install restic, copy the password locally, then use:\n'
                'restic -r /path/to/Repository -p /path/to/repository-password snapshots\n'
                'restic -r /path/to/Repository -p /path/to/repository-password restore SNAPSHOT --target /new/empty/folder --verify\n'
                'Do not edit repository pack/index files manually. Verified offloads may have removed local originals.\n'
                'Recovery/items records identify those separate cold snapshots. Preserve them all.\n'
                'Versioned recovery kits are under Kits; consult latest-kit.json and verify_kit.py.\n')
            save_json(recovery / 'configuration.json', self.cfg)
            self.event('initialized', {'repository': str(self.repo)})

    def sources(self):
        logical = []
        for root in self.cfg['project_roots']:
            base = Path(root)
            if base.is_dir():
                logical.extend(sorted(base.iterdir()))
        logical += [Path(p) for p in self.cfg.get('additional_paths', [])]
        # Permit reviewed source roots outside home when named explicitly in config.
        external = [Path(p) for p in self.cfg.get('allowed_external_roots', [])]

        def inside_home(resolved):
            return resolved.is_relative_to(Path(self.cfg['home'])) or any(resolved.is_relative_to(p) for p in external)

        records = []
        unique = set()
        for path in logical:
            if not path.exists():
                continue
            resolved = path.resolve()
            if resolved == self.root or resolved.is_relative_to(self.mount):
                raise VaultError('Backup source points into the iPad destination.')
            if not inside_home(resolved):
                raise VaultError('Source resolves outside the configured home: ' + str(path))
            records.append({'logical': str(path), 'stored_path': str(resolved), 'symlink': path.is_symlink()})
            unique.add(str(resolved))
        # Registered worktrees may live in cache directories outside the project roots.
        # Include their working files and shared Git metadata, not just their .git pointers.
        git_env = dict(os.environ, GIT_OPTIONAL_LOCKS='0')
        discovered = set()
        for item in list(records):
            directory = Path(item['stored_path'])
            if not directory.is_dir():
                continue
            result = subprocess.run(['git', '-C', str(directory), 'worktree', 'list', '--porcelain', '-z'],
                                    env=git_env, capture_output=True, text=True, timeout=20)
            if result.returncode:
                continue
            for field in result.stdout.split('\0'):
                if field.startswith('worktree '):
                    discovered.add((field[len('worktree '):], 'registered-worktree'))
            common = subprocess.run(['git', '-C', str(directory), 'rev-parse', '--path-format=absolute', '--git-common-dir'],
                                    env=git_env, capture_output=True, text=True, timeout=20)
            if common.returncode == 0:
                discovered.add((common.stdout.strip(), 'shared-git-metadata'))
        for original, kind in sorted(discovered):
            path = Path(original)
            if not path.exists():
                continue
            resolved = path.resolve()
            if not inside_home(resolved) or resolved.is_relative_to(self.mount):
                raise VaultError('Discovered worktree/metadata is outside the configured home: ' + original)
            if str(resolved) not in unique:
                records.append({'logical': original, 'stored_path': str(resolved), 'symlink': path.is_symlink(), 'kind': kind})
                unique.add(str(resolved))
        # Preserve logical symlinks as well as explicitly backing up their current targets.
        roots = sorted(set(self.cfg['project_roots']) | unique)
        roots = [p for p in roots if Path(p).exists()]
        roots = [p for p in roots if not any(Path(p).is_relative_to(Path(parent)) and p != parent for parent in roots)]
        return roots, records

    def backup(self):
        self.online()
        with self.locked():
            roots, mapping = self.sources()
            if not roots:
                raise VaultError('No configured sources exist.')
            save_json(self.state / 'source-map.json', mapping)
            free = shutil.disk_usage(self.root).free
            if free < self.cfg['reserve_bytes']:
                raise VaultError('iPad reserve reached. No data will be deleted automatically.')
            self.event('backup-started', {'roots': roots})
            # No excludes: build artifacts and source are both covered in this initial policy.
            self.run('backup', '--tag', self.cfg.get('snapshot_tag', 'managed-projects'),
                     '--group-by', 'host,paths,tags', '--skip-if-unchanged', '--', *roots)
            self.run('check')
            snapshot = self.refresh_catalog()
            save_json(self.root / 'Recovery/source-map.json', mapping)
            scope_record = {'scope': self.cfg.get('snapshot_tag', 'managed-projects'),
                            'snapshot': snapshot, 'roots': roots, 'mapping': mapping,
                            'recorded': now()}
            save_json(self.state / 'source-maps' / (snapshot + '.json'), scope_record)
            save_json(self.root / 'Recovery/source-maps' / (snapshot + '.json'), scope_record)
            self.event('backup-complete', {'roots': roots, 'metadata_check': 'passed', 'full_read_check': 'run project-vault check --full'})
            return snapshot

    def refresh_catalog(self):
        snapshots = json.loads(self.run('snapshots', '--tag', self.cfg.get('snapshot_tag', 'managed-projects'), '--json', capture=True))
        snapshots.sort(key=lambda item: item['time'])
        for snapshot in snapshots:
            self.db.execute('INSERT OR REPLACE INTO snapshots VALUES(?,?,?)', (snapshot['id'], snapshot['time'], json.dumps(snapshot)))
        self.db.commit()
        if not snapshots:
            raise VaultError('No snapshot exists for this project scope; backup completion is not established.')
        latest = snapshots[-1]['id']
        scopes_file = self.state / 'catalog-scopes.json'
        scopes = json.loads(scopes_file.read_text()) if scopes_file.exists() else {}
        group = self.cfg.get('snapshot_tag', 'managed-projects')
        if scopes.get(group) == latest:
            return latest
        process = subprocess.Popen(self.command('ls', '--json', latest), stdout=subprocess.PIPE, text=True)
        progress = {'phase': 'catalog', 'snapshot': latest, 'state': 'running',
                    'owner_pid': os.getpid(), 'pid': process.pid, 'started': now(), 'updated': now()}
        save_json(self.state / 'operation.json', progress)
        reported = time.monotonic()
        try:
            if not scopes:
                self.db.execute('DELETE FROM files')
            elif group in scopes:
                self.db.execute('DELETE FROM files WHERE snapshot=?', (scopes[group],))
            capacity = max(0, 100000 - self.db.execute('SELECT count(*) FROM files').fetchone()[0])
            indexed = 0
            for line in process.stdout:
                if time.monotonic() - reported >= 5:
                    progress.update(updated=now(), indexed_files=indexed)
                    save_json(self.state / 'operation.json', progress)
                    reported = time.monotonic()
                node = json.loads(line)
                if node.get('struct_type') != 'node' or 'path' not in node:
                    continue
                parts = Path(node['path']).parts
                if indexed >= min(10000, capacity) or len(parts) > 9 or any(p.startswith('target') or p in ('.git', 'node_modules', 'incremental', '.fingerprint', 'deps') for p in parts[:-1]):
                    continue
                self.db.execute('INSERT OR REPLACE INTO files VALUES(?,?,?,?,?)',
                                (latest, node['path'], node.get('type'), node.get('size', 0), node.get('mtime')))
                indexed += 1
            if process.wait():
                raise VaultError('Could not build catalog from snapshot.')
            self.db.commit()
            scopes[group] = latest
            save_json(scopes_file, scopes)
            progress.update(state='passed', finished=now(), indexed_files=indexed)
            save_json(self.state / 'operation.json', progress)
        except BaseException:
            self.db.rollback()
            process.terminate()
            process.wait()
            progress.update(state='failed', finished=now())
            save_json(self.state / 'operation.json', progress)
            raise
        finally:
            process.stdout.close()
        save_json(self.state / 'snapshots.json', snapshots)
        return latest

    def latest(self):
        row = self.db.execute('SELECT id FROM snapshots ORDER BY time DESC LIMIT 1').fetchone()
        if not row:
            raise VaultError('No cataloged repository snapshot yet. Initial backup may still be queued.')
        return row[0]

    def search(self, text):
        snapshot = self.latest()
        pattern = '%' + text.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        rows = self.db.execute("SELECT path,type,size,snapshot FROM files WHERE path LIKE ? ESCAPE '\\' ORDER BY path LIMIT 100", (pattern,)).fetchall()
        from cold import items
        return {'snapshot': snapshot, 'results': [{'path': p, 'type': t, 'bytes': s, 'snapshot': snap} for p,t,s,snap in rows], 'limit': 100,
                'cold_items': [x for x in items(self) if text.lower() in x['path'].lower()],
                'catalog_scope': 'Compact working index; use find --online for complete snapshot filename search.'}

    def restore(self, snapshot, path, destination):
        self.online()
        if snapshot == 'latest':
            snapshot = self.latest()
        if not path.startswith('/') or '..' in Path(path).parts:
            raise VaultError('Use an absolute path from the catalog, without parent traversal.')
        if not self.db.execute('SELECT 1 FROM files WHERE snapshot=? AND path=?', (snapshot, path)).fetchone():
            listing = self.run('ls', '--json', snapshot, path, capture=True)
            if not any(json.loads(line).get('path') == path for line in listing.splitlines()):
                raise VaultError('Path is not in this snapshot.')
        target = Path(destination).expanduser().absolute()
        if target.exists() or target.is_symlink():
            raise VaultError('Restore target must not exist; existing files will never be overwritten.')
        if target.resolve().is_relative_to(self.mount.resolve()):
            raise VaultError('Restore to the Linux working disk, not the iPad repository.')
        # Literal match, escaping restic glob metacharacters.
        literal = ''.join({'*': '[*]', '?': '[?]', '[': '[[]'}.get(c, c) for c in path)
        with self.locked():
            target.mkdir(parents=True, exist_ok=False)
            self.run('restore', snapshot, '--target', str(target), '--include', literal,
                     '--overwrite', 'never', '--verify', '--sparse')
            self.event('restore-complete', {'snapshot': snapshot, 'path': path, 'destination': str(target)})
        return {'restored_under': str(target / path.lstrip('/')), 'snapshot': snapshot}

    def status(self):
        snapshot = self.db.execute('SELECT id,time FROM snapshots ORDER BY time DESC LIMIT 1').fetchone()
        from cold import items
        queue = self.state / 'offload-queue.json'
        return {'repository': str(self.repo), 'mounted': os.path.ismount(self.mount),
                'initial_archive_transfer_active': self.legacy_active(),
                'latest_snapshot': {'id': snapshot[0], 'time': snapshot[1]} if snapshot else None,
                'cleanup_enabled': False, 'automatic_snapshot_deletion': False,
                'explicit_verified_offload_available': True,
                'cold_items': items(self),
                'offload_queue': json.loads(queue.read_text()) if queue.exists() else [],
                'catalog': str(self.state / 'catalog.sqlite')}

    def plan(self):
        # Deliberately advisory: age alone does not establish that agents no longer need files.
        roots, mapping = self.sources()
        candidates = []
        for item in mapping:
            path = Path(item['stored_path'])
            for name in ('target', 'node_modules', '.venv', '.lake'):
                candidate = path / name
                if candidate.is_dir() and not candidate.is_symlink():
                    candidates.append({'path': str(candidate), 'kind': 'potentially-rebuildable',
                        'action': 'review-after-verified-backup', 'automatic_removal': False})
        return {'policy': 'Review exact inactive candidates; only put --offload performs verified local retirement', 'candidates': candidates,
                'requirements': ['Successful full repository read check', 'Restore test', 'Check for active builds and unique data', 'User-approved cleanup selection']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default=str(Path.home() / '.config/project-vault/config.json'))
    sub = parser.add_subparsers(dest='action', required=True)
    for action in ('status', 'init', 'backup', 'catalog', 'list', 'plan', 'sources', 'items', 'recovery-export'):
        sub.add_parser(action)
    bench_parser = sub.add_parser('bench', help='Run an isolated synthetic benchmark')
    bench_parser.add_argument('--size-mib', type=int, default=16)
    bench_parser.add_argument('--files', type=int, default=8)
    bench_parser.add_argument('--pattern', choices=['incompressible','compressible'], default='incompressible')
    audit = sub.add_parser('audit'); audit.add_argument('--online', action='store_true')
    find = sub.add_parser('find'); find.add_argument('query'); find.add_argument('--online', action='store_true')
    put = sub.add_parser('put'); put.add_argument('path'); put.add_argument('--offload', action='store_true'); put.add_argument('--retain-binaries', action='store_true')
    get = sub.add_parser('get'); get.add_argument('item'); get.add_argument('--to')
    for name in ('pin', 'unpin', 'queue'):
        sub.add_parser(name).add_argument('path')
    origin = sub.add_parser('provenance')
    origin.add_argument('path'); origin.add_argument('--repository', required=True)
    origin.add_argument('--rebuild', required=True); origin.add_argument('--toolchain', required=True)
    check = sub.add_parser('check'); check.add_argument('--full', action='store_true')
    restore = sub.add_parser('restore')
    restore.add_argument('snapshot'); restore.add_argument('path'); restore.add_argument('--to', required=True)
    args = parser.parse_args()
    vault = Vault(args.config)
    result = None
    if args.action == 'status': result = vault.status()
    elif args.action == 'bench':
        from bench import reserve_request, validate_options, worker
        options = validate_options(args.size_mib, args.files, args.pattern)
        identity = reserve_request(args.config, options)
        result = worker(args.config, identity)
        print(json.dumps({'id':identity,'state':result['state'],'error':result.get('error')},indent=2))
        vault.db.close()
        raise SystemExit(0 if result['state']=='passed' else 1)
    elif args.action == 'init': vault.initialize()
    elif args.action == 'backup': vault.backup()
    elif args.action == 'recovery-export':
        from recovery import export_kit
        result = export_kit(vault)
    elif args.action == 'audit':
        from recovery import audit
        result = audit(vault, online=args.online)
    elif args.action == 'sources': result = vault.sources()[1]
    elif args.action == 'plan': result = vault.plan()
    elif args.action == 'list': result = [json.loads(row[0]) for row in vault.db.execute('SELECT metadata FROM snapshots ORDER BY time DESC')]
    elif args.action == 'find':
        if args.online:
            vault.online()
            with vault.locked():
                result = json.loads(vault.run('find', '--json', '--', args.query, capture=True))
        else: result = vault.search(args.query)
    elif args.action in ('put', 'get', 'items'):
        import cold
        if args.action == 'put': result = cold.put(vault, args.path, args.offload, retain_binaries=args.retain_binaries)
        elif args.action == 'get': result = cold.get(vault, args.item, args.to)
        else: result = cold.items(vault)
    elif args.action == 'queue':
        from queue_store import enqueue
        result = enqueue(vault, args.path)
    elif args.action == 'provenance':
        from provenance import register
        result = register(vault, args.path, args.repository, args.rebuild, args.toolchain)
    elif args.action in ('pin', 'unpin'):
        from pins import set_pin
        result = set_pin(vault, args.path, args.action == 'pin')
    elif args.action == 'catalog':
        vault.online()
        with vault.locked(): vault.refresh_catalog()
    elif args.action == 'restore': result = vault.restore(args.snapshot, args.path, args.to)
    elif args.action == 'check':
        vault.online()
        with vault.locked():
            vault.run('check', *(['--read-data'] if args.full else []))
            vault.event('full-read-check' if args.full else 'metadata-check', {'result': 'passed'})
    if result is not None: print(json.dumps(result, indent=2))
    if args.action == 'audit' and result['state'] != 'passed':
        raise SystemExit(1)


if __name__ == '__main__':
    try:
        main()
    except (VaultError, OSError, subprocess.SubprocessError) as error:
        print('project-vault: ' + str(error), file=sys.stderr)
        sys.exit(1)
