"""Fixed-original-contract liquidity/capacity diagnostics; no retrieval or simulation.

Uses only already saved IS inputs. Capacity screens never alter trade admissions.
Private details contain licensed-volume/quote-derived per-contract measurements;
the separate summary contains aggregate evidence and explicit limitations.
"""
from __future__ import annotations

import math
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from quote_valuation import (LEGS, build_scope, latest_quote_state, split_frame,
                            standard_contract, three_leg_mark)
from risk_evidence import _jsonable

PARTICIPATIONS = (.005, .01, .02)
QUOTE_AGES = (60, 300, math.inf)


def pre_entry_volume_evidence(record: dict, expected_sessions, entry_day,
                              contract: str, lookback: int = 20) -> dict:
    """Audit precisely the twenty completed sessions BEFORE the original entry.

    A valid observed zero volume remains zero. An absent bar is not silently
    asserted to mean zero: conditional zero-volume capacity is a separate
    sensitivity because listing-date/eligible-trade coverage is not established.
    """
    calendar = pd.DatetimeIndex(expected_sessions)
    if not calendar.is_unique or not calendar.is_monotonic_increasing:
        raise ValueError("Expected sessions must be sorted and unique.")
    entry = pd.Timestamp(entry_day).normalize()
    if entry not in calendar:
        raise ValueError("Entry must belong to the declared exchange calendar.")
    before = calendar[calendar < entry][-lookback:]
    out = {"required_sessions": lookback, "available_calendar_sessions": len(before),
        "observed_bar_sessions": 0, "absent_bar_sessions": lookback,
        "invalid_volume_sessions": 0, "observed_positive_volume_sessions": 0,
        "strict_20session_adv": np.nan, "conditional_absent_bar_zero_adv": np.nan,
        "observed_bar_mean_diagnostic": np.nan, "listing_date_verified": False,
        "status": "UNAVAILABLE_SOURCE", "lookback_start": str(before[0].date()) if len(before) else None,
        "lookback_end": str(before[-1].date()) if len(before) else None}
    if len(before) != lookback:
        out["status"] = "UNAVAILABLE_FULL_LOOKBACK_CALENDAR"
        return out
    if not isinstance(record, dict) or record.get("status") != "OK":
        return out
    if record.get("contract") != contract or pd.Timestamp(record.get("entry")).normalize() != entry:
        out["status"] = "SOURCE_IDENTITY_MISMATCH"
        return out
    if pd.Timestamp(record.get("start")) > before[0] or pd.Timestamp(record.get("exit")) < entry:
        out["status"] = "UNAVAILABLE_REQUEST_DOES_NOT_COVER_LOOKBACK"
        return out
    rows = record.get("rows")
    if not isinstance(rows, list):
        out["status"] = "INVALID_BAR_SCHEMA"
        return out
    observed = {}
    for row in rows:
        if not isinstance(row, dict) or isinstance(row.get("t"), bool) or not isinstance(row.get("t"), (int, float)):
            out["status"] = "INVALID_BAR_TIMESTAMP"
            return out
        if not math.isfinite(row["t"]):
            out["status"] = "INVALID_BAR_TIMESTAMP"
            return out
        day = pd.to_datetime(row["t"], unit="ms", utc=True).tz_convert("America/New_York").normalize().tz_localize(None)
        if day < pd.Timestamp(record["start"]) or day > pd.Timestamp(record["exit"]):
            out["status"] = "BAR_OUTSIDE_REQUEST_INTERVAL"
            return out
        if day not in before:
            continue
        if day in observed:
            out["status"] = "DUPLICATE_SESSION_BARS"
            return out
        volume = row.get("v")
        good = isinstance(volume, (int, float)) and not isinstance(volume, bool) and math.isfinite(volume) and volume >= 0
        observed[day] = float(volume) if good else np.nan
    data = pd.Series(observed, dtype=float).reindex(before)
    count = len(observed)
    invalid = sum(not math.isfinite(v) for v in observed.values())
    out.update(observed_bar_sessions=count, absent_bar_sessions=lookback-count,
               invalid_volume_sessions=invalid, observed_positive_volume_sessions=int((data > 0).sum()))
    if count > invalid:
        out["observed_bar_mean_diagnostic"] = float(data.mean())
    if invalid:
        out["status"] = "UNAVAILABLE_INVALID_RECORDED_VOLUME"
        return out
    # Mean over observed bars is descriptive, not a replacement for 20-day ADV.
    out["conditional_absent_bar_zero_adv"] = float(data.fillna(0).sum() / lookback)
    if count == lookback:
        out["strict_20session_adv"] = float(data.mean())
        out["status"] = "ALL_20_SESSION_VOLUMES_OBSERVED"
    else:
        out["status"] = "PARTIAL_BAR_HISTORY_ZERO_CONVENTION_ONLY"
    return out


