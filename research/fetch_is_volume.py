"""Plan or fetch original-contract ADV evidence through the observed IS scope."""
from __future__ import annotations
import json
import pandas as pd
from diagnostics_common import (argument_parser, load_snapshot, private_cache,
                                provenance, resolve_paths, sanitized_main, save_or_match_manifest, sha256)
from fetch_uniform_quotes import auth, fetch_one
from quote_valuation import build_scope, split_frame, LEGS


def plan(paths):
    snapshot = load_snapshot(paths)
    ledger = split_frame(snapshot['portfolio']['ledger'])
    by_acc = {p['accession_number']:p for p in snapshot['priced_primary']}
    # The validated quotation scope ends at the actual closed exit, or the last
    # observed IS session for an open position. Never fetch a future scheduled exit.
    scope_ends = {}
    for scope in build_scope(snapshot):
        scope_ends[scope['trade_id']] = max(scope_ends.get(scope['trade_id'], scope['day']), scope['day'])
    items = []
    for row in ledger.to_dict('records'):
        if not row['contracts'] or row['status']=='SKIPPED':
            continue
        pe = by_acc[row['accession_number']]
        start = (pd.Timestamp(row['entry_date'])-pd.Timedelta(days=40)).strftime('%Y-%m-%d')
        end = scope_ends[row['trade_id']]
        if not ('2024-01-01' <= start <= end <= '2025-12-31'):
            raise ValueError('Volume scope outside IS')
        for leg in LEGS:
            contract = pe['legs'][leg]['ticker']
            items.append({'kind':'option_volume','key':str(row['trade_id'])+'|'+leg,'contract':contract,
                          'entry':str(row['entry_date'])[:10],'exit':end,'start':start,
                          'path':f'/v2/aggs/ticker/{contract}/range/1/day/{start}/{end}',
                          'params':{'adjusted':'false','sort':'asc','limit':50000}})
    manifest = {**provenance(paths), 'requests':items,
                'lookback_sessions':20,'participation_scenarios':[0.005,0.01,0.02],
                'purpose':'retrospective capacity evidence; no revised trade admissions',
                'missing_volume_convention':'report actual observed-bar coverage separately from absent-bar-as-zero convention',
                'open_position_end_convention':'last observed IS session; not a realized exit'}
    return save_or_match_manifest(paths.work_dir / 'volume_manifest.json', manifest)


def main():
    paths = resolve_paths(argument_parser(__doc__).parse_args())
    manifest = plan(paths)
    if not paths.execute:
        print(json.dumps({'requests':len(manifest['requests']),'execute':False,'oos_access':False}))
        return
    cache = private_cache(paths, 'volume_evidence_is_v1')
    key = auth(paths.project); records = []
    for item in manifest['requests']:
        record = fetch_one(item,key,cache)
        rows = record.get('rows',[])
        if rows:
            dates = pd.to_datetime([r['t'] for r in rows],unit='ms',utc=True).tz_convert('America/New_York').tz_localize(None).normalize()
            if not ((dates>=pd.Timestamp(item['start'])) & (dates<=pd.Timestamp(item['exit']))).all():
                raise ValueError('Volume response outside authorized interval')
        records.append({**record,'contract':item['contract'],'start':item['start'],'entry':item['entry'],'exit':item['exit']})
    key = None
    (paths.work_dir / 'volume_inputs.private.json').write_text(
        json.dumps({'records':records,'manifest_hash':sha256(paths.work_dir / 'volume_manifest.json')},allow_nan=False), encoding='utf-8')
    print(json.dumps({'requests':len(records),'successes':sum(r['status']=='OK' for r in records),'oos_access':False}))


if __name__ == '__main__':
    sanitized_main(main)
