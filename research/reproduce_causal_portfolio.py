"""Apply the declared V3 portfolio repair to the saved V2 study, without HTTP."""
from __future__ import annotations
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pandas as pd

from causal_portfolio import simulate_causal_portfolio
from research_runtime import load_runtime, _source
from reproduce_is import FROZEN_SOURCE_AST_SHA256
from risk_evidence import _jsonable, summarize_existing_is

FROZEN_V3_PROTOCOL_SHA256 = '13d5c39407021a1c78a26aab6b9473264f9624a349021fffaa60e1de49be6e99'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def reconstruct_priced(snapshot, namespace):
    fields = ('ticker', 'event_date', 't_pre', 't_0', 'entry_day', 'accepted_at',
              'accession_number', 'source_tags', 'bucket', 'expiry', 'expiry_session',
              'spot_pre', 'strikes', 'observation_end')
    dates = ('event_date', 't_pre', 't_0', 'entry_day', 'accepted_at', 'expiry',
             'expiry_session', 'observation_end')
    result = []
    for item in snapshot['priced_primary']:
        values = {key: item[key] for key in fields}
        for key in dates:
            values[key] = pd.Timestamp(values[key]) if values[key] is not None else None
        for key in ('event_date','t_0','entry_day','observation_end'):
            value=values[key]
            if (value is None or pd.isna(value) or value.tzinfo is not None or value!=value.normalize()
                    or not pd.Timestamp('2024-01-01')<=value<=pd.Timestamp('2025-12-31')):
                raise ValueError('Saved event, entry and observation dates must remain inside IS.')
        if values['observation_end']!=pd.Timestamp('2025-12-31'):
            raise ValueError('Saved observation end differs from the fixed V2 IS window.')
        accepted=values['accepted_at'];pre=values['t_pre']
        if (accepted is None or pd.isna(accepted) or accepted.tzinfo is not None
                or not pd.Timestamp('2024-01-01')<=accepted.normalize()<=pd.Timestamp('2025-12-31')):
            raise ValueError('Saved acceptance timestamp must be an IS Eastern clock.')
        if (pre is None or pd.isna(pre) or pre.tzinfo is not None or pre!=pre.normalize()
                or not pd.Timestamp('2023-12-01')<=pre<=values['entry_day']):
            raise ValueError('Saved pre-event feature date exceeds its allowed history/entry cutoff.')
        for key in ('expiry','expiry_session'):
            value=values[key]
            if value is None or pd.isna(value) or value.tzinfo is not None or value!=value.normalize():
                raise ValueError('Saved expiry metadata must be a finite session/date; future expiry metadata is permitted.')
        values['source_tags'] = tuple(values['source_tags'])
        legs = {}
        for name, leg in item['legs'].items():
            raw = leg['bars']
            bars = pd.DataFrame(raw['data'], columns=raw['columns'], index=pd.to_datetime(raw['index']))
            if (not bars.index.is_monotonic_increasing or bars.index.has_duplicates or bars.index.hasnans
                    or bars.index.tz is not None or not bars.index.equals(bars.index.normalize())
                    or not {'open','close','volume'}<=set(bars.columns)):
                raise ValueError('Noncanonical bar history in the saved snapshot.')
            if len(bars) and (bars.index.min() < pd.Timestamp('2023-12-01') or bars.index.max() > pd.Timestamp('2025-12-31')):
                raise ValueError('Saved prices exceed the declared IS and feature-history fence.')
            legs[name] = namespace['Leg'](leg['ticker'], leg['kind'], leg['strike'], bars)
        values['legs'] = legs
        result.append(namespace['PricedEvent'](**values))
    return result