def capacity_screen(leg_advs: dict, entry_stock_gross: float,
                    displayed_size_raw: float | None = None,
                    displayed_sizes_are_contracts: bool = False) -> list[dict]:
    """Three-leg bottleneck at fixed .5%, 1%, 2%; no impact or fill guarantee.

    Dollar figures are per-trade underlying-reference gross notional. They are
    not strategy AUM, demonstrated scalable profit, or an execution simulation.
    Displayed-size units are deliberately unconfirmed by default.
    """
    if not math.isfinite(entry_stock_gross) or entry_stock_gross <= 0:
        raise ValueError("Positive finite original one-contract gross required.")
    if set(leg_advs) != set(LEGS):
        raise ValueError("Exactly the three frozen option legs are required.")
    good = all(isinstance(v, (int, float)) and math.isfinite(v) and v >= 0 for v in leg_advs.values())
    bottleneck = min(leg_advs.values()) if good else np.nan
    display = (float(displayed_size_raw) if displayed_size_raw is not None and math.isfinite(displayed_size_raw)
               and displayed_size_raw >= 0 else np.nan)
    rows = []
    for participation in PARTICIPATIONS:
        fractional = participation * bottleneck
        cap = math.floor(fractional) if math.isfinite(fractional) else None
        combined = min(cap, math.floor(display)) if cap is not None and math.isfinite(display) and displayed_sizes_are_contracts else None
        rows.append({"participation": participation, "volume_screen_contracts_fractional": fractional,
            "volume_screen_contracts_integer": cap,
            "volume_screen_entry_gross_usd": cap * entry_stock_gross if cap is not None else np.nan,
            "volume_allows_original_one_contract": cap >= 1 if cap is not None else None,
            "displayed_size_bottleneck_raw": display,
            "displayed_size_units_verified_contracts": displayed_sizes_are_contracts,
            "combined_volume_display_contracts": combined,
            "combined_entry_gross_usd": combined * entry_stock_gross if combined is not None else np.nan})
    return rows


