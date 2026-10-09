#!/usr/bin/env python3
"""Cooperative deferral for background vault maintenance, never job admission.

Observations are deliberately one-way: they may defer maintenance, never authorize
a build, offload or lock bypass. A workload starting after a check may overlap an
already-running scope; low scheduling priority remains the second line of defense.
"""
import argparse
import fcntl
import json
from pathlib import Path

from vault import now, save_json


BUILD_PROCESSES = frozenset({
    'gnatprove', 'gprbuild', 'gprbind', 'gprlib', 'gnat1', 'gnat2',
    'gnat2why', 'gnatwhy3', 'why3', 'alt-ergo', 'cvc4', 'cvc5', 'z3',
    'gcc', 'g++', 'cc1', 'cc1plus', 'rustc', 'cargo', 'ninja', 'make',
})
KINDS = ('backup', 'tier', 'scrub', 'drill')


def assess(config, *, proc_root=Path('/proc')):
    """Return a dated scheduling observation without touching the repository."""
    def result(allowed, reason, **details):
        return {'at': now(), 'allowed': allowed, 'reason': reason,
                'boundary': 'Cooperative scheduling observation only; not a lock, '
                            'build admission, backup success or offload authorization.',
                **details}

    try:
        state = Path(config['state'])
        policy = config.get('background_policy', {})
        if not isinstance(policy, dict):
            raise ValueError('background_policy must be an object')
        windows = policy.get('coordination_files', [])
        if not isinstance(windows, list) or any(not isinstance(p, str) or
                                               not Path(p).is_absolute() for p in windows):
            raise ValueError('coordination_files must be absolute paths')
        for name in windows:
            record = json.loads(Path(name).read_text())
            if not isinstance(record, dict) or record.get('status') != 'released':
                return result(False, 'Build/proof coordination window is not released',
                              coordination_file=name)

        for process in proc_root.iterdir():
            if not process.name.isdigit():
                continue
            try:
                command = (process / 'comm').read_text().strip()
            except (FileNotFoundError, ProcessLookupError):
                continue  # Process exited during this observation.
            if command in BUILD_PROCESSES:
                return result(False, 'Compiler or prover is active',
                              pid=int(process.name), command=command)

        requests_folder = state / 'requests'
        try:
            requests = sorted(requests_folder.iterdir())
        except FileNotFoundError:
            try:
                requests_folder.lstat()
            except FileNotFoundError:
                requests = []  # No retrieval has created this optional folder.
            else:
                return result(False, 'Retrieval directory cannot be enumerated',
                              directory=str(requests_folder))
        for path in requests:
            if path.suffix != '.json':
                continue
            request = json.loads(path.read_text())
            if not isinstance(request, dict):
                raise ValueError('Malformed retrieval request: ' + str(path))
            if request.get('state') in ('queued', 'waiting', 'running'):
                return result(False, 'Requested retrieval has priority', request=str(path))
            if request.get('state') not in ('done', 'failed'):
                return result(False, 'Retrieval request has an unknown state', request=str(path))

        # Probe only. The actual operation must still acquire its own existing
        # lock. Never unlink it or treat this observation as a future reservation.
        with (state / 'operation.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return result(False, 'Another vault operation has priority')
        return result(True, 'No observed foreground work or retrieval blocks maintenance')
    except (OSError, ValueError, KeyError, TypeError) as error:
        return result(False, 'Cannot establish background scheduling readiness',
                      error=str(error))


def permit(vault, kind):
    """Used between complete scopes/items; never interrupts in-flight work."""
    if kind not in KINDS:
        raise ValueError('Unknown background maintenance kind')
    decision = assess(vault.cfg)
    save_json(vault.state / ('background-' + kind + '.json'), decision)
    if not decision['allowed']:
        print('BACKGROUND DEFERRED: ' + decision['reason'], flush=True)
    return decision['allowed']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path,
                        default=Path.home() / '.config/project-vault/config.json')
    parser.add_argument('--kind', choices=KINDS, required=True)
    parser.add_argument('--check-only', action='store_true', help='Do not write the observation')
    args = parser.parse_args()
    try:
        config = json.loads(args.config.read_text())
        decision = assess(config)
        if not args.check_only:
            save_json(Path(config['state']) / ('background-' + args.kind + '.json'), decision)
    except (OSError, ValueError, KeyError, TypeError) as error:
        decision = {'at': now(), 'allowed': False,
                    'reason': 'Cannot read or record background scheduling policy',
                    'error': str(error)}
    print(json.dumps(decision, sort_keys=True))
    # ExecCondition exit 1 skips this timer activation without a failed service.
    return 0 if decision['allowed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
