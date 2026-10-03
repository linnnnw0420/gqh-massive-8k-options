"""Pure reporting helpers for the frozen GQH event study.

No data retrieval, credential access, strategy selection, or notebook execution.
Inputs must be preselected IS records, or a separately authorized frozen window.
Missing calendar observations never become zero returns. All returns are decimals.
Stress scenarios and bootstrap intervals are diagnostics, not new trading rules.
"""
from __future__ import annotations

from math import erf, exp, isfinite, log, pi, sqrt
from typing import Sequence

import numpy as np
import pandas as pd


def _dates(values) -> pd.DatetimeIndex:
    index = pd.DatetimeIndex(pd.to_datetime(values))
    if index.tz is not None:
        raise ValueError("Use timezone-naive exchange session dates, not timestamps.")
    if not index.equals(index.normalize()) or not index.is_unique or not index.is_monotonic_increasing:
        raise ValueError("Session dates must be normalized, unique, and increasing.")
    return index


def calendar_evidence(daily: pd.DataFrame, expected_sessions, initial_nav: float,
                      annual_sessions: int = 252) -> dict:
    """Supplement the existing scorecard without silently dropping any session.

    expected_sessions must come from the same exchange calendar and requested
    start/end window as the frozen study. Boundary-month returns refer only to
    sessions inside that window and are labeled as such. A month needs every NAV
    and its opening NAV. Worst-month is withheld if any month is unavailable.
    Turnover is two-sided gross / calendar mean NAV, NOT annualized or halved.
    """
    expected = _dates(expected_sessions)
    observed = _dates(daily.index)
    if len(observed.difference(expected)):
        raise ValueError("Daily observations fall outside the declared window.")
    if not isfinite(initial_nav) or initial_nav <= 0 or annual_sessions <= 0:
        raise ValueError("Positive finite initial NAV and annual session count required.")
    if "nav" not in daily:
        raise ValueError("NAV column required.")
    frame = daily.reindex(expected).copy()
    nav = pd.to_numeric(frame.nav, errors="coerce").astype(float)
    previous = nav.shift(1)
    if len(nav):
        previous.iloc[0] = initial_nav
    valid = np.isfinite(nav) & (nav >= 0) & np.isfinite(previous) & (previous > 0)
    returns = (nav / previous - 1).where(valid)
    complete_nav = bool(len(nav) and (np.isfinite(nav) & (nav >= 0)).all())
    complete_returns = bool(len(nav) and valid.all())
    n = len(nav)
    out = {
        "sessions": n, "calendar_rows_absent": len(expected.difference(observed)),
        "nav_gaps": int((~np.isfinite(nav)).sum()),
        "negative_nav_count": int((nav < 0).sum()),
        "complete_calendar_nav": complete_nav, "complete_calendar_returns": complete_returns,
        "annualized_return": np.nan, "annualized_volatility": np.nan,
        "sharpe_rf0": np.nan, "daily_return_skew_unbiased": np.nan,
        "maximum_drawdown": np.nan, "worst_month_return": np.nan,
        "worst_month": None, "total_net_return": np.nan,
        "status": "COMPLETE" if complete_returns else "INCOMPLETE_CALENDAR_PATH",
        "conventions": "252-session endpoint CAGR; ddof=1 volatility; rf=0 Sharpe; adjusted Fisher-Pearson daily skew; all idle-cash days retained",
    }
    if n and np.isfinite(nav.iloc[-1]):
        out["total_net_return"] = float(nav.iloc[-1] / initial_nav - 1)
        if nav.iloc[-1] >= 0:
            out["annualized_return"] = float((nav.iloc[-1] / initial_nav) ** (annual_sessions / n) - 1)
    if complete_nav:
        peaks = np.maximum.accumulate(np.r_[initial_nav, nav.to_numpy()])[1:]
        out["maximum_drawdown"] = float(np.max(1 - nav.to_numpy() / peaks))
    if complete_returns and n > 1:
        sigma = float(returns.std(ddof=1))
        out["annualized_volatility"] = sigma * sqrt(annual_sessions)
        if sigma > 0:
            out["sharpe_rf0"] = float(returns.mean() / sigma * sqrt(annual_sessions))
            if n >= 3:
                out["daily_return_skew_unbiased"] = float(returns.skew())
    monthly = []
    for period in expected.to_period("M").unique():
        mask = expected.to_period("M") == period
        dates = expected[mask]
        start_position = int(np.flatnonzero(mask)[0])
        beginning = initial_nav if start_position == 0 else nav.iloc[start_position - 1]
        marks = nav.loc[dates]
        good = bool(isfinite(beginning) and beginning > 0 and
                    (np.isfinite(marks) & (marks >= 0)).all())
        monthly.append({"month": str(period), "first_in_window_session": str(dates[0].date()),
                        "last_in_window_session": str(dates[-1].date()),
                        "sessions": len(dates), "return": float(marks.iloc[-1] / beginning - 1) if good else np.nan,
                        "status": "COMPLETE_IN_WINDOW_MONTH" if good else "UNAVAILABLE_NAV_OR_BEGINNING_GAP"})
    if monthly and all(np.isfinite(row["return"]) for row in monthly):
        worst = min(monthly, key=lambda row: row["return"])
        out["worst_month_return"], out["worst_month"] = worst["return"], worst["month"]
    out["monthly"] = pd.DataFrame(monthly)
    out["daily_returns"] = returns
    out["turnover"] = {}
    for col in ("traded_stock_gross", "traded_option_premium_gross", "traded_option_underlying_gross"):
        amounts = pd.to_numeric(frame[col], errors="coerce") if col in frame else pd.Series(np.nan, index=expected)
        flow_complete = bool(n and (np.isfinite(amounts) & (amounts >= 0)).all())
        total = float(amounts.sum()) if flow_complete else np.nan
        mean_nav = float(nav.mean()) if complete_nav else np.nan
        out["turnover"][col] = {
            "gross_usd": total, "two_sided_over_mean_nav": total / mean_nav if mean_nav > 0 else np.nan,
            "over_initial_nav_diagnostic": total / initial_nav,
            "status": "COMPLETE" if flow_complete and complete_nav else "UNAVAILABLE_COMPLETE_NAV_OR_CASHFLOWS",
        }
    return out