def endpoint_quote_evidence(snapshot: dict, quote_inputs: dict, max_age_seconds: int) -> list[dict]:
    """Actual endpoints only, with original direction-specific bid/ask sizes."""
    if max_age_seconds not in QUOTE_AGES:
        raise ValueError("Use the two predeclared screens or separately documented standing-state diagnostic.")
    standing = not math.isfinite(max_age_seconds)
    ledger = split_frame(snapshot["portfolio"]["ledger"])
    rows = {r["trade_id"]: r for r in ledger.to_dict("records")}
    priced = {p["accession_number"]: p for p in snapshot["priced_primary"]}
    scope = build_scope(snapshot)
    scope_ends = {}
    for item in scope:
        scope_ends[item["trade_id"]] = max(scope_ends.get(item["trade_id"], item["day"]), item["day"])
    grouped = {}
    for item in scope:
        if not (item["is_entry"] or item["is_exit"]):
            continue
        key = (item["trade_id"], item["day"])
        grouped.setdefault(key, {"item": item, "states": {}})
        qkey = item["contract"] + "|" + item["day"]
        request = quote_inputs["quotes"].get(qkey, {})
        state = latest_quote_state(request.get("rows", []), item["start_ns"], item["cutoff_ns"], max_age_seconds)
        if request.get("status") != "OK" or request.get("key", qkey) != qkey:
            state = {"status": "UNAVAILABLE_OR_MISMATCHED_QUOTE_REQUEST", "mid": None}
        pe = priced[item["accession"]]
        metadata = quote_inputs["metadata"].get(qkey)
        status = standard_contract(metadata, pe, item["leg_key"])
        if status != "STANDARD_METADATA":
            state = {"status": status, "mid": None}
        grouped[key]["states"][item["leg_key"]] = state
    action_records = {(r["kind"], r["key"]): r for r in quote_inputs.get("actions", [])}
    out = []
    for (trade, day), group in grouped.items():
        item, states, row = group["item"], group["states"], rows[trade]
        pe = priced[item["accession"]]
        side = "entry" if item["is_entry"] else "exit"
        split = action_records.get(("splits", row["ticker"]), {})
        # An open position's last IS mark is a scope boundary, never a sale.
        # build_scope validates the observed end without looking up the future
        # scheduled exit; corporate-action coverage uses that same interval.
        observed_end = scope_ends[trade]
        splits_in_hold = [r for r in split.get("rows", []) if str(row["entry_date"])[:10] <= str(r.get("execution_date", "")) <= observed_end]
        mark = three_leg_mark(states, pe["strikes"]["K"], pe["expiry"], day,
                              max_sync_seconds=math.inf if standing else 60)
        if split.get("status") != "OK" or splits_in_hold:
            mark = {"status": "UNVERIFIED_OR_CHANGED_DELIVERABLE_DURING_HOLD", "value_per_contract": None}
        report = {"trade_id": trade, "ticker": row["ticker"], "day": day, "side": side,
            "position_status": row["status"], "observed_scope_end": observed_end,
            "age_policy_seconds": max_age_seconds, "status": mark["status"],
            "policy_label": "post-coverage same-session standing-NBBO assumption" if standing else "predeclared update-age screen",
            "three_leg_halfspread_usd": np.nan, "midpoint_premium_haircut_usd": np.nan,
            "original_booked_endpoint_haircut_usd": row.get("entry_cost" if side == "entry" else "exit_cost"),
            "halfspread_to_same_quote_haircut": np.nan, "halfspread_to_original_haircut": np.nan,
            "halfspread_bps_entry_stock_gross": np.nan, "directional_display_bottleneck_raw": np.nan,
            "all_quote_condition_fields_present": False, "max_quote_age_seconds": np.nan,
            "sync_span_seconds": mark.get("sync_seconds", np.nan)}
        if mark["status"] == "AVAILABLE_INDICATIVE_PARITY_MARK":
            # Entry: long ATM call, short ATM put and OTM call; reverse at exit.
            entry_sides = {"C_K": "ask_size", "P_K": "bid_size", "C_U0.05": "bid_size"}
            needed = entry_sides if side == "entry" else {k: "bid_size" if v == "ask_size" else "ask_size" for k, v in entry_sides.items()}
            sizes = [states[leg][needed[leg]] for leg in LEGS]
            halfspread = mark["three_leg_half_spread_usd"]
            same_quote_haircut = .05 * 100 * sum(states[leg]["mid"] for leg in LEGS)
            original_cost = report["original_booked_endpoint_haircut_usd"]
            report.update(three_leg_halfspread_usd=halfspread, midpoint_premium_haircut_usd=same_quote_haircut,
                halfspread_to_same_quote_haircut=halfspread / same_quote_haircut if same_quote_haircut > 0 else np.nan,
                halfspread_to_original_haircut=halfspread / original_cost if original_cost and original_cost > 0 else np.nan,
                halfspread_bps_entry_stock_gross=halfspread / row["entry_stock_gross"] * 10000,
                directional_display_bottleneck_raw=min(sizes),
                all_quote_condition_fields_present=all(states[k].get("condition_metadata_present", False) for k in LEGS),
                max_quote_age_seconds=max(states[k]["age_seconds"] for k in LEGS))
        out.append(report)
    return out


def _stats(values) -> dict:
    x = np.asarray([v for v in values if v is not None and math.isfinite(v)], dtype=float)
    return {"n": len(x), "min": float(x.min()) if len(x) else None,
            "median": float(np.median(x)) if len(x) else None, "max": float(x.max()) if len(x) else None}


