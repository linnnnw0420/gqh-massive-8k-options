"""Independent synthetic tests: no API, notebook, prices, OOS or credentials.

Math and quote-layer tests use only the separately reviewed pure module. A missing
module is explicitly skipped, not reported as a passed implementation test. Fixtures
use invented contract labels and premiums rather than real market observations.
"""
import copy
import ast
import importlib.util
import math
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


SECOND = 1_000_000_000
CUTOFF = 1_000 * SECOND
SESSION_START = 100 * SECOND
MAX_AGE = 60 * SECOND


def qrow(t, bid=4.0, ask=6.0, bid_size=2, ask_size=3, sequence=1,
         source_contract='SYNTHETIC_PUT', **extra):
    return dict(sip_timestamp=t, bid_price=bid, ask_price=ask,
                bid_size=bid_size, ask_size=ask_size, sequence_number=sequence,
                source_contract=source_contract, **extra)


def quote_policy_fixtures():
    """Expected policy outcomes, deliberately independent of engine internals."""
    return [
        dict(name='future_tick_excluded',
             rows=[qrow(CUTOFF-20*SECOND), qrow(CUTOFF+SECOND,bid=90,ask=92)],
             expected='REJECTED_BOUNDS'),
        dict(name='exact_cutoff_is_end_exclusive',
             rows=[qrow(CUTOFF-SECOND),qrow(CUTOFF,bid=90,ask=92)],
             expected='REJECTED_BOUNDS'),
        dict(name='age_exact_limit_is_available',
             rows=[qrow(CUTOFF-MAX_AGE)], expected='OK',
             expected_timestamp=CUTOFF-MAX_AGE, expected_mid=5.0),
        dict(name='age_above_limit_is_missing',
             rows=[qrow(CUTOFF-MAX_AGE-1)], expected='STALE'),
        dict(name='invalid_latest_must_not_fallback',
             rows=[qrow(CUTOFF-10*SECOND),qrow(CUTOFF-SECOND,bid=6,ask=4)],
             expected='INVALID'),
        dict(name='zero_latest_size_must_not_fallback',
             rows=[qrow(CUTOFF-10*SECOND),qrow(CUTOFF-SECOND,bid_size=0)],
             expected='INVALID'),
        dict(name='nan_latest_price_must_not_fallback',
             rows=[qrow(CUTOFF-10*SECOND),qrow(CUTOFF-SECOND,ask=float('nan'))],
             expected='INVALID'),
        dict(name='quiet_interval_standing_quote_is_stale_not_absent',
             # A broader same-session lookup identifies a standing state even
             # though the last 15-second illustrative subwindow has no updates.
             rows=[qrow(CUTOFF-70*SECOND)], expected='STALE'),
        dict(name='previous_session_must_not_carry',
             rows=[qrow(SESSION_START-1)], expected='REJECTED_BOUNDS'),
        dict(name='conflicting_timestamp_tie_requires_sequence',
             rows=[qrow(CUTOFF-SECOND,sequence=None),
                   qrow(CUTOFF-SECOND,bid=7,ask=9,sequence=None)],
             expected='AMBIGUOUS'),
        dict(name='ordered_timestamp_tie_uses_latest_sequence',
             rows=[qrow(CUTOFF-SECOND,sequence=8),
                   qrow(CUTOFF-SECOND,bid=7,ask=9,sequence=9)],
             expected='OK',expected_timestamp=CUTOFF-SECOND,expected_mid=8.0),
        dict(name='bool_sequence_is_not_ordering_evidence',
             rows=[qrow(CUTOFF-SECOND,sequence=True),
                   qrow(CUTOFF-SECOND,bid=7,ask=9,sequence=2)],
             expected='AMBIGUOUS'),
    ]


def terminal_bundle(S, K=100.0, U=105.0, multiplier=100.0):
    return multiplier * (K+max(S-K,0)-max(K-S,0)-max(S-U,0))


def exit_credit_with_original_haircut(S, K=100.0, U=105.0,
                                      multiplier=100.0, haircut=.05):
    premiums = max(S-K,0)+max(K-S,0)+max(S-U,0)
    return terminal_bundle(S,K,U,multiplier)-haircut*multiplier*premiums