def factor_evidence(daily_returns: pd.Series, factors: pd.DataFrame, expected_sessions,
                    factor_columns: Sequence[str] = ("Mkt-RF", "HML", "Mom"),
                    rf_column: str = "RF", hac_lags: int = 21) -> dict:
    """OLS excess-return attribution with Bartlett/Newey-West covariance.

    Input factors and RF are DAILY DECIMAL returns (French downloads need /100).
    No incomplete-session deletion or interpolation. The 21-lag diagnostic is
    tied to the frozen 21-session holding horizon; it is not fitted for significance.
    Its normal intervals are asymptotic descriptions, not reliable small-event
    inference or evidence of causal event alpha. Equity factors do not span the
    nonlinear short-volatility risk of covered calls. Idle days stay in the sample.
    """
    dates = _dates(expected_sessions)
    _dates(daily_returns.index)
    _dates(factors.index)
    if len(daily_returns.index.difference(dates)):
        raise ValueError("Returns fall outside the declared session window.")
    if hac_lags < 0 or not isinstance(hac_lags, int):
        raise ValueError("HAC lags must be a nonnegative integer.")
    columns = list(factor_columns)
    if not columns or len(set(columns)) != len(columns) or rf_column in columns:
        raise ValueError("Distinct factor names excluding RF required.")
    missing_columns = set(columns + [rf_column]).difference(factors.columns)
    if missing_columns:
        raise ValueError(f"Missing factor columns: {sorted(missing_columns)}")
    ret = pd.to_numeric(daily_returns.reindex(dates), errors="coerce").to_numpy(float)
    data = factors.reindex(dates)[columns + [rf_column]].apply(pd.to_numeric, errors="coerce")
    finite = np.isfinite(ret) & np.isfinite(data.to_numpy()).all(axis=1)
    n, k = len(dates), len(columns) + 1
    result = {"sessions": n, "complete_rows": int(finite.sum()), "hac_lags": hac_lags,
              "status": "UNAVAILABLE_INCOMPLETE_PATH", "coefficients": pd.DataFrame(),
              "correlation": pd.DataFrame(), "r_squared": np.nan,
              "nonzero_return_sessions": int((np.isfinite(ret) & (ret != 0)).sum()),
              "inference": "Descriptive OLS with asymptotic HAC intervals; few independent events and nonlinear option exposure prevent a stable-alpha claim."}
    if not n or not finite.all():
        return result
    if n <= k + hac_lags:
        result["status"] = "UNAVAILABLE_INSUFFICIENT_SESSIONS_FOR_SPECIFIED_HAC"
        return result
    y = ret - data[rf_column].to_numpy(float)
    x = np.column_stack([np.ones(n), data[columns].to_numpy(float)])
    if np.linalg.matrix_rank(x) < k:
        result["status"] = "UNAVAILABLE_RANK_DEFICIENT_FACTORS"
        return result
    beta = np.linalg.lstsq(x, y, rcond=None)[0]
    errors = y - x @ beta
    scores = x * errors[:, None]
    meat = scores.T @ scores
    for lag in range(1, hac_lags + 1):
        covariance = scores[lag:].T @ scores[:-lag]
        meat += (1 - lag / (hac_lags + 1)) * (covariance + covariance.T)
    bread = np.linalg.inv(x.T @ x)
    covariance = bread @ meat @ bread * n / (n - k)
    se = np.sqrt(np.maximum(np.diag(covariance), 0))
    names = ["daily_intercept"] + columns
    result["coefficients"] = pd.DataFrame({"term": names, "estimate": beta,
        "hac_standard_error": se, "asymptotic_95_low": beta - 1.95996398454 * se,
        "asymptotic_95_high": beta + 1.95996398454 * se})
    matrix = data[columns].copy()
    matrix.insert(0, "portfolio_excess", y)
    result["correlation"] = matrix.corr().rename_axis("variable").reset_index()
    denominator = np.sum((y - y.mean()) ** 2)
    result["r_squared"] = float(1 - np.sum(errors ** 2) / denominator) if denominator > 0 else np.nan
    result["annualized_intercept_arithmetic_diagnostic"] = float(beta[0] * 252)
    result["status"] = "DESCRIPTIVE_COMPLETE_CALENDAR"
    result["condition_number"] = float(np.linalg.cond(x))
    return result


