"""V3 causal admission repair: pure fixed-contract portfolio transformation.

No I/O, API, credential loading, event pricing, selection or event-statistic call.
The caller supplies previously selected PricedEvents, audited source helpers and
the local NYSE clock. Read causal_portfolio_protocol_v3.md before evaluation.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

MODE = "causal_portfolio_v3"
ET = "America/New_York"


def _date(value):
    stamp = pd.Timestamp(value)
    if pd.isna(stamp) or stamp.tzinfo is not None or stamp != stamp.normalize():
        raise ValueError("A finite, timezone-naive session date is required.")
    return stamp


def _accepted(value):
    stamp = pd.Timestamp(value)
    if pd.isna(stamp):
        raise ValueError("A public signal timestamp is required.")
    return stamp.tz_localize(ET, ambiguous="raise", nonexistent="raise") if stamp.tzinfo is None else stamp.tz_convert(ET)


def _exposures(values):
    names, sectors = {}, {}
    for position, _, spot, _ in values:
        name, sector = position["pe"].ticker, position["row"]["sector"]
        names[name] = names.get(name, 0.0) + 100 * spot
        sectors[sector] = sectors.get(sector, 0.0) + 100 * spot
    return names, sectors


def _capacity_scenarios(capacity, ledger, participation):
    """Retain the original retrospective volume diagnostic, never an order gate."""
    scenarios, identities = [], {row["trade_id"]: row for row in ledger}
    for rate in sorted(set([.005, float(participation), .01, .02])):
        summaries, committed_ids = [], set()
        if not capacity.empty:
            for identity, group in capacity.groupby("trade_id"):
                row, volumes = identities[identity], group.observed_daily_volume
                committed_ids.add(identity)
                # An unpriced committed order is not a confirmed proxy execution.
                if row["entry_execution_status"] != "PRICED_PROXY":
                    continue
                complete = bool(np.isfinite(volumes).all() and (volumes > 0).all())
                entry = group[group.side == "entry"]
                entry_complete = len(entry) == 3 and bool(np.isfinite(entry.observed_daily_volume).all() and (entry.observed_daily_volume > 0).all())
                entry_bottleneck = float(entry.observed_daily_volume.min()) if entry_complete else np.nan
                summaries.append({"trade_id": identity, "complete": complete,
                    "fits": bool(complete and (volumes * rate >= 1).all()),
                    "closed": row["status"] == "CLOSED",
                    "contracts": int(np.floor(volumes.min() * rate)) if complete else np.nan,
                    "entry_capacity_stock_gross": np.floor(entry_bottleneck * rate) * row["entry_stock_gross"]
                        if np.isfinite(entry_bottleneck) else np.nan})
        scenarios.append({"participation_limit": rate, "executed_trades": len(summaries),
            "committed_order_trades": len(committed_ids),
            "unpriced_committed_trades": len(committed_ids)-len(summaries),
            "volume_assessed_trades": sum(x["complete"] for x in summaries),
            "all_observed_sides_fit": sum(x["fits"] for x in summaries),
            "closed_trades_all_sides_fit": sum(x["fits"] and x["closed"] for x in summaries),
            "volume_missing_trades": sum(not x["complete"] for x in summaries),
            "per_trade_contract_capacity": {x["trade_id"]: x["contracts"] for x in summaries},
            "per_trade_entry_stock_gross_capacity": {x["trade_id"]: x["entry_capacity_stock_gross"] for x in summaries}})
    return pd.DataFrame(scenarios)


def simulate_causal_portfolio(priced, start, end, sector_by_ticker, *, namespace, clock,
                             initial_nav=1e6, primary_horizon=21, otm=.05, haircut=.05, participation=.01):
    """Commit orders at open from previous-close financial state; report at close.

    This version is an explicit post-IS causal repair. It changes admission timing,
    not contracts, fees, economic filters, quantities or exits. No current-close
    price or exit credit affects an already committed same-day order. Missing
    execution leaves unknown cash permanently rather than pretending no fill.
    """
    start, end = _date(start), _date(end)
    if not pd.Timestamp("2024-01-01") <= start <= end <= pd.Timestamp("2025-12-31"):
        raise ValueError("Only the existing 2024-2025 IS outcomes are accepted.")
    if (initial_nav, primary_horizon, otm, haircut) != (1e6, 21, .05, .05):
        raise ValueError("V3 retains the frozen capital, horizon, strike offset and cost parameter.")
    if not np.isfinite(participation) or not 0 < participation <= 1:
        raise ValueError("Invalid retrospective capacity scenario.")
    required = {"_portfolio_marks", "_portfolio_volume_rows", "_portfolio_metric_block"}
    if not required <= set(namespace):
        raise ValueError("The original pure reporting/mark helpers are required.")
    marks_at, volume_at, metrics_at = (namespace[name] for name in
        ("_portfolio_marks", "_portfolio_volume_rows", "_portfolio_metric_block"))
    calendar = clock.sessions
    days = calendar[(calendar >= start) & (calendar <= end)]
    if not len(days) or start < calendar[0] or end > calendar[-1]:
        raise ValueError("The local calendar does not cover this portfolio window.")
    # The earliest permissible feature state is the explicitly documented warmup.
    if clock.session_before(days[0]) < pd.Timestamp("2023-12-01"):
        raise ValueError("Prior-session input would exceed the feature-only warmup fence.")
    short_key = f"C_U{otm}"
    ledger, entries, seen = [], {}, set()
    candidates = sorted((pe for pe in priced if pe.bucket == "3-6m"),
                        key=lambda pe: (pd.Timestamp(pe.entry_day), str(pe.ticker), str(pe.accession_number)))
    for pe in candidates:
        entry, signal = _date(pe.entry_day), _date(pe.t_0)
        row = {"trade_id": str(len(ledger)), "ticker": pe.ticker,
            "accession_number": pe.accession_number, "bucket": pe.bucket,
            "source_tags": pe.source_tags, "signal_session": signal, "entry_date": entry,
            "sector": sector_by_ticker.get(pe.ticker), "contracts": 0, "status": "PENDING", "reason": "",
            "entry_stock_gross": np.nan, "entry_short_call_premium": np.nan,
            "entry_cost": np.nan, "exit_cost": np.nan, "net_pnl": np.nan,
            "max_loss_proxy_at_entry": np.nan, "scheduled_exit": pd.NaT, "actual_exit": pd.NaT,
            "entry_mark_ages": None, "exit_mark_ages": None,
            "entry_cash_debit": np.nan, "exit_cash_credit": np.nan,
            "entry_execution_status": "NOT_ORDERED", "exit_execution_status": "NOT_DUE",
            "commitment_status": "NOT_COMMITTED"}
        ledger.append(row)
        identity = (pe.ticker, pe.accession_number, signal)
        if identity in seen:
            row.update(status="SKIPPED", reason="DUPLICATE_PRICED_EVENT")
            continue
        seen.add(identity)
        if not start <= entry <= end:
            row.update(status="SKIPPED", reason="ENTRY_OUTSIDE_WINDOW")
            continue
        if entry not in calendar or signal not in calendar:
            row.update(status="SKIPPED", reason="SESSION_NOT_IN_CALENDAR")
            continue
        accepted = _accepted(pe.accepted_at)
        open_time = clock.schedule.loc[entry, "open"]
        if accepted > open_time or clock.first_full_session_close(accepted) != entry:
            raise ValueError("Entry must be the frozen first-full session and signal public by its open.")
        if _date(pe.t_pre) > clock.session_before(entry):
            raise ValueError("Selected-contract pre-public session exceeds the financial cutoff.")
        i0 = calendar.get_loc(signal)
        if i0 + primary_horizon >= len(calendar):
            row.update(status="SKIPPED", reason="EXIT_OUTSIDE_CALENDAR")
            continue
        target_exit = calendar[i0 + primary_horizon]
        exit_day = min(target_exit, _date(pe.expiry_session))
        row.update(scheduled_exit=exit_day, expiry_capped=exit_day < target_exit)
        if exit_day <= entry:
            row.update(status="SKIPPED", reason="NO_POSITIVE_HOLDING_PERIOD")
            continue
        if not row["sector"] or not isinstance(row["sector"], str):
            row.update(status="SKIPPED", reason="SECTOR_MAPPING_REQUIRED")
            continue
        entries.setdefault(entry, []).append((pe, row))

    active, daily_rows, decisions, volume_rows, breaches = [], [], [], [], []
    cash, peak, paused, unresolved_exit = float(initial_nav), float(initial_nav), False, False

    def known_book(day):
        values, unknown = [], []
        for position in active:
            row, pe = position["row"], position["pe"]
            if row["status"] in {"UNRESOLVED_EXIT", "UNPRICED_EXECUTION"}:
                unknown.append(row["trade_id"] + ":" + row["status"].lower())
                continue
            marks, spot, ages, missing = marks_at(pe, day, short_key)
            if missing:
                unknown.append(row["trade_id"] + ":" + ";".join(missing))
            else:
                values.append((position, marks, spot, ages))
        if not np.isfinite(cash):
            unknown.append("cash:unpriced_execution_or_fixed_exit")
        return values, unknown

    for day in days:
        previous = clock.session_before(day)
        cutoff, decision_time = clock.schedule.loc[previous, "close"], clock.schedule.loc[day, "open"]
        # All admission decisions finish before any current-session mark is consulted.
        prior_values, prior_unknown = known_book(previous)
        prior_nav = cash + sum(100 * (spot - marks[short_key]) for _, marks, spot, _ in prior_values) if not prior_unknown else np.nan
        prior_dd = 1 - prior_nav / peak if np.isfinite(prior_nav) else np.nan
        # Peak/paused are the state already produced by the previous closing report.
        prior_cash, prior_peak, prior_paused = cash, peak, paused
        budget_cash, budget_nav = prior_cash, prior_nav
        names, sectors = _exposures(prior_values)
        committed, committed_tickers, reserved_debits, reserved_costs = [], set(), 0.0, 0.0
        prior_tickers = {p["pe"].ticker for p in active}
        for pe, row in entries.get(day, []):
            audit = {"trade_id": row["trade_id"], "ticker": pe.ticker, "accession_number": pe.accession_number,
                "entry_date": day, "signal_public_at": _accepted(pe.accepted_at),
                "financial_input_session": previous, "financial_input_cutoff": cutoff,
                "decision_at": decision_time, "prior_cash": prior_cash, "prior_nav": prior_nav,
                "prior_peak": prior_peak, "prior_drawdown": prior_dd, "prior_paused": prior_paused,
                "prior_open_trade_ids": tuple(p["row"]["trade_id"] for p in active),
                "prior_unknown_reasons": tuple(prior_unknown), "budget_cash_before": budget_cash,
                "budget_nav_before": budget_nav, "reserved_debits_before": reserved_debits,
                "reserved_costs_before": reserved_costs, "prior_selected_marks": None,
                "prior_selected_mark_ages": None, "estimated_entry_debit": np.nan,
                "estimated_entry_cost": np.nan, "estimated_stock_gross": np.nan,
                "estimated_gross_by_ticker_after": None, "estimated_gross_by_sector_after": None,
                "committed_contracts": 0, "admission": "BLOCKED", "reason": ""}
            reason = ""
            if prior_unknown or unresolved_exit or not np.isfinite(budget_nav) or not np.isfinite(budget_cash):
                reason = "UNKNOWN_PRIOR_PORTFOLIO_STATE_OR_UNRESOLVED_EXIT"
            elif budget_nav <= 0:
                reason = "NONPOSITIVE_PRIOR_NAV"
            elif prior_paused:
                reason = "PRIOR_DRAWDOWN_PAUSE"
            elif pe.ticker in prior_tickers or pe.ticker in committed_tickers:
                reason = "CONCURRENT_SAME_TICKER_PRIOR_OR_COMMITTED"
            else:
                marks, spot, ages, missing = marks_at(pe, previous, short_key)
                audit.update(prior_selected_marks=dict(marks), prior_selected_mark_ages=dict(ages))
                if missing:
                    reason = "PRIOR_SELECTED_MARK_UNAVAILABLE:" + ";".join(missing)
                else:
                    gross = 100 * spot
                    cost = 100 * haircut * sum(abs(value) for value in marks.values())
                    debit = 100 * (spot - marks[short_key]) + cost
                    nav_after = budget_nav - cost
                    names_after, sectors_after = dict(names), dict(sectors)
                    names_after[pe.ticker] = names_after.get(pe.ticker, 0) + gross
                    sectors_after[row["sector"]] = sectors_after.get(row["sector"], 0) + gross
                    audit.update(estimated_entry_debit=debit, estimated_entry_cost=cost, estimated_stock_gross=gross,
                        estimated_gross_by_ticker_after=names_after, estimated_gross_by_sector_after=sectors_after)
                    reason = ("CASH_OR_NAV_LIMIT" if nav_after <= 0 or debit > budget_cash or debit < 0 else
                        "NAME_GROSS_LIMIT" if max(names_after.values()) > .10 * nav_after else
                        "SECTOR_GROSS_LIMIT" if max(sectors_after.values()) > .25 * nav_after else
                        "TOTAL_GROSS_LIMIT" if sum(names_after.values()) > nav_after else "")
                    if not reason:
                        budget_cash -= debit
                        budget_nav = nav_after
                        names, sectors = names_after, sectors_after
                        reserved_debits += debit
                        reserved_costs += cost
                        committed_tickers.add(pe.ticker)
                        committed.append((pe, row))
                        row.update(contracts=1, commitment_status="COMMITTED_AT_OPEN",
                            order_decision_at=decision_time, financial_input_cutoff=cutoff,
                            prior_selected_mark_ages=dict(ages), estimated_entry_cash_debit=debit,
                            estimated_entry_cost=cost, estimated_entry_stock_gross=gross)
                        audit.update(committed_contracts=1, admission="COMMITTED")
            audit.update(reason=reason, budget_cash_after=budget_cash, budget_nav_after=budget_nav,
                         reserved_debits_after=reserved_debits, reserved_costs_after=reserved_costs)
            decisions.append(audit)
            if reason:
                row.update(status="SKIPPED", reason=reason)

        flows = {"traded_stock_gross": 0.0, "traded_option_premium_gross": 0.0,
                 "traded_option_underlying_gross": 0.0, "paid_premium_haircuts": 0.0}
        flow_unknown = False

        def add_flows(marks, spot, cost):
            flows["traded_stock_gross"] += 100 * spot
            flows["traded_option_premium_gross"] += 100 * sum(abs(v) for v in marks.values())
            flows["traded_option_underlying_gross"] += 3 * 100 * spot
            flows["paid_premium_haircuts"] += cost

        # Execution bookkeeping is downstream of the completed admission audit.
        for position in list(active):
            pe, row = position["pe"], position["row"]
            if day != row["scheduled_exit"] or row["status"] not in {"OPEN", "UNPRICED_EXECUTION"}:
                continue
            marks, spot, ages, missing = marks_at(pe, day, short_key)
            row["exit_mark_ages"] = ages
            volume_rows.extend(volume_at(pe, day, "exit", row["trade_id"], short_key))
            if missing:
                row.update(status="UNRESOLVED_EXIT", reason=";".join(missing), exit_execution_status="UNPRICED_FIXED_EXIT")
                unresolved_exit, flow_unknown, cash = True, True, np.nan
                continue
            cost = 100 * haircut * sum(abs(v) for v in marks.values())
            credit = 100 * (spot - marks[short_key]) - cost
            was_unpriced = row["status"] == "UNPRICED_EXECUTION"
            cash += credit  # NaN intentionally stays NaN permanently.
            if was_unpriced:
                # This credit is conditional on the unknown entry having filled;
                # it cannot be counted as an observed execution cashflow.
                flow_unknown = True
            else:
                add_flows(marks, spot, cost)
            row.update(status="CLOSED_WITH_UNPRICED_ENTRY" if was_unpriced else "CLOSED",
                actual_exit=day, exit_cost=cost, exit_option_premiums={k: 100*v for k, v in marks.items()},
                exit_all_option_underlying_gross=3*100*spot, exit_cash_credit=credit,
                exit_execution_status="CONDITIONAL_PROXY_IF_ENTRY_FILLED" if was_unpriced else "PRICED_PROXY",
                conditional_exit_cash_credit=credit if was_unpriced else np.nan,
                net_pnl=credit-row["entry_cash_debit"])
            active.remove(position)
        for pe, row in committed:
            marks, spot, ages, missing = marks_at(pe, day, short_key)
            row["entry_mark_ages"] = ages
            volume_rows.extend(volume_at(pe, day, "entry", row["trade_id"], short_key))
            if missing:
                row.update(status="UNPRICED_EXECUTION", reason=";".join(missing), entry_execution_status="UNPRICED_COMMITTED_ORDER")
                flow_unknown, cash = True, np.nan
                active.append({"pe": pe, "row": row})
                continue
            gross, cost = 100 * spot, 100 * haircut * sum(abs(v) for v in marks.values())
            debit = 100 * (spot - marks[short_key]) + cost
            cash -= debit
            add_flows(marks, spot, cost)
            row.update(status="OPEN", entry_execution_status="PRICED_PROXY", entry_stock_gross=gross,
                entry_short_call_premium=100*marks[short_key], entry_cost=cost, entry_cash_debit=debit,
                entry_option_premiums={k: 100*v for k, v in marks.items()},
                entry_all_option_underlying_gross=3*gross, max_loss_proxy_at_entry=max(debit, 0))
            active.append({"pe": pe, "row": row})
            if debit < 0:
                breaches.append({"date": day, "trade_id": row["trade_id"], "limit": "negative_execution_debit",
                                 "observed_usd": debit, "execution_feasibility_failure": True})

        values, unknown = known_book(day)
        nav = cash + sum(100*(spot-marks[short_key]) for _, marks, spot, _ in values) if not unknown else np.nan
        if np.isfinite(nav):
            peak = max(peak, nav)
            dd = 1-nav/peak
            if dd >= .10:
                paused = True
            elif paused and dd < .05:
                paused = False
        else:
            dd = np.nan
        names, sectors = _exposures(values)
        gross = sum(names.values()) if not unknown else np.nan
        if np.isfinite(cash) and cash < 0:
            breaches.append({"date": day, "limit": "cash", "observed_usd": cash,
                "execution_feasibility_failure": True, "action": "RETAIN_COMMITTED_ORDERS_NO_RETROACTIVE_REJECTION"})
        if np.isfinite(nav) and nav > 0:
            for label, value, limit in (("name", max(names.values(), default=0), .10),
                                       ("sector", max(sectors.values(), default=0), .25), ("total", gross, 1.0)):
                if value/nav > limit:
                    breaches.append({"date": day, "limit": label, "observed_fraction": value/nav,
                                     "limit_fraction": limit, "action": "RETAIN_COMMITTED_ORDERS"})
        daily_rows.append({"date": day, "cash": cash, "nav": nav, "stock_gross": gross,
            "stock_gross_fraction": gross/nav if np.isfinite(nav) and nav > 0 else np.nan,
            "short_call_liability": sum(100*m[short_key] for _,m,_,_ in values) if not unknown else np.nan,
            "stock_value_less_short_call_liability": sum(100*(s-m[short_key]) for _,m,s,_ in values) if not unknown else np.nan,
            "gross_by_ticker": names if not unknown else None, "gross_by_sector": sectors if not unknown else None,
            "drawdown": dd, "new_entries_paused": paused or bool(unknown) or unresolved_exit,
            "open_positions": len(active), "unknown_mark_reasons": tuple(unknown),
            "committed_orders_today": len(committed), "admission_input_cutoff": cutoff,
            "order_decision_at": decision_time, "execution_cashflows_complete": not flow_unknown,
            **{key: np.nan if flow_unknown else value for key, value in flows.items()},
            **{key+"_known_subtotal": value for key, value in flows.items()}})
    for position in active:
        if position["row"]["status"] == "OPEN":
            position["row"].update(status="OPEN_AT_WINDOW_END", reason="FIXED_EXIT_AFTER_WINDOW_END")
    daily = pd.DataFrame(daily_rows).set_index("date")
    previous_nav = daily.nav.shift(1)
    previous_nav.iloc[0] = initial_nav
    valid_returns = np.isfinite(daily.nav) & (daily.nav >= 0) & np.isfinite(previous_nav) & (previous_nav > 0)
    daily["net_return"] = np.nan
    daily.loc[valid_returns, "net_return"] = daily.nav.loc[valid_returns]/previous_nav.loc[valid_returns]-1
    yearly = []
    for year, subset in daily.groupby(daily.index.year):
        first = daily.index.get_loc(subset.index[0])
        beginning = initial_nav if first == 0 else daily.nav.iloc[first-1]
        block = metrics_at(subset, beginning) if np.isfinite(beginning) else {
            "sessions": len(subset), "nav_gaps": int((~np.isfinite(subset.nav)).sum()),
            "status": "UNAVAILABLE_PREVIOUS_NAV_GAP"}
        yearly.append({"year": int(year), **block})
    capacity = pd.DataFrame(volume_rows)
    return {"daily": daily, "ledger": pd.DataFrame(ledger), "order_decisions": pd.DataFrame(decisions),
        "metrics": metrics_at(daily, initial_nav), "annual_metrics": pd.DataFrame(yearly),
        "capacity": capacity, "capacity_scenarios": _capacity_scenarios(capacity, ledger, participation),
        "exposure_breaches": pd.DataFrame(breaches),
        "config": {"mode": MODE, "initial_nav": initial_nav, "bucket": "3-6m", "primary_horizon": primary_horizon,
            "otm": otm, "haircut_each_leg_each_side": haircut, "max_contracts": 1,
            "one_concurrent_per_ticker": True, "name_gross_limit": .10, "sector_gross_limit": .25,
            "total_gross_limit": 1.0, "pause_drawdown": .10, "resume_drawdown_strictly_below": .05,
            "cash_return": 0, "risk_free_for_sharpe": 0, "annual_sessions": 252,
            "entry_order": "entry_date, ticker, accession_number", "volume_conditioned_admission": False,
            "decision_clock": "CURRENT_SESSION_OPEN_AFTER_SIGNAL_PUBLIC",
            "financial_input_clock": "PREVIOUS_NYSE_SESSION_CLOSE",
            "today_exit_proceeds_fund_today_admission": False,
            "unknown_execution_cash_permanent": True, "post_is_causal_repair": True},
        "limitations": [
            "V3 is a post-IS admission-causality repair; preserve original V1/V2 event and portfolio evidence.",
            "Orders commit at open from prior-close financial state and fixed pre-public contracts; same-day exits never enable admissions.",
            "One contract is retained when actual proxy fills breach estimated budgets; negative cash is an unfinanced feasibility failure.",
            "UNPRICED_EXECUTION preserves an unknown committed fill rather than a no-trade assumption; cash uncertainty remains permanent.",
            "A missing fixed exit stays unresolved; later favorable marks never manufacture an exit.",
            "Daily synthetic parity and stale/asynchronous last-trade marks are valuation/execution proxies, not executable NBBO.",
            "Stock financing, dividends, assignment, corporate actions, broker acceptance, settlement and order mechanics are not reconstructed.",
            "All three option legs retain their original 5% premium haircut on each side; the entry debit is not a finite mathematical worst-case-loss bound under uncapped proxy costs.",
            "Current session prices, availability and volume never gate the same session's committed orders; they affect next-session state only.",
            "Capacity remains retrospective daily-volume scenarios, not ADV/NBBO/market-impact dollar capacity.",
            "Gross name/sector/total limits use synthetic stock-reference exposure; marked stock less sold-call value is not delta-adjusted net exposure.",
            "No missing NAV is filled and no return bridges a gap; full-path risk and mean-NAV turnover remain unavailable when incomplete.",
            "Manual industry mappings, historical universe survival, retrospective taxonomy and event-observation biases remain limitations."]}
