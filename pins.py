"""Serialize pin edits with the final local retirement window."""
import contextlib
import fcntl
import json
from pathlib import Path
from vault import save_json

@contextlib.contextmanager
def locked(state):
    with (state / 'pins.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield

def set_pin(vault, path, protect=True):
    selected = str(Path(path).expanduser().resolve())
    with locked(vault.state):
        file = vault.state / 'pinned-paths.json'
        current = json.loads(file.read_text()) if file.exists() else []
        if protect:
            current.append(selected)
        else:
            current = [p for p in current if p != selected]
        save_json(file, sorted(set(current)))
    return {'pin' if protect else 'unpin': selected,
            'boundary': 'Pins protect future retirement; already completed offloads require retrieval.'}