def _normal_cdf(x: float) -> float:
    return .5 * (1 + erf(x / sqrt(2)))


def european_call_put(spot: float, strike: float, years: float, rate: float,
                      volatility: float) -> tuple[float, float, float, float]:
    """No-dividend European model call, put, call delta, call vega per 1.0 IV.

    This is only a transparent scenario calculator. It is not a replacement for
    market quotes, American exercise/assignment, dividend, or deliverable handling.
    """
    if not all(isfinite(v) for v in (spot, strike, years, rate, volatility)):
        raise ValueError("Finite scenario inputs required.")
    if spot < 0 or strike <= 0 or years < 0 or volatility < 0:
        raise ValueError("Nonnegative spot/time/volatility and positive strike required.")
    discount = strike * exp(-rate * years)
    if spot == 0:
        return 0., discount, 0., 0.
    if years == 0 or volatility == 0:
        call = max(spot - discount, 0.)
        return call, max(discount - spot, 0.), float(spot > discount), 0.
    d1 = (log(spot / strike) + (rate + .5 * volatility ** 2) * years) / (volatility * sqrt(years))
    d2 = d1 - volatility * sqrt(years)
    call = spot * _normal_cdf(d1) - discount * _normal_cdf(d2)
    put = discount * _normal_cdf(-d2) - spot * _normal_cdf(-d1)
    vega = spot * exp(-.5 * d1 ** 2) / sqrt(2 * pi) * sqrt(years)
    return call, put, _normal_cdf(d1), vega


