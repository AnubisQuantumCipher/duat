"""Synthetic fixture integration and refusal checks. No production configuration is loaded."""
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import bench
from vault import Vault, VaultError

class BenchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='duat-bench-test-')
        self.root=Path(self.tmp.name);self.config=self.root/'config.json'
        self.config.write_text(json.dumps({'home':str(self.root),'state':str(self.root/'state'),
            'mount':str(self.root/'device'),'root':str(self.root/'device/vault'),
            'vault_id':'fixture','require_ifuse_mount':False,'reserve_bytes':0,
            'local_reserve_bytes':0,'project_roots':[],'additional_paths':[]}))
        self.v=Vault(self.config);self.v.root.mkdir(parents=True)
        (self.v.root/'.vault-id').write_text('fixture')
        # Deliberately invalid production repo and credential: benchmark must never open either.
        (self.v.root/'Repository').mkdir();(self.v.root/'Repository/sentinel').write_text('production sentinel')
        (self.v.state/'repository-password').write_text('production-credential-sentinel')
    def tearDown(self):
        self.v.db.close();self.tmp.cleanup()
    def engine(self):
        opts=bench.validate_options(1,3,'compressible')
        identity=bench.reserve_request(self.config,opts)
        return bench.Bench(self.v,identity,opts)
    def test_round_trip_isolated_and_exports_match(self):
        engine=self.engine();report=engine.execute()
        self.assertEqual(report['state'],'passed',report.get('error'))
        self.assertTrue(all(v=='passed' for v in report['integrity'].values()))
        self.assertEqual((self.v.root/'Repository/sentinel').read_text(),'production sentinel')
        self.assertEqual(list((self.v.root/'Repository').iterdir()),[self.v.root/'Repository/sentinel'])
        self.assertEqual((self.v.state/'repository-password').read_text(),'production-credential-sentinel')
        self.assertTrue((engine.work/'source').is_dir())
        self.assertIsNotNone(report['round_trip_elapsed_s']['value'])
        self.assertEqual(report['committed_object_bytes']['status'],'unavailable')
        self.assertEqual(report['wire_bytes']['status'],'unavailable')
        self.assertEqual(report['backend'],'local-fixture')
        self.assertEqual(hashlib.sha256((engine.folder/'samples.csv').read_bytes()).hexdigest(),report['samples_sha256'])
        with (engine.folder/'samples.csv').open() as f:rows=list(csv.DictReader(f))
        self.assertTrue(rows);self.assertTrue(all(float(r['sample_interval_s'])>=0 for r in rows))
        exported=(engine.folder/'report.json').read_text()+(engine.folder/'samples.csv').read_text()+(engine.folder/'card.html').read_text()
        self.assertNotIn(str(self.root),exported)
        self.assertNotIn('production-credential-sentinel',exported)
        self.assertNotIn((engine.work/'password').read_text(),exported)
        self.assertEqual(bench.read_report(self.v.state,engine.identity)['freshness'],'historical')
    def test_low_space_refuses_without_synthetic_or_archive_writes(self):
        engine=self.engine()
        with patch('bench.shutil.disk_usage',return_value=SimpleNamespace(free=0)):
            report=engine.execute()
        self.assertEqual(report['state'],'refused')
        self.assertFalse(engine.work.exists());self.assertFalse((self.v.root/'Bench').exists())
        self.assertIsNone(report['round_trip_elapsed_s']['value'])
    def test_offline_refuses_before_writing_mount(self):
        engine=self.engine();self.v.cfg['require_ifuse_mount']=True
        report=engine.execute();self.assertEqual(report['state'],'refused')
        self.assertFalse((self.v.root/'Bench').exists())
    def test_symlink_archive_parent_refused(self):
        other=self.root/'unrelated';other.mkdir();(self.v.root/'Bench').symlink_to(other)
        report=self.engine().execute()
        self.assertEqual(report['state'],'failed');self.assertEqual(list(other.iterdir()),[])
    def test_production_lock_refuses(self):
        engine=self.engine()
        with self.v.locked():report=engine.execute()
        self.assertEqual(report['state'],'refused');self.assertFalse((self.v.root/'Bench').exists())
    def test_cancel_preserves_source_without_claiming_recovery(self):
        engine=self.engine();original=engine.generate
        def cancel():
            result=original();(engine.folder/'cancel').touch();return result
        with patch.object(engine,'generate',side_effect=cancel):report=engine.execute()
        self.assertEqual(report['state'],'cancelled');self.assertTrue((engine.work/'source').exists())
        self.assertIsNone(report['round_trip_elapsed_s']['value'])
    def test_corrupt_readback_never_passes(self):
        engine=self.engine();copy=engine.copy_payload
        def corrupt(source,target):
            copy(source,target);next(target.iterdir()).write_bytes(b'corrupted')
        with patch.object(engine,'copy_payload',side_effect=corrupt):report=engine.execute()
        self.assertEqual(report['state'],'failed');self.assertIsNone(report['round_trip_elapsed_s']['value'])
        self.assertTrue((engine.work/'source').exists())
        self.assertEqual(report['integrity']['transport_readback'],'failed')
        self.assertEqual(report['integrity']['full_manifest'],'not-run')
    def test_reserve_loss_during_run_preserves_source(self):
        engine=self.engine();original=engine.generate
        def drop_reserve():
            result=original();self.v.cfg['local_reserve_bytes']=shutil.disk_usage(self.v.state).total
            return result
        with patch.object(engine,'generate',side_effect=drop_reserve):report=engine.execute()
        self.assertEqual(report['state'],'failed')
        self.assertIsNone(report['round_trip_elapsed_s']['value'])
        self.assertTrue((engine.work/'source').exists())
    def test_worker_cannot_overwrite_existing_run(self):
        opts=bench.validate_options(1,1,'compressible');identity=bench.reserve_request(self.config,opts)
        folder=bench.runs_root(self.v.state)/identity
        (folder/'started').write_text('already claimed')
        (folder/'report.json').write_text('{"state":"passed"}')
        before=(folder/'report.json').read_bytes()
        with self.assertRaises(VaultError):bench.worker(self.config,identity)
        self.assertEqual((folder/'report.json').read_bytes(),before)
    def test_window_requires_full_duration_and_counters_cannot_regress(self):
        rates=bench.Rates(0)
        self.assertEqual(rates.update(1,100)['peak']['status'],'unavailable')
        r=rates.update(5,500)
        self.assertEqual(r['peak']['value'],100);self.assertEqual(r['peak']['actual_window_s'],5)
        with self.assertRaises(VaultError):rates.update(6,1)
    def test_option_and_export_boundaries(self):
        for value in (True,0,-1,1025,'16'):
            with self.assertRaises(VaultError):bench.validate_options(value)
        with self.assertRaises(VaultError):bench.read_report(self.v.state,'../../config')

if __name__=='__main__':unittest.main()
