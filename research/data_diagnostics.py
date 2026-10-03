"""One portable command for the fixed IS snapshot's private data diagnostics.

This consumes a study snapshot; it never selects events or simulates trades.
An upstream reproduction entry point can call run_from_snapshot after its study.
Default execution prepares immutable manifests only. --execute is explicit.
"""
from __future__ import annotations
import argparse
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys

from diagnostics_common import (argument_parser, load_snapshot, provenance,
                                resolve_paths, sanitized_main, save_or_match_manifest, sha256)

STAGES = ('quotes','factors','volume','valuation','capacity')
SCRIPTS = {'quotes':'fetch_uniform_quotes.py','factors':'fetch_is_factors.py',
           'volume':'fetch_is_volume.py','valuation':'run_quote_supplement.py',
           'capacity':'run_capacity_diagnostics.py'}


def prepare(paths, stages):
    load_snapshot(paths)  # Guard before copying, authentication or requests.
    destination = paths.work_dir / 'first_is_state.json'
    if destination.exists() and destination.read_bytes() != paths.snapshot.read_bytes():
        raise ValueError('Run directory already contains a different immutable study snapshot.')
    paths.work_dir.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        destination.write_bytes(paths.snapshot.read_bytes())
    paths = replace(paths, snapshot=destination)
    here = Path(__file__).resolve().parent
    files = ('diagnostics_common.py','data_diagnostics.py','quote_valuation.py','risk_evidence.py','capacity_evidence.py',*SCRIPTS.values())
    manifest = {**provenance(paths), 'kind':'fixed_IS_snapshot_diagnostics',
                'source_code_sha256':{name:sha256(here / name) for name in files},
                'stage_scope':list(STAGES), 'valuation_conventions':[60,300,'standing'],
                'no_new_strategy_or_admission_simulation':True,
                'snapshot_copy_preserves_original_bytes':True}
    save_or_match_manifest(paths.work_dir / 'diagnostics_run_manifest.json', manifest,
                           ('source_sha256','source_code_sha256'))
    return paths


def run_from_snapshot(project, work_dir, snapshot, protocol_file, execute=False, stages=STAGES):
    """Library integration for the repository's upstream reproduction command."""
    if not stages or any(stage not in STAGES for stage in stages):
        raise ValueError('Unknown diagnostic stage.')
    args = argparse.Namespace(project=Path(project), work_dir=Path(work_dir), snapshot=Path(snapshot),
                              protocol_file=Path(protocol_file), execute=execute)
    paths = prepare(resolve_paths(args), stages)
    if not execute:
        # These plan functions contain no authentication, HTTP or pricing/risk
        # calculation. Valuation is not invoked during dry planning.
        from fetch_uniform_quotes import plan as quote_plan
        from fetch_is_factors import plan as factor_plan
        from fetch_is_volume import plan as volume_plan
        planners = {'quotes':quote_plan,'factors':factor_plan,'volume':volume_plan}
        for stage in stages:
            if stage in planners:
                planners[stage](paths)
        print(json.dumps({'execute':False,'stages':list(stages),'snapshot_sha256':sha256(paths.snapshot),
                          'private_work_dir':str(paths.work_dir),'no_data_fetched':True,
                          'no_valuation_or_trade_simulation':True}))
        return
    here = Path(__file__).resolve().parent
    for stage in stages:
        command = [sys.executable,str(here / SCRIPTS[stage]),'--project',str(paths.project),
                   '--work-dir',str(paths.work_dir),'--snapshot',str(paths.snapshot),
                   '--protocol-file',str(paths.protocol),'--execute']
        subprocess.run(command, check=True)
    summary = {'execute':True,'completed_stages':list(stages),
               'snapshot_sha256':sha256(paths.snapshot),'oos_access':False,'sealed_access':False,
               'no_new_strategy_or_admission_simulation':True}
    (paths.work_dir / 'diagnostics_execution_summary.json').write_text(json.dumps(summary,indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary))


def main():
    parser = argument_parser(__doc__)
    parser.add_argument('--stage', choices=('all',*STAGES), default='all',
                        help='Run all stages or one specified stage; valuation and capacity perform no HTTP.')
    args = parser.parse_args()
    paths = resolve_paths(args)
    stages = STAGES if args.stage=='all' else (args.stage,)
    run_from_snapshot(paths.project,paths.work_dir,paths.snapshot,paths.protocol,args.execute,stages)


if __name__ == '__main__':
    sanitized_main(main)