def derive_capacity(snapshot: dict, quote_inputs: dict, volume_inputs: dict) -> tuple[dict, dict]:
    if snapshot.get("oos_read") is not False:
        raise ValueError("Only the original IS snapshot is permitted.")
    daily = split_frame(snapshot["portfolio"]["daily"], True)
    if daily.index.min() < pd.Timestamp("2024-01-01") or daily.index.max() > pd.Timestamp("2025-12-31"):
        raise ValueError("Scope must remain inside the original IS window.")
    ledger = split_frame(snapshot["portfolio"]["ledger"])
    admitted = [r for r in ledger.to_dict("records") if r.get("contracts") and r.get("status") != "SKIPPED"]
    if any(r["contracts"] != 1 for r in admitted):
        raise ValueError("The frozen one-contract ledger is required.")
    # Scope validation also rejects unknown statuses, contradictory open exits,
    # and future data. Admission decisions and one-contract sizing stay fixed.
    build_scope(snapshot)
    closed_ids = {r["trade_id"] for r in admitted if r["status"] == "CLOSED"}
    open_ids = {r["trade_id"] for r in admitted if r["status"] == "OPEN_AT_WINDOW_END"}
    expected_actual_endpoints = len(admitted) + len(closed_ids)
    priced = {p["accession_number"]: p for p in snapshot["priced_primary"]}
    records = volume_inputs["records"]
    volumes = {r["key"]: r for r in records}
    if len(volumes) != len(records):
        raise ValueError("Duplicate volume request identities.")
    volume_details, screen_details = [], []
    endpoint_details = {age: endpoint_quote_evidence(snapshot, quote_inputs, age) for age in QUOTE_AGES}
    for row in admitted:
        pe = priced[row["accession_number"]]
        audits = {}
        for leg in LEGS:
            record = volumes.get(row["trade_id"] + "|" + leg, {})
            audit = pre_entry_volume_evidence(record, daily.index, row["entry_date"], pe["legs"][leg]["ticker"])
            audits[leg] = audit
            volume_details.append({"trade_id": row["trade_id"], "ticker": row["ticker"], "leg": leg, **audit})
        for convention, field in (("strict_complete_20_observations", "strict_20session_adv"),
                                  ("conditional_absent_bar_as_zero", "conditional_absent_bar_zero_adv")):
            screens = capacity_screen({leg: audits[leg][field] for leg in LEGS}, row["entry_stock_gross"])
            for screen in screens:
                screen_details.append({"trade_id": row["trade_id"], "ticker": row["ticker"],
                                       "volume_convention": convention, **screen})
    quote_summaries = []
    for age, endpoints in endpoint_details.items():
        valid = [r for r in endpoints if r["status"] == "AVAILABLE_INDICATIVE_PARITY_MARK"]
        complete_trade_ids = {r["trade_id"] for r in admitted if r["trade_id"] in closed_ids and
            {e["side"] for e in valid if e["trade_id"] == r["trade_id"]} == {"entry", "exit"}}
        complete_endpoints = [r for r in valid if r["trade_id"] in complete_trade_ids]
        quote_summaries.append({"max_quote_age_seconds": age,
            "policy_label": "post-coverage same-session standing-NBBO assumption" if not math.isfinite(age) else "predeclared update-age screen",
            "expected_endpoints": expected_actual_endpoints, "available_endpoints": len(valid),
            "expected_entry_endpoints": len(admitted), "expected_realized_exit_endpoints": len(closed_ids),
            "open_positions_without_realized_exit": len(open_ids), "scope_end_mark_is_executed_exit": False,
            "fully_covered_roundtrips": len(complete_trade_ids), "status_counts": dict(Counter(r["status"] for r in endpoints)),
            "observed_endpoint_halfspread_subtotal_usd": sum(r["three_leg_halfspread_usd"] for r in valid),
            "full_ledger_roundtrip_halfspread_usd": sum(r["three_leg_halfspread_usd"] for r in valid) if not open_ids and len(valid) == expected_actual_endpoints else None,
            "complete_roundtrip_subset_halfspread_usd": sum(r["three_leg_halfspread_usd"] for r in complete_endpoints),
            "halfspread_to_same_quote_5pct_haircut": _stats([r["halfspread_to_same_quote_haircut"] for r in valid]),
            "halfspread_to_original_booked_haircut": _stats([r["halfspread_to_original_haircut"] for r in valid]),
            "endpoints_halfspread_exceeds_original_haircut": sum(r["halfspread_to_original_haircut"] > 1 for r in valid),
            "endpoints_halfspread_exceeds_twice_original_haircut": sum(r["halfspread_to_original_haircut"] > 2 for r in valid),
            "halfspread_bps_entry_stock_gross": _stats([r["halfspread_bps_entry_stock_gross"] for r in valid]),
            "directional_display_size_bottleneck_raw_units": _stats([r["directional_display_bottleneck_raw"] for r in valid]),
            "endpoints_with_all_condition_fields": sum(r["all_quote_condition_fields_present"] for r in valid),
            "quote_update_age_seconds": _stats([r["max_quote_age_seconds"] for r in valid]),
            "inter_leg_update_span_seconds": _stats([r["sync_span_seconds"] for r in valid]),
            "execution_limit": "Indicative quotes at nearby times, not guaranteed simultaneous executable fills. Sum is an observed spread subtotal when any endpoints are missing. Commissions, impact, queue priority and financing are additional."})
    screen_summary = []
    for convention in ("strict_complete_20_observations", "conditional_absent_bar_as_zero"):
        for participation in PARTICIPATIONS:
            chosen = [r for r in screen_details if r["volume_convention"] == convention and r["participation"] == participation]
            known = [r for r in chosen if r["volume_screen_contracts_integer"] is not None]
            screen_summary.append({"volume_convention": convention, "participation": participation,
                "positions_expected": len(admitted), "positions_with_available_screen": len(known),
                "positions_passing_original_one_contract": sum(r["volume_allows_original_one_contract"] for r in known),
                "position_contract_cap_integer": _stats([r["volume_screen_contracts_integer"] for r in known]),
                "per_trade_entry_gross_capacity_usd": _stats([r["volume_screen_entry_gross_usd"] for r in known])})
    public = {"kind": "aggregate_predeclared_capacity_evidence_original_IS_positions",
        "actual_entered_positions": len(admitted), "closed_positions": len(closed_ids),
        "open_at_window_end_positions": len(open_ids), "lookback_sessions": 20,
        "endpoint_scope": "Actual entries and realized closed exits only; open scope-end marks are not executed exits.",
        "participation_scenarios": list(PARTICIPATIONS),
        "volume_leg_status_counts": dict(Counter(r["status"] for r in volume_details)),
        "all_twenty_bars_observed_leg_count": sum(r["observed_bar_sessions"] == 20 and r["invalid_volume_sessions"] == 0 for r in volume_details),
        "leg_observed_session_count": _stats([r["observed_bar_sessions"] for r in volume_details]),
        "quote_endpoint_summaries": quote_summaries, "capacity_screens": screen_summary,
        "display_size_contract_conversion": "UNVERIFIED: raw quote size units reported; no combined contract/AUM bound inferred.",
        "limitations": [
            "20-session lookback excludes entry day and uses only the original selected contracts. It does not re-admit or reject historical trades.",
            "Strict ADV requires valid volume bars on all 20 preceding sessions for each of three legs. Means on observed bars are private diagnostics, never relabeled as 20-session ADV.",
            "Conditional absent-bar-as-zero convention assumes the option was listed and absence represents no eligible trades; listing dates are not established. Missing quoted prices are never filled with zero.",
            "Participation percentages are fixed .5/1/2% sensitivity screens, not calibrated market-impact or execution models.",
            "Displayed size may vanish and three legs need not execute atomically. Quote conditions and size-unit interpretation require primary-source verification.",
            "Per-trade gross dollars are not strategy AUM or positive-edge capacity. One-contract sizing is fixed and observed depth alone does not establish profitable scaling."]}
    private = {"volume_details": volume_details, "per_trade_capacity_screens": screen_details,
               "endpoint_details": endpoint_details}
    return public, private


def main():
    import argparse
    import hashlib
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--quotes", type=Path, required=True)
    parser.add_argument("--volumes", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--private-details", type=Path, required=True)
    args = parser.parse_args()
    inputs = [args.snapshot, args.quotes, args.volumes]
    if len({p.resolve() for p in inputs + [args.output, args.private_details]}) != 5:
        raise ValueError("All input/output paths must be distinct.")
    payloads = [p.read_bytes() for p in inputs]
    summary, private = derive_capacity(*(json.loads(p) for p in payloads))
    summary["source_sha256"] = {p.name: hashlib.sha256(b).hexdigest() for p, b in zip(inputs, payloads)}
    args.output.write_text(json.dumps(_jsonable(summary), indent=2, allow_nan=False) + "\n", encoding="utf-8")
    args.private_details.write_text(json.dumps(_jsonable(private), indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "derived_capacity_only", "positions": summary["actual_entered_positions"],
                      "strict_leg_histories": summary["all_twenty_bars_observed_leg_count"]}))


if __name__ == "__main__":
    main()
