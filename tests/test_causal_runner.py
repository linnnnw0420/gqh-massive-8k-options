"""Focused replay-boundary tests with synthetic marks and a mocked simulator."""
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
import reproduce_causal_portfolio as runner

HERE=Path(__file__).resolve().parent
SOURCE=HERE.parent/'gator-quant-hacks-8k-options-challenge.ipynb'
PROTOCOL=HERE.parent/'reports/causal_portfolio_protocol_v3.md'
CORRECTION=HERE.parent/'research/correction_execution_v2.json'


def names():
    return {'Leg':lambda ticker,kind,strike,bars:SimpleNamespace(ticker=ticker,kind=kind,strike=strike,bars=bars),
            'PricedEvent':lambda **kwargs:SimpleNamespace(**kwargs),'SECTOR_BY_TICKER':{'SYN':'Synthetic'}}


def priced_item():
    bars={'columns':['open','close','volume'],'index':['2023-12-29','2024-01-02'],
          'data':[[1.,1.,10.],[None,None,0.]]}
    return {'ticker':'SYN','event_date':'2024-01-02','t_pre':'2023-12-29','t_0':'2024-01-02',
            'entry_day':'2024-01-02','accepted_at':'2024-01-02 08:00:00','accession_number':'PRIVATE_SENTINEL',
            'source_tags':['acquisition_agreement'],'bucket':'3-6m','expiry':'2026-01-16','expiry_session':'2026-01-16',
            'spot_pre':100.,'strikes':{'K':100.},'observation_end':'2025-12-31',
            'legs':{'C_K':{'ticker':'O:PRIVATE_SENTINEL','kind':'call','strike':100.,'bars':bars}}}


class ReconstructionTests(unittest.TestCase):
    def test_feature_history_and_future_expiry_allowed_but_missing_marks_preserved(self):
        item=priced_item();before=copy.deepcopy(item)
        result=runner.reconstruct_priced({'priced_primary':[item]},names())[0]
        self.assertEqual(result.expiry,pd.Timestamp('2026-01-16'))
        self.assertEqual(result.t_pre,pd.Timestamp('2023-12-29'))
        self.assertTrue(pd.isna(result.legs['C_K'].bars.close.iloc[1]))
        self.assertEqual(item,before)

    def test_event_or_price_scope_cannot_follow_future_expiry(self):
        for key,value in [('event_date','2026-01-02'),('entry_day','2026-01-02'),
                          ('observation_end','2026-01-02'),('t_pre','2023-08-01'),
                          ('accepted_at','2026-01-02 08:00:00')]:
            item=priced_item();item[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):
                runner.reconstruct_priced({'priced_primary':[item]},names())
        item=priced_item();item['legs']['C_K']['bars']['index'][-1]='2026-01-02'
        with self.assertRaises(ValueError):runner.reconstruct_priced({'priced_primary':[item]},names())

    def test_protocol_hash_is_exactly_pinned(self):
        self.assertEqual(runner.sha(PROTOCOL),runner.FROZEN_V3_PROTOCOL_SHA256)


class RunnerBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.project=Path(self.tmp.name);self.input_dir=self.project/'.massive_cache'/'v2';self.input_dir.mkdir(parents=True)
        self.input=self.input_dir/'snapshot.private.json';self.output=self.project/'.massive_cache'/'v3'
        self.snapshot={'oos_read':False,'runtime_manifest':{'event_mode':'corrected_is_v2','oos_access':False,'sealed_access':False},
                       'tables':{'private_marker':{'columns':['unchanged'],'index':[0],'data':[['PRIVATE_SENTINEL']]}},
                       'portfolio':{},'priced_primary':[priced_item()]}
        self.persist()

    def persist(self):
        self.input.write_text(json.dumps(self.snapshot))
        self.manifest={'status':'COMPLETE','mode':'corrected_is_v2','snapshot_sha256':runner.sha(self.input),
                       'runtime':{'event_mode':'corrected_is_v2','oos_access':False,'sealed_access':False}}
        (self.input_dir/'run_manifest.json').write_text(json.dumps(self.manifest))

    def call_runner(self):
        return runner.run(self.project,SOURCE,self.input,CORRECTION,PROTOCOL,self.output)

    def test_incomplete_or_wrong_hash_parent_rejected_before_simulation(self):
        for key,value in [('status','STARTED'),('snapshot_sha256','wrong'),('mode','approved_is_v1')]:
            self.persist();self.manifest[key]=value
            (self.input_dir/'run_manifest.json').write_text(json.dumps(self.manifest))
            with patch.object(runner,'simulate_causal_portfolio') as simulate:
                with self.subTest(key=key),self.assertRaises(ValueError):self.call_runner()
                simulate.assert_not_called()

    def test_reserved_access_flags_in_either_record_are_rejected(self):
        for where,key in [('snapshot','oos_access'),('snapshot','sealed_access'),('manifest','oos_access'),('manifest','sealed_access')]:
            self.snapshot['runtime_manifest'].update(oos_access=False,sealed_access=False);self.persist()
            if where=='snapshot':
                self.snapshot['runtime_manifest'][key]=True;self.persist()
            else:
                self.manifest['runtime'][key]=True;(self.input_dir/'run_manifest.json').write_text(json.dumps(self.manifest))
            with self.subTest(where=where,key=key),self.assertRaises(ValueError):self.call_runner()

    def test_unknown_cash_stays_null_and_private_data_never_reaches_stdout(self):
        days=pd.to_datetime(['2024-01-02','2024-01-03'])
        portfolio={'daily':pd.DataFrame({'cash':[np.nan,np.nan],'nav':[np.nan,np.nan]},index=days),
                   'ledger':pd.DataFrame({'status':['UNPRICED_EXECUTION'],'contracts':[1]}),'config':{'initial_nav':1e6}}
        runtime=SimpleNamespace(namespace=names(),clock=SimpleNamespace(sessions=days))
        capture=io.StringIO()
        with patch.object(runner,'load_runtime',return_value=runtime) as loader, \
             patch.object(runner,'simulate_causal_portfolio',return_value=portfolio), \
             patch.object(runner,'summarize_existing_is',return_value={'calendar':{'nav_gaps':2}}), \
             patch('sys.stdout',capture):
            self.call_runner()
        revised=json.loads((self.output/'snapshot.private.json').read_text())
        manifest=json.loads((self.output/'run_manifest.json').read_text())
        self.assertEqual(revised['tables'],self.snapshot['tables'])
        self.assertTrue(all(row==[None,None] for row in revised['portfolio']['daily']['data']))
        self.assertEqual(revised['portfolio_runtime_manifest']['status'],'COMPLETE')
        self.assertNotIn('snapshot_sha256',revised['portfolio_runtime_manifest'])
        self.assertEqual(manifest['source_snapshot_sha256'],runner.sha(self.input))
        self.assertEqual(manifest['snapshot_sha256'],runner.sha(self.output/'snapshot.private.json'))
        self.assertNotIn('PRIVATE_SENTINEL',capture.getvalue())
        with self.assertRaises(AssertionError):loader.call_args.args[1]('/any-api')

    def test_licensed_snapshot_output_cannot_leave_private_cache(self):
        with self.assertRaises(ValueError):
            runner.run(self.project,SOURCE,self.input,CORRECTION,PROTOCOL,self.project/'public')


if __name__=='__main__':unittest.main()
