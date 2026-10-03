"""Synthetic export/privacy/lineage tests; no API, real study or PDF execution."""
import hashlib
import copy
import itertools
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
import pandas as pd
from export_public_report import export_report, load_run, BOARD_COLUMNS, _close, implied_realized_summary


def write(path,value):
    Path(path).write_text(json.dumps(value,allow_nan=False))


def split(frame):
    return json.loads(frame.to_json(orient='split',date_format='iso'))


def fixture(base,kind):
    run=base/kind; diag=base/(kind+'_diag'); run.mkdir();diag.mkdir()
    horizons=[1,2,3,5,10,21,42,63,'exp']
    def board(strategy,a,b):
        rows=[]
        for h in horizons:
            row=dict.fromkeys(BOARD_COLUMNS,0.)
            row.update(strategy=strategy,horizon=h,n_a=3,n_b=3,n_candidates_a=3,n_candidates_b=3,
                       n_unavailable_a=0,n_unavailable_b=0,mean_a=a,mean_b=b,difference=a-b,
                       ci_lo=a-b-.01,ci_hi=a-b+.01,estimate_status='available',ci_status='available')
            rows.append(row)
        return split(pd.DataFrame(rows))
    def results(increment):
        return split(pd.DataFrame([{'bucket':'3-6m','entry':'full','otm':.05,'horizon':h,
                                    'stock_net':.01,'incremental_net':increment,'implied_scaled':.05,'realized':.025} for h in horizons for _ in range(3)]))
    grid=pd.DataFrame([dict(zip(['category','bucket','entry','otm','horizon'],v))
                       for v in itertools.product(['union','acquisition_agreement','merger_agreement'],
                         ['1m','2m','3-6m'],['pre','post','full','next_open'],[.03,.05,.1],horizons)])
    grid=grid.assign(n_event=3,n_ordinary=3,theta=.005,ci_lo=-.005,ci_hi=.015,timing_status='SYNTHETIC')
    days=pd.date_range('2024-01-02',periods=3,freq='B')
    daily=pd.DataFrame({'cash':[900000.]*3,'nav':[1000000.,1000001.,1000002.],
                        'traded_stock_gross':[100.,0.,0.]},index=days)
    statuses=['CLOSED','CLOSED','OPEN_AT_WINDOW_END'] if kind=='corrected' else ['CLOSED']*3
    snapshot={'oos_read':False,'runtime_manifest':{'oos_access':False,'sealed_access':False},
              'tables':{'theta_board':board('incremental_net',.02,.015),
                        'official_diff':board('covered_call_net',.03,.025),
                        'results':results(.02),'placebo_results':results(.015),
                        'event_stress':results(.01),'ordinary_stress':results(.004),
                        'sensitivity':split(grid),'events':split(pd.DataFrame({'ticker':['SYN']*(18 if kind=='corrected' else 16)})),
                        'candidate_events':split(pd.DataFrame({'accession_id':['fake']})),
                        'placebo_events':split(pd.DataFrame({'ticker':['SYN']*3}))},
              'portfolio':{'daily':split(daily),'ledger':split(pd.DataFrame({'status':statuses})),
                           'config':{'initial_nav':1000000.}},
              'priced_primary':[{'ticker':'PRIVATE_SENTINEL','legs':{'contract':'O:PRIVATE_SENTINEL','bars':['FORBIDDEN_BAR']}}]}
    path=run/'snapshot.private.json';write(path,snapshot);digest=hashlib.sha256(path.read_bytes()).hexdigest()
    evidence={'kind':'derived_IS_aggregate_evidence_no_raw_quotes','snapshot_sha256':digest,
              'dependence':{'theta':.005,'finite_event_issuers':1,'finite_ordinary_issuers':1,
                            'issuer':{'ci_low':-.005,'ci_high':.015},'overlap_interval':{'ci_low':-.005,'ci_high':.015}},
              'calendar':{'nav_gaps':0},'variants':{'distinct_grid_cells':972},
              'cost_stress_from_existing_results':{'base':{'finite_event':3,'finite_ordinary':3,'event_mean':.02,'ordinary_mean':.015,'theta':.005},
                                                  'doubled':{'finite_event':3,'finite_ordinary':3,'event_mean':.01,'ordinary_mean':.004,'theta':.006}}}
    write(run/'aggregate_evidence.json',evidence)
    write(run/'run_manifest.json',{'status':'COMPLETE','mode':'approved_is_v1' if kind=='original' else 'corrected_is_v2','snapshot_sha256':digest})
    levels=np.r_[1000000.,daily.nav.to_numpy()];returns=np.diff(levels)/levels[:-1]
    cal={'complete_calendar_returns':True,'nav_gaps':0,'annualized_return':float((levels[-1]/levels[0])**(252/3)-1),
         'sharpe_rf0':float(returns.mean()/returns.std(ddof=1)*np.sqrt(252)),
         'annualized_volatility':float(returns.std(ddof=1)*np.sqrt(252)),
         'daily_return_skew_unbiased':-.3,'worst_month_return':-.01,'worst_month':'2024-01',
         'maximum_drawdown':float(np.max(1-levels/np.maximum.accumulate(levels))),
         'turnover':{'traded_stock_gross':{'two_sided_over_mean_nav':float(daily.traded_stock_gross.sum()/daily.nav.mean())}}}
    write(diag/'quote_supplement_summary.json',{'snapshot_sha256':digest,'oos_access':False,'reports':[{'standing_quote_assumption':True,'calendar':cal}]})
    daily.rename_axis('date').to_csv(diag/'quote_nav_standing.private.csv')
    return run,diag


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)
        self.original,self.original_diag=fixture(self.base,'original')
        self.corrected,self.corrected_diag=fixture(self.base,'corrected')
        self.public=self.base/'public'

    def export(self):
        return export_report(self.original,self.corrected,self.original_diag,self.corrected_diag,self.public)

    def causal_fixture(self):
        run=self.base/'causal';diag=self.base/'causal_diag';run.mkdir();diag.mkdir()
        snapshot=json.loads((self.corrected/'snapshot.private.json').read_text())
        snapshot['portfolio']['config']['mode']='causal_portfolio_v3'
        write(run/'snapshot.private.json',snapshot)
        digest=hashlib.sha256((run/'snapshot.private.json').read_bytes()).hexdigest()
        source=hashlib.sha256((self.corrected/'snapshot.private.json').read_bytes()).hexdigest()
        evidence=json.loads((self.corrected/'aggregate_evidence.json').read_text());evidence['snapshot_sha256']=digest
        write(run/'aggregate_evidence.json',evidence)
        write(run/'run_manifest.json',{'status':'COMPLETE','mode':'causal_portfolio_v3','snapshot_sha256':digest,'source_snapshot_sha256':source})
        report=json.loads((self.corrected_diag/'quote_supplement_summary.json').read_text());report['snapshot_sha256']=digest
        write(diag/'quote_supplement_summary.json',report)
        (diag/'quote_nav_standing.private.csv').write_text((self.corrected_diag/'quote_nav_standing.private.csv').read_text())
        return run,diag

    def test_allowlisted_export_retains_all_variants_and_no_private_sentinel(self):
        result=self.export()
        self.assertEqual(result['corrected_open_at_window_end'],1)
        self.assertGreater(result['numeric_checks'],100)
        all_text=''.join(path.read_text() for path in self.public.iterdir())
        self.assertNotIn('PRIVATE_SENTINEL',all_text)
        self.assertNotIn('FORBIDDEN_BAR',all_text)
        self.assertFalse(any('private' in path.name for path in self.public.iterdir()))
        self.assertEqual(len(pd.read_csv(self.public/'corrected_sensitivity.csv')),972)
        implied=pd.read_csv(self.public/'corrected_implied_realized.csv')
        self.assertEqual(len(implied),18)
        self.assertTrue(implied['mean_realized_to_implied_ratio'].eq(.5).all())
        payload=json.loads((self.public/'finalreport_payload.json').read_text())
        self.assertEqual(payload['portfolios']['corrected']['daily_return_skew_unbiased'],-.3)
        self.assertEqual(payload['portfolios']['corrected']['worst_month_return'],-.01)
        self.assertGreater(payload['portfolios']['corrected']['annualized_volatility'],0.)
        self.assertEqual(pd.read_csv(self.public/'corrected_conditional_nav.csv').columns.tolist(),['date','nav'])
        manifest=json.loads((self.public/'publication_manifest.json').read_text())
        for item in manifest['artifacts']:
            self.assertEqual(item['sha256'],hashlib.sha256((self.public/item['file']).read_bytes()).hexdigest())

    def test_incomplete_corrected_run_cannot_export(self):
        path=self.corrected/'run_manifest.json';value=json.loads(path.read_text());value['status']='RUNNING';write(path,value)
        with self.assertRaises(ValueError):self.export()
        self.assertFalse(self.public.exists())

    def test_source_hash_mismatch_cannot_export(self):
        path=self.corrected/'snapshot.private.json';path.write_text(path.read_text()+' ')
        with self.assertRaises(ValueError):self.export()

    def test_other_snapshot_diagnostics_cannot_export(self):
        path=self.corrected_diag/'quote_supplement_summary.json';value=json.loads(path.read_text());value['snapshot_sha256']='wrong';write(path,value)
        with self.assertRaises(ValueError):self.export()

    def test_wrong_version_cash_and_claimed_path_are_rejected(self):
        path=self.corrected_diag/'quote_nav_standing.private.csv';frame=pd.read_csv(path);frame.loc[0,'cash']=123;frame.to_csv(path,index=False)
        with self.assertRaises(ValueError):self.export()

    def test_missing_valuation_cannot_claim_complete_risk(self):
        path=self.corrected_diag/'quote_nav_standing.private.csv';frame=pd.read_csv(path);frame.loc[1,'nav']=np.nan;frame.to_csv(path,index=False)
        with self.assertRaises(ValueError):self.export()

    def test_flat_complete_nav_has_undefined_sharpe_not_zero(self):
        path=self.corrected_diag/'quote_nav_standing.private.csv'
        frame=pd.read_csv(path);frame['nav']=1000000.;frame.to_csv(path,index=False)
        path=self.corrected_diag/'quote_supplement_summary.json';value=json.loads(path.read_text())
        cal=value['reports'][0]['calendar'];cal.update(annualized_return=0.,sharpe_rf0=None,maximum_drawdown=0.,annualized_volatility=0.,daily_return_skew_unbiased=None)
        cal['turnover']['traded_stock_gross']['two_sided_over_mean_nav']=.0001
        write(path,value);self.export()
        metric=json.loads((self.public/'finalreport_payload.json').read_text())['portfolios']['corrected']
        self.assertEqual(metric['status'],'COMPLETE_STANDING_NBBO_ASSUMPTION')
        self.assertIsNone(metric['sharpe'])
        self.assertEqual(metric['sharpe_unavailable_reason'],'ZERO_RETURN_VARIANCE')
        cal['sharpe_rf0']=0.;write(path,value)
        with self.assertRaisesRegex(ValueError,'unavailable Sharpe'):self.export()

    def test_numeric_cost_story_must_match_saved_results(self):
        path=self.corrected/'aggregate_evidence.json';value=json.loads(path.read_text())
        value['cost_stress_from_existing_results']['doubled']['theta']=.5;write(path,value)
        with self.assertRaisesRegex(ValueError,'doubled.theta'):self.export()

    def test_serialization_identity_tolerance_is_fixed_and_bounded(self):
        checks=[]
        _close(-.0195385614-(-.0199681338),.0004295725,'actual_saved_triplet',checks)
        self.assertEqual(checks[0]['absolute_tolerance'],2e-10)
        self.assertEqual(checks[0]['relative_tolerance'],0)
        with self.assertRaises(ValueError):
            _close(-.0195385614-(-.0199681338),.0004295727,'beyond_serialization_bound',checks)

    def test_causal_headline_retains_legacy_and_unchanged_event_evidence(self):
        causal,diag=self.causal_fixture()
        export_report(self.original,self.corrected,self.original_diag,self.corrected_diag,self.public,
                      causal_run=causal,causal_diagnostics=diag)
        payload=json.loads((self.public/'finalreport_payload.json').read_text())
        self.assertEqual(payload['portfolio_headline'],'causal')
        self.assertEqual(set(payload['portfolios']),{'original','corrected','causal'})
        self.assertEqual(set(payload['studies']),{'original','corrected'})
        self.assertFalse((self.public/'causal_theta_board.csv').exists())
        self.assertTrue((self.public/'causal_coverage.json').exists())
        self.assertTrue((self.public/'corrected_conditional_nav.csv').exists())
        self.assertIn('Causal-ledger',payload['capacity_summary'])

    def test_causal_source_cannot_change_event_rows_even_with_fresh_hashes(self):
        causal,diag=self.causal_fixture()
        path=causal/'snapshot.private.json';value=json.loads(path.read_text())
        value['tables']['theta_board']['data'][0][0]='CHANGED_EVENT_EVIDENCE';write(path,value)
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        for name in ('run_manifest.json','aggregate_evidence.json'):
            path=causal/name;value=json.loads(path.read_text());value['snapshot_sha256']=digest;write(path,value)
        with self.assertRaisesRegex(ValueError,'changed the retained V2 event study'):
            export_report(self.original,self.corrected,self.original_diag,self.corrected_diag,self.public,
                          causal_run=causal,causal_diagnostics=diag)

    def test_causal_inputs_must_be_paired(self):
        with self.assertRaisesRegex(ValueError,'supplied together'):
            export_report(self.original,self.corrected,self.original_diag,self.corrected_diag,self.public,causal_run=self.corrected)

    def test_implied_realized_keeps_extreme_ratios_and_missing_counts(self):
        rows=pd.DataFrame({'bucket':['3-6m']*5,'entry':['full']*5,'otm':[.05]*5,'horizon':[21]*5,
                           'implied_scaled':[.1,1e-6,0.,None,.1],'realized':[-.2,1.,1.,1.,None]})
        value={'tables':{'results':split(rows),'placebo_results':split(rows)}}
        result=implied_realized_summary(value)
        row=result[(result.horizon=='21')&(result['sample']=='event')].iloc[0]
        self.assertEqual((row.total_n,row.common_finite_positive_implied_n,row.missing_or_invalid_n),(5,2,3))
        self.assertAlmostEqual(row.mean_realized_to_implied_ratio,500001.)
        self.assertAlmostEqual(row.mean_absolute_realized,.6)
        self.assertAlmostEqual(row.mean_implied_scaled,.0500005)


if __name__=='__main__': unittest.main()
