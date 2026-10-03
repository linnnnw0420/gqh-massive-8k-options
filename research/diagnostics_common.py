"""Portable CLI paths and immutable private diagnostic manifests.

Importing this module performs no I/O, authentication, requests or calculations.
Licensed inputs and outputs must remain under the project's .massive_cache.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


@dataclass(frozen=True)
class Paths:
    project: Path
    work_dir: Path
    snapshot: Path
    protocol: Path
    execute: bool


def argument_parser(description):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('--project', type=Path, default=Path.cwd(), help='Repository root; default: current directory.')
    parser.add_argument('--work-dir', type=Path, default=Path('.massive_cache/research_runs/original'),
                        help='Private run directory, absolute or relative to --project.')
    parser.add_argument('--snapshot', type=Path,
                        help='Input snapshot, absolute or relative to --project; default: work-dir/first_is_state.json.')
    parser.add_argument('--protocol-file', type=Path, default=Path('RESEARCH_LOG.md'),
                        help='Read-only protocol/provenance file, absolute or relative to --project.')
    parser.add_argument('--execute', action='store_true', help='Explicitly enable this stage; default only validates/plans.')
    return parser


def resolve_paths(args):
    project = args.project.expanduser().resolve()
    work = (args.work_dir if args.work_dir.is_absolute() else project / args.work_dir).expanduser().resolve()
    private_root = (project / '.massive_cache').resolve()
    if not work.is_relative_to(private_root) or work == private_root:
        raise ValueError('Diagnostic work-dir must be a run directory below project/.massive_cache.')
    snapshot = args.snapshot if args.snapshot is not None else work / 'first_is_state.json'
    snapshot = (snapshot if snapshot.is_absolute() else project / snapshot).expanduser().resolve()
    if not snapshot.is_relative_to(private_root):
        raise ValueError('Input snapshot must remain below project/.massive_cache.')
    protocol = (args.protocol_file if args.protocol_file.is_absolute() else project / args.protocol_file).expanduser().resolve()
    if protocol.suffix.lower() != '.md':
        raise ValueError('Protocol provenance must be a read-only Markdown research file.')
    if not project.is_dir() or not snapshot.is_file() or not protocol.is_file():
        raise ValueError('Project, private snapshot and read-only protocol file are required.')
    return Paths(project, work, snapshot, protocol, args.execute)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_snapshot(paths):
    snapshot = json.loads(paths.snapshot.read_text(encoding='utf-8-sig'))
    daily = snapshot['portfolio']['daily']
    dates = [str(day)[:10] for day in daily['index']]
    if not dates or any(not '2024-01-01' <= day <= '2025-12-31' for day in dates):
        raise ValueError('These diagnostics are restricted to the declared 2024-2025 IS snapshot.')
    return snapshot


def provenance(paths):
    return {'created_utc': datetime.now(timezone.utc).isoformat(),
            'source_sha256': sha256(paths.snapshot), 'protocol_sha256': sha256(paths.protocol),
            'protocol_file': paths.protocol.name,
            'raw_prices_public': False, 'oos_access': False, 'sealed_access': False}


def save_or_match_manifest(path, manifest, invariant_keys=('requests', 'source_sha256')):
    """Preserve an existing manifest byte-for-byte, including its old protocol hash.

    A newer RESEARCH_LOG is not retroactively substituted into old provenance.
    New run manifests hash the explicitly supplied read-only protocol file.
    """
    if path.exists():
        prior = json.loads(path.read_text(encoding='utf-8-sig'))
        for key in invariant_keys:
            if key in prior and prior[key] != manifest[key]:
                raise ValueError('Existing diagnostic manifest conflicts with the requested snapshot or scope.')
        return prior
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    return manifest


def private_cache(paths, name):
    # Response identity includes the entire canonical request, so identical
    # historical requests can reuse the immutable sponsor-data cache across
    # original/corrected runs. Run manifests and outputs remain separate.
    allowed = {'uniform_fixed_ledger_v1', 'factor_proxy_is_v1', 'volume_evidence_is_v1'}
    if name not in allowed:
        raise ValueError('Unknown private diagnostic cache namespace.')
    cache = paths.project / '.massive_cache' / name
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def sanitized_main(function):
    try:
        function()
    except Exception:
        print('Stopped: sanitized validation or execution error; credentials and response bodies withheld.')
        raise SystemExit(1)
