"""Competition research entry point. OOS and judges' sealed data stay disabled."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
import unittest


def main():
    project = Path(__file__).resolve().parent
    research = project / 'research'
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('check', 'complete-is', 'report', 'oos'), default='check')
    parser.add_argument('--execute', action='store_true', help='Explicitly authorize the IS data/analysis stages; never enables OOS.')
    parser.add_argument('--offline', action='store_true', help='Original/corrected study may use existing cache only. Diagnostics require their existing cached inputs; do not combine with complete-is.')
    parser.add_argument('--run-dir', type=Path, help='Private run parent, below .massive_cache; report mode requires it.')
    args = parser.parse_args()
    sys.path.insert(0, str(research))
    if args.mode == 'oos':
        raise SystemExit('OOS NOT READY: complete unseen-window filing sources/classification have not passed validation. A flag cannot waive this gate.')
    if args.mode == 'check':
        suite = unittest.defaultTestLoader.discover(str(project / 'tests'))
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        raise SystemExit(0 if result.wasSuccessful() else 1)
    if args.mode == 'complete-is' and (not args.execute or args.offline):
        raise SystemExit('Use --mode complete-is --execute for the bounded full IS reproduction. For pure cached study reproduction use research/reproduce_is.py --offline; report mode performs no API calls.')
    private_root = (project / '.massive_cache').resolve()
    root = args.run_dir or Path('.massive_cache/research_runs') / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    root = (root if root.is_absolute() else project / root).resolve()
    if not root.is_relative_to(private_root) or root == private_root:
        raise SystemExit('Execution state and licensed inputs must stay in a directory below .massive_cache.')
    if args.mode == 'report' and not args.run_dir:
        raise SystemExit('Report mode needs the existing private --run-dir; it never fetches data or runs trades.')
    if args.mode == 'complete-is':
        from data_diagnostics import run_from_snapshot
        for version, correction in (('original', None), ('corrected', research / 'correction_execution_v2.json')):
            work = root / version
            command = [sys.executable, '-u', str(research / 'reproduce_is.py'), '--project', str(project),
                       '--source', str(project / 'gator-quant-hacks-8k-options-challenge.ipynb'), '--output-dir', str(work)]
            if correction:
                command += ['--correction', str(correction)]
            subprocess.run(command, check=True)
            run_from_snapshot(project, work / 'diagnostics', work / 'snapshot.private.json', project / 'RESEARCH_LOG.md', execute=True)
        causal = root / 'causal'
        subprocess.run([sys.executable, str(research / 'reproduce_causal_portfolio.py'),
                        '--project', str(project),
                        '--source', str(project / 'gator-quant-hacks-8k-options-challenge.ipynb'),
                        '--input-snapshot', str(root / 'corrected/snapshot.private.json'),
                        '--correction-file', str(research / 'correction_execution_v2.json'),
                        '--protocol-file', str(project / 'reports/causal_portfolio_protocol_v3.md'),
                        '--output-dir', str(causal)], check=True)
        run_from_snapshot(project, causal / 'diagnostics', causal / 'snapshot.private.json',
                          project / 'RESEARCH_LOG.md', execute=True)
    if not (root / 'causal/snapshot.private.json').is_file():
        raise SystemExit('Current report requires the declared causal V3 portfolio bundle; do not substitute the legacy portfolio.')
    public = project / 'reports'
    command = [sys.executable, str(research / 'export_public_report.py'),
               '--original-run', str(root / 'original'), '--corrected-run', str(root / 'corrected'),
               '--original-diagnostics', str(root / 'original/diagnostics'),
               '--corrected-diagnostics', str(root / 'corrected/diagnostics'),
               '--causal-run', str(root / 'causal'), '--causal-diagnostics', str(root / 'causal/diagnostics'),
               '--public-dir', str(public)]
    subprocess.run(command, check=True)
    subprocess.run([sys.executable, str(research / 'make_quant_note.py'), '--public-dir', str(public),
                    '--output', str(project / 'quant_note.pdf')], check=True)
    print('IS research report regenerated. OOS and unseen-window eligibility remain incomplete; see RULES.md.')


if __name__ == '__main__':
    main()