def synthetic_covered_call_stress(entry_marks: dict, synthetic_strike: float,
                                  short_strike: float, entry_years: float,
                                  rate: float, scenarios: Sequence[dict],
                                  haircut: float = .05, contracts: int = 1,
                                  multiplier: int = 100) -> dict:
    """Match the notebook's bond + C(K) - P(K) - C(U) cash bookkeeping.

    entry_marks has C_K, P_K and C_U, per share. Each fixed scenario specifies
    name, spot, years_remaining, volatility. Rate is the notebook rate and cash
    earns zero. No new financing or assignment assumptions are silently inserted.
    Exit haircuts apply to ALL three gross premiums, as in the frozen model.

    At expiry gross proceeds = min(S, U). With any positive uncapped percentage
    haircut, two deep-ITM calls have premiums growing with S. Therefore model
    liquidation costs make worst-case net loss unbounded as S -> infinity. A
    finite scenario grid cannot be advertised as a mathematical maximum loss.
    """
    required = ("C_K", "P_K", "C_U")
    if not all(k in entry_marks and isfinite(entry_marks[k]) and entry_marks[k] >= 0 for k in required):
        raise ValueError("Three finite nonnegative entry premiums required.")
    if not all(isfinite(v) for v in (synthetic_strike, short_strike, entry_years, rate, haircut)):
        raise ValueError("Finite model terms required.")
    if synthetic_strike <= 0 or short_strike <= 0 or entry_years < 0 or haircut < 0:
        raise ValueError("Positive strikes and nonnegative time/cost required.")
    if not isinstance(contracts, int) or contracts <= 0 or multiplier != 100:
        raise ValueError("Only positive integer standard 100-share contracts supported.")
    quantity = contracts * multiplier
    synthetic_spot = synthetic_strike * exp(-rate * entry_years) + entry_marks["C_K"] - entry_marks["P_K"]
    if synthetic_spot <= 0:
        raise ValueError("Positive entry synthetic spot required.")
    gross_debit = quantity * (synthetic_spot - entry_marks["C_U"])
    entry_cost = quantity * haircut * sum(entry_marks[k] for k in required)
    entry_debit = gross_debit + entry_cost
    rows = []
    for scenario in scenarios:
        spot, years, vol = (float(scenario[k]) for k in ("spot", "years_remaining", "volatility"))
        if years > entry_years:
            raise ValueError("Stress horizon cannot precede entry.")
        c_k, p_k, _, _ = european_call_put(spot, synthetic_strike, years, rate, vol)
        c_u, _, delta_u, vega_u = european_call_put(spot, short_strike, years, rate, vol)
        implied_spot = synthetic_strike * exp(-rate * years) + c_k - p_k
        cost = quantity * haircut * (c_k + p_k + c_u)
        gross_credit = quantity * (implied_spot - c_u)
        net_pnl = gross_credit - cost - entry_debit
        rows.append({"scenario": str(scenario["name"]), "spot": spot, "years_remaining": years,
            "volatility": vol, "synthetic_spot": implied_spot, "gross_exit_value": gross_credit,
            "entry_haircut_usd": entry_cost, "exit_haircut_usd": cost, "net_pnl": net_pnl,
            "pnl_over_entry_stock_gross": net_pnl / (quantity * synthetic_spot),
            "model_net_delta_shares": quantity * (1 - delta_u),
            "model_net_delta_dollars": quantity * spot * (1 - delta_u),
            "model_short_vega_per_vol_point_usd": -quantity * vega_u / 100,
            "status": "HYPOTHETICAL_EUROPEAN_SCENARIO_NOT_OBSERVED_OUTCOME"})
    table = pd.DataFrame(rows)
    zero_spot_expiry_loss = entry_debit + quantity * haircut * synthetic_strike
    return {"entry_cash_debit": entry_debit, "entry_stock_gross": quantity * synthetic_spot,
        "zero_spot_expiry_model_loss": zero_spot_expiry_loss,
        "gross_payoff_max_loss_before_haircuts": max(gross_debit, 0.),
        "finite_net_max_loss_exists_under_uncapped_exit_haircut": haircut == 0,
        "net_max_loss": max(gross_debit, 0.) if haircut == 0 else np.inf,
        "net_max_loss_reason": "Exit premium haircuts grow without bound on offsetting deep-ITM calls as spot tends to infinity." if haircut else "No-cost terminal payoff minimum is zero.",
        "minimum_grid_pnl": float(table.net_pnl.min()) if len(table) else np.nan,
        "scenarios": table,
        "limitations": "Scenario IV is hypothetical. No dividends, American assignment, financing spread, exercise fees, changed deliverables, bid/ask or market impact. Model Greeks exclude the derivative of assumed liquidation costs. Do not use this to certify live-trading loss limits."}


def _cluster_summary(frame: pd.DataFrame, clusters: np.ndarray, n_boot: int, seed: int) -> dict:
    values = frame["_value"].to_numpy(float)
    event = frame["_event"].to_numpy(bool)
    labels, group = np.unique(clusters.astype(str), return_inverse=True)
    g = len(labels)
    numerator_event = np.bincount(group, weights=np.where(event, values, 0), minlength=g)
    numerator_ordinary = np.bincount(group, weights=np.where(~event, values, 0), minlength=g)
    count_event = np.bincount(group, weights=event.astype(int), minlength=g)
    count_ordinary = np.bincount(group, weights=(~event).astype(int), minlength=g)
    result = {"clusters": g, "largest_cluster_rows": int(np.bincount(group).max()) if g else 0,
        "ci_low": np.nan, "ci_high": np.nan, "valid_draws": 0, "draws": n_boot,
        "leave_one_cluster_out_min": np.nan, "leave_one_cluster_out_max": np.nan,
        "status": "UNAVAILABLE_FEWER_THAN_TWO_CLUSTERS",
        "inference": "Exploratory percentile resampling, not calibrated small-cluster confidence. Preserve both groups within each cluster; no p-value or significance claim."}
    if g < 2:
        return result
    rng = np.random.default_rng(seed)
    draws, leave = [], []
    for _ in range(n_boot):
        w = rng.multinomial(g, np.repeat(1 / g, g))
        ne, no = w @ count_event, w @ count_ordinary
        if ne and no:
            draws.append((w @ numerator_event) / ne - (w @ numerator_ordinary) / no)
    for i in range(g):
        ne, no = count_event.sum() - count_event[i], count_ordinary.sum() - count_ordinary[i]
        if ne and no:
            leave.append((numerator_event.sum() - numerator_event[i]) / ne -
                         (numerator_ordinary.sum() - numerator_ordinary[i]) / no)
    result["valid_draws"] = len(draws)
    if len(draws) >= .95 * n_boot:
        result["ci_low"], result["ci_high"] = map(float, np.quantile(draws, [.025, .975]))
        result["status"] = "EXPLORATORY_FEW_CLUSTERS" if g < 20 else "EXPLORATORY_CLUSTER_DIAGNOSTIC"
    else:
        result["status"] = "UNAVAILABLE_MANY_DRAWS_LOSE_A_GROUP"
    if leave:
        result["leave_one_cluster_out_min"], result["leave_one_cluster_out_max"] = map(float, (min(leave), max(leave)))
    return result


