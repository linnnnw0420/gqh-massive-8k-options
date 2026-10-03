"""Run a bounded IS reproduction; never execute notebook cells or OOS."""
from __future__ import annotations
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import traceback

from research_runtime import load_runtime, run_is, _source
from risk_evidence import _jsonable, summarize_existing_is
from safe_transport import MassiveIS

FROZEN_SOURCE_AST_SHA256 = "5b189cbbb8128877a1227aa5455fd5e5260e6326539763eed0a171b5cf6e1114"
CORRECTION_SHA256 = "fcc7ab0d28c7705ab360b6d666d8e70c1e9f97b12ae1c146ecfdb7d5c3eaf94a"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--correction", type=Path)
    args = parser.parse_args()
    args.project = args.project.expanduser().resolve()
    private_root = (args.project / ".massive_cache").resolve()
    out = (args.output_dir if args.output_dir.is_absolute() else args.project / args.output_dir).expanduser().resolve()
    if not out.is_relative_to(private_root) or out == private_root:
        raise ValueError("Licensed study outputs must remain in a run directory below project/.massive_cache.")
    # Guard before directory creation, source execution, authentication or I/O.
    out.mkdir(parents=True, exist_ok=True)
    if (out / "snapshot.private.json").exists():
        raise ValueError("Output already contains a completed run; choose a new version directory.")
    source_ast_sha = hashlib.sha256(ast.dump(ast.parse(_source(args.source)), include_attributes=False).encode()).hexdigest()
    if source_ast_sha != FROZEN_SOURCE_AST_SHA256:
        raise ValueError("The preserved notebook source changed; record/review a new experiment version before running.")
    transport = MassiveIS(args.project, offline=args.offline, warmup_start="2023-12-01")
    run_manifest = {"started_utc": datetime.now(timezone.utc).isoformat(), "source_sha256": hashlib.sha256(args.source.read_bytes()).hexdigest(),
                    "window": ["2024-01-01", "2025-12-31"], "mode": "corrected_is_v2" if args.correction else "approved_is_v1",
                    "oos_authorized_by_this_command": False, "original_source_modified": False}
    run_manifest["source_ast_sha256"] = source_ast_sha
    run_manifest["feature_warmup_start"] = "2023-12-01"
    correction = json.loads(args.correction.read_text()) if args.correction else None
    if correction is not None:
        run_manifest["correction_sha256"] = hashlib.sha256(args.correction.read_bytes()).hexdigest()
        if run_manifest["correction_sha256"] != CORRECTION_SHA256:
            raise ValueError("The outcome-blind correction manifest changed; refuse an unlogged sample revision.")
    (out / "run_manifest.json").write_text(json.dumps(run_manifest, indent=2))
    try:
        runtime = load_runtime(args.source, transport.get, transport.all, warmup_start="2023-12-01")
        kwargs = {"event_mode": run_manifest["mode"]}
        if correction is not None:
            kwargs["corrected_rows"] = correction["corrected_rows"]
            runtime.namespace["SECTOR_BY_TICKER"] = {**runtime.namespace["SECTOR_BY_TICKER"], **correction.get("additional_industry_groups", {})}
        result = run_is(runtime, **kwargs)
        snapshot = result.to_private_snapshot()
        payload = json.dumps(_jsonable(snapshot), allow_nan=False)
        (out / "snapshot.private.json").write_text(payload)
        days = runtime.clock.sessions
        evidence = summarize_existing_is(snapshot, days[(days >= "2024-01-01") & (days <= "2025-12-31")])
        evidence["snapshot_sha256"] = hashlib.sha256(payload.encode()).hexdigest()
        (out / "aggregate_evidence.json").write_text(json.dumps(_jsonable(evidence), indent=2, allow_nan=False))
        run_manifest.update(completed_utc=datetime.now(timezone.utc).isoformat(), status="COMPLETE",
                            runtime=result.manifest, snapshot_sha256=evidence["snapshot_sha256"])
        print(json.dumps({"status": "COMPLETE", "mode": run_manifest["mode"], "events": len(result.tables["events"]),
                          "priced_primary": len(snapshot["priced_primary"]), "theta": evidence["dependence"]["theta"],
                          "nav_gaps": evidence["calendar"]["nav_gaps"]}), flush=True)
    except Exception as exc:
        run_manifest.update(status="FAILED", error_type=type(exc).__name__)
        # Source line positions aid local debugging; exception messages and HTTP bodies are withheld.
        run_manifest["trace_locations"] = [{"file": Path(item.filename).name, "line": item.lineno, "function": item.name}
                                            for item in traceback.extract_tb(exc.__traceback__)]
        print(json.dumps({"status": "FAILED", "error_type": type(exc).__name__, "locations": run_manifest["trace_locations"]}), flush=True)
        raise SystemExit(1) from None
    finally:
        run_manifest["transport"] = transport.manifest()
        (out / "run_manifest.json").write_text(json.dumps(_jsonable(run_manifest), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
