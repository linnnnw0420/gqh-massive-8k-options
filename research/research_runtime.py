"""Explicit clean-process execution of the frozen notebook's IS research functions.

Loading this module never executes a notebook, authenticates, or retrieves data.
The caller supplies audited cache/auth/pagination transports. The AST loader
imports only allowlisted dependencies, configurations, definitions and classes;
credential loaders, notebook output cells and top-level API calls are omitted.
No OOS or sealed-window entry point is enabled by this implementation.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import sys
import types
from typing import Callable
from urllib.parse import parse_qs, unquote, urlparse
import uuid

import numpy as np
import pandas as pd
from event_pipeline import NYSEClock, EVENT_COLUMNS


CONFIG_NAMES = {
    "BASE_URL", "EVENT_TAGS", "EVENT_TAG", "STUDY_START", "STUDY_END", "IS_OBSERVATION_END",
    "OOS_START", "OOS_END", "HOLDOUT_START", "HOLDOUT_END", "TOP_100", "EXPIRY_BUCKETS",
    "BASELINE_BUCKET", "HORIZONS", "PRIMARY_HORIZON", "OTM_PCT", "OTM_GRID", "ENTRY", "RISK_FREE",
    "STRIKE_WINDOW", "MAX_STALE_SESSIONS", "MAX_EVENTS", "RUN_PLACEBO", "N_PLACEBO", "PLACEBO_GAP_DAYS",
    "COST_HAIRCUT", "RUN_OOS", "RUN_HOLDOUT", "APPROVED_IS", "FILER_TICKER_ALIASES", "SECTOR_BY_TICKER",
    "INITIAL_NAV", "NAME_GROSS_LIMIT", "SECTOR_GROSS_LIMIT", "TOTAL_GROSS_LIMIT", "PAUSE_DRAWDOWN",
    "RESUME_DRAWDOWN", "CAPACITY_PARTICIPATION", "STRATEGIES", "STRATEGY_LABEL",
}
FUNCTION_NAMES = {
    "trading_sessions", "session_on_or_after", "session_before", "sessions_between", "session_close_time",
    "next_session", "normalize_ticker", "ticker_tokens", "accession_id", "fetch_union_disclosures",
    "first_full_session_close", "public_signal_session", "pre_public_session", "next_public_open",
    "canonical_filer_ticker", "acceptance_regime", "build_events", "option_bars", "fetch_chain",
    "paired_strikes", "contract", "last_close_on_or_before", "locate_spot", "pick_expiry", "select_strikes",
    "price_event", "price_events", "summarize_priced", "option_cost", "strategy_pnl", "evaluate",
    "finite_values", "bootstrap_ci", "slice_results", "_fixed_horizons", "_horizon_rows", "_summary",
    "scoreboard", "difference_board", "fmt_board", "_tag_set", "category_slice", "category_boards",
    "coverage_table", "issuer_influence", "yearly_theta_diagnostics", "sample_placebo", "decay_table",
    "fmt_decay", "implied_realized_summary", "_portfolio_marks", "_portfolio_volume_rows",
    "_portfolio_metric_block", "portfolio_scorecard", "refresh_portfolio_metrics", "simulate_portfolio",
}
CLASS_NAMES = {"NYSEHolidays", "Leg", "PricedEvent"}
IMPORT_ROOTS = {"json", "time", "hashlib", "re", "dataclasses", "numpy", "pandas"}
RESULT_COLUMNS = ["ticker", "accession_number", "source_tags", "event_date", "t_0", "bucket", "expiry",
    "entry", "entry_date", "entry_price_field", "horizon", "requested_exit_date", "exit_date", "expiry_capped",
    "observation_end", "sessions_held", "dte_sessions", "S_entry", "S_exit", "realized", "implied_move",
    "implied_scaled", "otm", "option_volume", "atm_call_volume", "atm_put_volume", "short_call_strike",
    "otm_selector_fallback", "pre_call_moneyness", "entry_call_moneyness", "coverage_reason", "stale_mark_details",
    "quote_coverage", "stock_gross", "covered_call_gross", "stock_cost", "covered_call_cost", "stock_net",
    "covered_call_net", "incremental_net", "ratio"]
RAW_COLUMNS = ["tickers", "cik", "accession_number", "filing_date", "primary_category", "secondary_category",
               "tertiary_category", "supporting_text", "filing_url", "source_tag", "accession_id", "ticker_tokens"]
PLACEBO_COLUMNS = ["ticker", "filing_date", "event_date", "t_0", "t_pre", "entry_day", "accepted_at",
                   "accession_number", "source_tags", "matched_event_accession", "transaction_group"]


class ScopeViolation(ValueError):
    """A requested resource or date falls outside the explicit IS boundary."""


class ISFence:
    """Check all calls before delegating and validate returned row dates.

    The supplied transport owns pagination verification, secrets and caching.
    A paginated callback must not follow cross-host URLs or change the initial
    filter scope. This class cannot inspect I/O hidden inside an arbitrary callback.
    """
    def __init__(self, start, end, api_get: Callable, api_get_all: Callable, *, warmup_start=None):
        self.start, self.end = pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize()
        if not pd.Timestamp("2024-01-01") <= self.start <= self.end <= pd.Timestamp("2025-12-31"):
            raise ScopeViolation("This runtime accepts only the declared 2024-2025 IS interval.")
        self.feature_start = self.start if warmup_start is None else pd.Timestamp(warmup_start)
        if (pd.isna(self.feature_start) or self.feature_start.tzinfo is not None
                or self.feature_start != self.feature_start.normalize()
                or not pd.Timestamp("2023-12-01") <= self.feature_start <= self.start):
            raise ScopeViolation("Explicit feature warmup must begin no earlier than 2023-12-01 and no later than IS start.")
        self._get, self._get_all = api_get, api_get_all
        self.requests, self.boundary_notes = [], []

    def _day(self, value, label, *, feature=False):
        try:
            day = pd.Timestamp(value)
        except Exception as exc:
            raise ScopeViolation(f"Invalid {label} date.") from exc
        lower = self.feature_start if feature else self.start
        if pd.isna(day) or day.tzinfo is not None or day != day.normalize() or not lower <= day <= self.end:
            raise ScopeViolation(f"{label} date is outside the explicit IS fence.")
        return day

    def _request(self, path, params):
        if not isinstance(path, str):
            raise ScopeViolation("A resource path is required.")
        parsed = urlparse(path)
        if parsed.scheme and (parsed.scheme != "https" or parsed.hostname != "api.massive.com" or parsed.username):
            raise ScopeViolation("Only the supplied Massive transport host is allowed.")
        if parsed.fragment:
            raise ScopeViolation("Fragments are not API request scope.")
        route = unquote(parsed.path)
        parameters = dict(params or {})
        for key, values in parse_qs(parsed.query).items():
            if len(values) != 1 or key in parameters and str(parameters[key]) != values[0]:
                raise ScopeViolation("Ambiguous API query parameters.")
            parameters[key] = values[0]
        if any(re.search(r"key|token|authorization|secret", str(k), re.I) for k in parameters):
            raise ScopeViolation("Authentication must remain inside the caller's transport.")
        metadata = {"route": route, "start": None, "end": None}
        if route == "/stocks/taxonomies/vX/disclosures":
            metadata["kind"] = "taxonomy_definitions"
        elif route in ("/stocks/filings/8-K/vX/disclosures", "/stocks/filings/8-K/vX/text"):
            lower = self._day(parameters.get("filing_date.gte"), "filing start")
            upper = self._day(parameters.get("filing_date.lte"), "filing end")
            if lower > upper:
                raise ScopeViolation("Reversed filing dates.")
            if route.endswith("disclosures") and parameters.get("tertiary_category") not in {"acquisition_agreement", "merger_agreement"}:
                raise ScopeViolation("Only the frozen agreement tag union is allowed.")
            metadata.update(kind="filings", start=lower, end=upper)
        elif route == "/v3/reference/options/contracts":
            as_of = self._day(parameters.get("as_of"), "contract as-of", feature=True)
            if not isinstance(parameters.get("underlying_ticker"), str):
                raise ScopeViolation("An explicit underlying is required.")
            # Future expiration is historical contract metadata, not a future mark.
            metadata.update(kind="contract_metadata", start=as_of, end=as_of)
        else:
            match = re.fullmatch(r"/v2/aggs/ticker/(O:[A-Za-z0-9.]+[0-9]{6}[CP][0-9]{8})/range/1/day/(\d{4}-\d{2}-\d{2})/(\d{4}-\d{2}-\d{2})", route)
            if not match:
                raise ScopeViolation("Endpoint is outside the frozen study's data interface.")
            lower, upper = self._day(match[2], "option-bar start", feature=True), self._day(match[3], "option-bar end", feature=True)
            if lower > upper:
                raise ScopeViolation("Reversed option-bar dates.")
            metadata.update(kind="option_bars", start=lower, end=upper)
        if metadata["start"] is not None and metadata["start"] < self.start:
            metadata["pre_is_role"] = "FEATURE_WARMUP_ONLY_NO_EVENT_OR_OUTCOME_EXPANSION"
        self.requests.append({k: str(v.date()) if isinstance(v, pd.Timestamp) else v for k, v in metadata.items()})
        return metadata

    def _validate_rows(self, rows, scope):
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ScopeViolation("Transport must return a complete list of object records.")
        if scope["kind"] not in {"filings", "option_bars"}:
            return rows
        for row in rows:
            if scope["kind"] == "filings":
                date = pd.Timestamp(row.get("filing_date"))
                if pd.isna(date) or date.tzinfo is not None:
                    raise ScopeViolation("Invalid filing date in returned records.")
                date = date.normalize()
            else:
                value = row.get("t")
                if not isinstance(value, (float, int)) or isinstance(value, bool) or not np.isfinite(value):
                    raise ScopeViolation("Invalid option-bar timestamp in returned records.")
                date = pd.to_datetime(value, unit="ms", utc=True).tz_convert("America/New_York").normalize().tz_localize(None)
            if not scope["start"] <= date <= scope["end"]:
                raise ScopeViolation("Returned records fall outside the requested historical interval.")
        return rows

    def get(self, path, params=None):
        scope = self._request(path, params)
        value = self._get(path, params)
        if not isinstance(value, dict):
            raise ScopeViolation("Single-page transport must return an object.")
        self._validate_rows(value.get("results") or [], scope)
        return value

    def get_all(self, path, params=None, max_pages=500):
        scope = self._request(path, params)
        rows = self._get_all(path, params, max_pages=max_pages)
        return self._validate_rows(rows, scope)


def _source(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".ipynb":
        notebook = json.loads(text)
        return "\n\n".join("\n".join(line for line in "".join(cell["source"]).splitlines()
                                      if not line.lstrip().startswith(("%", "!")))
                            for cell in notebook["cells"] if cell.get("cell_type") == "code")
    if path.suffix != ".py":
        raise ValueError("Supply the frozen notebook or extracted Python source.")
    return text


def _targets(node):
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    return {part.id for target in targets for part in ast.walk(target) if isinstance(part, ast.Name) and isinstance(part.ctx, ast.Store)}


def _definition_module(source):
    kept = [ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)]
    for node in ast.parse(source).body:
        if isinstance(node, ast.Import):
            names = [name for name in node.names if name.name.split(".")[0] in IMPORT_ROOTS]
            if names:
                kept.append(ast.Import(names=names))
        elif isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] in IMPORT_ROOTS:
            kept.append(node)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            names = _targets(node)
            if names and names <= CONFIG_NAMES:
                kept.append(node)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in FUNCTION_NAMES:
            kept.append(node)
        elif isinstance(node, ast.ClassDef) and node.name in CLASS_NAMES:
            kept.append(node)
    return ast.fix_missing_locations(ast.Module(body=kept, type_ignores=[]))


@dataclass
class Runtime:
    namespace: dict
    fence: ISFence
    clock: NYSEClock
    source_sha256: str
    source_name: str
    calendar_matches_original_is: bool


def load_runtime(notebook_source: Path | str, api_get: Callable, api_get_all: Callable,
                 *, start="2024-01-01", end="2025-12-31", clock=None, warmup_start=None) -> Runtime:
    path = Path(notebook_source)
    source = _source(path)
    fence = ISFence(start, end, api_get, api_get_all, warmup_start=warmup_start)
    clock = clock or NYSEClock.for_window(start, end)
    module_name = "_gqh_definitions_" + uuid.uuid4().hex
    module = types.ModuleType(module_name)
    module.__file__ = str(path)
    sys.modules[module_name] = module  # dataclass resolves postponed annotations here
    namespace = module.__dict__
    try:
        exec(compile(_definition_module(source), str(path), "exec"), namespace)
        required = CONFIG_NAMES - {"BASE_URL"}
        if not required <= set(namespace):
            raise ValueError("Frozen source lacks required research configuration names.")
        for name, expected in {"EVENT_TAGS": ("acquisition_agreement", "merger_agreement"), "ENTRY": "full",
                               "OTM_PCT": .05, "PRIMARY_HORIZON": 21, "COST_HAIRCUT": .05,
                               "RUN_OOS": False, "RUN_HOLDOUT": False, "N_PLACEBO": 120,
                               "BASELINE_BUCKET": "3-6m", "MAX_EVENTS": None, "PLACEBO_GAP_DAYS": 30,
                               "RISK_FREE": .04, "MAX_STALE_SESSIONS": 3,
                               "HORIZONS": [1, 2, 3, 5, 10, 21, 42, 63], "OTM_GRID": [.03, .05, .1],
                               "STRATEGIES": ["stock_net", "covered_call_net"], "INITIAL_NAV": 1_000_000.,
                               "NAME_GROSS_LIMIT": .1, "SECTOR_GROSS_LIMIT": .25, "TOTAL_GROSS_LIMIT": 1.,
                               "PAUSE_DRAWDOWN": .1, "RESUME_DRAWDOWN": .05}.items():
            if namespace[name] != expected:
                raise ValueError("Source does not match the frozen primary configuration: " + name)
        if len(namespace["TOP_100"]) != 100 or len(set(namespace["TOP_100"])) != 100:
            raise ValueError("Frozen static TOP100 must contain one hundred unique names.")
        if len(namespace["APPROVED_IS"]) != 16 or len({row[2] for row in namespace["APPROVED_IS"]}) != 16:
            raise ValueError("Original approved-is mode must retain its sixteen reviewed accession identities.")
        original_dates = namespace["trading_sessions"]("2024-01-01", "2025-12-31")
        real_dates = clock.sessions[(clock.sessions >= pd.Timestamp("2024-01-01")) & (clock.sessions <= pd.Timestamp("2025-12-31"))]
        full_is_covered = clock.sessions[0] <= pd.Timestamp("2024-01-02") and clock.sessions[-1] >= pd.Timestamp("2025-12-31")
        calendar_matches = bool(full_is_covered and original_dates.equals(real_dates))
        if (start, end) == ("2024-01-01", "2025-12-31") and not calendar_matches:
            raise ValueError("Validated NYSE calendar differs from the original IS session calendar.")
        namespace.update(STUDY_START=str(fence.start.date()), STUDY_END=str(fence.end.date()),
                         IS_OBSERVATION_END=fence.end, CAL=clock.sessions, RUN_OOS=False, RUN_HOLDOUT=False,
                         api_get=fence.get, api_get_all=fence.get_all)
        for name in ("session_on_or_after", "session_before", "sessions_between", "session_close_time",
                     "next_session", "first_full_session_close", "public_signal_session", "pre_public_session",
                     "next_public_open", "acceptance_regime"):
            namespace[name] = getattr(clock, name)
        namespace["trading_sessions"] = lambda first, last: clock.sessions[(clock.sessions >= pd.Timestamp(first)) & (clock.sessions <= pd.Timestamp(last))]
        original_bars, original_chain = namespace["option_bars"], namespace["fetch_chain"]
        def bars(ticker, first, last):
            lower, upper = max(pd.Timestamp(first), fence.feature_start), min(pd.Timestamp(last), fence.end)
            if lower > upper:
                fence.boundary_notes.append({"kind": "option_bar_window_unavailable", "start": str(first), "end": str(last)})
                return pd.DataFrame(columns=["open", "close", "volume"], index=pd.DatetimeIndex([], name="session"))
            if lower != pd.Timestamp(first) or upper != pd.Timestamp(last):
                fence.boundary_notes.append({"kind": "option_bar_window_clipped", "requested_start": str(first), "requested_end": str(last),
                                             "used_start": str(lower.date()), "used_end": str(upper.date())})
            return original_bars(ticker, lower, upper)
        def chain(ticker, as_of, lo, hi):
            if not fence.feature_start <= pd.Timestamp(as_of) <= fence.end:
                fence.boundary_notes.append({"kind": "contract_asof_unavailable", "as_of": str(as_of)})
                return pd.DataFrame(columns=["ticker", "contract_type", "strike_price", "expiration_date", "dte"])
            return original_chain(ticker, as_of, lo, hi)
        namespace["option_bars"], namespace["fetch_chain"] = bars, chain
        return Runtime(namespace, fence, clock, hashlib.sha256(source.encode()).hexdigest(), path.name, calendar_matches)
    except Exception:
        sys.modules.pop(module_name, None)
        raise


def _raw_candidates(runtime):
    ns, pieces = runtime.namespace, []
    for tag in ns["EVENT_TAGS"]:
        records = runtime.fence.get_all("/stocks/filings/8-K/vX/disclosures", {
            "tertiary_category": tag, "filing_date.gte": ns["STUDY_START"], "filing_date.lte": ns["STUDY_END"],
            "limit": 1000, "sort": "filing_date.asc"})
        if records:
            part = pd.DataFrame(records)
            part["source_tag"] = tag
            pieces.append(part)
    if not pieces:
        return pd.DataFrame(columns=RAW_COLUMNS)
    raw = pd.concat(pieces, ignore_index=True)
    raw["filing_date"] = pd.to_datetime(raw["filing_date"])
    raw["accession_id"] = raw.apply(ns["accession_id"], axis=1)
    if raw.accession_id.eq("").any() or "tickers" not in raw:
        raise ValueError("Disclosure records require accession identities and ticker tokens.")
    raw["ticker_tokens"] = raw.tickers.map(ns["ticker_tokens"])
    return raw


def _normalize_events(events: pd.DataFrame, runtime) -> pd.DataFrame:
    if not isinstance(events, pd.DataFrame):
        raise ValueError("Event provider must return a DataFrame.")
    if events.empty:
        return pd.DataFrame(columns=EVENT_COLUMNS)
    if not set(EVENT_COLUMNS) <= set(events):
        raise ValueError("Event provider omitted required audited event columns.")
    events = events.copy()
    for column in ("filing_date", "accepted_at", "t_pre", "t_0", "entry_day", "event_date"):
        events[column] = pd.to_datetime(events[column])
        if getattr(events[column].dt, "tz", None) is not None:
            events[column] = events[column].dt.tz_convert("America/New_York").dt.tz_localize(None)
    if not events.accession_number.is_unique or not events.transaction_group.is_unique:
        raise ValueError("Event accession/transaction identities must be deduplicated before prices.")
    if not set(events.ticker) <= set(runtime.namespace["TOP_100"]):
        raise ValueError("Event provider expanded the frozen universe.")
    if not events.filing_date.between(runtime.fence.start, runtime.fence.end).all():
        raise ScopeViolation("Event provider returned a filing outside the IS fence.")
    if not events.accepted_at.dt.normalize().between(runtime.fence.start, runtime.fence.end).all():
        raise ScopeViolation("Event provider returned acceptance information outside the IS fence.")
    for row in events.itertuples(index=False):
        expected = (runtime.clock.pre_public_session(row.accepted_at), runtime.clock.public_signal_session(row.accepted_at),
                    runtime.clock.first_full_session_close(row.accepted_at))
        if (row.t_pre, row.t_0, row.entry_day) != expected:
            raise ValueError("Event public clock does not match the validated NYSE calendar.")
    return events.sort_values(["accepted_at", "accession_number"]).reset_index(drop=True)


@dataclass
class RunResult:
    tables: dict
    portfolio: dict
    priced: list
    placebo_priced: list
    manifest: dict

    def to_private_snapshot(self) -> dict:
        def frame(value):
            return json.loads(value.to_json(orient="split", date_format="iso"))
        portfolio = {key: frame(value) if isinstance(value, pd.DataFrame) else value
                     for key, value in self.portfolio.items() if isinstance(value, pd.DataFrame) or key in ("config", "limitations")}
        contracts = []
        for event in self.priced:
            if event.bucket != "3-6m":
                continue
            row = {key: str(getattr(event, key)) if isinstance(getattr(event, key), pd.Timestamp) else getattr(event, key)
                   for key in ("ticker", "event_date", "t_pre", "t_0", "entry_day", "accepted_at", "accession_number",
                               "source_tags", "bucket", "expiry", "expiry_session", "spot_pre", "strikes", "observation_end")}
            row["legs"] = {key: {"ticker": leg.ticker, "kind": leg.kind, "strike": leg.strike, "bars": frame(leg.bars)}
                           for key, leg in event.legs.items()}
            contracts.append(row)
        return {"kind": "private_clean_process_IS_snapshot_contains_licensed_inputs",
                "tables": {key: frame(value) for key, value in self.tables.items()}, "portfolio": portfolio,
                "priced_primary": contracts, "oos_read": False, "runtime_manifest": self.manifest}


def run_is(runtime: Runtime, *, event_mode="approved_is_v1", corrected_rows=None,
           event_provider: Callable | None = None, candidate_events: pd.DataFrame | None = None) -> RunResult:
    """Run explicitly, after caller authorization, with the unchanged primary design.

    corrected_rows are four-tuples (ticker,target,accession,accepted_at), supplied
    from a separate price-blind adjudication manifest. General-auto provider is
    a callback accepting keyword tags,start,end,universe,raw,calendar,api_get_all;
    it must preserve evidence/decisions in DataFrame.attrs for the caller audit.
    This entry point is IS-only regardless of any provider's other capabilities.
    """
    ns = runtime.namespace
    if event_mode not in {"approved_is_v1", "corrected_is_v2", "general_auto_is"}:
        raise ValueError("Unknown IS event mode.")
    raw = _raw_candidates(runtime) if candidate_events is None else candidate_events.copy()
    if not set(RAW_COLUMNS[-3:]) <= set(raw):
        raise ValueError("Supplied candidate table lacks normalized source/accession/ticker fields.")
    if len(raw):
        raw["filing_date"] = pd.to_datetime(raw["filing_date"])
        if getattr(raw.filing_date.dt, "tz", None) is not None or not raw.filing_date.between(runtime.fence.start, runtime.fence.end).all():
            raise ScopeViolation("Candidate table contains records outside the declared IS interval.")
    original_approved = ns["APPROVED_IS"]
    if event_mode == "general_auto_is":
        if event_provider is None:
            raise ValueError("General-auto IS requires an explicit audited event provider.")
        events = event_provider(tags=ns["EVENT_TAGS"], start=ns["STUDY_START"], end=ns["STUDY_END"],
                                universe=ns["TOP_100"], raw=raw, calendar=runtime.clock, api_get_all=runtime.fence.get_all)
    else:
        chosen = original_approved if event_mode == "approved_is_v1" else corrected_rows
        if chosen is None:
            raise ValueError("Corrected mode requires a separately approved, explicit event manifest.")
        chosen = list(chosen)
        if any(not isinstance(row, (tuple, list)) or len(row) != 4 for row in chosen):
            raise ValueError("Reviewed rows must be four-tuples of ticker, target, accession, acceptance.")
        chosen = [row for row in chosen if runtime.fence.start <= pd.Timestamp(row[3]).normalize() <= runtime.fence.end]
        ns["APPROVED_IS"] = chosen
        try:
            events = ns["build_events"](ns["EVENT_TAGS"], ns["STUDY_START"], ns["STUDY_END"], ns["TOP_100"], raw=raw) if chosen else pd.DataFrame(columns=EVENT_COLUMNS)
        finally:
            ns["APPROVED_IS"] = original_approved
    event_audit_attrs = dict(events.attrs)
    events = _normalize_events(events, runtime)
    priced, dropped = ns["price_events"](events, label=event_mode, observation_end=runtime.fence.end)
    def evaluate(prices, haircut):
        output = ns["evaluate"](prices, haircut=haircut)
        if len(output):
            outside = ~pd.to_datetime(output.entry_date).between(runtime.fence.start, runtime.fence.end)
            if outside.any():
                # Warmup can select contracts; it must not create pre-IS outcomes.
                outcome_columns = [c for c in output if c.endswith(("_gross", "_cost", "_net"))
                                   or c in {"S_entry", "S_exit", "realized", "ratio", "implied_scaled"}]
                output.loc[outside, outcome_columns] = np.nan
                output.loc[outside, "coverage_reason"] = "ENTRY_OUTSIDE_IS_OBSERVATION_WINDOW_FEATURE_WARMUP_ONLY"
        return output.reindex(columns=list(dict.fromkeys(RESULT_COLUMNS + list(output.columns))))
    results = evaluate(priced, ns["COST_HAIRCUT"])
    placebo_events = ns["sample_placebo"](events, raw, ns["N_PLACEBO"], ns["STUDY_START"], ns["STUDY_END"]) if len(events) else pd.DataFrame(columns=PLACEBO_COLUMNS)
    placebo_priced, placebo_dropped = ns["price_events"](placebo_events, label="ordinary dates", observation_end=runtime.fence.end)
    placebo_results = evaluate(placebo_priced, ns["COST_HAIRCUT"])
    official = ns["difference_board"](results, placebo_results, strategies=["covered_call_net"])
    theta = ns["difference_board"](results, placebo_results, strategies=["incremental_net"])
    grid = []
    for category in ("union",) + ns["EVENT_TAGS"]:
        a, b = ns["category_slice"](results, category), ns["category_slice"](placebo_results, category)
        for bucket in ns["EXPIRY_BUCKETS"]:
            for entry in ("post", "next_open", "full", "pre"):
                for otm in ns["OTM_GRID"]:
                    board = ns["difference_board"](a, b, bucket=bucket, entry=entry, otm=otm, strategies=["incremental_net"])
                    for row in board.itertuples(index=False):
                        grid.append({"category": category, "bucket": bucket, "entry": entry, "otm": otm,
                                     "horizon": row.horizon, "n_event": row.n_a, "n_ordinary": row.n_b,
                                     "theta": row.difference, "ci_lo": row.ci_lo, "ci_hi": row.ci_hi,
                                     "timing_status": "DIAGNOSTIC_NOT_TRADEABLE" if entry == "pre" else "COVERAGE_AND_CLOCK_GUARDS_REQUIRED"})
    portfolio = ns["simulate_portfolio"](priced, ns["STUDY_START"], ns["STUDY_END"], ns["SECTOR_BY_TICKER"],
                    initial_nav=ns["INITIAL_NAV"], primary_horizon=ns["PRIMARY_HORIZON"], otm=ns["OTM_PCT"], haircut=ns["COST_HAIRCUT"])
    if portfolio["ledger"].empty:
        portfolio["ledger"] = pd.DataFrame(columns=["trade_id", "ticker", "accession_number", "contracts", "status", "reason",
                                                    "entry_date", "scheduled_exit", "actual_exit", "entry_cash_debit", "exit_cash_credit"])
    tables = {"events": events, "candidate_events": raw, "results": results, "placebo_events": placebo_events,
              "placebo_results": placebo_results, "sensitivity": pd.DataFrame(grid), "theta_board": theta,
              "official_diff": official, "dropped": dropped, "placebo_dropped": placebo_dropped,
              "event_stress": evaluate(priced, 2 * ns["COST_HAIRCUT"]),
              "ordinary_stress": evaluate(placebo_priced, 2 * ns["COST_HAIRCUT"])}
    manifest = {"event_mode": event_mode, "window": [ns["STUDY_START"], ns["STUDY_END"]],
                "feature_warmup_start": str(runtime.fence.feature_start.date()),
                "warmup_scope": "Option bars and historical contract metadata only; no additional events or pre-IS outcomes",
                "source_name": runtime.source_name, "source_sha256": runtime.source_sha256,
                "calendar_matches_original_full_is": runtime.calendar_matches_original_is,
                "credential_code_loaded": False, "notebook_cells_executed": False, "oos_access": False,
                "sealed_access": False, "boundary_notes": runtime.fence.boundary_notes.copy(),
                "transport_requests": runtime.fence.requests.copy(), "event_audit_attrs": event_audit_attrs,
                "primary_rule_changed": False, "original_approved_manifest_restored": ns["APPROVED_IS"] == original_approved,
                "portfolio_open_at_window_end": int((portfolio["ledger"].status == "OPEN_AT_WINDOW_END").sum()),
                "note": "Results must be compared with the archived first-IS snapshot before claiming exact reproduction. Corrected/auto labels are distinct post-IS operational modes, never replacements of the archived result."}
    return RunResult(tables, portfolio, priced, placebo_priced, manifest)


def run_oos(*args, **kwargs):
    raise ScopeViolation("OOS remains blocked here. An external frozen/readiness-verified one-time evaluation implementation is required; a flag alone cannot enable it.")
