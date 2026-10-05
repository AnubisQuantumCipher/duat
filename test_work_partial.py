import json
from pathlib import Path
import tempfile
import unittest

from vault import Vault, VaultError
from work_partial import TAG, check_saved_map, prepare


class PartialWorkTests(unittest.TestCase):
    def test_declared_selection_preserves_incomplete_broad_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            work = home / 'Work'
            (work / 'source').mkdir(parents=True)
            (work / 'source' / 'proof.txt').write_text('source')
            (work / 'excluded').mkdir()
            config = home / 'config.json'
            config.write_text(json.dumps(dict(home=str(home), state=str(home/'state'),
                mount=str(home/'device'), root=str(home/'device/TryOmarchy'),
                vault_id='test', require_ifuse_mount=False, reserve_bytes=0,
                project_roots=[], additional_paths=[])))
            policy = home / 'policy.json'
            policy.write_text(json.dumps(dict(schema='project-vault.work-readable-partial.policy-v1',
                base=str(work), original_scope='project-Work', original_scope_state='incomplete',
                reference_source=str(work/'source'), diagnostic_sha256='fixture',
                excluded_error_roots={'excluded':['permission_denied']},
                excluded_name_prefixes={}, allowed_discovered_roots=[])))
            included, manifest = prepare(config, work, policy)
            self.assertEqual(included, [str(work/'source')])
            self.assertEqual(manifest['original_scope_remains'], 'INCOMPLETE')
            self.assertEqual(manifest['omitted_top_level_names_and_reasons']['excluded'],
                             'observed backup errors: permission_denied')
            vault = Vault(config)
            try:
                vault.initialize()
                vault.cfg.update(project_roots=[], additional_paths=included, snapshot_tag=TAG)
                snapshot = vault.backup()
                check_saved_map(vault, snapshot, manifest)
                manifest['actual_vault_roots'] = []
                with self.assertRaises(VaultError):
                    check_saved_map(vault, snapshot, manifest)
            finally:
                vault.db.close()


if __name__ == '__main__':
    unittest.main()