class IndependentMathTests(unittest.TestCase):
    def test_common_expiry_intrinsic_identity(self):
        for S in (0,1,50,99,100,101,105,110,1000):
            with self.subTest(S=S):
                self.assertEqual(terminal_bundle(S),100*min(S,105))

    def test_zero_stock_exit_cost_exceeds_entry_capital_loss_proxy(self):
        # S_entry=100, ATM call=10, put=10, sold call=5. These are invented.
        original_debit=100*(100-5)+.05*100*(10+10+5)
        pnl=exit_credit_with_original_haircut(0)-original_debit
        self.assertEqual(original_debit,9625)
        self.assertEqual(pnl,-10125)
        self.assertLess(pnl,-original_debit)

    def test_premium_exit_haircut_has_no_debit_only_global_loss_bound(self):
        losses=[-exit_credit_with_original_haircut(S) for S in (1e4,1e5,1e6)]
        self.assertTrue(losses[0]<losses[1]<losses[2])
        self.assertGreater(losses[-1],1e6)
        self.assertEqual(terminal_bundle(1e6),10500)

    def test_position_value_is_not_net_delta_notional(self):
        marked_value=100*(100-5)
        net_delta_notional=100*100*(1-.8)
        self.assertNotAlmostEqual(marked_value,net_delta_notional)

    def test_downside_delta_bound_has_no_put_protection(self):
        deltas=[100*(1-call_delta) for call_delta in (0,.2,.8,1)]
        self.assertEqual(deltas[0],100)
        self.assertEqual(deltas[-1],0)
        self.assertTrue(all(0<=x<=100 for x in deltas))

    def test_half_day_and_DST_cutoffs(self):
        ny=ZoneInfo('America/New_York')
        expected=[('2025-03-21',16,'2025-03-21T20:00:00+00:00'),
                  ('2025-06-04',16,'2025-06-04T20:00:00+00:00'),
                  ('2025-11-28',13,'2025-11-28T18:00:00+00:00'),
                  ('2025-01-02',16,'2025-01-02T21:00:00+00:00')]
        for date,hour,target in expected:
            stamp=datetime.fromisoformat(date).replace(tzinfo=ny)+timedelta(hours=hour)
            self.assertEqual(stamp.astimezone(timezone.utc).isoformat(),target)

    def test_parity_bond_uses_declared_time_rate(self):
        K,r,T=100,.04,.5
        value=K*math.exp(-r*T)
        self.assertLess(value,K)
        self.assertEqual(K*math.exp(-r*0),K)


