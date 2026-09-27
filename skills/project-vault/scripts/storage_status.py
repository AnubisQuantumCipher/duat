#!/usr/bin/env python3
"""Local, read-only DUAT preflight; never traverses sources or contacts the iPad."""
import json
from collections import Counter
import os
from pathlib import Path
import shutil
import subprocess

home = Path.home()
state = home / '.local/state/project-vault'

def read(path):
    try:
        return json.loads(path.read_text()) if path.exists() else None
    except (OSError, ValueError) as error:
        return {'unreadable': str(error)}

def summary(value, fields):
    if not isinstance(value, dict):
        return value
    if 'unreadable' in value:
        return value
    return {key: value[key] for key in fields if key in value}

usage = shutil.disk_usage(home)
config = read(home / '.config/project-vault/config.json') or {}
result = {
    'local_disk_bytes': {'total': usage.total, 'used': usage.used, 'free': usage.free},
    'configured_local_reserve_bytes': config.get('local_reserve_bytes', 10000000000),
    'blanket_eviction_enabled': False,
    'reviewed_queue_policy': 'Existing worker can offload explicitly enrolled candidates; no blanket cleanup.',
    'ipad_availability': 'Not probed by this local-only preflight; vault operations validate mount and identity.',
    'pins': read(state / 'pinned-paths.json'),
}
operation = summary(read(state / 'operation.json'),
                    ('state', 'phase', 'owner_pid', 'pid', 'started', 'updated', 'finished', 'exit_code'))
if isinstance(operation, dict):
    operation['boundary'] = 'Recorded operation; a running label can be stale after interruption.'
result['recorded_operation'] = operation
queue = read(state / 'offload-queue.json')
result['offload_queue'] = ({'counts_by_state': dict(Counter(x.get('state', 'unknown') for x in queue)),
                           'pending_or_review': [summary(x, ('id', 'path', 'state', 'error')) for x in queue
                                                 if x.get('state') not in ('done', 'cancelled')]}
                          if isinstance(queue, list) and all(isinstance(x, dict) for x in queue) else queue)
result['recovery_receipts'] = {}
for name in ('restore-drill.json', 'recovery-audit.json', 'scrub.json',
             'capacity-campaign.json', 'capacity-final-kit.json'):
    result['recovery_receipts'][name] = summary(read(state / name),
        ('state', 'time', 'updated', 'finished', 'snapshot', 'reason', 'error',
         'items_checked', 'issues', 'regrown_paths', 'files_checked', 'kit',
         'last_success', 'method', 'boundary'))
health = read(state / 'project-health.json')
result['project_scopes'] = {
    key: summary(value, ('state', 'snapshot', 'last_success', 'updated', 'error', 'reason'))
    for key, value in health.items()
} if isinstance(health, dict) else health
# systemctl is local and bounded; use the ordinary user bus when the runner omitted it.
env = os.environ.copy()
runtime = Path('/run/user') / str(os.getuid())
if (runtime / 'bus').exists():
    env.setdefault('XDG_RUNTIME_DIR', str(runtime))
    env.setdefault('DBUS_SESSION_BUS_ADDRESS', 'unix:path=' + str(runtime / 'bus'))
try:
    p = subprocess.run(['systemctl', '--user', 'show', 'project-vault-backup.service',
                        '-p', 'ActiveState', '-p', 'SubState', '-p', 'ExecMainStatus'],
                       capture_output=True, text=True, timeout=15, env=env)
    result['backup_service'] = {'exit_status': p.returncode, 'output': p.stdout.strip(),
                                'error': p.stderr.strip()}
except (OSError, subprocess.TimeoutExpired) as error:
    result['backup_service'] = {'unavailable': str(error)}
print(json.dumps(result, indent=2))
