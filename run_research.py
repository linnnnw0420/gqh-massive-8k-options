"""One entry for offline checks and the accepted Massive IS/one-shot OOS study."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest
import hashlib

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    project=Path(__file__).resolve().parent
    research=project/'research'
    sys.path.insert(0,str(research))
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=('check','submission'),default='check')
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--offline',action='store_true',help='Use immutable cached inputs only.')
    parser.add_argument('--start',default='2024-01-01')
    parser.add_argument('--end',default='2025-12-31')
    parser.add_argument('--accept-operational-revision',action='store_true')
    parser.add_argument('--approve-oos-once',action='store_true')
    args=parser.parse_args()
    if args.mode=='check':
        suite=unittest.defaultTestLoader.discover(str(project/'tests'))
        result=unittest.TextTestRunner(verbosity=2).run(suite)
        raise SystemExit(0 if result.wasSuccessful() else 1)
    if args.mode == 'submission':
        from submission_variant import VERSION, TIMING_BASIS, run_submission
        if not args.execute:
            print({"status": "ADOPTED_READY_FOR_REVISED_IS", "version": VERSION,
                "event_definition": "Literal Massive acquisition_agreement OR merger_agreement",
                "timing_basis": TIMING_BASIS,
                "changes_original_screened_event_definition": True,
                "OOS_data_read": False, "API_calls": 0})
            return
        if not args.accept_operational_revision:
            raise SystemExit('This is a disclosed post-IS event-and-timing revision. Explicitly accept it before execution.')
        from safe_transport import MassiveSubmission
        from research_runtime import SubmissionFence
        from submission_variant import check_window
        import pandas as pd
        from risk_evidence import _jsonable
        JOURNAL_NAME = "oos_once_2026.private.json"
        import json
        root = project / '.massive_cache' / 'submission_v4'
        root.mkdir(parents=True, exist_ok=True)
        code_files = ['run_research.py', 'strategy_defs.py', 'requirements.txt']
        code_files += [str(p.relative_to(project)) for p in sorted(research.glob('*.py'))]
        import ast, hashlib
        from research_runtime import _source
        fingerprint = {name: (hashlib.sha256(ast.dump(ast.parse(_source(project / name)), include_attributes=False).encode()).hexdigest()
            if name.endswith('.ipynb') else sha(project / name)) for name in code_files}
        role = 'is' if args.end <= '2025-12-31' else 'oos'
        check_window(args.start, args.end, role=role, authorized=args.approve_oos_once)
        fence = SubmissionFence(args.start, args.end, None, None,
            warmup_start=str((pd.Timestamp(args.start) - pd.Timedelta(days=31)).date()))
        transport = MassiveSubmission(project, fence=fence, offline=args.offline)
        if role == 'oos':
            if not args.approve_oos_once:
                raise SystemExit('Contestant OOS requires --approve-oos-once after reviewing this concrete version.')
            is_manifest = root / 'is' / 'run_manifest.private.json'
            if not is_manifest.is_file():
                raise SystemExit('First run this same fixed version on IS; the original screened IS is a different version.')
            prior = json.loads(is_manifest.read_text())
            if prior.get('status') != 'COMPLETE' or prior.get('file_sha256') != fingerprint:
                raise SystemExit('The completed revised IS must match the current source; do not tune after OOS.')
            if (project / '.massive_cache' / JOURNAL_NAME).exists():
                raise SystemExit('The global OOS attempt already exists; preserve it and do not retry automatically.')
        output = root / role
        if output.exists():
            raise SystemExit('This version already has a run record. Preserve it; do not overwrite results.')
        output.mkdir()
        journal = project / '.massive_cache' / JOURNAL_NAME
        claimed = False
        record = {'status': 'STARTED', 'started_utc': datetime.now(timezone.utc).isoformat(),
            'version': VERSION, 'window': [args.start, args.end],
            'role': role, 'file_sha256': fingerprint, 'public_upload': False}
        def claim_outcomes():
            nonlocal claimed
            if role != 'oos':
                return
            with journal.open('x') as handle:
                json.dump(dict(record, status='STARTED_ATTEMPT_CONSUMED'), handle, indent=2)
            claimed = True
        try:
            result = run_submission(project / 'strategy_defs.py',
                args.start, args.end, transport.get, transport.all, role=role,
                authorized=role == 'oos', before_market=claim_outcomes if role == 'oos' else None)
            payload = result.to_private_snapshot()
            payload['portfolio']['metrics'] = result.portfolio.get('metrics', {})
            (output / 'snapshot.private.json').write_text(json.dumps(_jsonable(payload), allow_nan=False))
            # Aggregated derived evidence stays local. Raw filing/option inputs
            # are private; no publication is performed by this command.
            for name in ('theta_board', 'official_diff', 'sensitivity', 'implied_realized', 'ordinary_implied_realized', 'stress_theta_board'):
                result.tables[name].to_csv(output / (name + '.csv'), index=False)
            result.portfolio['daily'].to_csv(output / 'portfolio_daily.private.csv', index=True)
            record.update(status='COMPLETE', completed_utc=datetime.now(timezone.utc).isoformat(), runtime=result.manifest,
                snapshot_sha256=sha(output / 'snapshot.private.json'))
            print({'status': 'COMPLETE', 'role': role, 'events': len(result.tables['events']),
                'outputs': str(output.relative_to(project)), 'publication': 'LOCAL_ONLY'})
        except Exception as exc:
            record.update(status='FAILED_ATTEMPT_CONSUMED' if claimed else 'FAILED_BEFORE_OUTCOME_REQUEST',
                error_type=type(exc).__name__)
            raise RuntimeError('Study failed; preserve its private record. No alternate parameters or automatic rerun.') from None
        finally:
            record['transport'] = transport.manifest()
            encoded = json.dumps(_jsonable(record), indent=2, allow_nan=False)
            (output / 'run_manifest.private.json').write_text(encoded)
            if claimed:
                journal.write_text(encoded)
        return

if __name__=='__main__':
    main()
