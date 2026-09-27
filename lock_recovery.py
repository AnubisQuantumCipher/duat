"""Only recover locks belonging to absent processes on this same host."""
import json
import os
import socket
from pathlib import Path
from vault import VaultError

def recover(vault):
    # Caller holds the local operation lock. Never force-unlock a foreign host.
    locks = vault.run('list', 'locks', capture=True).splitlines()
    stale = []
    for identity in locks:
        if len(identity) != 64 or any(c not in '0123456789abcdef' for c in identity):
            raise VaultError('Unexpected repository lock listing; manual review required.')
        record = json.loads(vault.run('--no-lock', 'cat', 'lock', identity, capture=True))
        pid = record.get('pid')
        if record.get('hostname') != socket.gethostname() or not isinstance(pid, int) or pid <= 0:
            raise VaultError('Another repository owner may be active; foreign or unknown lock retained.')
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            stale.append(identity)
        except PermissionError:
            raise VaultError('Another repository owner may be active; uninspectable process retained.')
        else:
            raise VaultError('Another repository owner is active; lock retained.')
    if stale:
        vault.run('unlock')  # restic also checks staleness; never --remove-all.
        vault.event('stale-lock-recovery', {'locks': stale, 'host': socket.gethostname()})
    return stale
