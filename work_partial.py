"""Declared partial Work selection; never describe it as complete Work coverage."""

from hashlib import sha256
import json
from pathlib import Path

from vault import Vault, VaultError


TAG = 'project-Work-readable-partial'


def prepare(config: Path, base: Path, policy_path: Path) -> tuple[list[str], dict]:
    if base.name != 'Work' or not base.is_dir() or not policy_path.is_absolute():
        raise VaultError('Partial Work policy has an invalid root or path')
    policy_bytes = policy_path.read_bytes()
    policy = json.loads(policy_bytes)
    if (policy.get('schema') != 'project-vault.work-readable-partial.policy-v1' or
            policy.get('base') != str(base) or
            policy.get('original_scope') != 'project-Work' or
            policy.get('original_scope_state') != 'incomplete'):
        raise VaultError('Partial Work policy identity differs')
    error_roots = policy['excluded_error_roots']
    active_roots = policy.get('excluded_active_roots', {})
    prefixes = policy['excluded_name_prefixes']
    included: list[str] = []
    omitted: dict[str, str] = {}
    children = sorted(base.iterdir(), key=lambda path: path.name)
    for child in children:
        if child.name in error_roots:
            omitted[child.name] = 'observed backup errors: ' + ', '.join(error_roots[child.name])
        elif child.name in active_roots:
            omitted[child.name] = active_roots[child.name]
        elif (prefix := next((name for name in prefixes if child.name.startswith(name)), None)) is not None:
            omitted[child.name] = prefixes[prefix]
        else:
            included.append(str(child))
    if policy['reference_source'] not in included or len(included) + len(omitted) != len(children):
        raise VaultError('Partial Work selection omitted its reference source')
    scoped = Vault(config)
    try:
        scoped.cfg.update(project_roots=[], additional_paths=included, snapshot_tag=TAG)
        roots, mapping = scoped.sources()
    finally:
        scoped.db.close()
    outside = [path for path in roots if not Path(path).is_relative_to(base)]
    if not set(outside).issubset(set(policy['allowed_discovered_roots'])):
        raise VaultError('Undeclared outside-Work worktree discovery')
    if any(Path(path).is_relative_to(base) and
           Path(path).relative_to(base).parts[0] in omitted for path in roots):
        raise VaultError('Omitted Work root was reintroduced by Git discovery')
    manifest = {
        'schema': 'project-vault.work-readable-partial.manifest-v1',
        'scope': TAG,
        'state': 'PLANNED_PARTIAL_SCOPE',
        'original_scope': 'project-Work',
        'original_scope_remains': 'INCOMPLETE',
        'policy_sha256': sha256(policy_bytes).hexdigest(),
        'policy_diagnostic_sha256': policy['diagnostic_sha256'],
        'top_level_work_names': [path.name for path in children],
        'included_top_level_paths': included,
        'omitted_top_level_names_and_reasons': omitted,
        'actual_vault_roots': roots,
        'outside_work_linked_roots': outside,
        'source_mapping_sha256': sha256(json.dumps(mapping, sort_keys=True).encode()).hexdigest(),
        'scheduled_verification': 'snapshot saved and repository metadata checked; no scheduled full restore',
        'coverage_limits': [
            'Intentionally partial readable Work selection only; not a complete Work backup.',
            'Omitted Work roots remain local and their backup coverage is not asserted here.',
            'No source or evidence is deleted or offloaded by the scheduled backup.',
        ],
    }
    return included, manifest


def check_saved_map(vault: Vault, snapshot: str, manifest: dict) -> None:
    path = vault.root / 'Recovery/source-maps' / f'{snapshot}.json'
    source_map = json.loads(path.read_text(encoding='utf-8'))
    if (source_map.get('scope') != TAG or
            source_map.get('snapshot') != snapshot or
            source_map.get('roots') != manifest['actual_vault_roots'] or
            sha256(json.dumps(source_map.get('mapping'), sort_keys=True).encode()).hexdigest()
            != manifest['source_mapping_sha256']):
        raise VaultError('Partial Work source map differs from declared selection')
