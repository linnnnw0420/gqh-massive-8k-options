"""Export allowlisted aggregate IS evidence; no API, strategy or PDF execution.

Private snapshots are read as inputs only. Nothing copies a snapshot, contract,
option price, volume bar, filing body, credential or transport request to output.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import tempfile

import numpy as np
import pandas as pd

from make_quant_note import HORIZONS, validate_payload, SNAPSHOT_DECIMAL_IDENTITY_ATOL

BOARD_COLUMNS = ['strategy','horizon','n_a','n_b','n_candidates_a','n_candidates_b',
                 'n_unavailable_a','n_unavailable_b','mean_a','mean_b','median_a','median_b',
                 'hit_rate_a','hit_rate_b','ci_lo_a','ci_hi_a','ci_lo_b','ci_hi_b',
                 'difference','ci_lo','ci_hi','estimate_status','ci_status']
GRID_COLUMNS = ['category','bucket','entry','otm','horizon','n_event','n_ordinary','theta',
                'ci_lo','ci_hi','timing_status']
RISK_FIELDS = ['kind','window','primary','original_iid_primary','dependence','calendar',
               'variants','cost_stress_from_existing_results','scenario_stress','factor_status',
               'research_interpretation','snapshot_sha256']
QUOTE_FIELDS = ['label','max_age_seconds','convention','standing_quote_assumption',
                'no_guarantee_of_executable_or_uninterrupted_feed','position_day_coverage',
                'leg_day_statuses','nav_gaps','calendar','factor','quote_conditions_present_count',
                'valid_leg_quote_age_median_seconds','all_timestamp_known_latest_state_age_seconds',
                'all_three_leg_latest_update_span_seconds','roundtrip_three_leg_halfspread_aggregate_usd',
                'endpoint_position_snapshots_available','endpoint_position_snapshots_expected',
                'observed_scope_boundary_position_snapshots_expected','open_at_window_end_count','open_scope_end_is_realized_exit',
                'original_cashflows_unchanged','same_final_cash_NAV']
CAPACITY_FIELDS = ['kind','actual_entered_positions','closed_positions','open_at_window_end_positions','endpoint_scope','lookback_sessions','participation_scenarios',
                   'volume_leg_status_counts','all_twenty_bars_observed_leg_count','leg_observed_session_count',
                   'quote_endpoint_summaries','capacity_screens','display_size_contract_conversion','limitations']


def _read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _frame(item):
    return pd.DataFrame(item['data'], columns=item['columns'], index=item['index'])


def _horizon(value):
    return 'expiry' if str(value) in {'exp','expiry'} else str(int(value))


def _finite(value):
    return isinstance(value,(float,int)) and not isinstance(value,bool) and math.isfinite(value)


def _close(left, right, label, checks, *, atol=SNAPSHOT_DECIMAL_IDENTITY_ATOL):
    if not _finite(left) or not _finite(right) or not math.isclose(left,right,rel_tol=0,abs_tol=atol):
        raise ValueError('Numeric self-check failed: '+label)
    checks.append({'check':label,'status':'PASS','absolute_tolerance':atol,'relative_tolerance':0})


def _jsonable(value):
    if isinstance(value,dict): return {str(k):_jsonable(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)): return [_jsonable(v) for v in value]
    if isinstance(value,np.generic): return _jsonable(value.item())
    if isinstance(value,float) and not math.isfinite(value): return None
    if isinstance(value,pd.Timestamp): return value.isoformat()
    return value


def _write_json(path,value):
    Path(path).write_text(json.dumps(_jsonable(value),indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')


def _board(snapshot, name, strategy):
    frame = _frame(snapshot['tables'][name])
    if not set(BOARD_COLUMNS)<=set(frame.columns):
        raise ValueError('Missing official aggregate board fields: '+name)
    frame = frame.loc[frame.strategy.eq(strategy),BOARD_COLUMNS].copy()
    frame['horizon'] = frame.horizon.map(_horizon)
    if not frame.horizon.is_unique or set(frame.horizon)!=set(HORIZONS):
        raise ValueError('Official board must preserve every fixed horizon once.')
    return frame.set_index('horizon').loc[HORIZONS].reset_index()


def _primary_rows(snapshot, table, horizon=21):
    frame = _frame(snapshot['tables'][table])
    mask = (frame.bucket.eq('3-6m') & frame.entry.eq('full') & pd.to_numeric(frame.otm).sub(.05).abs().lt(1e-10)
            & frame.horizon.map(_horizon).eq(_horizon(horizon)))
    return frame.loc[mask]


def implied_realized_summary(snapshot):
    """Aggregate the retained starter diagnostic on a common finite sample."""
    rows=[]
    for horizon in HORIZONS:
        for group,table in (('event','results'),('ordinary','placebo_results')):
            subset=_primary_rows(snapshot,table,horizon)
            if not {'implied_scaled','realized'}<=set(subset.columns):
                raise ValueError('Retained primary outcomes lack the required starter implied/realized diagnostic.')
            scaled=pd.to_numeric(subset.implied_scaled,errors='coerce')
            realized=pd.to_numeric(subset.realized,errors='coerce').abs()
            valid=np.isfinite(scaled)&scaled.gt(0)&np.isfinite(realized)
            ratio=realized[valid]/scaled[valid]
            rows.append({'horizon':horizon,'sample':group,'total_n':len(subset),
                         'common_finite_positive_implied_n':int(valid.sum()),
                         'missing_or_invalid_n':int((~valid).sum()),
                         'mean_absolute_realized':float(realized[valid].mean()) if valid.any() else None,
                         'mean_implied_scaled':float(scaled[valid].mean()) if valid.any() else None,
                         'mean_realized_to_implied_ratio':float(ratio.mean()) if len(ratio) else None,
                         'median_realized_to_implied_ratio':float(ratio.median()) if len(ratio) else None,
                         'diagnostic':'Starter sqrt-time ATM-straddle proxy; not true IV, fair value or a mispricing test',
                         'sample_rule':'Common finite realized and finite positive implied_scaled; no ratio trimming'})
    return pd.DataFrame(rows)


def load_run(path,name,checks):
    path = Path(path)
    manifest = _read(path/'run_manifest.json')
    expected = 'approved_is_v1' if name=='original' else 'corrected_is_v2'
    if manifest.get('status')!='COMPLETE' or manifest.get('mode')!=expected:
        raise ValueError(name+' must be a completed, correctly identified IS run.')
    snapshot_path = path/'snapshot.private.json'
    digest = _sha(snapshot_path)
    snapshot = _read(snapshot_path)
    evidence = _read(path/'aggregate_evidence.json')
    if evidence.get('snapshot_sha256')!=digest or manifest.get('snapshot_sha256')!=digest:
        raise ValueError(name+' snapshot provenance hash does not match its aggregate evidence.')
    runtime = snapshot.get('runtime_manifest',{})
    if snapshot.get('oos_read') is not False or runtime.get('oos_access') is not False or runtime.get('sealed_access') is not False:
        raise ValueError('Export requires explicit untouched OOS/sealed provenance.')
    theta = _board(snapshot,'theta_board','incremental_net')
    official = _board(snapshot,'official_diff','covered_call_net')
    for t,o in zip(theta.to_dict('records'),official.to_dict('records')):
        for label,row in (('theta',t),('official',o)):
            _close(row['mean_a']-row['mean_b'],row['difference'],f'{name}.{label}.{row["horizon"]}.difference',checks)
            for suffix in ('a','b'):
                _close(row['n_candidates_'+suffix],row['n_'+suffix]+row['n_unavailable_'+suffix],f'{name}.{label}.{row["horizon"]}.coverage_{suffix}',checks,atol=0)
        if (t['n_a'],t['n_b'])!=(o['n_a'],o['n_b']):
            raise ValueError('Official and primary estimand finite coverage diverge; review explicitly.')
    primary = theta.loc[theta.horizon.eq('21')].iloc[0]
    dep = evidence['dependence']
    _close(float(primary['difference']),dep['theta'],name+'.primary_vs_dependence',checks)
    for convention, event_table, ordinary_table in (('base','results','placebo_results'),('doubled','event_stress','ordinary_stress')):
        reported = evidence['cost_stress_from_existing_results'][convention]
        a = pd.to_numeric(_primary_rows(snapshot,event_table).incremental_net,errors='coerce')
        b = pd.to_numeric(_primary_rows(snapshot,ordinary_table).incremental_net,errors='coerce')
        a,b = a[np.isfinite(a)],b[np.isfinite(b)]
        for field,value in {'finite_event':len(a),'finite_ordinary':len(b),'event_mean':float(a.mean()),
                            'ordinary_mean':float(b.mean()),'theta':float(a.mean()-b.mean())}.items():
            _close(value,reported[field],name+'.'+convention+'.'+field,checks)
    grid = _frame(snapshot['tables']['sensitivity'])[GRID_COLUMNS].copy()
    grid['horizon'] = grid.horizon.map(_horizon)
    if len(grid)!=972 or grid.duplicated(['category','bucket','entry','otm','horizon']).any():
        raise ValueError('The frozen complete 972-cell grid must remain visible.')
    _close(evidence['variants']['distinct_grid_cells'],len(grid),name+'.variant_count',checks,atol=0)
    events = _frame(snapshot['tables']['events'])
    candidates = _frame(snapshot['tables']['candidate_events'])
    ordinary = _frame(snapshot['tables']['placebo_events'])
    ledger = _frame(snapshot['portfolio']['ledger'])
    statuses = ledger.status.value_counts().to_dict()
    unknown = set(statuses)-{'CLOSED','OPEN_AT_WINDOW_END','SKIPPED'}
    if unknown:
        raise ValueError('Unresolved ledger statuses require explicit reporting before export: '+repr(sorted(unknown)))
    coverage = {'eligible_disclosures':len(events),'union_source_label_records':len(candidates),
                'union_unique_accessions':int(candidates.accession_id.nunique()),'ordinary_date_draws':len(ordinary),
                'primary_event_candidates':int(primary.n_candidates_a),'primary_event_finite':int(primary.n_a),
                'primary_ordinary_candidates':int(primary.n_candidates_b),'primary_ordinary_finite':int(primary.n_b),
                'finite_event_issuers':dep['finite_event_issuers'],'finite_ordinary_issuers':dep['finite_ordinary_issuers'],
                'portfolio_status_counts':statuses,'original_daily_NAV_gaps':evidence['calendar']['nav_gaps'],
                'source_coverage_claim':'Counts reproduce the saved bounded query; they do not prove an exhaustive historical market denominator.'}
    # Additional aggregate stock baseline; no per-event price/outcome rows leave this function.
    stock_rows = []
    for horizon in HORIZONS:
        a = _primary_rows(snapshot,'results',horizon)
        b = _primary_rows(snapshot,'placebo_results',horizon)
        av = pd.to_numeric(a.stock_net,errors='coerce'); bv = pd.to_numeric(b.stock_net,errors='coerce')
        av,bv = av[np.isfinite(av)],bv[np.isfinite(bv)]
        stock_rows.append({'horizon':horizon,'n_event':len(av),'n_ordinary':len(bv),
                           'event_stock_net_mean':av.mean(),'ordinary_stock_net_mean':bv.mean(),
                           'stock_net_difference':av.mean()-bv.mean()})
    study = {'status':'COMPLETE_IS_AGGREGATES','eligible_disclosures':len(events),'n_event':int(primary.n_a),
             'n_ordinary':int(primary.n_b),'theta':float(primary['difference']),
             'iid_interval':[float(primary.ci_lo),float(primary.ci_hi)],
             'issuer_range':[dep['issuer']['ci_low'],dep['issuer']['ci_high']],
             'date_range':[dep['overlap_interval']['ci_low'],dep['overlap_interval']['ci_high']],
             'variants':len(grid),'original_nav_gaps':evidence['calendar']['nav_gaps'],
             'horizons':[{'horizon':t['horizon'],'event_cc_mean':o['mean_a'],'ordinary_cc_mean':o['mean_b'],
                          'n_event':int(t['n_a']),'n_ordinary':int(t['n_b']),
                          'cc_difference':o['difference'],'cc_iid_interval':[o['ci_lo'],o['ci_hi']],
                          'theta':t['difference'],'theta_iid_interval':[t['ci_lo'],t['ci_hi']]}
                         for t,o in zip(theta.to_dict('records'),official.to_dict('records'))]}
    implied_realized=implied_realized_summary(snapshot)
    for row in implied_realized.to_dict('records'):
        _close(row['total_n'],row['common_finite_positive_implied_n']+row['missing_or_invalid_n'],
               f'{name}.implied_realized.{row["sample"]}.{row["horizon"]}.coverage',checks,atol=0)
    return {'snapshot':snapshot,'evidence':evidence,'study':study,'theta':theta,'official':official,
            'implied_realized':implied_realized,
            'grid':grid,'coverage':coverage,'stock':pd.DataFrame(stock_rows),
            'source_hashes':{'snapshot_sha256':digest,'aggregate_sha256':_sha(path/'aggregate_evidence.json'),
                             'run_manifest_sha256':_sha(path/'run_manifest.json')}}


def load_diagnostics(path,name,run,checks):
    path = Path(path)
    summary = _read(path/'quote_supplement_summary.json')
    if summary.get('snapshot_sha256')!=run['source_hashes']['snapshot_sha256'] or summary.get('oos_access') is not False:
        raise ValueError('Quote diagnostic must identify this exact IS snapshot and untouched OOS status.')
    reports = [{key:report[key] for key in QUOTE_FIELDS if key in report} for report in summary['reports']]
    standing = [report for report in reports if report.get('standing_quote_assumption') is True]
    if len(standing)!=1:
        raise ValueError('Exactly one separately labeled standing-NBBO diagnostic is required.')
    standing = standing[0]
    original = _frame(run['snapshot']['portfolio']['daily'])
    original.index = pd.to_datetime(original.index)
    curve = pd.read_csv(path/'quote_nav_standing.private.csv',index_col='date',parse_dates=True)
    if not curve.index.equals(original.index) or curve.index.min()<pd.Timestamp('2024-01-01') or curve.index.max()>pd.Timestamp('2025-12-31'):
        raise ValueError('Derived quote curve must exactly match its source full IS calendar.')
    # The diagnostic must keep this version's ledger, including still-open final positions.
    if 'cash' not in curve or not np.allclose(curve.cash,original.cash,rtol=1e-12,atol=1e-8,equal_nan=True):
        raise ValueError('Quote diagnostic cashflows do not match this run version.')
    cal = standing['calendar']; initial = float(run['snapshot']['portfolio']['config']['initial_nav'])
    gaps = int(curve.nav.isna().sum())
    _close(gaps,cal['nav_gaps'],name+'.diagnostic_NAV_gap_count',checks,atol=0)
    complete = bool(cal.get('complete_calendar_returns'))
    metrics = {'status':'UNAVAILABLE','initial_nav':initial,'nav_csv':name+'_conditional_nav.csv',
               'cagr':None,'annualized_volatility':None,'sharpe':None,'maximum_drawdown':None,'stock_turnover':None,
               'daily_return_skew_unbiased':None,'worst_month_return':None,'worst_month':None}
    if complete:
        if gaps or not np.isfinite(curve.nav.to_numpy(float)).all() or (curve.nav<=0).any():
            raise ValueError('Complete calendar claim contains unavailable or invalid NAV.')
        levels = np.r_[initial,curve.nav.to_numpy(float)]
        returns = pd.Series(np.diff(levels)/levels[:-1],index=curve.index)
        sigma = float(returns.std(ddof=1))
        measured = {'annualized_return':(levels[-1]/initial)**(252/len(curve))-1,
                    'maximum_drawdown':float(np.max(1-levels/np.maximum.accumulate(levels)))}
        if np.isfinite(sigma) and sigma>0:
            measured['sharpe_rf0']=float(returns.mean()/sigma*np.sqrt(252))
        elif sigma==0 and cal.get('sharpe_rf0') is None:
            metrics['sharpe_unavailable_reason']='ZERO_RETURN_VARIANCE'
            checks.append({'check':name+'.portfolio.undefined_Sharpe_not_zero_filled','status':'PASS'})
        else:
            raise ValueError('Undefined return variance requires unavailable Sharpe, not a numeric substitute.')
        for field,value in measured.items(): _close(value,cal[field],name+'.portfolio.'+field,checks)
        if 'traded_stock_gross' not in curve:
            raise ValueError('Full portfolio turnover requires its derived trade flow series.')
        turnover = float(curve.traded_stock_gross.sum()/curve.nav.mean())
        _close(turnover,cal['turnover']['traded_stock_gross']['two_sided_over_mean_nav'],name+'.portfolio.turnover',checks)
        metrics.update(status='COMPLETE_STANDING_NBBO_ASSUMPTION',cagr=cal['annualized_return'],sharpe=cal['sharpe_rf0'],
                       annualized_volatility=cal['annualized_volatility'],
                       maximum_drawdown=cal['maximum_drawdown'],stock_turnover=turnover,
                       daily_return_skew_unbiased=cal['daily_return_skew_unbiased'],
                       worst_month_return=cal['worst_month_return'],worst_month=cal['worst_month'])
    capacity_path = path/'capacity_evidence_summary.json'
    capacity = _read(capacity_path) if capacity_path.exists() else None
    if capacity is not None:
        capacity = {key:capacity[key] for key in CAPACITY_FIELDS if key in capacity}
    return {'metrics':metrics,'curve':curve[['nav']].copy(),'reports':reports,'standing':standing,'capacity':capacity,
            'source_hashes':{'quote_summary_sha256':_sha(path/'quote_supplement_summary.json'),
                             'private_quote_curve_sha256':_sha(path/'quote_nav_standing.private.csv'),
                             'capacity_summary_sha256':_sha(capacity_path) if capacity_path.exists() else None}}


def load_causal_run(path,corrected,checks):
    """Read a portfolio-only timing repair; it cannot replace event-study rows."""
    path=Path(path); manifest=_read(path/'run_manifest.json')
    if manifest.get('status')!='COMPLETE' or manifest.get('mode')!='causal_portfolio_v3':
        raise ValueError('Causal portfolio must be a completed, explicitly named V3 run.')
    snapshot_path=path/'snapshot.private.json'; digest=_sha(snapshot_path)
    snapshot=_read(snapshot_path); evidence=_read(path/'aggregate_evidence.json')
    if manifest.get('snapshot_sha256')!=digest or evidence.get('snapshot_sha256')!=digest:
        raise ValueError('Causal portfolio snapshot/evidence provenance is inconsistent.')
    if manifest.get('source_snapshot_sha256')!=corrected['source_hashes']['snapshot_sha256']:
        raise ValueError('Causal portfolio must derive from this exact corrected V2 snapshot.')
    runtime=snapshot.get('runtime_manifest',{})
    if snapshot.get('oos_read') is not False or runtime.get('oos_access') is not False or runtime.get('sealed_access') is not False:
        raise ValueError('Causal repair cannot include OOS or sealed evaluation.')
    if snapshot['tables']!=corrected['snapshot']['tables']:
        raise ValueError('Portfolio-only repair changed the retained V2 event study.')
    checks.append({'check':'causal.event_tables_exactly_equal_corrected_v2','status':'PASS'})
    ledger=_frame(snapshot['portfolio']['ledger'])
    statuses=ledger.status.value_counts().to_dict()
    daily=_frame(snapshot['portfolio']['daily'])
    coverage={'event_evidence_version':'corrected_is_v2','portfolio_version':'causal_portfolio_v3',
              'portfolio_status_counts':statuses,'daily_NAV_gaps':int(pd.to_numeric(daily.nav,errors='coerce').isna().sum()),
              'decision_clock':'Current entry-session open using previous-session close financial state',
              'fill_model':'Unchanged starter closing daily-bar proxy; no live-execution claim',
              'selection_basis':'Objective post-IS same-close admission bias repair, not better performance',
              'unpriced_or_unresolved_position_count':sum(n for label,n in statuses.items() if label not in {'CLOSED','OPEN_AT_WINDOW_END','SKIPPED'})}
    for key in ('order_decisions','decision_audit','decisions'):
        if key in snapshot['portfolio'] and isinstance(snapshot['portfolio'][key],dict):
            decisions=_frame(snapshot['portfolio'][key])
            for column in ('reason','decision_reason'):
                if column in decisions:
                    coverage['decision_reason_counts']=decisions[column].value_counts().to_dict()
                    break
    return {'snapshot':snapshot,'evidence':evidence,'coverage':coverage,
            'source_hashes':{'snapshot_sha256':digest,'aggregate_sha256':_sha(path/'aggregate_evidence.json'),
                             'run_manifest_sha256':_sha(path/'run_manifest.json'),
                             'source_corrected_snapshot_sha256':manifest['source_snapshot_sha256']}}


def _capacity_sentence(diagnostics):
    name = 'causal' if 'causal' in diagnostics else 'corrected' if diagnostics['corrected']['capacity'] is not None else 'original'
    capacity = diagnostics[name]['capacity']
    if capacity is None:
        return f'{name.title()}-ledger volume/depth capacity evidence is unavailable. Legacy capacity, if available, is separate; no executable dollar capacity or scalable edge is established.'
    screens = capacity['capacity_screens']
    strict = [r for r in screens if r['volume_convention']=='strict_complete_20_observations' and r['participation']==.01][0]
    conditional = [r for r in screens if r['volume_convention']=='conditional_absent_bar_as_zero' and r['participation']==.01][0]
    count = capacity['actual_entered_positions']
    return (f'{name.title()}-ledger capacity: complete 20-session volume for {strict["positions_with_available_screen"]}/{count} positions; '
            f'{conditional["positions_passing_original_one_contract"]}/{count} pass one contract at conditional 1% ADV. '
            'Absent-bar/listing assumptions and unresolved size units preclude an executable dollar-capacity claim.')


def _factor_sentence(diagnostics):
    pieces = []
    for name in (('causal',) if 'causal' in diagnostics else ('original','corrected')):
        factor = diagnostics[name]['standing'].get('factor',{})
        coefficients = factor.get('coefficients',[])
        market = next((row for row in coefficients if row['term']=='market_SPY'),None)
        pieces.append(name+(' beta '+f'{market["estimate"]:.3f}' if market else ' fit unavailable'))
    return ('Conditional '+ '; '.join(pieces)+'. Fixed SPY, IWD-IWF and MTUM-SPY price-only proxies use HAC(21). '
            'Idle capital, dividends omitted, few active episodes and nonlinear exposure preclude an established-alpha interpretation.')


def _cost_sentence(cost,diagnostics):
    name='causal' if 'causal' in diagnostics else 'original'
    capacity = diagnostics[name]['capacity']
    peak = None
    if capacity is not None:
        primary = next((row for row in capacity['quote_endpoint_summaries'] if row.get('max_quote_age_seconds')==60),None)
        if primary:
            peak = primary.get('halfspread_to_original_booked_haircut',{}).get('max')
    spread = (f'{name.title()} peak observed half-spread is {peak:.2f}x the booked haircut. '
              if _finite(peak) else 'Observed-spread validation is incomplete. ')
    return (f'Doubled-cost theta: original {100*cost["original"]["doubled"]["theta"]:+.2f}, '
            f'corrected {100*cost["corrected"]["doubled"]["theta"]:+.2f} pp. Relative gaps need not imply absolute profits. '
            +spread+'Commissions, impact and financing are additional.')


def export_report(original_run,corrected_run,original_diagnostics,corrected_diagnostics,public_dir,
                  *, hypothesis_commit='63664eb',causal_run=None,causal_diagnostics=None):
    if (causal_run is None)!=(causal_diagnostics is None):
        raise ValueError('Causal run and causal diagnostics must be supplied together.')
    checks = []
    runs = {name:load_run(path,name,checks) for name,path in [('original',original_run),('corrected',corrected_run)]}
    diagnostics = {name:load_diagnostics(path,name,runs[name],checks)
                   for name,path in [('original',original_diagnostics),('corrected',corrected_diagnostics)]}
    portfolio_runs=dict(runs)
    if causal_run is not None:
        portfolio_runs['causal']=load_causal_run(causal_run,runs['corrected'],checks)
        diagnostics['causal']=load_diagnostics(causal_diagnostics,'causal',portfolio_runs['causal'],checks)
    cost = {name:run['evidence']['cost_stress_from_existing_results'] for name,run in runs.items()}
    original_count,corrected_count = [runs[name]['study']['eligible_disclosures'] for name in ('original','corrected')]
    open_count = runs['corrected']['coverage']['portfolio_status_counts'].get('OPEN_AT_WINDOW_END',0)
    change = corrected_count-original_count
    payload = {'schema':'gqh_quant_note_v1','generated_utc':datetime.now(timezone.utc).isoformat(),
               'hypothesis_commit':hypothesis_commit,'oos_status':'NOT_RUN','unseen_classifier_status':'NOT_READY',
               'studies':{name:run['study'] for name,run in runs.items()},
               'portfolios':{name:diagnostic['metrics'] for name,diagnostic in diagnostics.items()},
               'portfolio_headline':'causal' if causal_run is not None else 'corrected',
               'correction_summary':f'Post-IS chronology repair changes eligibility from {original_count} to {corrected_count}, retaining rules and both versions. Ordinary controls regenerate under the same algorithm; differences cannot be attributed solely to restored events. Legacy V2 ledger: {open_count} open at window end.',
               'cost_summary':_cost_sentence(cost,diagnostics),
               'capacity_summary':_capacity_sentence(diagnostics),'factor_summary':_factor_sentence(diagnostics),
               'conclusion':'Both IS versions remain exploratory. Source repairs and conditional valuation improve auditability, not independent sample size, validated event alpha, execution readiness or demonstrated capacity. OOS evidence is still absent.'}
    if causal_run is not None:
        payload['portfolio_repair']={'version':'causal_portfolio_v3','event_evidence_version':'corrected_is_v2',
                                     'selection_basis':'OBJECTIVE_TIMING_REPAIR_NOT_PERFORMANCE',
                                     'stage':'POST_IS_IMPLEMENTATION_REPAIR',
                                     'legacy_portfolios_retained':['original','corrected'],
                                     'live_execution_validated':False}
    out = Path(public_dir).resolve()
    out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='aggregate-export-',dir=out.parent) as folder:
        stage = Path(folder)
        for name,run in runs.items():
            for title,frame in [('theta_board',run['theta']),('official_diff',run['official']),('sensitivity',run['grid']),('stock_baseline',run['stock']),('implied_realized',run['implied_realized'])]:
                frame.to_csv(stage/f'{name}_{title}.csv',index=False)
            risk = {key:run['evidence'][key] for key in RISK_FIELDS if key in run['evidence']}
            _write_json(stage/f'{name}_aggregate_risk.json',risk)
            _write_json(stage/f'{name}_coverage.json',run['coverage'])
            pd.DataFrame([{'cost_convention':label,**row} for label,row in cost[name].items()]).to_csv(stage/f'{name}_primary_cost_stress.csv',index=False)
        if causal_run is not None:
            causal=portfolio_runs['causal']
            # Keep portfolio-only evidence separate: never publish new V3 event
            # tables that could imply a third event hypothesis/parameter run.
            causal_risk={key:causal['evidence'][key] for key in ('kind','window','calendar','scenario_stress','factor_status','snapshot_sha256') if key in causal['evidence']}
            causal_risk.update(event_evidence_version='corrected_is_v2',portfolio_version='causal_portfolio_v3')
            _write_json(stage/'causal_aggregate_risk.json',causal_risk)
            _write_json(stage/'causal_coverage.json',causal['coverage'])
        for name in portfolio_runs:
            diagnostics[name]['curve'].rename_axis('date').to_csv(stage/payload['portfolios'][name]['nav_csv'])
            _write_json(stage/f'{name}_quote_diagnostics.json',{'kind':'aggregate_valuation_sensitivities','reports':diagnostics[name]['reports']})
            if diagnostics[name]['capacity'] is not None:
                _write_json(stage/f'{name}_capacity_evidence.json',diagnostics[name]['capacity'])
        _write_json(stage/'finalreport_payload.json',payload)
        validate_payload(payload,stage)
        artifacts = []
        forbidden_fields = {'apiKey','api_key','bid_price','ask_price','contract','contracts_ticker','bars','priced_primary','supporting_text'}
        for path in sorted(stage.iterdir()):
            text = path.read_text(encoding='utf-8')
            # Defense-in-depth: export is already built from allowlisted schemas.
            if any(('"'+key+'"') in text for key in forbidden_fields) or 'O:' in text:
                raise ValueError('Unexpected raw-data or credential field in aggregate export: '+path.name)
            artifacts.append({'file':path.name,'sha256':_sha(path),'bytes':path.stat().st_size,
                              'content_class':'derived_aggregate_or_portfolio_NAV_no_licensed_input_records'})
        manifest = {'kind':'public_derived_artifact_manifest','created_utc':payload['generated_utc'],
                    'hypothesis_commit':hypothesis_commit,'oos_access':False,'sealed_access':False,
                    'status':'IS_REPORT_DRAFT_NOT_FINAL_SUBMISSION','license_boundary':'Only aggregate strategy statistics and derived portfolio NAV; no raw option prices, contracts, volume histories, filing bodies, API keys or transport records.',
                    'input_hashes':{name:{**portfolio_runs[name]['source_hashes'],**diagnostics[name]['source_hashes']} for name in portfolio_runs},
                    'headline_portfolio':payload['portfolio_headline'],'event_evidence_versions':['original','corrected'],
                    'numeric_self_checks':checks,'artifacts':artifacts,
                    'numeric_serialization_policy':{'snapshot_decimal_places':10,'identity_absolute_tolerance_decimal_return':SNAPSHOT_DECIMAL_IDENTITY_ATOL,
                                                   'relative_tolerance':0,'values_changed':False,
                                                   'reason':'Three independently rounded ten-decimal quantities have an identity error bound of 1.5e-10 before binary roundoff.'},
                    'excluded_by_design':['snapshot.private.json','licensed quotes/bars/volumes','API responses','credentials','per-position licensed inputs'],
                    'limitations':['Historical data-license terms still govern source acquisition; this export does not relicense any source.',
                                   'OOS and unseen-window operational readiness remain incomplete.']}
        _write_json(stage/'publication_manifest.json',manifest)
        out.mkdir(parents=True,exist_ok=True)
        for path in sorted(stage.iterdir(),key=lambda path:path.name=='publication_manifest.json'):
            path.replace(out/path.name)
    return {'status':'PUBLIC_AGGREGATES_EXPORTED','artifacts':len(artifacts),'numeric_checks':len(checks),
            'original_theta':payload['studies']['original']['theta'],'corrected_theta':payload['studies']['corrected']['theta'],
            'corrected_open_at_window_end':open_count,'public_dir':str(out)}


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('original-run','corrected-run','original-diagnostics','corrected-diagnostics','public-dir'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--hypothesis-commit',default='63664eb')
    parser.add_argument('--causal-run',type=Path)
    parser.add_argument('--causal-diagnostics',type=Path)
    args = parser.parse_args()
    print(json.dumps(export_report(args.original_run,args.corrected_run,args.original_diagnostics,
                                   args.corrected_diagnostics,args.public_dir,hypothesis_commit=args.hypothesis_commit,
                                   causal_run=args.causal_run,causal_diagnostics=args.causal_diagnostics)))
