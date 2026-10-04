"""Accepted post-IS literal-tag variant; no execution or authentication on import.

This is NOT the screened first-buyer hypothesis. It uses one economic tag union,
one covered-call proxy, no SEC downloads, and a conservative filing-date clock.
The public judges function needs only API transports and dates. Contestant OOS
authorization and its one-shot journal belong to the root runner, not this code.
"""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd
from event_pipeline import NYSEClock, EVENT_COLUMNS, canonical_filer_ticker, ticker_tokens
from research_runtime import load_runtime, _raw_candidates, RunResult, ScopeViolation

VERSION = "LITERAL_TAG_UNION_POST_IS_V4"
TIMING_BASIS = "FILING_DATE_ONLY_NEXT_SESSION"


def check_window(start, end, *, role, authorized=False):
    first, last = pd.Timestamp(start), pd.Timestamp(end)
    if any(pd.isna(x) or x.tzinfo is not None or x != x.normalize() for x in (first,last)) or first > last:
        raise ScopeViolation("Use a non-reversed calendar-date interval.")
    if role == "is" and not pd.Timestamp("2024-01-01") <= first <= last <= pd.Timestamp("2025-12-31"):
        raise ScopeViolation("Contestant IS must stay within2024-2025.")
    if role == "oos" and (authorized is not True or (str(first.date()),str(last.date())) != ("2026-01-01","2026-08-31")):
        raise ScopeViolation("Contestant OOS needs explicit authorization and its complete fixed window.")
    if role == "judges" and authorized is not True:
        raise ScopeViolation("Judges execution must be explicitly selected; contestant modes cannot access sealed dates.")
    if role not in {"is","oos","judges"}:
        raise ScopeViolation("Unknown execution role.")
    return first, last


class FilingDateClock(NYSEClock):
    """A labeled scheduling proxy, never a claim about SEC acceptance."""
    def pre_public_session(self, value):
        return self.session_before(pd.Timestamp(value).normalize())

    def public_signal_session(self, value):
        return self.next_session(pd.Timestamp(value).normalize())

    def first_full_session_close(self, value):
        return self.next_session(pd.Timestamp(value).normalize())

    def next_public_open(self, value):
        return self.first_full_session_close(value)

    def acceptance_regime(self, value):
        return "FILING_DATE_ONLY"


def literal_events(raw, universe, clock, end):
    """Deduplicate accession/tags; do not infer buyer, control, firstness or targets."""
    universe = set(universe)
    rows, audit = [], []
    if raw.empty:
        result = pd.DataFrame(columns=EVENT_COLUMNS)
        result.attrs["classification_audit"] = pd.DataFrame()
        return result
    for accession, group in raw.groupby("accession_id", sort=True):
        days = pd.to_datetime(group.filing_date).dt.normalize().unique()
        if len(days) != 1:
            raise ValueError("Duplicate accession rows disagree about filing date.")
        tickers = {canonical_filer_ticker(t) for value in group.tickers for t in ticker_tokens(value)} & universe
        if len(tickers) != 1:
            audit.append({"accession_number":accession,"status":"SKIP","reason":"NO_UNAMBIGUOUS_TOP100_TICKER"})
            continue
        day = pd.Timestamp(days[0])
        entry = clock.first_full_session_close(day)
        if entry > pd.Timestamp(end):
            audit.append({"accession_number":accession,"status":"SKIP","reason":"NO_FULL_SESSION_INSIDE_WINDOW"})
            continue
        ticker = next(iter(tickers))
        # Internal scheduling compatibility field only. It is deliberately after
        # every regular close, makes filing-day post-close trading unavailable,
        # and is separately labeled in the event table and run manifest.
        anchor = day + pd.Timedelta(hours=23,minutes=59,seconds=59)
        rows.append({"ticker":ticker,"target":"NOT_CLASSIFIED","transaction_group":"ACCESSION:"+accession,
            "accession_number":accession,"source_tags":tuple(sorted(set(group.source_tag))),
            "filing_date":day,"filing_url":group.iloc[0].get("filing_url", ""),
            "supporting_text":group.iloc[0].get("supporting_text", ""),"accepted_at":anchor,
            "scheduling_anchor":anchor,"actual_sec_acceptance":None,"timing_basis":TIMING_BASIS,
            "t_pre":clock.pre_public_session(day),"t_0":entry,"entry_day":entry,"event_date":day,
            "days_since_prev_event":None})
        audit.append({"accession_number":accession,"ticker":ticker,"status":"TAG_INCLUDED",
            "reason":"LITERAL_VENDOR_TAG_NO_FIRST_BUYER_OR_CONTROL_CLAIM"})
    result = pd.DataFrame(rows, columns=EVENT_COLUMNS+["scheduling_anchor","actual_sec_acceptance","timing_basis"])
    result = result.sort_values(["filing_date","accession_number"]).reset_index(drop=True)
    if len(result):
        result["days_since_prev_event"] = result.groupby("ticker").filing_date.diff().dt.days
    result.attrs["classification_audit"] = pd.DataFrame(audit)
    return result