def dependence_evidence(events: pd.DataFrame, ordinary: pd.DataFrame,
                        value_column: str = "incremental_net", issuer_column: str = "ticker",
                        entry_column: str = "entry_day", exit_column: str = "exit_day",
                        n_boot: int = 2000, seed: int = 20261003) -> dict:
    """Cluster diagnostics for ONE already frozen horizon/entry/expiry/OTM slice.

    Primary theta remains the row-weighted event mean minus ordinary-date mean.
    Two diagnostics separately resample issuer clusters and connected overlapping
    holding-interval clusters. Neither is claimed robust to both dependence axes.
    Interval clusters are transitive and may collapse to one; then no CI is given.
    Missing returns are counted; missing issuer/clock information fails closed.
    No sample trimming, reweighting, parameter ranking or new hypothesis occurs.
    """
    if not isinstance(n_boot, int) or n_boot < 100:
        raise ValueError("At least 100 predeclared bootstrap draws required.")
    frames, counts = [], {}
    for is_event, raw in ((True, events), (False, ordinary)):
        if value_column not in raw or issuer_column not in raw:
            raise ValueError("Value and issuer columns required in both groups.")
        frame = raw.copy()
        frame["_value"] = pd.to_numeric(frame[value_column], errors="coerce")
        good = np.isfinite(frame["_value"])
        counts["event" if is_event else "ordinary"] = {"candidate_rows": len(frame), "finite_rows": int(good.sum())}
        frame = frame.loc[good].copy()
        frame["_event"] = is_event
        frames.append(frame)
    joint = pd.concat(frames, ignore_index=True)
    point = float(frames[0]._value.mean() - frames[1]._value.mean()) if all(len(f) for f in frames) else np.nan
    result = {"theta": point, "coverage": counts, "issuer": {}, "overlap_interval": {},
              "finite_event_issuers": int(frames[0][issuer_column].nunique()),
              "finite_ordinary_issuers": int(frames[1][issuer_column].nunique()),
              "warning": "Few independent events; report this alongside the original IID interval and leave-one-issuer influence. These are separate dependence sensitivities, not simultaneous two-way-robust inference."}
    if not np.isfinite(point):
        result["status"] = "UNAVAILABLE_ONE_GROUP_EMPTY"
        return result
    issuers = joint[issuer_column]
    if issuers.isna().any() or issuers.astype(str).str.strip().eq("").any():
        result["issuer"] = {"status": "UNAVAILABLE_ISSUER_ID_MISSING"}
    else:
        result["issuer"] = _cluster_summary(joint, issuers.astype(str).to_numpy(), n_boot, seed)
    if entry_column not in joint or exit_column not in joint:
        result["overlap_interval"] = {"status": "UNAVAILABLE_HOLDING_INTERVALS"}
        return result
    starts = pd.to_datetime(joint[entry_column], errors="coerce")
    ends = pd.to_datetime(joint[exit_column], errors="coerce")
    if starts.isna().any() or ends.isna().any() or (ends < starts).any():
        result["overlap_interval"] = {"status": "UNAVAILABLE_INVALID_HOLDING_INTERVALS"}
        return result
    labels = np.zeros(len(joint), dtype=int)
    right_edge, label = None, -1
    for i in np.argsort(starts.to_numpy(), kind="stable"):
        if right_edge is None or starts.iloc[i] > right_edge:
            label += 1
            right_edge = ends.iloc[i]
        else:
            right_edge = max(right_edge, ends.iloc[i])
        labels[i] = label
    result["overlap_interval"] = _cluster_summary(joint, labels, n_boot, seed + 1)
    result["status"] = "DESCRIPTIVE_DEPENDENCE_SENSITIVITY"
    return result


def _split_frame(obj: dict, datetime_index: bool = False) -> pd.DataFrame:
    frame = pd.DataFrame(obj["data"], columns=obj["columns"], index=obj["index"])
    if datetime_index:
        frame.index = pd.to_datetime(frame.index)
    return frame


