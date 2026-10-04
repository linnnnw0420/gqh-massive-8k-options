"""Synthetic-only tests. No credentials, real filings, market data or OOS reads."""
from pathlib import Path
import tempfile
import unittest
import re
import numpy as np
import pandas as pd
from event_pipeline import NYSEClock
from research_runtime import SubmissionFence, ScopeViolation, load_runtime
from safe_transport import MassiveSubmission
from submission_variant import FilingDateClock, literal_events, check_window, run_submission

NOTEBOOK=Path(__file__).resolve().parent.parent / 'strategy_defs.py'


class SubmissionVariantTests(unittest.TestCase):
    def setUp(self):
        self.clock=FilingDateClock(NYSEClock.for_window('2024-01-01','2024-12-31').schedule)

    def raw(self,**updates):
        base={'accession_id':'000000000124000001','filing_date':pd.Timestamp('2024-03-28'),
              'tickers':['HD'],'source_tag':'acquisition_agreement','filing_url':'','supporting_text':''}
        base.update(updates)
        return base

    def test_before_filing_chain_and_after_filing_entry_with_holiday(self):
        events=literal_events(pd.DataFrame([self.raw()]),['HD'],self.clock,'2024-12-31')
        row=events.iloc[0]
        self.assertEqual(row.t_pre,pd.Timestamp('2024-03-27'))
        self.assertEqual(row.entry_day,pd.Timestamp('2024-04-01')) # Good Friday closed
        self.assertIsNone(row.actual_sec_acceptance)
        self.assertEqual(row.timing_basis,'FILING_DATE_ONLY_NEXT_SESSION')

    def test_accession_union_is_not_transaction_dedup(self):
        raw=pd.DataFrame([self.raw(),self.raw(source_tag='merger_agreement'),
                          self.raw(accession_id='000000000124000002',filing_date=pd.Timestamp('2024-04-02'))])
        result=literal_events(raw,['HD'],self.clock,'2024-12-31')
        self.assertEqual(len(result),2)
        self.assertEqual(result.iloc[0].source_tags,('acquisition_agreement','merger_agreement'))

    def test_ambiguous_top100_identity_is_logged(self):
        result=literal_events(pd.DataFrame([self.raw(tickers=['HD','LOW'])]),['HD','LOW'],self.clock,'2024-12-31')
        self.assertTrue(result.empty)
        self.assertEqual(result.attrs['classification_audit'].iloc[0].reason,'NO_UNAMBIGUOUS_TOP100_TICKER')

    def test_clock_same_rules_for_ordinary_day_helpers(self):
        stamp=pd.Timestamp('2024-03-28 23:59:59')
        self.assertEqual(self.clock.pre_public_session(stamp),pd.Timestamp('2024-03-27'))
        self.assertEqual(self.clock.public_signal_session(stamp),pd.Timestamp('2024-04-01'))
        self.assertEqual(self.clock.next_public_open(stamp),pd.Timestamp('2024-04-01'))

    def test_contestant_no_sealed_or_partial_oos(self):
        with self.assertRaises(ScopeViolation):check_window('2023-01-01','2023-12-31',role='is')
        with self.assertRaises(ScopeViolation):check_window('2026-01-01','2026-08-31',role='oos')
        with self.assertRaises(ScopeViolation):check_window('2026-01-01','2026-08-30',role='oos',authorized=True)
        with self.assertRaises(ScopeViolation):check_window('2023-01-01','2023-12-31',role='judges')
        check_window('2023-01-01','2023-12-31',role='judges',authorized=True)

    def test_loader_does_not_call_api_and_shared_placebo_clock(self):
        def forbidden(*a,**k):raise AssertionError('No request while loading')
        runtime=load_runtime(NOTEBOOK,forbidden,forbidden,start='2024-01-01',end='2024-12-31',
            warmup_start='2023-12-01',clock=self.clock,window_role='submission',submission_authorized=True)
        ns=runtime.namespace
        self.assertEqual(ns['pre_public_session'](pd.Timestamp('2024-03-28 23:59:59')),pd.Timestamp('2024-03-27'))
        raw=pd.DataFrame([self.raw(ticker_tokens=['HD'])])
        events=literal_events(raw,['HD'],self.clock,'2024-12-31')
        ordinary=ns['sample_placebo'](events,raw,10,'2024-01-01','2024-12-31')
        for row in ordinary.itertuples():
            self.assertLess(row.t_pre,row.filing_date)
            self.assertGreater(row.entry_day,row.filing_date)

    def test_source_failure_precedes_outcome_claim(self):
        claims=[]
        def fail(*a,**k):raise RuntimeError('Synthetic source failure')
        with self.assertRaises(RuntimeError):
            run_submission(NOTEBOOK,'2026-01-01','2026-08-31',fail,fail,
                role='oos',authorized=True,before_market=lambda:claims.append(True))
        self.assertEqual(claims,[])

    def test_generic_fence_rejects_outside_features_and_new_categories(self):
        fence=SubmissionFence('2023-01-01','2023-03-31',None,None,warmup_start='2022-12-01')
        with self.assertRaises(ScopeViolation):
            fence._request('/stocks/filings/8-K/vX/disclosures',{'tertiary_category':'acquisition_completion',
                'filing_date.gte':'2023-01-01','filing_date.lte':'2023-03-31'})
        with self.assertRaises(ScopeViolation):
            fence._request('/v2/aggs/ticker/O:HD230317C00300000/range/1/day/2022-11-30/2023-03-31',{})

    def test_transport_blocks_scope_before_credentials(self):
        fence=SubmissionFence('2024-01-01','2024-12-31',None,None,warmup_start='2023-12-01')
        with tempfile.TemporaryDirectory() as directory:
            transport=MassiveSubmission(directory,fence=fence,offline=True)
            with self.assertRaises(ScopeViolation):
                transport.get('/v2/aggs/ticker/O:HD260116C00300000/range/1/day/2026-01-01/2026-01-02')
            self.assertIsNone(transport._key)
            self.assertEqual(transport.records,[])

    def test_empty_synthetic_is_end_to_end_no_market_requests(self):
        requests=[]
        def empty(path,params=None,**kwargs):
            requests.append((path,params))
            self.assertEqual(path,'/stocks/filings/8-K/vX/disclosures')
            return []
        def forbidden(*a,**k):raise AssertionError('No single-page or market request')
        result=run_submission(NOTEBOOK,'2024-01-01','2024-12-31',forbidden,empty)
        self.assertEqual(len(requests),2)
        self.assertEqual(result.manifest['version'],'LITERAL_TAG_UNION_POST_IS_V4')
        self.assertFalse(result.manifest['original_screened_primary_reproduced'])
        self.assertTrue(result.tables['events'].empty)
        self.assertIn('implied_realized',result.tables)
        self.assertIn('portfolio',result.to_private_snapshot())

    def test_nonempty_synthetic_end_to_end_filing_chain_bars_controls_and_portfolio(self):
        # All records below are constructed here. No network or private cache is
        # consulted. Only six chain requests succeed to keep the120-control test
        # bounded while exercising both finite controls and explicit drops.
        calls=[]
        chain_calls=0
        def synthetic(path,params=None,**kwargs):
            nonlocal chain_calls
            calls.append(path)
            if path=='/stocks/filings/8-K/vX/disclosures':
                return [{'accession_number':'0000000001-24-000001','filing_date':'2024-03-28',
                         'tickers':['HD'],'filing_url':'','supporting_text':'Synthetic filing'}]
            if path=='/v3/reference/options/contracts':
                chain_calls+=1
                if chain_calls>6:return []
                as_of=pd.Timestamp(params['as_of'])
                rows=[]
                for days in (30,60,120):
                    expiry=self.clock.session_on_or_after(as_of+pd.Timedelta(days=days))
                    for strike in (90.,95.,100.,103.,105.,110.):
                        for kind,code in (('call','C'),('put','P')):
                            rows.append({'ticker':f'O:HD{expiry:%y%m%d}{code}{int(strike*1000):08d}',
                                'contract_type':kind,'strike_price':strike,'expiration_date':str(expiry.date()),
                                'shares_per_contract':100})
                return rows
            match=re.fullmatch(r'/v2/aggs/ticker/(O:HD(\d{6})([CP])(\d{8}))/range/1/day/(\d{4}-\d{2}-\d{2})/(\d{4}-\d{2}-\d{2})',path)
            self.assertIsNotNone(match,'Only synthetic disclosure/contract/bar routes may be called')
            _,expiry_code,kind,strike_code,first,last=match.groups()
            expiry=pd.to_datetime(expiry_code,format='%y%m%d')
            strike=int(strike_code)/1000
            rows=[]
            for day in self.clock.sessions[(self.clock.sessions>=first)&(self.clock.sessions<=last)]:
                years=max((expiry-day).days,0)/365
                parity_delta=100.-strike*np.exp(-.04*years)
                premium=max(parity_delta if kind=='C' else -parity_delta,0.)+8.*years
                stamp=int(self.clock.schedule.loc[day,'close'].timestamp()*1000)
                rows.append({'t':stamp,'o':premium,'c':premium,'v':10000})
            return rows
        def no_single(*a,**k):raise AssertionError('No single-page request required')
        result=run_submission(NOTEBOOK,'2024-01-01','2024-12-31',no_single,synthetic)
        self.assertEqual(len(result.tables['events']),1) # two vendor labels, one accession
        self.assertGreater(len(result.priced),0)
        self.assertTrue(any('/options/contracts' in p for p in calls))
        self.assertTrue(any('/aggs/ticker/' in p for p in calls))
        self.assertEqual(set(result.tables['results'].horizon),{1,2,3,5,10,21,42,63,'exp'})
        self.assertGreater(len(result.tables['placebo_results']),0)
        primary=result.tables['results'].query("bucket=='3-6m' and entry=='full' and otm==0.05")
        self.assertTrue(np.isfinite(primary.covered_call_net).all())
        self.assertGreater(len(result.tables['sensitivity']),0)
        self.assertIn('ci_lo',result.tables['theta_board'])
        self.assertEqual(len(result.tables['implied_realized']),9)
        self.assertIn('CLOSED',set(result.portfolio['ledger'].status))
        self.assertEqual(len(result.to_private_snapshot()['priced_primary']),1)


if __name__=='__main__':unittest.main()
