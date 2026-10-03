"""Derive fixed quote valuation diagnostics from a private immutable IS snapshot."""
from __future__ import annotations
import json
import numpy as np
import pandas as pd
from diagnostics_common import (argument_parser, load_snapshot, resolve_paths,
                                sanitized_main, sha256)
from quote_valuation import build_scope, revalue_fixed_ledger, split_frame
from risk_evidence import calendar_evidence, factor_evidence, _jsonable


def validate_inputs(paths):
    snapshot = load_snapshot(paths)
    manifest_path = paths.work_dir / 'uniform_quote_manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    if manifest['source_sha256'] != sha256(paths.snapshot):
        raise ValueError('Quote manifest belongs to a different input snapshot.')
    input_path = paths.work_dir / 'uniform_quote_inputs.private.json'
    inputs = json.loads(input_path.read_text(encoding='utf-8-sig'))
    if inputs['manifest_hash'] != sha256(manifest_path):
        raise ValueError('Quote inputs belong to a different manifest.')
    factor_path = paths.work_dir / 'factor_proxy_inputs.private.csv'
    if not factor_path.is_file():
        raise ValueError('Fixed factor inputs are required.')
    return snapshot, inputs, factor_path


def calculate(paths, snapshot, inputs, factor_path):
    metadata = dict(inputs['metadata'])
    ledger = split_frame(snapshot['portfolio']['ledger'])
    by_acc = {p['accession_number']:p for p in snapshot['priced_primary']}
    scope_ends = {}
    for scope in build_scope(snapshot):
        scope_ends[scope['trade_id']] = max(scope_ends.get(scope['trade_id'], scope['day']), scope['day'])
    actions = {(r['kind'],r['key']):r for r in inputs['actions']}
    action_audit = []
    for row in ledger.to_dict('records'):
        if not row['contracts'] or row['status']=='SKIPPED':
            continue
        pe = by_acc[row['accession_number']]
        start, end = str(row['entry_date'])[:10], scope_ends[row['trade_id']]
        split = actions.get(('splits',row['ticker']),{})
        div = actions.get(('dividends',row['ticker']),{})
        affected = [r for r in split.get('rows',[]) if start<=str(r.get('execution_date',''))<=end]
        dividends = [r for r in div.get('rows',[]) if start<=str(r.get('ex_dividend_date',''))<=end]
        blocked = split.get('status')!='OK' or bool(affected)
        if blocked:
            for leg in ('C_K','P_K','C_U0.05'):
                metadata[pe['legs'][leg]['ticker']+'|'+start] = None
        action_audit.append({'trade_id':row['trade_id'],'ticker':row['ticker'],
                             'split_audit_status':'BLOCKED' if blocked else 'NO_SPLIT_IN_HOLDING_INTERVAL',
                             'dividend_audit_status':div.get('status','UNAVAILABLE'),
                             'ex_dividend_dates_in_holding':[r['ex_dividend_date'] for r in dividends],
                             'dividend_count':len(dividends),
                             'observed_scope_end':end,'position_status':row['status']})
    original = split_frame(snapshot['portfolio']['daily'],True)
    factors = pd.read_csv(factor_path,index_col='date',parse_dates=True)
    factor_columns = list(factors.columns); factors['RF'] = 0.
    reports = []
    for age in (60,300,float('inf')):
        standing = not np.isfinite(age)
        suffix = 'standing' if standing else 'age'+str(age)
        result = revalue_fixed_ledger(snapshot,inputs['quotes'],metadata,age,float('inf') if standing else 60)
        daily = result['daily']
        calendar = calendar_evidence(daily,original.index,snapshot['portfolio']['config']['initial_nav'])
        fit = factor_evidence(calendar['daily_returns'].loc[factors.index],factors,factors.index,
                              factor_columns=factor_columns,hac_lags=21)
        fit['scope'] = 'Jan 3 2024-Dec 31 2025; split-adjusted ETF price-return proxies, RF=0'
        fit['not_causal_alpha'] = 'ETF proxies exclude dividends and are not pure style factors; nonlinear option risk and sparse positions remain'
        daily.to_csv(paths.work_dir / f'quote_nav_{suffix}.private.csv',index_label='date')
        result['quality'].to_csv(paths.work_dir / f'quote_quality_{suffix}.private.csv',index=False)
        result['marks'].to_csv(paths.work_dir / f'quote_marks_{suffix}.private.csv',index=False)
        quality = result['quality']; marks = result['marks']
        endpoints = marks.merge(quality[['trade_id','day','is_entry','is_exit','is_scope_end']].drop_duplicates(),on=['trade_id','day'])
        spread = endpoints.loc[(endpoints.is_entry | endpoints.is_exit) & (endpoints['status']=='AVAILABLE_INDICATIVE_PARITY_MARK'),'three_leg_half_spread_usd']
        calendar.pop('daily_returns',None)
        for key,value in list(calendar.items()):
            if isinstance(value,pd.DataFrame) and len(value)>30:
                calendar.pop(key)
        known = quality.loc[quality['status']=='VALID_INDICATIVE_QUOTE']
        ages = pd.to_numeric(quality.get('age_seconds',pd.Series(dtype=float)),errors='coerce')
        ages = ages[np.isfinite(ages)]
        times = pd.to_numeric(quality.get('sip_timestamp',pd.Series(dtype=float)),errors='coerce')
        spans = quality.assign(_timestamp=times).groupby(['trade_id','day'])['_timestamp'].agg(lambda x:(x.max()-x.min())/1e9 if x.notna().sum()==3 else np.nan)
        def distribution(values):
            values = pd.Series(values).dropna()
            return {'count':len(values),'min':values.min() if len(values) else None,
                    'median':values.median() if len(values) else None,'p95':values.quantile(.95) if len(values) else None,
                    'p99':values.quantile(.99) if len(values) else None,'max':values.max() if len(values) else None,
                    'above_60_seconds':int((values>60).sum()),'above_300_seconds':int((values>300).sum())}
        admitted = ledger.contracts>0
        closed = admitted & ledger.status.eq('CLOSED')
        report = {'label':('post-coverage same-session standing-NBBO assumption' if standing else 'primary supplemental valuation' if age==60 else 'prespecified age sensitivity'),
                  'max_age_seconds':None if standing else age,'convention':result['convention'],
                  'standing_quote_assumption':standing,'no_guarantee_of_executable_or_uninterrupted_feed':True,
                  'position_day_coverage':result['coverage'],'leg_day_statuses':quality['status'].value_counts().to_dict(),
                  'nav_gaps':result['nav_gaps'],'calendar':calendar,'factor':fit,
                  'quote_conditions_present_count':int(quality.get('condition_metadata_present',pd.Series(False,index=quality.index)).fillna(False).sum()),
                  'valid_leg_quote_age_median_seconds':float(known['age_seconds'].median()) if len(known) else None,
                  'all_timestamp_known_latest_state_age_seconds':distribution(ages),
                  'all_three_leg_latest_update_span_seconds':distribution(spans),
                  'roundtrip_three_leg_halfspread_aggregate_usd':float(spread.sum()) if len(spread) else None,
                  'endpoint_position_snapshots_available':int(len(spread)),
                  'endpoint_position_snapshots_expected':int(admitted.sum()+closed.sum()),
                  'observed_scope_boundary_position_snapshots_expected':2*int(admitted.sum()),
                  'open_at_window_end_count':int((admitted & ledger.status.eq('OPEN_AT_WINDOW_END')).sum()),
                  'open_scope_end_is_realized_exit':False,
                  'original_cashflows_unchanged':bool(daily['cash'].equals(original['cash'])),
                  'same_final_cash_NAV':bool(daily['nav'].iloc[-1]==original['nav'].iloc[-1])}
        reports.append(report)
    summary = {'kind':'post_IS_fixed_original_ledger_uniform_quote_marking','reports':reports,'corporate_actions':action_audit,
               'no_new_strategy_or_admission_simulation':True,'oos_access':False,
               'snapshot_sha256':sha256(paths.snapshot),
               'warning':'Supplemental marks with original daily-trade proxy cashflows. Not synchronous executions, not a repaired trading/admission path, no claim that a changed-mark drawdown rule would make identical decisions.'}
    (paths.work_dir / 'quote_supplement_summary.json').write_text(json.dumps(_jsonable(summary),indent=2,allow_nan=False), encoding='utf-8')
    return reports


def main():
    paths = resolve_paths(argument_parser(__doc__).parse_args())
    snapshot, inputs, factor_path = validate_inputs(paths)
    if not paths.execute:
        print(json.dumps({'execute':False,'snapshot_sha256':sha256(paths.snapshot),
                          'valuation_conventions':[60,300,'standing'],'no_new_strategy_simulation':True}))
        return
    reports = calculate(paths,snapshot,inputs,factor_path)
    print(json.dumps(_jsonable([{'age':r['max_age_seconds'],'nav_gaps':r['nav_gaps'],
                                'coverage':r['position_day_coverage'],'factor_status':r['factor']['status'],
                                'cashflows_unchanged':r['original_cashflows_unchanged']} for r in reports])))


if __name__ == '__main__':
    sanitized_main(main)
