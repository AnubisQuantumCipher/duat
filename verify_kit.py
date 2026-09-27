#!/usr/bin/env python3
"""Verify recovery-kit file hashes without importing or executing kit modules."""
import argparse
import hashlib
import json
from pathlib import Path

def verify(root):
    root = Path(root).resolve()
    manifest = json.loads((root / 'manifest.json').read_text())
    failures = []
    for name, expected in manifest['files'].items():
        relative = Path(name)
        file = root / relative
        if relative.is_absolute() or '..' in relative.parts or not file.resolve().is_relative_to(root) or file.is_symlink():
            failures.append({'path': name, 'error': 'Unsafe path'})
            continue
        try:
            if hashlib.sha256(file.read_bytes()).hexdigest() != expected:
                failures.append({'path': name, 'error': 'SHA256 mismatch'})
        except OSError as error:
            failures.append({'path': name, 'error': str(error)})
    return {'state': 'failed' if failures else 'passed', 'kit': manifest['id'],
            'files_checked': len(manifest['files']), 'failures': failures,
            'boundary': 'Hash consistency against this manifest, not authenticity or application recovery.'}

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('kit', type=Path)
    result = verify(p.parse_args().kit)
    print(json.dumps(result, indent=2))
    raise SystemExit(result['state'] != 'passed')