def stress_entry_coverage(ledger: pd.DataFrame) -> tuple[list[dict], dict]:
    """Select known original entry marks for toy stresses; retain omission counts.

    Open or unresolved positions remain exposed. Their known entry marks can be
    stressed without any terminal market observation. An unknown executed entry
    cannot be invented merely because a later exit has a known credit.
    """
    rows=[]; omitted={}; admitted=0
    for row in ledger.to_dict('records'):
        quantity=row.get('contracts',0)
        if row.get('status')=='SKIPPED' or not isinstance(quantity,(int,float)) or not isfinite(quantity) or quantity<=0:
            continue
        admitted+=1
        if quantity!=1:
            raise ValueError('The frozen entry stress expects one contract per admitted position.')
        premiums=row.get('entry_option_premiums')
        values=[premiums.get(key) for key in ('C_K','P_K','C_U0.05')] if isinstance(premiums,dict) else []
        gross=row.get('entry_stock_gross')
        valid=(len(values)==3 and all(isinstance(value,(int,float)) and not isinstance(value,bool)
                                    and isfinite(value) and value>=0 for value in values)
               and isinstance(gross,(int,float)) and not isinstance(gross,bool) and isfinite(gross) and gross>0)
        if not valid:
            omitted['UNAVAILABLE_ENTRY_MARKS']=omitted.get('UNAVAILABLE_ENTRY_MARKS',0)+1
            continue
        rows.append(row)
    return rows,{'admitted_or_committed_positions':admitted,'positions_with_known_entry_stress':len(rows),
                 'positions_omitted':admitted-len(rows),'omission_reasons':omitted,
                 'scope':'All committed positions with known original entry premiums, including open-at-window-end or unresolved exits; missing entries remain unavailable.'}