def run_submission(notebook, start, end, api_get, api_get_all, *, role="is", authorized=False,
                   sector_by_ticker=None, before_market=None):
    """Explicit execution only, after adopting this operational variant.

    For contestant OOS, the root runner's before_market callback must atomically
    claim the one outcome attempt. Failed source enumeration happens before that
    callback; no option-bar/contract request precedes it. Judges use arbitrary
    supplied dates without private freeze files or accession lists.
    """
    first,last = check_window(start,end,role=role,authorized=authorized)
    warmup = str((first-pd.Timedelta(days=31)).date())
    clock = FilingDateClock(NYSEClock.for_window(start,end).schedule)
    runtime = load_runtime(Path(notebook),api_get,api_get_all,start=str(first.date()),end=str(last.date()),
        warmup_start=warmup,clock=clock,window_role="submission",submission_authorized=True)
    ns = runtime.namespace
    sectors = dict(ns["SECTOR_BY_TICKER"] if sector_by_ticker is None else sector_by_ticker)
    if not set(sectors) <= set(ns["TOP_100"]):
        raise ScopeViolation("Sector metadata expands the frozen universe.")
    ns["SECTOR_BY_TICKER"] = sectors
    raw = _raw_candidates(runtime)
    events = literal_events(raw,ns["TOP_100"],clock,last)
    event_audit = events.attrs.get("classification_audit",pd.DataFrame()).copy()
    if role == "oos" and before_market is None:
        raise ScopeViolation("Contestant OOS requires the runner's one-shot outcome claim.")
    if before_market is not None:
        before_market()
    priced,dropped = ns["price_events"](events,label=VERSION,observation_end=last)
    def evaluate(prices,haircut):
        output=ns["evaluate"](prices,haircut=haircut)
        if len(output):
            outside=~pd.to_datetime(output.entry_date).between(first,last)
            if outside.any():
                outcomes=[c for c in output if c.endswith(("_gross","_cost","_net"))
                          or c in {"S_entry","S_exit","realized","ratio","implied_scaled"}]
                output.loc[outside,outcomes]=np.nan
                output.loc[outside,"coverage_reason"]="ENTRY_OUTSIDE_WINDOW_FEATURE_WARMUP_ONLY"
        return output
    results = evaluate(priced,ns["COST_HAIRCUT"])
    ordinary = ns["sample_placebo"](events,raw,ns["N_PLACEBO"],start,end) if len(events) else pd.DataFrame()
    placebo,placebo_dropped = ns["price_events"](ordinary,label="ordinary dates",observation_end=last)
    controls = evaluate(placebo,ns["COST_HAIRCUT"])
    theta = ns["difference_board"](results,controls,strategies=["incremental_net"])
    official = ns["difference_board"](results,controls,strategies=["covered_call_net"])
    grid=[]
    for category in ("union",)+ns["EVENT_TAGS"]:
        a,b=ns["category_slice"](results,category),ns["category_slice"](controls,category)
        for bucket in ns["EXPIRY_BUCKETS"]:
            for entry in ("post","next_open","full","pre"):
                for otm in ns["OTM_GRID"]:
                    board=ns["difference_board"](a,b,bucket=bucket,entry=entry,otm=otm,strategies=["incremental_net"])
                    for row in board.itertuples(index=False):
                        grid.append({"category":category,"bucket":bucket,"entry":entry,"otm":otm,
                            "horizon":row.horizon,"n_event":row.n_a,"n_ordinary":row.n_b,"theta":row.difference,
                            "ci_lo":row.ci_lo,"ci_hi":row.ci_hi,"timing_basis":TIMING_BASIS,
                            "timing_status":"DIAGNOSTIC_NOT_TRADEABLE" if entry in {"pre","post"} else "DATE_ONLY_AFTER_FILING"})
    from causal_portfolio import simulate_causal_portfolio
    portfolio=simulate_causal_portfolio(priced,start,end,sectors,namespace=ns,clock=clock,
        window_role="submission",submission_authorized=True,feature_warmup_start=warmup)
    tables={"events":events,"candidate_events":raw,"classification_audit":event_audit,"results":results,
        "placebo_events":ordinary,"placebo_results":controls,"theta_board":theta,"official_diff":official,
        "sensitivity":pd.DataFrame(grid),"dropped":dropped,"placebo_dropped":placebo_dropped,
        "stress_theta_board":ns["difference_board"](evaluate(priced,2*ns["COST_HAIRCUT"]),evaluate(placebo,2*ns["COST_HAIRCUT"]),strategies=["incremental_net"]),
        "event_stress":evaluate(priced,2*ns["COST_HAIRCUT"]),"ordinary_stress":evaluate(placebo,2*ns["COST_HAIRCUT"]),
        "implied_realized":ns["implied_realized_summary"](ns["slice_results"](results,ns["BASELINE_BUCKET"],"pre",ns["OTM_PCT"])),
        "ordinary_implied_realized":ns["implied_realized_summary"](ns["slice_results"](controls,ns["BASELINE_BUCKET"],"pre",ns["OTM_PCT"]))}
    manifest={"version":VERSION,"window":[str(first.date()),str(last.date())],"role":role,
        "post_IS_operational_variant":True,"original_screened_primary_reproduced":False,
        "timing_basis":TIMING_BASIS,"actual_sec_acceptance_available":False,
        "event_definition":"Literal acquisition_agreement OR merger_agreement; deduplicate accession, not transaction",
        "buyer_control_firstness_claim":False,"taxonomy_historical_availability_proven":False,
        "feature_warmup_start":warmup,"oos_access":role=="oos","sealed_access":role=="judges",
        "source_sha256":runtime.source_sha256,"transport_requests":runtime.fence.requests,
        "classification_audit":event_audit.to_dict("records"),
        "portfolio_sector_mapping_policy":"PRESERVE_EXISTING_MAPPING_SKIP_UNMAPPED_IN_PORTFOLIO_ONLY",
        "portfolio_mapped_tickers":sorted(sectors),
        "event_tickers_without_portfolio_sector":sorted(set(events.ticker)-set(sectors)),
        "limitations":["Multi-ticker filings cannot establish issuer identity; ambiguous rows skipped.",
            "Vendor tags can include seller, minority, updates, or repeat transaction disclosures.",
            "This changes event selection and clock after IS; report separately from V1/V2/V3.",
            "Daily option trades are mark proxies, not executable NBBO quotes.",
            "Event theta uses all unambiguous TOP100 tagged filings; the capital ledger skips unmapped sectors under the existing risk rule. These are different estimands."]}
    return RunResult(tables,portfolio,priced,placebo,manifest)


def run_submission_study(start, end, api_key=None, *, judges_window=False):
    """Clean-key/date entry for the explicitly adopted operational version.

    Defining/importing this function performs no authentication or data calls.
    Entrants use the root CLI for the reserved OOS so its journal is enforced.
    """
    from research_runtime import SubmissionFence
    from safe_transport import MassiveSubmission
    project = Path(__file__).resolve().parent.parent
    role = 'judges' if judges_window else 'is'
    if not judges_window and (str(start), str(end)) == ('2026-01-01', '2026-08-31'):
        raise ScopeViolation('Entrants evaluate the reserved OOS once through the root CLI after approval.')
    check_window(start, end, role=role, authorized=judges_window)
    warmup = str((pd.Timestamp(start) - pd.Timedelta(days=31)).date())
    fence = SubmissionFence(start, end, None, None, warmup_start=warmup)
    transport = MassiveSubmission(project, fence=fence)
    if api_key is not None:
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError('A nonempty API key is required; never print it.')
        transport._key = api_key.strip()
    return run_submission(project / 'strategy_defs.py',
        start, end, transport.get, transport.all, role=role, authorized=judges_window)