def run(project, source, input_snapshot, correction_file, protocol_file, output_dir):
    project, output_dir = Path(project).resolve(), Path(output_dir).resolve()
    private = project / '.massive_cache'
    if not output_dir.is_relative_to(private) or not Path(input_snapshot).resolve().is_relative_to(private):
        raise ValueError('Licensed snapshots must remain below the project private cache.')
    if (output_dir / 'snapshot.private.json').exists():
        raise ValueError('A completed portfolio version cannot be overwritten.')
    source_ast = hashlib.sha256(ast.dump(ast.parse(_source(source)), include_attributes=False).encode()).hexdigest()
    if source_ast != FROZEN_SOURCE_AST_SHA256:
        raise ValueError('Unexpected notebook source version.')
    snapshot = json.loads(Path(input_snapshot).read_text())
    source_manifest_path=Path(input_snapshot).parent/'run_manifest.json'
    source_manifest=json.loads(source_manifest_path.read_text())
    digest=sha(input_snapshot)
    if (source_manifest.get('status')!='COMPLETE' or source_manifest.get('mode')!='corrected_is_v2'
            or source_manifest.get('snapshot_sha256')!=digest):
        raise ValueError('V3 input must match its paired completed V2 manifest and snapshot hash.')
    if snapshot.get('oos_read') is not False or snapshot.get('runtime_manifest', {}).get('event_mode') != 'corrected_is_v2':
        raise ValueError('V3 requires the explicit corrected IS snapshot.')
    for record in (snapshot.get('runtime_manifest',{}),source_manifest.get('runtime',{})):
        if record.get('oos_access') is not False or record.get('sealed_access') is not False:
            raise ValueError('V3 requires explicit no-OOS/no-sealed provenance in snapshot and source manifest.')
    if sha(protocol_file) != FROZEN_V3_PROTOCOL_SHA256:
        raise ValueError('Unreviewed V3 decision protocol.')
    correction = json.loads(Path(correction_file).read_text())
    from reproduce_is import CORRECTION_SHA256
    if sha(correction_file) != CORRECTION_SHA256:
        raise ValueError('Unreviewed event correction manifest.')
    def no_io(*args, **kwargs):
        raise AssertionError('V3 replay performs no HTTP or new event study.')
    runtime = load_runtime(source, no_io, no_io, warmup_start='2023-12-01')
    sectors = {**runtime.namespace['SECTOR_BY_TICKER'], **correction.get('additional_industry_groups', {})}
    priced = reconstruct_priced(snapshot, runtime.namespace)
    manifest = {'mode': 'causal_portfolio_v3', 'status': 'STARTED',
                'started_utc': datetime.now(timezone.utc).isoformat(),
                'window': ['2024-01-01', '2025-12-31'],
                'source_snapshot_sha256': digest, 'source_run_manifest_sha256':sha(source_manifest_path), 'source_ast_sha256': source_ast,
                'protocol_sha256': sha(protocol_file), 'code_sha256': sha(Path(__file__).with_name('causal_portfolio.py')),
                'correction_sha256': sha(correction_file), 'no_api_calls': True,
                'event_tables_unchanged': True, 'event_study_version': 'corrected_is_v2',
                'post_is_implementation_repair': True, 'oos_read': False}
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / 'run_manifest.json').write_text(json.dumps(manifest, indent=2))
    portfolio = simulate_causal_portfolio(priced, '2024-01-01', '2025-12-31', sectors,
                                         namespace=runtime.namespace, clock=runtime.clock)
    portfolio_json = {key: json.loads(value.to_json(orient='split', date_format='iso'))
                      if isinstance(value, pd.DataFrame) else value
                      for key, value in portfolio.items()}
    revised = dict(snapshot)
    revised['portfolio'] = portfolio_json
    revised['portfolio_runtime_manifest'] = {**manifest,'status':'COMPLETE',
        'completed_utc':datetime.now(timezone.utc).isoformat(),
        'self_snapshot_hash_location':'External run_manifest.json; omitted here to avoid a circular hash'}
    revised['kind'] = 'private_corrected_v2_study_with_causal_v3_portfolio_contains_licensed_inputs'
    payload = json.dumps(_jsonable(revised), allow_nan=False)
    (output_dir / 'snapshot.private.json').write_text(payload)
    days = runtime.clock.sessions
    evidence = summarize_existing_is(revised, days[(days >= '2024-01-01') & (days <= '2025-12-31')])
    evidence['snapshot_sha256'] = hashlib.sha256(payload.encode()).hexdigest()
    evidence['event_study_version'] = 'corrected_is_v2'
    evidence['portfolio_version'] = 'causal_portfolio_v3'
    (output_dir / 'aggregate_evidence.json').write_text(json.dumps(_jsonable(evidence), indent=2, allow_nan=False))
    manifest.update(status='COMPLETE', completed_utc=datetime.now(timezone.utc).isoformat(),
                    snapshot_sha256=evidence['snapshot_sha256'])
    (output_dir / 'run_manifest.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps({'status': 'COMPLETE', 'mode': manifest['mode'],
                      'event_tables_unchanged': revised['tables'] == snapshot['tables'],
                      'ledger_status': portfolio['ledger']['status'].value_counts().to_dict(),
                      'nav_gaps': evidence['calendar']['nav_gaps'], 'no_api_calls': True}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--input-snapshot', type=Path, required=True)
    parser.add_argument('--correction-file', type=Path, required=True)
    parser.add_argument('--protocol-file', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    run(**vars(args))