def summarize_existing_is(snapshot: dict, expected_sessions) -> dict:
    """Derive public-safe aggregates from the private saved first-IS snapshot.

    Only the frozen primary slice is used for inference. The full prespecified
    sensitivity table is counted, not ranked. Hypothetical stress scenarios are
    fixed here before their outputs and use only original entry marks. No raw
    contract prices, option symbols, volumes or instrument-level stress are output.
    """
    if snapshot.get("oos_read") is not False:
        raise ValueError("This CLI accepts only the explicitly tagged untouched-OOS IS snapshot.")
    dates = _dates(expected_sessions)
    if not len(dates) or dates.min() < pd.Timestamp("2024-01-01") or dates.max() > pd.Timestamp("2025-12-31"):
        raise ValueError("Only the frozen 2024-2025 IS window is permitted by this reporting CLI.")
    tables = snapshot["tables"]
    events, ordinary = (_split_frame(tables[key]) for key in ("results", "placebo_results"))
    def primary(frame):
        mask = ((frame.bucket == "3-6m") & (frame.entry == "full") &
                np.isclose(pd.to_numeric(frame.otm), .05) & (frame.horizon.astype(str) == "21"))
        selected = frame.loc[mask].copy()
        for col in ("entry_date", "exit_date"):
            # A requested exit beyond observation_end is retained as an
            # unavailable candidate by the notebook, not an OOS observation.
            finite_outcome = np.isfinite(pd.to_numeric(selected.incremental_net, errors="coerce"))
            observed = pd.to_datetime(selected.loc[finite_outcome, col], errors="coerce").dropna()
            if len(observed) and (observed.min() < dates.min() or observed.max() > dates.max()):
                raise ValueError("Selected record crosses the declared IS observation window.")
        return selected
    event_primary, ordinary_primary = primary(events), primary(ordinary)
    dependence = dependence_evidence(event_primary, ordinary_primary,
                                    entry_column="entry_date", exit_column="exit_date")
    daily = _split_frame(snapshot["portfolio"]["daily"], datetime_index=True)
    calendar = calendar_evidence(daily, dates, snapshot["portfolio"]["config"]["initial_nav"])
    # Session-by-session returns are not needed in a public aggregate report.
    calendar.pop("daily_returns")
    sensitivity = _split_frame(tables["sensitivity"])
    cells = ["category", "bucket", "entry", "otm", "horizon"]
    cell_dimensions = {col: sorted(sensitivity[col].astype(str).unique()) for col in cells}
    finite_theta = np.isfinite(pd.to_numeric(sensitivity.theta, errors="coerce"))
    variants = {"saved_sensitivity_rows": len(sensitivity),
        "distinct_grid_cells": len(sensitivity[cells].drop_duplicates()),
        "duplicate_grid_cells": int(sensitivity[cells].duplicated().sum()),
        "non_horizon_configurations": len(sensitivity[cells[:-1]].drop_duplicates()),
        "cells_with_finite_theta": int(finite_theta.sum()),
        "cells_unavailable": int((~finite_theta).sum()),
        "pre_filing_diagnostic_cells": int((sensitivity.entry == "pre").sum()),
        "dimensions": cell_dimensions,
        "interpretation": "Correlated prespecified report cells, not independent hypothesis tests or a count of all research decisions. Primary covered-call rule unchanged. Base and doubled-cost results both retained. Earlier discarded research ideas require the separate decision log; they cannot be reconstructed from this result table."}
    ledger = _split_frame(snapshot["portfolio"]["ledger"])
    priced = {str(pe["accession_number"]): pe for pe in snapshot["priced_primary"]}
    stress_rows = []
    stress_entries,stress_coverage=stress_entry_coverage(ledger)
    for row in stress_entries:
        pe = priced.get(str(row["accession_number"]))
        if pe is None:
            raise ValueError("Ledger entry is missing its original selected contract metadata.")
        values = row["entry_option_premiums"]
        marks = {"C_K": values["C_K"] / 100, "P_K": values["P_K"] / 100,
                 "C_U": values["C_U0.05"] / 100}
        years = max((pd.Timestamp(pe["expiry"]) - pd.Timestamp(row["entry_date"])).days, 0) / 365
        entry_spot = row["entry_stock_gross"] / 100
        scenarios = []
        # Broad, predeclared toy stress states, never chosen from event outcomes.
        for name, ratio in (("zero_underlying", 0.), ("down_50pct", .5),
                            ("down_25pct", .75), ("flat", 1.),
                            ("up_25pct", 1.25), ("double_underlying", 2.)):
            scenarios.append({"name": "expiry_" + name, "spot": entry_spot * ratio,
                              "years_remaining": 0., "volatility": .30})
        for name, ratio, vol in (("flat_iv20", 1., .20), ("flat_iv60", 1., .60),
                                 ("down25_iv60", .75, .60), ("up25_iv60", 1.25, .60)):
            scenarios.append({"name": "instant_" + name, "spot": entry_spot * ratio,
                              "years_remaining": years, "volatility": vol})
        strike = pe["strikes"]["K"]
        short_strike = pe["legs"]["C_U0.05"]["strike"]
        stress = synthetic_covered_call_stress(marks, strike, short_strike, years, .04, scenarios)
        for item in stress["scenarios"].to_dict("records"):
            stress_rows.append({"scenario": item["scenario"], "pnl_fraction": item["pnl_over_entry_stock_gross"],
                                "net_pnl": item["net_pnl"], "entry_capital": stress["entry_cash_debit"]})
    stress_frame = pd.DataFrame(stress_rows)
    aggregate_stress = []
    if len(stress_frame):
        for name, rows in stress_frame.groupby("scenario", sort=False):
            aggregate_stress.append({"scenario": name, "positions": len(rows),
                "mean_pnl_fraction_entry_stock": float(rows.pnl_fraction.mean()),
                "minimum_pnl_fraction_entry_stock": float(rows.pnl_fraction.min()),
                "maximum_pnl_fraction_entry_stock": float(rows.pnl_fraction.max()),
                "sum_independent_position_pnl_usd": float(rows.net_pnl.sum())})
    board = _split_frame(tables["theta_board"])
    original = board.loc[board.horizon.astype(str) == "21"].to_dict("records")
    costs = {}
    for label, event_key, ordinary_key in (("base", "results", "placebo_results"),
                                          ("doubled", "event_stress", "ordinary_stress")):
        a, b = primary(_split_frame(tables[event_key])), primary(_split_frame(tables[ordinary_key]))
        x, y = pd.to_numeric(a.incremental_net, errors="coerce"), pd.to_numeric(b.incremental_net, errors="coerce")
        x, y = x[np.isfinite(x)], y[np.isfinite(y)]
        costs[label] = {"finite_event": len(x), "finite_ordinary": len(y),
                        "event_mean": float(x.mean()), "ordinary_mean": float(y.mean()),
                        "theta": float(x.mean() - y.mean())}
    return {"kind": "derived_IS_aggregate_evidence_no_raw_quotes",
        "window": [str(dates.min().date()), str(dates.max().date())],
        "primary": {"category": "acquisition_agreement OR merger_agreement", "bucket": "3-6m",
                    "entry": "full", "otm": .05, "horizon_sessions": 21},
        "original_iid_primary": original, "dependence": dependence, "calendar": calendar,
        "variants": variants, "cost_stress_from_existing_results": costs,
        "scenario_stress": {"aggregate": aggregate_stress,"coverage":stress_coverage,
            "not_portfolio_backtest": "All committed positions with known entry marks are stressed independently, including open positions. Unknown entries are explicitly omitted. Sum is NOT a simultaneous portfolio stress because entry dates differ. Scenarios are not predictions or new valuation marks.",
            "not_max_loss": "The frozen uncapped exit haircut has unbounded high-spot modeled liquidation loss; entry debit is not a finite maximum-loss bound.",
            "financing_assignment_limit": "No-dividend European scenario parity at notebook 4% rate; no American assignment, dividend reinvestment, financing spread or execution-depth model."},
        "factor_status": "AWAITING_COMPLETE_UNIFORM_NAV_AND_EXTERNAL_DAILY_FACTORS",
        "research_interpretation": "Positive event-vs-ordinary incremental theta does not imply positive covered-call portfolio returns, causal event alpha, stable edge or adequate executable option prices."}


