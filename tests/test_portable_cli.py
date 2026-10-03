"""Synthetic CLI/path/provenance checks only; no fetch or valuation execution."""
from __future__ import annotations
import argparse
import importlib
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from diagnostics_common import load_snapshot, resolve_paths, save_or_match_manifest, private_cache


class TestPortableCLI(unittest.TestCase):
    def fixture(self, root, year='2025'):
        project = Path(root)
        private = project / '.massive_cache' / 'research_runs' / 'original'
        private.mkdir(parents=True)
        snapshot = private / 'snapshot.private.json'
        snapshot.write_text(json.dumps({'portfolio':{'daily':{'index':[year+'-12-31'],'columns':[],'data':[[]]}}}))
        protocol = project / 'RESEARCH_LOG.md'; protocol.write_text('Approved diagnostic conventions.\n')
        return argparse.Namespace(project=project,work_dir=Path('.massive_cache/research_runs/original'),
                                  snapshot=snapshot,protocol_file=Path('RESEARCH_LOG.md'),execute=False)

    def test_relative_paths_and_readonly_protocol(self):
        with tempfile.TemporaryDirectory() as root:
            args = self.fixture(root)
            before = (Path(root) / 'RESEARCH_LOG.md').read_bytes()
            paths = resolve_paths(args)
            self.assertEqual(paths.work_dir, Path(root) / '.massive_cache' / 'research_runs' / 'original')
            load_snapshot(paths)
            self.assertEqual(before, paths.protocol.read_bytes())

    def test_public_work_directory_and_credentials_protocol_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            args = self.fixture(root)
            args.work_dir = Path('outputs')
            with self.assertRaises(ValueError):
                resolve_paths(args)
            args.work_dir = Path('.massive_cache/research_runs/original')
            args.protocol_file = Path('.env')
            with self.assertRaises(ValueError):
                resolve_paths(args)

    def test_reserved_snapshot_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as root:
            args = self.fixture(root, year='2026')
            with self.assertRaises(ValueError):
                load_snapshot(resolve_paths(args))

    def test_old_manifest_bytes_and_protocol_hash_preserved(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'manifest.json'
            original = b'{"requests": [], "source_sha256": "same", "protocol_sha256": "old"}\n'
            path.write_bytes(original)
            prior = save_or_match_manifest(path, {'requests':[],'source_sha256':'same','protocol_sha256':'new'})
            self.assertEqual(prior['protocol_sha256'], 'old')
            self.assertEqual(path.read_bytes(), original)
            with self.assertRaises(ValueError):
                save_or_match_manifest(path, {'requests':[{'changed':True}],'source_sha256':'same','protocol_sha256':'new'})

    def test_imports_never_authenticate_or_request(self):
        with patch('requests.get', side_effect=AssertionError('No requests in import checks')):
            for name in ('fetch_uniform_quotes','fetch_is_factors','fetch_is_volume','run_quote_supplement','run_capacity_diagnostics','data_diagnostics'):
                importlib.import_module(name)
        # auth() must be callable only after an explicit execute decision.
        from fetch_uniform_quotes import auth
        self.assertTrue(callable(auth))

    def test_help_needs_no_project_snapshot_or_credentials(self):
        here = Path(__file__).resolve().parent.parent / "research"
        for name in ('fetch_uniform_quotes.py','fetch_is_factors.py','fetch_is_volume.py',
                     'run_quote_supplement.py','run_capacity_diagnostics.py','data_diagnostics.py'):
            result = subprocess.run([sys.executable,str(here / name),'--help'],capture_output=True,text=True,check=False)
            self.assertEqual(result.returncode,0,result.stderr)
            for flag in ('--project','--work-dir','--snapshot','--protocol-file','--execute'):
                self.assertIn(flag,result.stdout)

    def test_shared_cache_reuses_identical_request_without_network(self):
        from fetch_uniform_quotes import fetch_one
        with tempfile.TemporaryDirectory() as root:
            args = self.fixture(root); paths = resolve_paths(args)
            cache = private_cache(paths,'uniform_fixed_ledger_v1')
            self.assertEqual(cache,Path(root)/'.massive_cache'/'uniform_fixed_ledger_v1')
            item = {'kind':'quote','key':'FAKE|2025-12-31','path':'/v3/quotes/FAKE',
                    'params':{'timestamp.gte':1,'timestamp.lt':2,'limit':64}}
            identity = hashlib.sha256(json.dumps(item,sort_keys=True).encode()).hexdigest()
            dest = cache/(identity+'.json')
            original = json.dumps({'kind':'quote','key':item['key'],'request_hash':identity,
                                   'status':'OK','rows':[]}).encode()
            dest.write_bytes(original)
            with patch('requests.get',side_effect=AssertionError('Cached reuse must perform no HTTP')):
                prior = fetch_one(item,'UNUSED_OFFLINE',cache)
            self.assertEqual(prior['request_hash'],identity)
            self.assertEqual(dest.read_bytes(),original)
            args.work_dir = Path('.massive_cache/research_runs/corrected')
            self.assertEqual(private_cache(resolve_paths(args),'uniform_fixed_ledger_v1'),cache)
            with self.assertRaises(ValueError):
                private_cache(paths,'../public')

    def test_corrupt_cache_identity_fails_without_refetch(self):
        from fetch_uniform_quotes import fetch_one
        with tempfile.TemporaryDirectory() as root:
            paths = resolve_paths(self.fixture(root)); cache = private_cache(paths,'factor_proxy_is_v1')
            item = {'kind':'factor_bars','key':'FAKE','path':'/fake','params':{}}
            identity = hashlib.sha256(json.dumps(item,sort_keys=True).encode()).hexdigest()
            (cache/(identity+'.json')).write_text(json.dumps({'kind':'factor_bars','key':'OTHER',
                                                            'request_hash':identity,'status':'OK','rows':[]}))
            with patch('requests.get',side_effect=AssertionError('No network fallback for identity corruption')):
                with self.assertRaises(ValueError):
                    fetch_one(item,'UNUSED_OFFLINE',cache)

    def test_capacity_stage_is_in_one_command_and_has_no_auth_import(self):
        import data_diagnostics
        import run_capacity_diagnostics
        self.assertEqual(data_diagnostics.SCRIPTS['capacity'],'run_capacity_diagnostics.py')
        self.assertEqual(data_diagnostics.STAGES[-1],'capacity')
        self.assertNotIn('auth',run_capacity_diagnostics.__dict__)


if __name__ == '__main__':
    unittest.main(verbosity=2)
