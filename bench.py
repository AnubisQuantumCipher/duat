#!/usr/bin/env python3
"""DUAT Bench: isolated synthetic measurements; never operates on production snapshots."""
import argparse
import contextlib
import csv
import datetime as dt
import fcntl
import hashlib
import html
import json
import os
from pathlib import Path
import re
import secrets
import selectors
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from vault import Vault, VaultError, save_json, now

SCHEMA = 'duat-bench/v1'
CHUNK = 1024 * 1024
INTERVAL = .5
PEAK_WINDOW = 5.0
ID = re.compile(r'^[a-f0-9]{32}$')
TERMINAL = {'passed', 'failed', 'cancelled', 'refused', 'interrupted'}
CSV_FIELDS = ('timestamp', 'elapsed_s', 'phase', 'phase_elapsed_s', 'counter_bytes',
              'counter_kind', 'counter_status', 'current_Bps', 'current_status',
              'sample_interval_s', 'sustained_Bps', 'local_free_bytes',
              'archive_free_bytes', 'scratch_logical_bytes', 'scratch_allocated_bytes',
              'load_1m', 'memory_available_bytes', 'temperature_max_c',
              'wrapper_retries', 'backend_retries', 'committed_bytes', 'wire_bytes')


def datum(value=None, status='unavailable', unit=None, reason=None):
    result = {'value': value, 'status': status}
    if unit: result['unit'] = unit
    if reason: result['reason'] = reason
    return result


def read_json(path, default=None):
    try: return json.loads(Path(path).read_text())
    except (OSError, ValueError): return default


def validate_options(size_mib=16, files=8, pattern='incompressible'):
    if type(size_mib) is not int or not 1 <= size_mib <= 1024:
        raise VaultError('Choose a payload from 1 through 1024 MiB.')
    if type(files) is not int or not 1 <= files <= 1024:
        raise VaultError('Choose a file count from 1 through 1024.')
    if pattern not in ('incompressible', 'compressible'):
        raise VaultError('Unknown synthetic workload.')
    return {'size_mib': size_mib, 'files': files, 'pattern': pattern,
            'payload_bytes': size_mib * CHUNK, 'seed': 'duat-bench-v1',
            'generator': 'SHAKE-256 per file, or repeated ASCII DUAT-BENCH; no user input files',
            'sample_interval_s': INTERVAL, 'peak_window_s': PEAK_WINDOW,
            'compression': 'auto', 'cache_policy': 'fresh restic cache; OS/device caches uncontrolled'}


def usage_tree(path):
    """Only the small, explicitly owned synthetic work directory, never production roots."""
    logical = allocated = 0
    for base, dirs, files in os.walk(path, followlinks=False):
        dirs[:] = [d for d in dirs if not (Path(base) / d).is_symlink()]
        for name in files:
            try:
                st = (Path(base) / name).lstat()
                logical += st.st_size
                allocated += st.st_blocks * 512
            except FileNotFoundError: pass
    return logical, allocated


def telemetry(local, archive=None, scratch=None):
    result = {'observed_at': now()}
    for name, path in (('local_free_bytes', local), ('archive_free_bytes', archive)):
        try: result[name] = datum(shutil.disk_usage(path).free, 'measured', 'bytes') if path else datum(reason='Archive offline or unconfigured')
        except OSError: result[name] = datum(reason='Filesystem unavailable')
    try: result['load_1m'] = datum(os.getloadavg()[0], 'measured', 'load')
    except OSError: result['load_1m'] = datum()
    try:
        mem = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
        result['memory_available_bytes'] = datum(int(mem['MemAvailable'].split()[0]) * 1024, 'measured', 'bytes')
    except (OSError, KeyError, ValueError): result['memory_available_bytes'] = datum()
    temperatures = []
    for p in Path('/sys/class/thermal').glob('thermal_zone*/temp'):
        try: temperatures.append(int(p.read_text()) / 1000)
        except (OSError, ValueError): pass
    result['temperature_max_c'] = datum(max(temperatures), 'measured', 'C') if temperatures else datum(reason='Host thermal telemetry not exposed')
    result['device_temperature_c'] = datum(reason='iPad temperature not exposed by this backend')
    result['negotiated_link_Bps'] = datum(reason='No authoritative negotiated-link counter; cable labels are not measurements')
    result['committed_object_Bps'] = datum(reason='ifuse/filesystem backend exposes no device commit acknowledgement counter')
    result['power_state'] = datum(reason='No device power-state telemetry exposed by this backend')
    if scratch:
        logical, allocated = usage_tree(scratch)
        result['scratch_logical_bytes'] = datum(logical, 'measured', 'bytes')
        result['scratch_allocated_bytes'] = datum(allocated, 'measured', 'bytes', 'Filesystem st_blocks; includes source, restore, cache and test credential')
    return result