def _jsonable(value):
    if isinstance(value, pd.DataFrame):
        return [_jsonable(row) for row in value.to_dict("records")]
    if isinstance(value, pd.Series):
        return [_jsonable(x) for x in value.tolist()]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (float, np.floating)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, (pd.Timestamp, pd.Period)):
        return str(value)
    return value


def main():
    import argparse
    import hashlib
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser(description="Derive aggregate evidence from the saved original 2024-2025 IS state; never retrieves data or runs a strategy.")
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--factors", type=Path, help="Optional privately saved, predeclared IS-only daily ETF proxy CSV.")
    args = parser.parse_args()
    if args.snapshot.resolve() == args.output.resolve():
        raise ValueError("Output must not overwrite the private source snapshot.")
    payload = args.snapshot.read_bytes()
    snapshot = json.loads(payload)
    # Exact closed sessions used by the existing notebook's NYSE holiday rules,
    # including the 2025 Carter mourning closure. This CLI is explicitly IS-only;
    # general-window callers must supply their separately validated calendar.
    closures = pd.to_datetime([
        "2024-01-01", "2024-01-15", "2024-02-19", "2024-03-29", "2024-05-27",
        "2024-06-19", "2024-07-04", "2024-09-02", "2024-11-28", "2024-12-25",
        "2025-01-01", "2025-01-09", "2025-01-20", "2025-02-17", "2025-04-18",
        "2025-05-26", "2025-06-19", "2025-07-04", "2025-09-01", "2025-11-27", "2025-12-25"])
    dates = pd.bdate_range("2024-01-01", "2025-12-31").difference(closures)
    report = summarize_existing_is(snapshot, dates)
    report["source_sha256"] = hashlib.sha256(payload).hexdigest()
    if args.factors:
        factor_bytes = args.factors.read_bytes()
        factors = pd.read_csv(args.factors, index_col="date", parse_dates=True)
        factor_columns = ["market_SPY", "value_IWD_minus_IWF", "momentum_MTUM_minus_SPY"]
        if list(factors.columns) != factor_columns:
            raise ValueError("Factor columns do not match the predeclared proxy manifest.")
        factor_dates = dates[dates >= pd.Timestamp("2024-01-03")]
        if not factors.index.equals(factor_dates):
            raise ValueError("Proxy CSV must contain every declared Jan 3 2024-Dec 31 2025 session, with no extras.")
        daily = _split_frame(snapshot["portfolio"]["daily"], datetime_index=True)
        calculated = calendar_evidence(daily, dates, snapshot["portfolio"]["config"]["initial_nav"])
        factors["RF"] = 0.
        evidence = factor_evidence(calculated["daily_returns"].loc[factor_dates], factors,
                                   factor_dates, factor_columns=factor_columns, hac_lags=21)
        evidence["source_sha256"] = hashlib.sha256(factor_bytes).hexdigest()
        evidence["window"] = ["2024-01-03", "2025-12-31"]
        evidence["boundary_day_exclusion"] = "Jan 2 portfolio return excluded only from this regression because no 2023 ETF close was requested. Later missing observations are not dropped."
        evidence["proxy_limitations"] = "Split-adjusted ETF price-return proxies, excluding dividends. Value=IWD-IWF; momentum=MTUM-SPY. These are not Fama-French factors or market-neutral pure style portfolios."
        report["factor_evidence"] = evidence
        report["factor_status"] = evidence["status"]
    args.output.write_text(json.dumps(_jsonable(report), indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "saved_derived_IS_aggregates", "sessions": report["calendar"]["sessions"],
                      "nav_gaps": report["calendar"]["nav_gaps"], "theta": report["dependence"]["theta"]}))


if __name__ == "__main__":
    main()
