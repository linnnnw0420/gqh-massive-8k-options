"""Uniform fixed-ledger quote marking; no strategy simulation or data access."""
from __future__ import annotations
import math
from collections import Counter
import numpy as np
import pandas as pd

LEGS = ('C_K', 'P_K', 'C_U0.05')


def split_frame(obj, date_index=False):
    frame = pd.DataFrame(obj['data'], columns=obj['columns'], index=obj['index'])
    if date_index:
        frame.index = pd.to_datetime(frame.index)
    return frame


def latest_quote_state(rows, start_ns, cutoff_ns, max_age_seconds=60):
    """Choose latest state before validation; never resurrect an older valid quote."""
    bad = lambda reason: {'status': reason, 'mid': None}
    if not rows:
        return bad('NO_SAME_SESSION_QUOTE')
    if any(not isinstance(r, dict) or not isinstance(r.get('sip_timestamp'), int)
           or isinstance(r.get('sip_timestamp'), bool) for r in rows):
        return bad('INVALID_TIMESTAMP_SCHEMA')
    if any(not start_ns <= r['sip_timestamp'] < cutoff_ns for r in rows):
        return bad('OUT_OF_INTERVAL_RESPONSE')
    times = [r['sip_timestamp'] for r in rows]
    if times != sorted(times, reverse=True):
        return bad('UNEXPECTED_RESPONSE_ORDER')
    latest = times[0]
    tied = [r for r in rows if r['sip_timestamp'] == latest]
    if len(rows) >= 64 and len(tied) == len(rows):
        return bad('UNRESOLVED_TIMESTAMP_TIE')
    if len(tied) > 1 and any(not isinstance(r.get('sequence_number'), int)
                             or isinstance(r.get('sequence_number'), bool) for r in tied):
        return bad('UNRESOLVED_SEQUENCE_TIE')
    row = max(tied, key=lambda r: r.get('sequence_number', 0))
    if len(tied) > 1:
        chosen = [r for r in tied if r.get('sequence_number') == row.get('sequence_number')]
        if any(r != row for r in chosen):
            return bad('CONFLICTING_LATEST_STATE')
    age = (cutoff_ns-latest)/1e9
    base = {'sip_timestamp': latest, 'age_seconds': age,
            'condition_metadata_present': 'conditions' in row}
    for key in ('bid_price','ask_price','bid_size','ask_size'):
        value = row.get(key)
        if isinstance(value, bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
            return dict(base, **bad('INVALID_QUOTE_SCHEMA'))
    bid, ask = row['bid_price'], row['ask_price']
    if bid < 0 or ask <= 0 or bid > ask or row['bid_size'] <= 0 or row['ask_size'] <= 0:
        return dict(base, **bad('INVALID_LATEST_QUOTE_STATE'))
    if row.get('conditions') not in (None, []):
        return dict(base, **bad('UNVERIFIED_QUOTE_CONDITION'))
    if age > max_age_seconds:
        return dict(base, **bad('STALE_LATEST_QUOTE_STATE'))
    return dict(base, status='VALID_INDICATIVE_QUOTE', mid=bid/2+ask/2,
                bid=bid, ask=ask, bid_size=row['bid_size'], ask_size=row['ask_size'],
                spread=ask-bid)


def standard_contract(result, pe, leg_key):
    """Explicit metadata validation; missing multiplier is not assumed 100."""
    leg = pe['legs'][leg_key]
    if not isinstance(result, dict):
        return 'METADATA_UNAVAILABLE'
    if result.get('shares_per_contract') != 100:
        return 'NONSTANDARD_OR_MISSING_MULTIPLIER'
    if result.get('additional_underlyings'):
        return 'ADDITIONAL_DELIVERABLE'
    checks = (result.get('ticker') == leg['ticker'],
              result.get('contract_type') == leg['kind'],
              result.get('strike_price') == leg['strike'],
              result.get('expiration_date') == pe['expiry'][:10],
              result.get('underlying_ticker') in {pe['ticker'], 'GOOG' if pe['ticker']=='GOOGL' else pe['ticker']})
    return 'STANDARD_METADATA' if all(checks) else 'CONTRACT_IDENTITY_MISMATCH'


def three_leg_mark(states, strike, expiry, day, max_sync_seconds=60):
    reasons = [k+':'+states.get(k,{}).get('status','MISSING_REQUIRED_LEG')
               for k in LEGS if states.get(k,{}).get('status')!='VALID_INDICATIVE_QUOTE']
    if reasons:
        return {'status': ';'.join(reasons), 'value_per_contract': None}
    selected = [states[k] for k in LEGS]
    span = (max(s['sip_timestamp'] for s in selected) - min(s['sip_timestamp'] for s in selected))/1e9
    if span > max_sync_seconds:
        return {'status':'ASYNCHRONOUS_THREE_LEG_STATE','value_per_contract':None,'sync_seconds':span}
    discount = float(strike)*math.exp(-.04*max((pd.Timestamp(expiry)-pd.Timestamp(day)).days,0)/365)
    stock = discount + states['C_K']['mid']-states['P_K']['mid']
    if not math.isfinite(stock) or stock <= 0:
        return {'status':'INVALID_PARITY_SPOT','value_per_contract':None}
    value = 100*(stock-states['C_U0.05']['mid'])
    if not math.isfinite(value):
        return {'status':'NONFINITE_POSITION_VALUE','value_per_contract':None}
    return {'status':'AVAILABLE_INDICATIVE_PARITY_MARK','value_per_contract':value,
            'synthetic_stock':stock, 'sync_seconds':span,
            'three_leg_half_spread_usd':50*sum(s['spread'] for s in selected),
            'min_displayed_size':min(min(s['bid_size'],s['ask_size']) for s in selected)}


def _position_scope_bounds(row, daily_index):
    """Scope an admitted position without inventing a window-end liquidation."""
    start = pd.Timestamp(row['entry_date'])
    actual = row.get('actual_exit')
    missing_actual = actual is None or actual == '' or bool(pd.isna(actual))
    scheduled = pd.Timestamp(row['scheduled_exit'])
    status = row['status']
    if status == 'CLOSED':
        if missing_actual:
            raise ValueError('Closed position requires an observed actual exit')
        end = pd.Timestamp(actual)
    elif status == 'OPEN_AT_WINDOW_END':
        if not missing_actual or pd.isna(scheduled) or scheduled <= daily_index.max():
            raise ValueError('Open-at-end requires no actual exit and a fixed exit after the observation window')
        end = daily_index.max()
    else:
        raise ValueError('Unsupported admitted position status; unresolved exits cannot be extended')
    if (pd.isna(start) or pd.isna(end) or start.tzinfo is not None or end.tzinfo is not None
            or start not in daily_index or end not in daily_index or end < start):
        raise ValueError('Admitted position dates must be ordered sessions inside the observed IS calendar')
    contracts = row['contracts']
    if isinstance(contracts, bool) or not isinstance(contracts, (int, float)) or not math.isfinite(contracts) or contracts <= 0 or contracts != int(contracts):
        raise ValueError('Admitted contract count must be a positive integer')
    return start, end


def build_scope(snapshot):
    daily = split_frame(snapshot['portfolio']['daily'], True)
    ledger = split_frame(snapshot['portfolio']['ledger'])
    if daily.empty or not daily.index.is_unique or not daily.index.is_monotonic_increasing:
        raise ValueError('Original daily calendar must be nonempty, sorted and unique')
    if daily.index.min()<pd.Timestamp('2024-01-01') or daily.index.max()>pd.Timestamp('2025-12-31'):
        raise ValueError('Original quote-valuation calendar outside IS')
    by_accession = {p['accession_number']:p for p in snapshot['priced_primary']}
    if len(by_accession)!=len(snapshot['priced_primary']):
        raise ValueError('Duplicate original priced-event identity')
    scope=[]
    for row in ledger.to_dict('records'):
        if row['status']=='SKIPPED' or not row['contracts']:
            continue
        start,end = _position_scope_bounds(row, daily.index)
        pe=by_accession[row['accession_number']]
        if pe['ticker']!=row['ticker']:
            raise ValueError('Original ledger/priced-event ticker mismatch')
        if start<pd.Timestamp('2024-01-01') or end>pd.Timestamp('2025-12-31') or end<start:
            raise ValueError('Original admitted position dates outside IS or reversed')
        for day in daily.index[(daily.index>=start)&(daily.index<=end)]:
            if not pd.Timestamp('2024-01-01')<=day<=pd.Timestamp('2025-12-31'):
                raise ValueError('Quote scope outside original IS')
            hour=13 if day.strftime('%Y-%m-%d') in {'2024-07-03','2024-11-29','2024-12-24','2025-07-03','2025-11-28','2025-12-24'} else 16
            opening=day.tz_localize('America/New_York')+pd.Timedelta(hours=9,minutes=30)
            cutoff=day.tz_localize('America/New_York')+pd.Timedelta(hours=hour)
            for key in LEGS:
                scope.append({'trade_id':row['trade_id'],'accession':row['accession_number'],'ticker':pe['ticker'],
                              'day':day.strftime('%Y-%m-%d'),'leg_key':key,'contract':pe['legs'][key]['ticker'],
                              'start_ns':int(opening.value),'cutoff_ns':int(cutoff.value),
                              'is_entry':day==start,'is_exit':row['status']=='CLOSED' and day==end,
                              'is_scope_end':day==end,'position_status':row['status']})
    return scope


def revalue_fixed_ledger(snapshot, quotes, metadata, max_age_seconds=60, max_sync_seconds=60):
    original = split_frame(snapshot['portfolio']['daily'], True)
    daily=original.copy(deep=True)
    # Original decisions/cashflows stay intact. Risk/valuation columns must not
    # retain old daily-bar values beside the new quote NAV under the same label.
    old_valuation_columns=('nav','net_return','drawdown','stock_gross','stock_gross_fraction',
                           'short_call_liability','stock_value_less_short_call_liability',
                           'gross_by_ticker','gross_by_sector','unknown_mark_reasons','new_entries_paused')
    for column in old_valuation_columns:
        if column in original:
            daily['original_'+column]=original[column]
    for column in ('unknown_mark_reasons','new_entries_paused'):
        if column in daily:
            daily=daily.drop(columns=column)
    for column in ('gross_by_ticker','gross_by_sector','quote_unknown_mark_reasons'):
        daily[column]=pd.Series([None]*len(daily),index=daily.index,dtype=object)
    ledger=split_frame(snapshot['portfolio']['ledger'])
    by_accession={p['accession_number']:p for p in snapshot['priced_primary']}
    marks, quality=[],[]
    grouped={}
    for item in build_scope(snapshot):
        quote_key=item['contract']+'|'+item['day']
        q=quotes.get(quote_key,{})
        state=latest_quote_state(q.get('rows',[]),item['start_ns'],item['cutoff_ns'],max_age_seconds)
        if q.get('status')!='OK':
            state={'status':q.get('status','REQUEST_UNAVAILABLE'),'mid':None}
        elif q.get('key') is not None and q['key']!=quote_key:
            state={'status':'SOURCE_QUOTE_KEY_MISMATCH','mid':None}
        pe=by_accession[item['accession']]
        meta=metadata.get(item['contract']+'|'+item['day'])
        if meta is not None:
            valid=standard_contract(meta,pe,item['leg_key'])
            if valid!='STANDARD_METADATA':
                state={'status':valid,'mid':None}
        quality.append({**item,**state})
        grouped.setdefault((item['trade_id'],item['day']),{})[item['leg_key']]=state
    for (trade_id,day),states in grouped.items():
        row=next(r for r in ledger.to_dict('records') if r['trade_id']==trade_id)
        pe=by_accession[row['accession_number']]
        # Validate metadata at entry and the observed scope end. For an open
        # position the latter is the final IS session, never its future sale.
        meta_errors=[]
        start,end = _position_scope_bounds(row, original.index)
        for boundary in (start.strftime('%Y-%m-%d'),end.strftime('%Y-%m-%d')):
            for key in LEGS:
                code=standard_contract(metadata.get(pe['legs'][key]['ticker']+'|'+boundary),pe,key)
                if code!='STANDARD_METADATA': meta_errors.append(code)
        mark=three_leg_mark(states,pe['strikes']['K'],pe['expiry'],day,max_sync_seconds)
        if meta_errors: mark={'status':';'.join(sorted(set(meta_errors))),'value_per_contract':None}
        marks.append({'trade_id':trade_id,'day':day,'ticker':pe['ticker'],**mark})
    mark_by_id={(r['trade_id'],r['day']):r for r in marks}
    for day in daily.index:
        open_rows=[r for r in ledger.to_dict('records') if r['contracts'] and r['status']!='SKIPPED'
                   and pd.Timestamp(r['entry_date'])<=day
                   and (r['status']=='OPEN_AT_WINDOW_END' or day<pd.Timestamp(r['actual_exit']))]
        required=[mark_by_id[(r['trade_id'],day.strftime('%Y-%m-%d'))] for r in open_rows]
        valid=all(m['value_per_contract'] is not None for m in required)
        daily.loc[day,'nav']=float(original.loc[day,'cash'])+sum(r['contracts']*m['value_per_contract'] for r,m in zip(open_rows,required)) if valid else np.nan
        daily.loc[day,'stock_gross']=sum(r['contracts']*100*m['synthetic_stock'] for r,m in zip(open_rows,required)) if valid else np.nan
        daily.loc[day,'short_call_liability']=sum(r['contracts']*(100*m['synthetic_stock']-m['value_per_contract']) for r,m in zip(open_rows,required)) if valid else np.nan
        daily.loc[day,'stock_value_less_short_call_liability']=sum(r['contracts']*m['value_per_contract'] for r,m in zip(open_rows,required)) if valid else np.nan
        nav=float(daily.loc[day,'nav'])
        daily.loc[day,'stock_gross_fraction']=daily.loc[day,'stock_gross']/nav if valid and nav>0 else np.nan
        names,sectors={},{}
        if valid:
            for row,mark in zip(open_rows,required):
                gross=row['contracts']*100*mark['synthetic_stock']
                names[row['ticker']]=names.get(row['ticker'],0)+gross
                sector=row.get('sector','UNVERIFIED_SECTOR')
                sectors[sector]=sectors.get(sector,0)+gross
        daily.at[day,'gross_by_ticker']=names if valid else None
        daily.at[day,'gross_by_sector']=sectors if valid else None
        daily.at[day,'quote_unknown_mark_reasons']=tuple(m['trade_id']+':'+m['status'] for m in required if m['value_per_contract'] is None)
    # Full path drawdown is unavailable if any quote NAV remains unknown. The
    # observed excursion is retained separately, with the original capital peak.
    initial=float(snapshot['portfolio']['config']['initial_nav'])
    peak=initial
    observed=[]
    for nav in daily['nav']:
        if math.isfinite(float(nav)):
            peak=max(peak,float(nav)); observed.append(1-float(nav)/peak)
        else:
            observed.append(np.nan)
    daily['observed_drawdown_lower_bound']=observed
    daily['drawdown']=observed if daily.nav.notna().all() else np.nan
    previous=daily['nav'].shift(1); previous.iloc[0]=snapshot['portfolio']['config']['initial_nav']
    daily['net_return']=daily['nav']/previous-1
    return {'daily':daily,'marks':pd.DataFrame(marks),'quality':pd.DataFrame(quality),
            'coverage':dict(Counter(r['status'] for r in marks)),
            'convention':'Fixed original cashflows/admissions; uniform indicative quote marks only',
            'risk_column_convention':'Original decisions are original_*; quote NAV/accounting risk columns recomputed without resimulating risk gates',
            'max_age_seconds':max_age_seconds,'nav_gaps':int(daily.nav.isna().sum())}