class Rates:
    """Phase-local monotonic counters. Peak needs an actual complete window."""
    def __init__(self, start, status='measured'):
        self.start = start
        self.points = deque([(start, 0)])
        self.peak = datum(reason='No complete peak window observed')
        self.status = status

    def update(self, clock, count):
        previous_t, previous_b = self.points[-1]
        if count < previous_b: raise VaultError('Measurement counter moved backwards')
        duration = clock - previous_t
        current = (count - previous_b) / duration if duration > 0 else None
        self.points.append((clock, count))
        while len(self.points) > 2 and self.points[1][0] <= clock - PEAK_WINDOW:
            self.points.popleft()
        first_t, first_b = self.points[0]
        window = clock - first_t
        if window >= PEAK_WINDOW:
            value = (count - first_b) / window
            if self.peak['value'] is None or value > self.peak['value']:
                self.peak = datum(value, self.status, 'bytes/s')
                self.peak.update(start_s=first_t-self.start, end_s=clock-self.start,
                                 actual_window_s=window, target_window_s=PEAK_WINDOW)
        elapsed = clock - self.start
        return {'current': datum(current, self.status if current is not None else 'unavailable', 'bytes/s'),
                'sample_interval_s': duration,
                'sustained': datum(count / elapsed if elapsed > 0 else None, 'measured', 'bytes/s'),
                'peak': dict(self.peak)}


@contextlib.contextmanager
def exclusive(path):
    with Path(path).open('a') as f:
        try: fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise VaultError('Another benchmark or launch is active')
        yield


def checked_folder(parent, name):
    p = parent / name
    if p.is_symlink(): raise VaultError('Benchmark directory must not be a symlink')
    p.mkdir(mode=0o700, exist_ok=True)
    if not p.is_dir(): raise VaultError('Benchmark directory is not a directory')
    return p


def runs_root(state):
    return checked_folder(checked_folder(Path(state), 'bench'), 'runs')


def process_identity(pid):
    try:
        fields=Path('/proc',str(pid),'stat').read_text().rsplit(')',1)[1].split()
        return {'start_ticks':fields[19], 'boot':Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
    except (OSError,IndexError):return None


def read_report(state, identity):
    if not ID.fullmatch(str(identity)): raise VaultError('Invalid benchmark ID')
    folder = runs_root(state) / identity
    if folder.is_symlink(): raise VaultError('Invalid benchmark directory')
    result = read_json(folder / 'report.json') or read_json(folder / 'request.json')
    if not result: raise VaultError('Benchmark not found')
    if result['state'] not in TERMINAL:
        request = read_json(folder / 'request.json', {})
        pid = request.get('pid')
        if not pid or process_identity(pid) != request.get('process_identity'):
            result = dict(result, state='interrupted', freshness='historical',
                          error='Worker no longer running; retained synthetic files require review')
        else: result = dict(result, freshness='live')
    else: result = dict(result, freshness='historical')
    result = dict(result)
    result.pop('pid',None);result.pop('process_identity',None)
    return result


def overview(state, config=None):
    root = runs_root(state)
    reports = []
    for p in sorted(root.iterdir(), key=lambda p:p.stat().st_mtime, reverse=True):
        if ID.fullmatch(p.name) and not p.is_symlink():
            try: reports.append(read_report(state, p.name))
            except VaultError: pass
        if len(reports) >= 20: break
    archive = None
    if config:
        v = None
        try:
            v = Vault(config); v.online(); archive = v.root
        except (VaultError, OSError): pass
        finally:
            if v: v.db.close()
    return {'runs': reports, 'telemetry': telemetry(state, archive), 'schema': SCHEMA}


def reserve_request(config, options, detached=False):
    v = Vault(config)
    try:
        root = runs_root(v.state)
        with exclusive(root.parent / 'launch.lock'):
            with exclusive(root.parent / 'worker.lock'):
                latest = read_json(root.parent / 'latest.json', {})
                if latest.get('id'):
                    r = read_report(v.state, latest['id'])
                    if r['state'] not in TERMINAL: raise VaultError('A benchmark is already active')
                identity = uuid.uuid4().hex
                folder = root / identity; folder.mkdir(mode=0o700)
                request = {'schema': SCHEMA, 'id': identity, 'state': 'queued',
                           'created': now(), 'options': options, 'pid': os.getpid(),
                           'process_identity':process_identity(os.getpid())}
                save_json(folder / 'request.json', request)
                save_json(root.parent / 'latest.json', {'id': identity})
            if detached:
                child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()),
                    '--config', str(Path(config).resolve()), 'worker', identity],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    start_new_session=True)
                request['pid'] = child.pid
                request['process_identity'] = process_identity(child.pid)
                save_json(folder / 'request.json', request)
            return identity
    finally: v.db.close()


