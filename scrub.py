#!/usr/bin/env python3
"""Record each full-data check attempt separately from its last successful run."""
from pathlib import Path
import json
import subprocess
from vault import Vault, VaultError, save_json, now

def scrub(v):
    path = v.state / 'scrub.json'
    previous = json.loads(path.read_text()) if path.exists() else {}
    last_success = previous.get('time') if previous.get('state') == 'passed' else previous.get('last_success')
    try:
        v.online()
        with v.locked():
            v.run('check', '--read-data')
        receipt = {'state': 'passed', 'time': now(), 'method': 'restic check --read-data'}
        receipt['last_success'] = receipt['time']
    except (VaultError, OSError) as error:
        waiting = getattr(error, 'exit_code', None) == 11 or any(
            x in str(error) for x in ('offline', 'Another vault', 'queued until'))
        receipt = {'state': 'waiting' if waiting else 'failed', 'time': now(),
                   'reason': str(error), 'last_success': last_success,
                   'method': 'restic check --read-data'}
    save_json(path, receipt)
    try:
        v.online()
        save_json(v.root / 'Recovery/scrub.json', receipt)
    except (VaultError, OSError):
        pass
    return receipt

def main():
    v = Vault(Path.home() / '.config/project-vault/config.json')
    result = scrub(v)
    print(json.dumps(result, indent=2))
    if result['state'] == 'failed':
        subprocess.run(['notify-send', 'Project Vault integrity check needs attention', result['reason']], check=False)
        raise SystemExit(1)

if __name__ == '__main__':
    main()