def load_pure_quote_layer():
    """Load only the separately reviewed pure module, never the fetcher/notebook."""
    path=Path(__file__).with_name('quote_valuation.py')
    if not path.exists():
        return None
    source=path.read_text(encoding='utf-8')
    tree=ast.parse(source)
    allowed={'__future__','math','collections','numpy','pandas'}
    for node in tree.body:
        if isinstance(node,(ast.Import,ast.ImportFrom)):
            imported=[x.name.split('.')[0] for x in node.names] if isinstance(node,ast.Import) else [node.module.split('.')[0]]
            if not set(imported)<=allowed:
                raise RuntimeError('Unexpected import in pure quote layer: '+repr(imported))
    forbidden={'api_get','api_get_all','load_api_key','auth','fetch_one','simulate_portfolio',
               'price_events','price_event','run_study','evaluate','option_bars','exec','eval','open'}
    calls={node.func.id for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,ast.Name)}
    if calls&forbidden:
        raise RuntimeError('Data/strategy execution forbidden in pure quote layer')
    spec=importlib.util.spec_from_file_location('reviewed_pure_quote_layer',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


LAYER=load_pure_quote_layer()


def select_quote_adapter(rows,expected_contract,cutoff_ns,session_start_ns,max_age_ns):
    # Real responses are requested descending and contain no contract field;
    # contract provenance is tested separately at revalue_fixed_ledger's input.
    ordered=sorted(copy.deepcopy(rows),key=lambda x:x['sip_timestamp'],reverse=True)
    answer=LAYER.latest_quote_state(ordered,session_start_ns,cutoff_ns,max_age_ns/SECOND)
    status=answer['status']
    mapping={'VALID_INDICATIVE_QUOTE':'OK','OUT_OF_INTERVAL_RESPONSE':'REJECTED_BOUNDS',
             'STALE_LATEST_QUOTE_STATE':'STALE','NO_SAME_SESSION_QUOTE':'MISSING',
             'INVALID_LATEST_QUOTE_STATE':'INVALID','INVALID_QUOTE_SCHEMA':'INVALID',
             'UNRESOLVED_SEQUENCE_TIE':'AMBIGUOUS','CONFLICTING_LATEST_STATE':'AMBIGUOUS'}
    return {'status':mapping.get(status,status),'mid':answer.get('mid'),
            'quote_timestamp':answer.get('sip_timestamp')}


SELECT_QUOTE_ADAPTER=select_quote_adapter if LAYER is not None else None


class QuotePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if SELECT_QUOTE_ADAPTER is None:
            raise unittest.SkipTest('Pending root pure-function interface; implementation not tested.')

    def test_policy_fixtures_and_no_input_mutation(self):
        for case in quote_policy_fixtures():
            with self.subTest(case=case['name']):
                rows=case['rows']
                before=copy.deepcopy(rows)
                answer=SELECT_QUOTE_ADAPTER(rows,'SYNTHETIC_PUT',CUTOFF,
                                             SESSION_START,MAX_AGE)
                self.assertEqual(answer['status'],case['expected'])
                if case['expected']=='OK':
                    self.assertEqual(answer['quote_timestamp'],case['expected_timestamp'])
                    self.assertEqual(answer['mid'],case['expected_mid'])
                # NaN is not equal to itself: inspect a normalized repr instead.
                self.assertEqual(repr(rows),repr(before))

    def test_malformed_timestamp_cannot_be_dropped_to_resurrect_state(self):
        result=LAYER.latest_quote_state([qrow(None),qrow(CUTOFF-SECOND)],SESSION_START,CUTOFF)
        self.assertEqual(result['status'],'INVALID_TIMESTAMP_SCHEMA')

    def test_server_order_is_a_validation_condition(self):
        result=LAYER.latest_quote_state([qrow(CUTOFF-10*SECOND),qrow(CUTOFF-SECOND)],SESSION_START,CUTOFF)
        self.assertEqual(result['status'],'UNEXPECTED_RESPONSE_ORDER')

    def test_unknown_condition_is_not_silently_certified(self):
        result=LAYER.latest_quote_state([qrow(CUTOFF-SECOND,conditions=[999])],SESSION_START,CUTOFF)
        self.assertEqual(result['status'],'UNVERIFIED_QUOTE_CONDITION')

    def test_absent_conditions_are_indicative_only(self):
        result=LAYER.latest_quote_state([qrow(CUTOFF-SECOND)],SESSION_START,CUTOFF)
        self.assertEqual(result['status'],'VALID_INDICATIVE_QUOTE')
        self.assertFalse(result['condition_metadata_present'])

    def test_standing_diagnostic_preserves_age_and_same_session_guard(self):
        rows=[qrow(CUTOFF-600*SECOND)]
        strict=LAYER.latest_quote_state(rows,SESSION_START,CUTOFF,60)
        standing=LAYER.latest_quote_state(rows,SESSION_START,CUTOFF,float('inf'))
        self.assertEqual(strict['status'],'STALE_LATEST_QUOTE_STATE')
        self.assertEqual(standing['status'],'VALID_INDICATIVE_QUOTE')
        self.assertEqual(standing['age_seconds'],600)
        previous=LAYER.latest_quote_state([qrow(SESSION_START-1)],SESSION_START,
                                          CUTOFF,float('inf'))
        self.assertEqual(previous['status'],'OUT_OF_INTERVAL_RESPONSE')

    def test_standing_diagnostic_cannot_resurrect_cancelled_latest(self):
        rows=[qrow(CUTOFF-100*SECOND,bid_size=0),qrow(CUTOFF-600*SECOND)]
        standing=LAYER.latest_quote_state(rows,SESSION_START,CUTOFF,float('inf'))
        self.assertEqual(standing['status'],'INVALID_LATEST_QUOTE_STATE')
        self.assertIsNone(standing['mid'])


def synthetic_snapshot():
    def split(columns,data,index):
        return dict(columns=columns,data=data,index=index)
    days=['2025-03-18','2025-03-19','2025-03-20']
    legs={'C_K':{'ticker':'SYN_C','kind':'call','strike':10.},
          'P_K':{'ticker':'SYN_P','kind':'put','strike':10.},
          'C_U0.05':{'ticker':'SYN_U','kind':'call','strike':11.}}
    priced=dict(ticker='SYN',accession_number='A1',expiry='2025-06-20',
                strikes={'K':10.},legs=legs,bucket='3-6m')
    daily=split(['cash','nav','net_return','stock_gross','stock_gross_fraction',
                 'short_call_liability','drawdown','open_positions',
                 'unknown_mark_reasons','new_entries_paused'],
                [[9000.,10000.,0.,1500.,.15,500.,0.,1,[],False],
                 [9000.,None,None,None,None,None,None,1,['old_gap'],True],
                 [10150.,10150.,None,0.,0.,0.,0.,0,[],False]],days)
    ledger=split(['trade_id','ticker','accession_number','contracts','status','entry_date',
                  'actual_exit','scheduled_exit','sector'],
                 [['T1','SYN','A1',1,'CLOSED',days[0],days[2],days[2],'Tech'],
                  ['S2','SYN','A2',0,'SKIPPED',days[1],None,days[2],'Tech']],[0,1])
    return {'portfolio':{'daily':daily,'ledger':ledger,'config':{'initial_nav':10000.}},
            'priced_primary':[priced]}


def synthetic_inputs(snapshot):
    scopes=LAYER.build_scope(snapshot)
    pe=snapshot['priced_primary'][0]
    quotes,metadata={},{}
    mids={'C_K':1.,'P_K':.5,'C_U0.05':.25}
    for item in scopes:
        mid=mids[item['leg_key']]
        key=item['contract']+'|'+item['day']
        quotes[key]={'status':'OK','key':key,
                     'rows':[qrow(item['cutoff_ns']-10*SECOND,bid=mid-.05,ask=mid+.05)]}
        leg=pe['legs'][item['leg_key']]
        if item['is_entry'] or item.get('is_scope_end',item['is_exit']):
            metadata[key]=dict(ticker=leg['ticker'],shares_per_contract=100,
                               contract_type=leg['kind'],strike_price=leg['strike'],
                               expiration_date=pe['expiry'],underlying_ticker='SYN',
                               additional_underlyings=[])
    return quotes,metadata


class BundleAndFixedLedgerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if LAYER is None:
            raise unittest.SkipTest('Pure quote layer not supplied.')

    def states(self):
        return {k:LAYER.latest_quote_state([qrow(CUTOFF-10*SECOND)],SESSION_START,CUTOFF)
                for k in LAYER.LEGS}

    def open_snapshot(self):
        snap = synthetic_snapshot()
        ledger = snap['portfolio']['ledger']
        row = ledger['data'][0]
        row[ledger['columns'].index('status')] = 'OPEN_AT_WINDOW_END'
        row[ledger['columns'].index('actual_exit')] = None
        row[ledger['columns'].index('scheduled_exit')] = '2025-03-21'
        daily = snap['portfolio']['daily']
        daily['data'][-1][daily['columns'].index('cash')] = 9000.
        daily['data'][-1][daily['columns'].index('open_positions')] = 1
        return snap

    def test_open_at_end_uses_final_IS_mark_without_sale(self):
        snap = self.open_snapshot(); before = copy.deepcopy(snap)
        scope = LAYER.build_scope(snap)
        self.assertEqual(len(scope),9)
        self.assertFalse(any(item['is_exit'] for item in scope))
        self.assertEqual(sum(item['is_scope_end'] for item in scope),3)
        self.assertEqual(max(item['day'] for item in scope),'2025-03-20')
        quotes,metadata = synthetic_inputs(snap)
        self.assertFalse(any(key.endswith('2025-03-21') for key in metadata))
        for age,sync in ((60,60),(300,60),(float('inf'),float('inf'))):
            with self.subTest(age=age):
                output = LAYER.revalue_fixed_ledger(snap,quotes,metadata,age,sync)
                mark = output['marks'].loc[output['marks'].day=='2025-03-20','value_per_contract'].iloc[0]
                self.assertEqual(output['nav_gaps'],0)
                self.assertAlmostEqual(output['daily'].nav.iloc[-1],9000.+mark)
                self.assertGreater(output['daily'].stock_gross.iloc[-1],0)
                self.assertEqual(output['daily'].cash.tolist(),[9000.]*3)
        self.assertEqual(snap,before)

    def test_open_at_end_missing_final_quote_stays_missing(self):
        snap = self.open_snapshot(); quotes,metadata = synthetic_inputs(snap)
        quotes.pop('SYN_P|2025-03-20')
        output = LAYER.revalue_fixed_ledger(snap,quotes,metadata)
        self.assertEqual(output['nav_gaps'],1)
        self.assertTrue(math.isnan(output['daily'].nav.iloc[-1]))
        self.assertEqual(output['daily'].cash.iloc[-1],9000.)

    def test_open_at_end_requires_scope_end_metadata(self):
        snap = self.open_snapshot(); quotes,metadata = synthetic_inputs(snap)
        metadata.pop('SYN_P|2025-03-20')
        output = LAYER.revalue_fixed_ledger(snap,quotes,metadata)
        self.assertEqual(output['nav_gaps'],3)
        self.assertTrue(all('METADATA_UNAVAILABLE' in status for status in output['marks'].status))

    def test_open_scope_cannot_hide_failed_or_already_due_exit(self):
        for column,value in (('actual_exit','2025-03-20'),('scheduled_exit','2025-03-20'),
                             ('status','MISSING_EXIT'),('status','UNKNOWN'),('status','CLOSED')):
            with self.subTest(column=column,value=value):
                snap = self.open_snapshot()
                ledger = snap['portfolio']['ledger']
                ledger['data'][0][ledger['columns'].index(column)] = value
                with self.assertRaises(ValueError):
                    LAYER.build_scope(snap)

    def test_marked_value_scales_by_actual_contract_count(self):
        snap = self.open_snapshot()
        ledger = snap['portfolio']['ledger']
        ledger['data'][0][ledger['columns'].index('contracts')] = 2
        quotes,metadata = synthetic_inputs(snap)
        output = LAYER.revalue_fixed_ledger(snap,quotes,metadata)
        mark = output['marks'].loc[output['marks'].day=='2025-03-20'].iloc[0]
        self.assertAlmostEqual(output['daily'].nav.iloc[-1],9000.+2*mark.value_per_contract)
        self.assertAlmostEqual(output['daily'].stock_gross.iloc[-1],200*mark.synthetic_stock)

    def test_missing_leg_is_explicit_not_partial_value(self):
        states=self.states(); del states['P_K']
        mark=LAYER.three_leg_mark(states,100,'2025-06-20','2025-03-19')
        self.assertIsNone(mark['value_per_contract'])
        self.assertIn('MISSING_REQUIRED_LEG',mark['status'])

    def test_different_update_times_form_same_asof_book(self):
        states=self.states(); states['P_K']['sip_timestamp']=CUTOFF-35*SECOND
        mark=LAYER.three_leg_mark(states,100,'2025-06-20','2025-03-19')
        self.assertEqual(mark['status'],'AVAILABLE_INDICATIVE_PARITY_MARK')
        self.assertEqual(mark['sync_seconds'],25)

    def test_sync_above_fixed_limit_is_missing(self):
        states=self.states(); states['P_K']['sip_timestamp']=CUTOFF-71*SECOND
        mark=LAYER.three_leg_mark(states,100,'2025-06-20','2025-03-19')
        self.assertIsNone(mark['value_per_contract'])
        self.assertEqual(mark['status'],'ASYNCHRONOUS_THREE_LEG_STATE')

    def test_standing_book_keeps_update_span_as_quality_not_expiry(self):
        states=self.states()
        states['P_K']=LAYER.latest_quote_state([qrow(CUTOFF-600*SECOND)],
            SESSION_START,CUTOFF,float('inf'))
        strict=LAYER.three_leg_mark(states,100,'2025-06-20','2025-03-19',60)
        standing=LAYER.three_leg_mark(states,100,'2025-06-20','2025-03-19',float('inf'))
        self.assertIsNone(strict['value_per_contract'])
        self.assertEqual(standing['status'],'AVAILABLE_INDICATIVE_PARITY_MARK')
        self.assertEqual(standing['sync_seconds'],590)

    def test_missing_multiplier_is_not_defaulted_to_100(self):
        pe=synthetic_snapshot()['priced_primary'][0]
        self.assertEqual(LAYER.standard_contract({},pe,'C_K'),'NONSTANDARD_OR_MISSING_MULTIPLIER')

    def test_uniform_scope_and_original_skips_endpoints_preserved(self):
        snap=synthetic_snapshot(); before=copy.deepcopy(snap)
        scopes=LAYER.build_scope(snap)
        self.assertEqual(len(scopes),9)  # includes original gap and both endpoint days
        self.assertEqual({x['trade_id'] for x in scopes},{'T1'})
        quotes,metadata=synthetic_inputs(snap)
        input_copy=copy.deepcopy((quotes,metadata))
        output=LAYER.revalue_fixed_ledger(snap,quotes,metadata)
        daily=output['daily']
        self.assertEqual(output['nav_gaps'],0)
        self.assertEqual(daily.nav.iloc[-1],10150.)
        self.assertEqual(daily.cash.tolist(),[9000.,9000.,10150.])
        self.assertEqual(daily.original_nav.iloc[0],10000.)
        self.assertNotEqual(daily.stock_gross.iloc[0],1500.)
        self.assertEqual(daily.original_new_entries_paused.tolist(),[False,True,False])
        self.assertNotIn('new_entries_paused',daily)
        self.assertEqual(snap,before)
        self.assertEqual((quotes,metadata),input_copy)

    def test_missing_active_leg_keeps_NAV_unknown_and_no_gap_bridge(self):
        snap=synthetic_snapshot(); quotes,metadata=synthetic_inputs(snap)
        quotes.pop('SYN_P|2025-03-19')
        output=LAYER.revalue_fixed_ledger(snap,quotes,metadata)
        daily=output['daily']
        self.assertTrue(math.isnan(daily.nav.iloc[1]))
        self.assertTrue(math.isnan(daily.net_return.iloc[2]))
        self.assertTrue(daily.drawdown.isna().all())
        self.assertEqual(daily.nav.iloc[-1],10150.)

    def test_standing_uniform_ledger_preserves_cash_and_original_primary(self):
        snap=synthetic_snapshot(); quotes,metadata=synthetic_inputs(snap)
        for key,response in quotes.items():
            if key.startswith('SYN_P|'):
                response['rows'][0]['sip_timestamp']-=600*SECOND
        primary=LAYER.revalue_fixed_ledger(snap,quotes,metadata,60,60)
        standing=LAYER.revalue_fixed_ledger(snap,quotes,metadata,float('inf'),float('inf'))
        self.assertEqual(primary['nav_gaps'],2)
        self.assertEqual(standing['nav_gaps'],0)
        self.assertEqual(primary['daily'].cash.tolist(),standing['daily'].cash.tolist())
        self.assertEqual(standing['daily'].nav.iloc[-1],10150.)
        self.assertEqual(primary['daily'].nav.iloc[-1],10150.)
        self.assertEqual(len(primary['quality']),len(standing['quality']))

    def test_wrong_quote_source_key_cannot_supply_this_leg(self):
        snap=synthetic_snapshot(); quotes,metadata=synthetic_inputs(snap)
        quotes['SYN_P|2025-03-19']['key']='WRONG|2025-03-19'
        output=LAYER.revalue_fixed_ledger(snap,quotes,metadata)
        self.assertEqual(output['nav_gaps'],1)
        self.assertIn('SOURCE_QUOTE_KEY_MISMATCH',repr(output['quality']['status'].tolist()))

    def test_ambiguous_event_mapping_fails_closed(self):
        snap=synthetic_snapshot(); snap['priced_primary'].append(copy.deepcopy(snap['priced_primary'][0]))
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            LAYER.build_scope(snap)

    def test_reserved_calendar_cannot_enter_IS_supplement(self):
        snap=synthetic_snapshot(); snap['portfolio']['daily']['index'][-1]='2026-01-02'
        with self.assertRaisesRegex(ValueError,'outside IS'):
            LAYER.build_scope(snap)


if __name__=='__main__':
    unittest.main(verbosity=2)