def cancel_run(state, identity):
    report = read_report(state, identity)
    if report['state'] in TERMINAL: raise VaultError('Benchmark has already ended')
    (runs_root(state) / identity / 'cancel').touch(mode=0o600)
    return {'message': 'Cancellation requested. Synthetic files will be retained.'}


class Bench:
    def __init__(self, vault, identity, options):
        if not ID.fullmatch(identity): raise VaultError('Invalid benchmark ID')
        self.v = vault; self.identity = identity; self.options = options
        self.folder = runs_root(vault.state) / identity
        self.work = self.folder / 'work'
        self.start = time.monotonic(); self.lock = threading.RLock()
        self.stop = threading.Event(); self.abort = None; self.active = None
        self.counter = 0; self.counter_kind = 'none'; self.proc = None
        self.report = {'schema': SCHEMA, 'id': identity, 'state': 'running', 'created': now(),
            'options': options, 'phases': [], 'integrity': {'transport_readback': 'not-run',
            'restic_check': 'not-run', 'restic_restore_verify': 'not-run', 'full_manifest': 'not-run'},
            'wrapper_retries': datum(0, 'measured', 'attempts', 'No automatic retries; failures remain failures'),
            'backend_retries': datum(reason='Backend internal retries not exposed'),
            'restic_packed_bytes': datum(reason='Encrypted backup has not completed'),
            'wire_bytes': datum(reason='No per-run wire counter; filesystem payload is not physical traffic'),
            'committed_object_bytes': datum(reason='No device commit acknowledgement counter exposed'),
            'committed_object_Bps': datum(reason='No device commit acknowledgement counter exposed'),
            'round_trip_elapsed_s': datum(reason='Requires successful full restore and manifest comparison'),
            'round_trip_scope': 'After generation: payload write/sync/readback, repository init, encrypted backup, data check, restore --verify, full manifest comparison',
            'retention': 'All synthetic source, scratch and isolated archive files retained; no production retirement or pruning',
            'backend': 'ifuse' if vault.cfg.get('require_ifuse_mount', True) else 'local-fixture',
            'non_claims': ['No negotiated cable speed inference', 'No device durability assertion',
                           'Upload is not verified recovery', 'OS/device caches uncontrolled',
                           'Synthetic results do not establish production archive recovery']}
        self.csv_file = None; self.writer = None; self.last_sample = 0

    def guard(self, remaining=0, admission=False):
        if self.abort: raise VaultError(self.abort)
        if (self.folder / 'cancel').exists(): raise VaultError('Benchmark cancelled')
        self.v.online()
        local = shutil.disk_usage(self.v.state).free
        remote = shutil.disk_usage(self.v.root).free
        local_reserve = self.v.cfg.get('local_reserve_bytes', 10_000_000_000)
        remote_reserve = self.v.cfg['reserve_bytes']
        if local < local_reserve + remaining or remote < remote_reserve + remaining:
            raise VaultError('Storage reserve would be crossed; benchmark refused' if admission else 'Storage reserve reached; benchmark stopped')

    def persist(self):
        self.report['updated'] = now()
        self.report['elapsed_s'] = time.monotonic() - self.start
        save_json(self.folder / 'report.json', self.report)

    def sample(self):
        with self.lock:
            self.guard()
            clock = time.monotonic()
            env = telemetry(self.v.state, self.v.root, self.work)
            self.report['telemetry'] = env
            if self.active:
                rates = self.rates.update(clock, self.counter)
                self.active.update(counter_bytes=self.counter if self.counter_kind!='none' else None, counter_kind=self.counter_kind,
                                   elapsed_s=clock-self.phase_start, rates=rates)
                row = {'timestamp': env['observed_at'], 'elapsed_s': clock-self.start,
                       'phase': self.active['name'], 'phase_elapsed_s':clock-self.phase_start,
                       'counter_bytes':self.counter if self.counter_kind!='none' else None, 'counter_kind':self.counter_kind,
                       'counter_status':'measured' if self.counter_kind!='none' else 'unavailable',
                       'current_Bps': rates['current']['value'], 'current_status':rates['current']['status'],
                       'sample_interval_s':rates['sample_interval_s'],
                       'sustained_Bps':rates['sustained']['value'], 'wrapper_retries':0}
                if self.counter_kind == 'none':
                    self.active['rates'] = {'current':datum(), 'sustained':datum(), 'peak':datum()}
                    row.update(current_Bps=None, current_status='unavailable', sustained_Bps=None)
                for k in CSV_FIELDS:
                    if k in env: row[k] = env[k]['value']
                self.writer.writerow(row); self.csv_file.flush()
                series=self.report.setdefault('series',[])
                series.append({'t':clock-self.start,'phase':self.active['name'],
                               'rate':row.get('current_Bps'),'status':row['current_status']})
                self.report['series']=series[-240:]
            self.persist(); self.last_sample = clock

    def sampler(self):
        while not self.stop.wait(INTERVAL):
            try: self.sample()
            except Exception as e:
                self.abort = self.safe_error(e); return

    def safe_error(self, error):
        if isinstance(error, VaultError):
            # All messages here are fixed strings without backend paths or credential contents.
            return str(error)
        return type(error).__name__ + ': benchmark operation failed; synthetic files retained'

    @contextlib.contextmanager
    def phase(self, name, counter_kind='none', rate_status='measured'):
        self.guard()
        with self.lock:
            self.phase_start = time.monotonic(); self.counter=0; self.counter_kind=counter_kind
            self.rates=Rates(self.phase_start, rate_status)
            self.active={'name':name, 'state':'running', 'started':now(),
                         'start_s':self.phase_start-self.start, 'counter_bytes':0,
                         'counter_kind':counter_kind, 'elapsed_s':0}
            self.report['phases'].append(self.active); self.persist()
        try:
            yield
            self.sample()
            with self.lock: self.active.update(state='passed', finished=now())
        except BaseException as error:
            with self.lock:
                gate={'Transport payload readback':'transport_readback',
                      'Encrypted repository data check':'restic_check',
                      'Restore with restic verification':'restic_restore_verify',
                      'Complete restored manifest comparison':'full_manifest'}.get(name)
                if gate:
                    reason=str(error)
                    self.report['integrity'][gate]='failed' if 'Integrity failure' in reason or 'restic command failed' in reason else 'incomplete'
                self.active.update(state='failed', finished=now(), elapsed_s=time.monotonic()-self.phase_start,
                                   counter_bytes=self.counter)
            raise
        finally:
            with self.lock: self.active=None; self.persist()

    def advance(self, amount):
        with self.lock: self.counter += amount
        self.guard()

    def generate(self):
        source = self.work / 'source'; source.mkdir()
        total = self.options['payload_bytes']; count = self.options['files']; manifest = {}
        for index in range(count):
            size = total // count + (1 if index < total % count else 0)
            name = f'payload-{index:04d}.bin'; digest = hashlib.sha256()
            # File size is bounded by request limits. Stream SHAKE blocks with distinct coordinates.
            with (source / name).open('xb') as out:
                offset = 0
                while offset < size:
                    self.guard(); n=min(CHUNK,size-offset)
                    if self.options['pattern']=='incompressible':
                        data=hashlib.shake_256(f"{self.options['seed']}:{index}:{offset}".encode()).digest(n)
                    else: data=(b'DUAT-BENCH\n' * (n//len(b'DUAT-BENCH\n')+1))[:n]
                    self.guard(n); out.write(data); digest.update(data); offset+=n; self.advance(n)
                out.flush(); os.fsync(out.fileno())
            manifest[name]={'bytes':size,'sha256':digest.hexdigest()}
        save_json(self.folder/'manifest.json',manifest)
        with self.lock:self.report['workload_manifest']=manifest
        return source, manifest

    def copy_payload(self, source, target):
        target.mkdir()
        for p in sorted(source.iterdir()):
            with p.open('rb') as inp, (target/p.name).open('xb', buffering=0) as out:
                while True:
                    self.guard(); block=inp.read(CHUNK)
                    if not block:break
                    view=memoryview(block)
                    while view:
                        self.guard(len(view)); written=out.write(view)
                        if not written:raise VaultError('Payload write made no progress')
                        view=view[written:];self.advance(written)

    def sync_payload(self, target):
        for p in sorted(target.iterdir()):
            self.guard()
            with p.open('rb') as f:os.fsync(f.fileno())
        self.report['filesystem_sync']=datum(True,'measured',reason='Host fsync returned; not an iPad durability or object-commit acknowledgement')

    def verify(self, directory, manifest):
        if {p.name for p in directory.iterdir()} != set(manifest):
            raise VaultError('Integrity failure: file set differs')
        for name, expected in manifest.items():
            p=directory/name
            if p.is_symlink() or not p.is_file():raise VaultError('Integrity failure: file type differs')
            digest=hashlib.sha256();size=0
            with p.open('rb') as f:
                while True:
                    self.guard();block=f.read(CHUNK)
                    if not block:break
                    digest.update(block);size+=len(block);self.advance(len(block))
            if size!=expected['bytes'] or digest.hexdigest()!=expected['sha256']:
                raise VaultError('Integrity failure: full content comparison differs')

    def restic(self, *args):
        # Explicit isolated paths; discard inherited restic/remote-backend configuration.
        env={k:v for k,v in os.environ.items() if not k.startswith(('RESTIC_','AWS_','B2_','AZURE_','GOOGLE_','RCLONE_'))}
        env.update(RESTIC_PROGRESS_FPS='2', TMPDIR=str(self.work))
        command=['restic','--repo',str(self.remote/'repository'),'--password-file',str(self.work/'password'),
                 '--cache-dir',str(self.work/'cache'),'--compression','auto','--json',*args]
        summaries=[]
        # Raw stderr stays private in owned scratch; no logs, paths or commands in exports.
        with (self.work/'backend-errors.log').open('ab') as errors:
            self.proc=subprocess.Popen(command,cwd=self.work,env=env,stdout=subprocess.PIPE,stderr=errors,
                                       start_new_session=True)
            selector=selectors.DefaultSelector();selector.register(self.proc.stdout,selectors.EVENT_READ)
            buffer=b''
            try:
                while selector.get_map():
                    self.guard()
                    for key,_ in selector.select(INTERVAL):
                        data=os.read(key.fd,65536)
                        if not data:selector.unregister(key.fileobj);continue
                        buffer+=data
                        while b'\n' in buffer:
                            line,buffer=buffer.split(b'\n',1)
                            try: event=json.loads(line)
                            except ValueError:continue
                            if event.get('message_type') in ('status','summary'):
                                count=event.get('bytes_done',event.get('bytes_restored',event.get('total_bytes_processed')))
                                if count is not None:
                                    with self.lock:self.counter=max(self.counter,int(count))
                            if event.get('message_type')=='summary':summaries.append(event)
                    if time.monotonic()-self.phase_start > 1800:
                        raise VaultError('Benchmark phase timed out; files retained')
                code=self.proc.wait()
                if code:raise VaultError(f'Isolated restic command failed with exit code {code}; private log retained in benchmark scratch')
                return summaries[-1] if summaries else {}
            finally:
                selector.close()
                if self.proc.poll() is None:
                    os.killpg(self.proc.pid,signal.SIGTERM)
                    try:self.proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:os.killpg(self.proc.pid,signal.SIGKILL);self.proc.wait()
                self.proc.stdout.close(); self.proc=None

    def execute(self):
        thread=None
        self.csv_file=(self.folder/'samples.csv').open('w',newline='')
        self.writer=csv.DictWriter(self.csv_file,fieldnames=CSV_FIELDS);self.writer.writeheader()
        try:
            with exclusive(self.folder.parent.parent/'worker.lock'), self.v.locked():
                # Budget is intentionally conservative, not an exact forecast. No cleanup to fit.
                allowance=self.options['payload_bytes']*4 + 64*CHUNK
                self.report['admission_bytes']=datum(allowance,'estimated','bytes','Conservative payload multiple plus overhead on each volume')
                self.guard(allowance,admission=True)
                self.work.mkdir(mode=0o700,exist_ok=False)
                remote_parent=checked_folder(self.v.root,'Bench')
                self.remote=remote_parent/self.identity;self.remote.mkdir(mode=0o700,exist_ok=False)
                save_json(self.remote/'bench-owner.json',{'schema':SCHEMA,'id':self.identity,'synthetic_only':True})
                self.report['software']={'python':sys.version.split()[0],
                    'restic':subprocess.check_output(['restic','version'],text=True).strip(),
                    'engine_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
                with (self.work/'password').open('x') as f:os.chmod(f.name,0o600);f.write(secrets.token_urlsafe(48))
                thread=threading.Thread(target=self.sampler,daemon=True);thread.start()
                with self.phase('Generate synthetic source','logical_generated_bytes'):source,manifest=self.generate()
                round_start=time.monotonic()
                with self.phase('Transport payload write','filesystem_payload_written_bytes'):
                    self.copy_payload(source,self.remote/'payload')
                with self.phase('Filesystem sync acknowledgement'):self.sync_payload(self.remote/'payload')
                with self.phase('Transport payload readback','filesystem_payload_read_bytes'):
                    self.verify(self.remote/'payload',manifest)
                self.report['integrity']['transport_readback']='passed'
                with self.phase('Initialize isolated encrypted repository'):self.restic('init')
                with self.phase('Encrypted backup','logical_backup_bytes','estimated'):
                    summary=self.restic('backup','--host','duat-bench','--tag','duat-bench-synthetic','source')
                    snapshot=summary.get('snapshot_id')
                    if not snapshot:raise VaultError('Isolated backup did not return a snapshot')
                packed=summary.get('data_added_packed')
                self.report['restic_packed_bytes']=datum(packed,'measured' if packed is not None else 'unavailable','bytes',
                    'Restic-reported added compressed data; excludes wire overhead and is not a device commit counter')
                with self.phase('Encrypted repository data check'):self.restic('check','--read-data')
                self.report['integrity']['restic_check']='passed'
                with self.phase('Restore with restic verification','logical_restored_bytes','estimated'):
                    self.restic('restore',snapshot,'--target',str(self.work/'restored'),'--verify')
                self.report['integrity']['restic_restore_verify']='passed'
                with self.phase('Complete restored manifest comparison','logical_verified_bytes'):
                    self.verify(self.work/'restored/source',manifest)
                    # Also re-read the retained source; never turn a changed source into a pass.
                    self.verify(source,manifest)
                self.report['integrity']['full_manifest']='passed'
                self.report['round_trip_elapsed_s']=datum(time.monotonic()-round_start,'measured','seconds')
                self.report['state']='passed'
        except BaseException as e:
            reason=self.safe_error(e)
            self.report['state']='cancelled' if 'cancel' in reason.lower() else ('refused' if not self.work.exists() else 'failed')
            self.report['error']=reason
        finally:
            self.stop.set()
            if thread:thread.join(timeout=5)
            if self.csv_file:
                self.csv_file.close()
                self.report['samples_sha256']=hashlib.sha256((self.folder/'samples.csv').read_bytes()).hexdigest()
            self.report['finished']=now();self.report['freshness']='historical'
            with self.lock:self.persist()
            write_card(self.folder, self.report)
        return self.report


def write_card(folder, report):
    e=html.escape
    rows=[]
    for phase in report['phases']:
        rate=phase.get('rates',{}).get('sustained',{})
        value=rate.get('value')
        peak=phase.get('rates',{}).get('peak',{})
        peak_text=f"{peak['value']:,.0f} B/s over {peak['actual_window_s']:.3f} s ({peak['status']})" if peak.get('value') is not None else 'unavailable'
        rows.append(f"<tr><td>{e(phase['name'])}</td><td>{e(phase['state'])}</td><td>{phase.get('elapsed_s',0):.3f} s</td><td>{f'{value:,.0f} B/s' if value is not None else 'unavailable'}</td><td>{peak_text}</td></tr>")
    elapsed=report['round_trip_elapsed_s']
    duration=f"{elapsed['value']:.3f} s" if elapsed['value'] is not None else 'not verified'
    conditions=report.get('telemetry',{})
    condition_rows=''.join(f'<li>{e(key)}: {e(str(value.get("value")) if value.get("value") is not None else "unavailable")} {e(value.get("unit",""))} · {e(value["status"])}</li>' for key,value in conditions.items() if isinstance(value,dict))
    packed=report.get('restic_packed_bytes',{})
    doc=f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>DUAT Bench result</title>
<style>body{{max-width:900px;margin:40px auto;padding:24px;background:#edf3f7;color:#173447;font:16px system-ui}}h1{{font:46px Georgia}}table{{width:100%;border-collapse:collapse}}td,th{{padding:12px;text-align:left;border-bottom:1px solid #bdcdd7}}.value{{font:40px monospace}}small{{color:#476173}}@media print{{body{{background:white}}}}</style>
<p>DUAT BENCH · historical result · {e(report['backend'])}</p><h1>Verified round trip</h1><div class="value">{duration}</div>
<p>Outcome: <strong>{e(report['state'])}</strong> · {e(report['created'])}</p><p>{e(report.get('error',''))}</p>
<p>Logical payload: {report['options']['payload_bytes']:,} bytes · {report['options']['files']} files · {e(report['options']['pattern'])}</p>
<table><tr><th>Phase</th><th>Result</th><th>Measured elapsed</th><th>Sustained counter rate · measured</th><th>Peak complete window</th></tr>{''.join(rows)}</table>
<p>Integrity: {e(json.dumps(report['integrity']))}</p>
<p>Restic added packed bytes: {e(str(packed.get('value')) if packed.get('value') is not None else 'unavailable')} · {e(packed.get('status','unavailable'))}. Wire bytes: unavailable. Wrapper retries: {report['wrapper_retries']['value']} · measured; backend internal retries: unavailable.</p>
<details open><summary>Historical operating conditions</summary><ul>{condition_rows}</ul></details><p>Device-committed throughput: unavailable. Negotiated link speed: unavailable.</p>
<p><small>Filesystem payload counters are measured at the application boundary. Backup/restore counters are logical bytes; packed data is distinct from wire traffic. Live rates may be estimated from batched backend progress. No upload alone establishes verified recovery. OS and device caches were not controlled. This card contains synthetic results only and omits paths, usernames, credentials and production identifiers. JSON and CSV exports contain detailed counters, phase timings, peak windows and operating telemetry.</small></p></html>'''
    (folder/'card.html').write_text(doc)


def worker(config, identity):
    v=Vault(config)
    try:
        request=read_json(runs_root(v.state)/identity/'request.json')
        if not request:raise VaultError('Missing benchmark request')
        claim=runs_root(v.state)/identity/'started'
        try:
            with claim.open('x') as f:f.write(now())
        except FileExistsError:raise VaultError('This run has already started; create a new benchmark')
        options=request['options']
        validated=validate_options(options['size_mib'],options['files'],options['pattern'])
        engine=Bench(v,identity,validated)
        def terminate(signum, frame): engine.abort='Benchmark cancelled by service shutdown'
        previous={s:signal.signal(s,terminate) for s in (signal.SIGTERM,signal.SIGINT)}
        try:return engine.execute()
        finally:
            for sig,handler in previous.items():signal.signal(sig,handler)
    finally:v.db.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',default=str(Path.home()/'.config/project-vault/config.json'))
    sub=parser.add_subparsers(dest='action',required=True)
    run=sub.add_parser('run');run.add_argument('--size-mib',type=int,default=16);run.add_argument('--files',type=int,default=8)
    run.add_argument('--pattern',choices=['incompressible','compressible'],default='incompressible')
    job=sub.add_parser('worker');job.add_argument('id')
    args=parser.parse_args()
    identity=args.id if args.action=='worker' else reserve_request(args.config,validate_options(args.size_mib,args.files,args.pattern))
    report=worker(args.config,identity)
    print(json.dumps({'id':identity,'state':report['state'],'error':report.get('error')},indent=2))
    return 0 if report['state']=='passed' else 1

if __name__=='__main__':
    try:sys.exit(main())
    except (VaultError,OSError,ValueError) as e:print('DUAT Bench: '+str(e),file=sys.stderr);sys.exit(1)
