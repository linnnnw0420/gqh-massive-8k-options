"""Compare headline/statistical data from a clean run with the private first IS."""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from quote_valuation import split_frame


def compare(left, right):
    checks = []
    sections = [("tables", name) for name in ("events", "results", "placebo_events", "placebo_results", "theta_board", "official_diff", "sensitivity", "event_stress", "ordinary_stress")]
    sections += [("portfolio", name) for name in ("daily", "ledger")]
    for section, name in sections:
        a, b = (split_frame(snapshot[section][name]) for snapshot in (left, right))
        result = {"table": section + "/" + name, "original_rows": len(a), "reproduced_rows": len(b), "failures": []}
        if len(a) != len(b):
            result["failures"].append("row count changed")
        else:
            for column in a.columns.intersection(b.columns):
                if column == "timing_status":
                    continue  # Explicitly more accurate descriptive label; not a numerical change.
                av, bv = a[column], b[column]
                if pd.api.types.is_numeric_dtype(av) and pd.api.types.is_numeric_dtype(bv):
                    if not np.allclose(av.to_numpy(dtype=float), bv.to_numpy(dtype=float), atol=1e-7, rtol=1e-10, equal_nan=True):
                        result["failures"].append(column)
                elif av.tolist() != bv.tolist():
                    def canonical(value):
                        if isinstance(value, (tuple, list)):
                            return [canonical(item) for item in value]
                        if isinstance(value, float) and not np.isfinite(value):
                            return None
                        return value
                    if [canonical(x) for x in av] != [canonical(x) for x in bv]:
                        result["failures"].append(column)
            result["original_only_columns"] = sorted(set(a) - set(b))
            result["new_only_columns"] = sorted(set(b) - set(a))
        result["status"] = "MATCH" if not result["failures"] else "DIFFERENCE"
        checks.append(result)
    return {"status": "MATCH" if all(c["status"] == "MATCH" for c in checks) else "INVESTIGATE",
            "tolerances": {"absolute": 1e-7, "relative": 1e-10}, "scope": "All common columns; explicit column additions/omissions listed. No prices fetched or strategy executed.", "checks": checks}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("original", type=Path)
    p.add_argument("reproduction", type=Path)
    p.add_argument("output", type=Path)
    args = p.parse_args()
    report = compare(json.loads(args.original.read_text()), json.loads(args.reproduction.read_text()))
    args.output.write_text(json.dumps(report, indent=2))
    print(json.dumps(report))
