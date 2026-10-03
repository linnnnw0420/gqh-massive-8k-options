"""Derive predeclared capacity evidence from an immutable saved IS ledger.

No authentication or network requests occur in this stage. Capacity diagnostics
do not change the frozen admissions, contracts, costs, or risk controls.
"""
from __future__ import annotations

import json
from pathlib import Path

from capacity_evidence import derive_capacity
from diagnostics_common import (argument_parser, load_snapshot, resolve_paths,
                                sanitized_main, sha256)
from risk_evidence import _jsonable


def validate_inputs(paths):
    snapshot = load_snapshot(paths)
    manifest_path = paths.work_dir / 'uniform_quote_manifest.json'
    quote_path = paths.work_dir / 'uniform_quote_inputs.private.json'
    volume_path = paths.work_dir / 'volume_inputs.private.json'
    volume_manifest_path = paths.work_dir / 'volume_manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    if manifest['source_sha256'] != sha256(paths.snapshot):
        raise ValueError('Quote manifest belongs to a different input snapshot.')
    quotes = json.loads(quote_path.read_text(encoding='utf-8-sig'))
    if quotes['manifest_hash'] != sha256(manifest_path):
        raise ValueError('Quote inputs belong to a different manifest.')
    volume_manifest = json.loads(volume_manifest_path.read_text(encoding='utf-8-sig'))
    if ('source_sha256' in volume_manifest and
            volume_manifest['source_sha256'] != sha256(paths.snapshot)):
        raise ValueError('Volume manifest belongs to a different input snapshot.')
    volumes = json.loads(volume_path.read_text(encoding='utf-8-sig'))
    if ('manifest_hash' in volumes and
            volumes['manifest_hash'] != sha256(volume_manifest_path)):
        raise ValueError('Volume inputs belong to a different manifest.')
    # Older original volume files have no manifest hash. Preserve their bytes,
    # but require exact request identity and scope against their immutable log.
    requests = {item['key']:item for item in volume_manifest['requests']}
    records = volumes['records']
    if len(requests) != len(volume_manifest['requests']) or len(records) != len(requests):
        raise ValueError('Incomplete or duplicate volume requests.')
    identities = set()
    for record in records:
        key = record['key']; item = requests.get(key)
        if item is None or key in identities:
            raise ValueError('Mismatched or duplicate volume response identity.')
        identities.add(key)
        for field in ('contract','start','entry','exit'):
            if record.get(field) != item[field]:
                raise ValueError('Volume response scope does not match its manifest.')
    return snapshot, quotes, volumes, (quote_path, volume_path, manifest_path, volume_manifest_path)


def calculate(paths, snapshot, quotes, volumes, input_paths):
    summary, private = derive_capacity(snapshot, quotes, volumes)
    summary['source_sha256'] = {path.name:sha256(path) for path in (paths.snapshot,*input_paths)}
    here = Path(__file__).resolve().parent
    summary['implementation_sha256'] = {name:sha256(here / name) for name in
        ('capacity_evidence.py','quote_valuation.py','run_capacity_diagnostics.py')}
    summary['no_revised_trade_admissions'] = True
    summary['oos_access'] = False
    summary['sealed_access'] = False
    (paths.work_dir / 'capacity_evidence_summary.json').write_text(
        json.dumps(_jsonable(summary),indent=2,allow_nan=False)+'\n',encoding='utf-8')
    (paths.work_dir / 'capacity_details.private.json').write_text(
        json.dumps(_jsonable(private),indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'status':'derived_capacity_only','positions':summary['actual_entered_positions'],
                      'closed_positions':summary['closed_positions'],
                      'open_positions':summary['open_at_window_end_positions'],
                      'strict_leg_histories':summary['all_twenty_bars_observed_leg_count'],
                      'oos_access':False}))


def main():
    paths = resolve_paths(argument_parser(__doc__).parse_args())
    inputs = validate_inputs(paths)
    if not paths.execute:
        print(json.dumps({'execute':False,'snapshot_sha256':sha256(paths.snapshot),
                          'no_network_requests':True,'no_capacity_calculation':True}))
        return
    calculate(paths,*inputs)


if __name__ == '__main__':
    sanitized_main(main)
