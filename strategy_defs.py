"""Pricing and research definitions extracted from the official starter notebook.

Only imports, configuration, classes and function definitions are retained.
No credential loader, notebook results or top-level API call is included.
The previous screened APPROVED_IS constants are retained solely for AST-loader
compatibility and provenance; the literal-tag submission never uses that list.
Original extracted source SHA256: 59d36a0999e182fa8d43a0fa31a59c70563bdde29d39b7f4fae888c3eadbb878
"""
from __future__ import annotations
import json, time, hashlib, re

from dataclasses import dataclass, field

import numpy as np

import pandas as pd

from pandas.tseries.holiday import (AbstractHolidayCalendar, Holiday, nearest_workday, USMartinLutherKingJr,
                                    USPresidentsDay, GoodFriday, USMemorialDay, USLaborDay, USThanksgivingDay)

from pandas.tseries.offsets import CustomBusinessDay

BASE_URL = "https://api.massive.com"

EVENT_TAGS = ("acquisition_agreement", "merger_agreement")

EVENT_TAG = "first_buyer_definitive_agreement"

STUDY_START, STUDY_END = "2024-01-01", "2025-12-31"

IS_OBSERVATION_END = pd.Timestamp(STUDY_END)

OOS_START, OOS_END = "2026-01-01", "2026-08-31"

HOLDOUT_START, HOLDOUT_END = "2023-06-01", "2023-08-31"

TOP_100 = """
AAPL ABBV ABT ACN ADBE AIG AMD AMGN AMT AMZN AVGO AXP BA BAC BK BKNG BLK BMY BRK.B C
CAT CHTR CL CMCSA COF COP COST CRM CSCO CVS CVX DE DHR DIS DUK EMR FDX GD GE GILD
GM GOOGL GS HD HON IBM INTC INTU ISRG JNJ JPM KO LIN LLY LMT LOW MA MCD MDLZ MDT
MET META MMM MO MRK MS MSFT NEE NFLX NKE NOW NVDA ORCL PEP PFE PG PLTR PM PYPL QCOM
RTX SBUX SCHW SO T TGT TMO TMUS TSLA TXN UBER UNH UNP UPS USB V VZ WFC WMT XOM
""".split()

EXPIRY_BUCKETS = {"1m": (21, 45, 30), "2m": (46, 80, 60), "3-6m": (90, 180, 120)}

BASELINE_BUCKET = "3-6m"

HORIZONS = [1, 2, 3, 5, 10, 21, 42, 63]

PRIMARY_HORIZON = 21

OTM_PCT = 0.05

OTM_GRID = [0.03, 0.05, 0.10]

ENTRY = "full"

RISK_FREE = 0.04

STRIKE_WINDOW = 0.25

MAX_STALE_SESSIONS = 3

MAX_EVENTS = None

RUN_PLACEBO = True

N_PLACEBO = 120

PLACEBO_GAP_DAYS = 30

COST_HAIRCUT = 0.05

RUN_OOS = False

RUN_HOLDOUT = False

APPROVED_IS = [
    ("COF", "Discover", "000119312524039233", "2024-02-20 06:12:03"),
    ("HD", "SRS", "000110465924040163", "2024-03-28 08:30:39"),
    ("BA", "Spirit", "000119312524172676", "2024-07-01 06:06:32"),
    ("BLK", "Preqin", "000119312524172680", "2024-07-01 06:08:01"),
    ("AMD", "ZT", "000119312524202457", "2024-08-19 06:22:30"),
    ("BLK", "HPS", "000119312524269350", "2024-12-03 06:09:31"),
    ("TMO", "Solventum P&F", "000009774525000016", "2025-02-25 16:17:16"),
    ("NOW", "Moveworks", "000137371525000095", "2025-03-10 09:02:23"),
    ("GOOGL", "Wiz", "000165204425000027", "2025-03-18 08:43:32"),
    ("CHTR", "Cox", "000114036125019410", "2025-05-16 07:08:51"),
    ("CRM", "Informatica", "000119312525126271", "2025-05-27 08:11:04"),
    ("QCOM", "Alphawave", "000110465925057814", "2025-06-09 16:05:19"),
    ("UNP", "Norfolk Southern", "000119312525167154", "2025-07-29 07:16:26"),
    ("TMO", "Clario", "000009774525000156", "2025-10-29 06:05:40"),
    ("SCHW", "Forge", "000119312525268187", "2025-11-06 08:30:42"),
    ("ABT", "Exact", "000110465925114422", "2025-11-20 07:37:40"),
]

FILER_TICKER_ALIASES = {"GOOGL": {"GOOG", "GOOGL"}}

SECTOR_BY_TICKER = {
    "COF": "Financials", "HD": "Consumer Discretionary", "BA": "Industrials",
    "BLK": "Financials", "AMD": "Information Technology", "TMO": "Health Care",
    "NOW": "Information Technology", "GOOGL": "Communication Services",
    "CHTR": "Communication Services", "CRM": "Information Technology",
    "QCOM": "Information Technology", "UNP": "Industrials", "SCHW": "Financials",
    "ABT": "Health Care",
}

INITIAL_NAV = 1_000_000.0

NAME_GROSS_LIMIT, SECTOR_GROSS_LIMIT, TOTAL_GROSS_LIMIT = .10, .25, 1.00

PAUSE_DRAWDOWN, RESUME_DRAWDOWN = .10, .05

CAPACITY_PARTICIPATION = (.005, .01, .02)

class NYSEHolidays(AbstractHolidayCalendar):
    """NYSE full-day closures. Differs from the federal calendar: Good Friday closed, Columbus and
    Veterans Day open, no observance when New Year's Day falls on a Saturday."""
    rules = [
        Holiday("New Year's Day", month=1, day=1,
                observance=lambda d: d + pd.Timedelta(days=1) if d.weekday() == 6 else d),
        USMartinLutherKingJr, USPresidentsDay, GoodFriday, USMemorialDay,
        Holiday("Juneteenth", month=6, day=19, start_date="2022-01-01", observance=nearest_workday),
        Holiday("Independence Day", month=7, day=4, observance=nearest_workday),
        USLaborDay, USThanksgivingDay,
        Holiday("Christmas Day", month=12, day=25, observance=nearest_workday),
        Holiday("National day of mourning, President Carter", year=2025, month=1, day=9),
    ]

def trading_sessions(start, end) -> pd.DatetimeIndex:
    holidays = NYSEHolidays().holidays(pd.Timestamp(start) - pd.Timedelta(days=7), pd.Timestamp(end) + pd.Timedelta(days=7))
    return pd.bdate_range(start, end, freq=CustomBusinessDay(holidays=holidays))

def session_on_or_after(day) -> pd.Timestamp:
    return CAL[CAL.searchsorted(pd.Timestamp(day), side="left")]

def session_before(day) -> pd.Timestamp:
    return CAL[CAL.searchsorted(pd.Timestamp(day), side="left") - 1]

def sessions_between(a, b) -> int:
    """Number of sessions strictly after `a` up to and including `b`."""
    return int(CAL.searchsorted(pd.Timestamp(b), side="right") - CAL.searchsorted(pd.Timestamp(a), side="right"))

def session_close_time(day):
    return pd.Timestamp("13:00:00").time() if pd.Timestamp(day).normalize() in EARLY_CLOSE_DATES else pd.Timestamp("16:00:00").time()

def next_session(day):
    index = CAL.searchsorted(pd.Timestamp(day).normalize(), side="right")
    if index >= len(CAL):
        raise RuntimeError("Date exceeds the configured trading calendar.")
    return CAL[index]

def normalize_ticker(t) -> str | None:
    if not isinstance(t, str) or not t.strip():
        return None
    return t.strip().upper().replace("/", ".")

def ticker_tokens(value) -> list[str]:
    """Massive may give a whitespace-separated string or a list, including preferred classes."""
    if isinstance(value, str):
        values = value.replace(",", " ").split()
    elif isinstance(value, list):
        values = [part for item in value for part in ticker_tokens(item)]
    else:
        values = []
    return [t for t in map(normalize_ticker, values) if t]

def accession_id(row: pd.Series) -> str:
    """Prefer the SEC URL's 18-digit directory; keep API accession as the fallback."""
    url = str(row.get("filing_url") or "")
    match = re.search(r"/Archives/edgar/data/\d+/(\d{18})(?:/|\.)", url)
    return match.group(1) if match else re.sub(r"\D", "", str(row.get("accession_number") or ""))

def fetch_union_disclosures(tags: tuple[str, ...], start: str, end: str) -> pd.DataFrame:
    """Fetch both specified tags; retain every source tag and dedupe by SEC accession."""
    pieces = []
    for tag in tags:
        rows = api_get_all("/stocks/filings/8-K/vX/disclosures", {
            "tertiary_category": tag, "filing_date.gte": start, "filing_date.lte": end,
            "limit": 1000, "sort": "filing_date.asc",
        })
        part = pd.DataFrame(rows)
        if not part.empty:
            part["source_tag"] = tag
            pieces.append(part)
    if not pieces:
        raise RuntimeError("No disclosures returned for the prespecified tag union; check coverage, not returns.")
    raw = pd.concat(pieces, ignore_index=True)
    raw["filing_date"] = pd.to_datetime(raw["filing_date"])
    raw["accession_id"] = raw.apply(accession_id, axis=1)
    if raw["accession_id"].eq("").any():
        raise RuntimeError("A disclosure lacks an accession; cannot safely deduplicate.")
    raw["ticker_tokens"] = raw["tickers"].map(ticker_tokens)
    return raw

def first_full_session_close(accepted_at: pd.Timestamp) -> pd.Timestamp:
    """Premarket -> that session close; at/after open -> next session close (ET)."""
    day = accepted_at.normalize()
    candidate = session_on_or_after(day)
    if candidate != day or accepted_at.time() < pd.Timestamp("09:30:00").time():
        return candidate
    return next_session(candidate)

def public_signal_session(accepted_at: pd.Timestamp) -> pd.Timestamp:
    """Horizon clock shifts after the actual regular cash-session close, including halfdays."""
    candidate = session_on_or_after(accepted_at.normalize())
    if candidate == accepted_at.normalize() and accepted_at.time() >= session_close_time(candidate):
        return next_session(candidate)
    return candidate

def pre_public_session(accepted_at: pd.Timestamp) -> pd.Timestamp:
    """Last completed session strictly before acceptance; earlier IR may already be public."""
    day = accepted_at.normalize()
    candidate = session_on_or_after(day)
    if candidate == day and accepted_at.time() >= session_close_time(candidate):
        return candidate
    return session_before(candidate)

def next_public_open(accepted_at: pd.Timestamp) -> pd.Timestamp:
    """First cash-session open strictly after the public acceptance clock."""
    day = accepted_at.normalize()
    candidate = session_on_or_after(day)
    if candidate != day or accepted_at.time() < pd.Timestamp("09:30:00").time():
        return candidate
    return next_session(candidate)

def canonical_filer_ticker(ticker: str) -> str:
    ticker = normalize_ticker(ticker)
    for primary, aliases in FILER_TICKER_ALIASES.items():
        if ticker in aliases:
            return primary
    return ticker

def acceptance_regime(accepted_at):
    day = accepted_at.normalize()
    if session_on_or_after(day) != day: return "NONSESSION"
    if accepted_at.time() < pd.Timestamp("09:30:00").time(): return "PREMARKET"
    return "INTRADAY" if accepted_at.time() < session_close_time(day) else "AFTER_CLOSE"

def build_events(tags: tuple[str, ...], start: str, end: str, universe: list[str],
                 raw: pd.DataFrame | None = None) -> pd.DataFrame:
    """Match the frozen IS review by accession and buyer; never infer eligibility from returns."""
    if (start, end) != (STUDY_START, STUDY_END):
        raise RuntimeError("This window has no frozen disclosure review. Classify it before running.")
    raw = fetch_union_disclosures(tags, start, end) if raw is None else raw
    approved = [r for r in APPROVED_IS if r[0] in universe]
    rows = []
    for ticker, target, accession, accepted in approved:
        aliases = FILER_TICKER_ALIASES.get(ticker, {ticker})
        match = raw[(raw.accession_id == accession) & raw.ticker_tokens.map(lambda ts: bool(aliases.intersection(ts)))]
        if match.empty:
            raise RuntimeError(f"Reviewed accession {accession} for {ticker} is missing from the tag union; inspect coverage.")
        if match.filing_date.dt.normalize().nunique() != 1:
            raise RuntimeError(f"Conflicting filing dates for {accession}.")
        clock = pd.Timestamp(accepted)
        filing_date = match.filing_date.iloc[0].normalize()
        if clock.normalize() != filing_date:
            raise RuntimeError(f"SEC acceptance date differs from Massive filing date for {accession}.")
        signal_session = public_signal_session(clock)
        entry_day = first_full_session_close(clock)
        t_pre = pre_public_session(clock)
        rows.append({"ticker": ticker, "target": target, "transaction_group": ticker + "/" + target,
                     "accession_number": accession, "source_tags": tuple(sorted(match.source_tag.unique())),
                     "filing_date": filing_date, "filing_url": match.filing_url.iloc[0],
                     "supporting_text": match.supporting_text.iloc[0], "accepted_at": clock,
                     "t_pre": t_pre, "t_0": signal_session, "entry_day": entry_day,
                     "event_date": filing_date})
    ev = pd.DataFrame(rows).sort_values(["accepted_at", "accession_number"]).reset_index(drop=True)
    assert ev.accession_number.is_unique and ev.transaction_group.is_unique
    ev["days_since_prev_event"] = ev.groupby("ticker")["filing_date"].diff().dt.days
    return ev

def option_bars(opt_ticker: str, start, end) -> pd.DataFrame:
    """Daily bars for one contract: index = session, columns close and volume. Only sessions where it traded."""
    rows = api_get_all(f"/v2/aggs/ticker/{opt_ticker}/range/1/day/{pd.Timestamp(start):%Y-%m-%d}/{pd.Timestamp(end):%Y-%m-%d}",
                       {"adjusted": "false", "sort": "asc", "limit": 50000})
    if not rows:
        return pd.DataFrame(columns=["open", "close", "volume"], index=pd.DatetimeIndex([], name="session"))
    idx = (pd.to_datetime([r["t"] for r in rows], unit="ms", utc=True)
             .tz_convert("America/New_York").normalize().tz_localize(None))
    return pd.DataFrame({"open": [float(r["o"]) if r.get("o") is not None else np.nan for r in rows],
                         "close": [float(r["c"]) for r in rows], "volume": [float(r.get("v") or 0) for r in rows]},
                        index=pd.DatetimeIndex(idx, name="session"))

def fetch_chain(ticker: str, as_of: pd.Timestamp, dte_lo: int, dte_hi: int) -> pd.DataFrame:
    """Every standard contract that existed on `as_of` with an expiry `dte_lo`..`dte_hi` days out."""
    rows = api_get_all("/v3/reference/options/contracts", {
        "underlying_ticker": ticker, "as_of": as_of.strftime("%Y-%m-%d"),
        "expiration_date.gte": (as_of + pd.Timedelta(days=dte_lo)).strftime("%Y-%m-%d"),
        "expiration_date.lte": (as_of + pd.Timedelta(days=dte_hi)).strftime("%Y-%m-%d"),
        "limit": 1000,
    })
    chain = pd.DataFrame(rows)
    if chain.empty:
        return chain
    if "shares_per_contract" in chain:
        chain = chain[chain["shares_per_contract"].fillna(100) == 100]      # drop post-split non-standard series
    chain = chain[["ticker", "contract_type", "strike_price", "expiration_date"]].copy()
    chain["expiration_date"] = pd.to_datetime(chain["expiration_date"])
    chain["dte"] = (chain["expiration_date"] - as_of).dt.days
    chain["strike_price"] = chain["strike_price"].astype(float)
    return chain.reset_index(drop=True)

def paired_strikes(e: pd.DataFrame) -> np.ndarray:
    both = e.groupby("strike_price")["contract_type"].nunique()
    return both[both == 2].index.to_numpy(dtype=float)

def contract(e: pd.DataFrame, strike: float, kind: str) -> str:
    return e[(e.strike_price == strike) & (e.contract_type == kind)]["ticker"].iloc[0]

def last_close_on_or_before(opt_ticker: str, day: pd.Timestamp, lookback_days: int = 7) -> float | None:
    bars = option_bars(opt_ticker, day - pd.Timedelta(days=lookback_days), day)
    if bars.empty or sessions_between(bars.index[-1], day) > MAX_STALE_SESSIONS:
        return None
    value = float(bars.close.iloc[-1])
    return value if np.isfinite(value) and value >= 0 else None

def locate_spot(chain: pd.DataFrame, day: pd.Timestamp, max_iter: int = 8) -> dict | None:
    """Recover the stock price on `day` from the option chain alone, via put-call parity.

    At any strike K with both a call and a put, S = K·e^(−rT) + C − P. The strike that minimises |C − P|
    is at-the-money, and the estimate is best there because both legs are liquid. We start at the
    median strike of the nearest expiry (new weekly series are listed around the current price, so that
    median is already close), then step to the strike nearest our estimate until it stops moving.
    """
    near = chain[chain.dte >= 3]
    if near.empty:
        return None
    near = near[near.dte == near.dte.min()]
    strikes = paired_strikes(near)
    if len(strikes) < 3:
        return None
    T = near.dte.iloc[0] / 365
    k, tried, est = float(np.median(strikes)), set(), None
    k = strikes[np.abs(strikes - k).argmin()]
    for _ in range(max_iter):
        tried.add(k)
        c = last_close_on_or_before(contract(near, k, "call"), day)
        p = last_close_on_or_before(contract(near, k, "put"), day)
        if c is None or p is None:                                   # an illiquid strike: try the next-nearest untried one
            rest = [s for s in strikes if s not in tried]
            if not rest:
                break
            k = rest[int(np.abs(np.array(rest) - k).argmin())]
            continue
        est = k * np.exp(-RISK_FREE * T) + c - p
        k_new = strikes[np.abs(strikes - est).argmin()]
        if k_new == k or k_new in tried:
            break
        k = k_new
    if est is None or not np.isfinite(est) or est <= 0:
        return None
    return {"spot": float(est), "strike": float(k), "expiry": near.expiration_date.iloc[0], "dte": int(near.dte.iloc[0])}

def pick_expiry(chain: pd.DataFrame, lo: int, hi: int, target: int) -> pd.Timestamp | None:
    cand = chain[(chain.dte >= lo) & (chain.dte <= hi)]
    if cand.empty:
        return None
    dte_of = cand.groupby("expiration_date")["dte"].first()
    ok = [x for x, g in cand.groupby("expiration_date") if len(paired_strikes(g)) >= 3]   # needs a real chain, not a stub
    if not ok:
        return None
    return min(ok, key=lambda x: (abs(dte_of[x] - target), dte_of[x]))

def select_strikes(e: pd.DataFrame, spot: float, otm_pcts: list[float]) -> dict[str, float] | None:
    """ATM strike K (nearest to spot, both legs listed) plus, for each OTM level, the call strike U at or
    above spot·(1+pct) and the put strike L at or below spot·(1−pct)."""
    both = paired_strikes(e)
    both = both[(both >= spot * (1 - STRIKE_WINDOW)) & (both <= spot * (1 + STRIKE_WINDOW))]
    if len(both) == 0:
        return None
    calls = np.sort(e.loc[e.contract_type == "call", "strike_price"].unique())
    puts = np.sort(e.loc[e.contract_type == "put", "strike_price"].unique())
    out = {"K": float(both[np.abs(both - spot).argmin()])}
    for pct in otm_pcts:
        up, dn = calls[calls >= spot * (1 + pct)], puts[puts <= spot * (1 - pct)]
        out[f"U{pct}"] = float(up.min()) if len(up) else float(calls.max())
        out[f"L{pct}"] = float(dn.max()) if len(dn) else float(puts.min())
    return out

@dataclass
class Leg:
    ticker: str
    kind: str                 # "call" or "put"
    strike: float
    bars: pd.DataFrame        # close, volume by session (only sessions with trades)

    def mark(self, day: pd.Timestamp, price_field: str = "close") -> float:
        """Close may use <=3-session-old marks; open requires a same-date bar."""
        day = pd.Timestamp(day)
        if price_field == "open":
            if day not in self.bars.index or "open" not in self.bars:
                return np.nan
            value = float(self.bars.loc[day, "open"])
        elif price_field == "close":
            b = self.bars.loc[:day]
            if b.empty or sessions_between(b.index[-1], day) > MAX_STALE_SESSIONS:
                return np.nan
            value = float(b.close.iloc[-1])
        else:
            raise ValueError("Unknown price field")
        return value if np.isfinite(value) and value >= 0 else np.nan

    def mark_status(self, day: pd.Timestamp, price_field: str = "close") -> str:
        value = self.mark(day, price_field)
        if not np.isfinite(value):
            return "MISSING_OR_INVALID"
        if price_field == "open":
            return "EXACT_DATE_OPEN_PROXY"
        last = self.bars.loc[:pd.Timestamp(day)].index[-1]
        return "FRESH" if last == pd.Timestamp(day) else f"STALE_{sessions_between(last, day)}_SESSIONS"


    def volume_on(self, day: pd.Timestamp) -> float:
        return float(self.bars["volume"].get(pd.Timestamp(day), 0.0))

@dataclass
class PricedEvent:
    """One event × one expiry bucket: the chain-derived spot, the expiry and every leg a strategy may need."""
    ticker: str
    event_date: pd.Timestamp
    t_pre: pd.Timestamp
    t_0: pd.Timestamp
    entry_day: pd.Timestamp
    accepted_at: pd.Timestamp
    accession_number: str | None
    source_tags: tuple[str, ...]
    bucket: str
    expiry: pd.Timestamp
    expiry_session: pd.Timestamp        # last session on or before expiry
    spot_pre: float                     # chain-implied spot on t_pre
    strikes: dict[str, float]
    legs: dict[str, Leg]                # "C_K", "P_K", "C_U0.05", "P_L0.05", ...

    observation_end: pd.Timestamp | None = None

    def marks(self, day, price_field="close") -> dict[str, float]:
        return {name: leg.mark(day, price_field) for name, leg in self.legs.items()}

    def synthetic_spot(self, day, m: dict[str, float] | None = None) -> float:
        """Stock price implied by the ATM pair on `day`: K·e^(−rT) + C_K − P_K. An expiry last-trade mark is still a proxy, not intrinsic settlement."""
        m = m if m is not None else self.marks(day)
        T = max((self.expiry - pd.Timestamp(day)).days, 0) / 365
        return self.strikes["K"] * np.exp(-RISK_FREE * T) + m["C_K"] - m["P_K"]

def price_event(ticker: str, t_pre: pd.Timestamp, t_0: pd.Timestamp, entry_day: pd.Timestamp,
                accepted_at: pd.Timestamp, accession_number: str | None, source_tags: tuple[str, ...],
                event_date: pd.Timestamp, buckets: dict, otm_pcts: list[float], observation_end=None) -> tuple[list[PricedEvent], list[str]]:
    observation_end = pd.Timestamp(observation_end or STUDY_END)
    dte_hi = max(b[1] for b in buckets.values())
    chain = fetch_chain(ticker, t_pre, 2, dte_hi)
    if chain.empty:
        return [], ["no option chain as of the pre-event session"]
    loc = locate_spot(chain, t_pre)
    if loc is None:
        return [], ["could not recover spot from the chain (no liquid near-dated pair)"]
    priced, notes = [], []
    for name, (lo, hi, target) in buckets.items():
        expiry = pick_expiry(chain, lo, hi, target)
        if expiry is None:
            notes.append(f"{name}: no expiry {lo}-{hi} days out")
            continue
        e = chain[chain.expiration_date == expiry]
        strikes = select_strikes(e, loc["spot"], otm_pcts)
        if strikes is None:
            notes.append(f"{name}: no paired strikes near spot")
            continue
        wanted = {"C_K": ("call", strikes["K"]), "P_K": ("put", strikes["K"])}
        for pct in otm_pcts:
            wanted[f"C_U{pct}"] = ("call", strikes[f"U{pct}"])
            # The frozen study has no protective-put or cash-secured-put leg.
        legs = {}
        for key, (kind, k) in wanted.items():
            tk = contract(e, k, kind)
            legs[key] = Leg(tk, kind, k, option_bars(tk, t_pre - pd.Timedelta(days=10), min(expiry, observation_end)))
        pe = PricedEvent(ticker, event_date, t_pre, t_0, entry_day, accepted_at, accession_number, source_tags, name, expiry, CAL[CAL.searchsorted(expiry, side="right") - 1],
                         loc["spot"], strikes, legs, observation_end)
        if np.isnan(pe.legs["C_K"].mark(t_pre)) or np.isnan(pe.legs["P_K"].mark(t_pre)):
            notes.append(f"{name}: ATM pair did not trade on or near the pre-event session")
            continue
        priced.append(pe)
    return priced, notes

def price_events(ev: pd.DataFrame, buckets: dict = None, otm_pcts: list[float] = None, label: str = "events", observation_end=None) -> tuple[list[PricedEvent], pd.DataFrame]:
    buckets = buckets or EXPIRY_BUCKETS
    otm_pcts = otm_pcts or OTM_GRID
    priced, dropped, t0 = [], [], time.time()
    for n, row in enumerate(ev.itertuples(index=False), 1):
        got, notes = price_event(row.ticker, row.t_pre, row.t_0, row.entry_day, row.accepted_at,
                                 row.accession_number, row.source_tags, row.event_date, buckets, otm_pcts, observation_end=observation_end)
        priced += got
        dropped += [(row.ticker, row.t_0, note) for note in notes]
        if n % 25 == 0:
            print(f"  {label}: {n}/{len(ev)} events, {time.time() - t0:.0f}s")
    print(f"{label}: {len(ev)} events -> {len(priced)} priced (event, bucket) pairs; {len(dropped)} drops; {time.time() - t0:.0f}s")
    return priced, pd.DataFrame(dropped, columns=["ticker", "t_0", "reason"])

def summarize_priced(priced: list[PricedEvent]) -> pd.DataFrame:
    rows = []
    for pe in priced:
        m = pe.marks(pe.t_pre)
        rows.append({"ticker": pe.ticker, "event_date": pe.event_date, "t_pre": pe.t_pre, "t_0": pe.t_0, "bucket": pe.bucket,
                     "expiry": pe.expiry, "dte": (pe.expiry - pe.t_pre).days, "spot_pre": pe.spot_pre, "K": pe.strikes["K"],
                     "moneyness": pe.strikes["K"] / pe.spot_pre - 1, "call": pe.legs["C_K"].ticker, "put": pe.legs["P_K"].ticker,
                     "call_px": m["C_K"], "put_px": m["P_K"], "implied_move": (m["C_K"] + m["P_K"]) / pe.spot_pre,
                     "spot_gap": pe.synthetic_spot(pe.t_pre, m) / pe.spot_pre - 1,     # this bucket's parity spot vs the near-dated one
                     "atm_volume": pe.legs["C_K"].volume_on(pe.t_pre) + pe.legs["P_K"].volume_on(pe.t_pre)})
    return pd.DataFrame(rows)

STRATEGIES = ["stock_net", "covered_call_net"]

STRATEGY_LABEL = {"stock_net": "Synthetic stock, net", "covered_call_net": "Covered call, net",
                  "incremental_net": "Covered call minus stock, net"}

def option_cost(m_e, m_x, keys, S_e, haircut=COST_HAIRCUT):
    return haircut * sum(abs(m_e[k]) + abs(m_x[k]) for k in keys) / S_e

def strategy_pnl(m_e, m_x, S_e, S_x, otm, haircut=COST_HAIRCUT):
    key = f"C_U{otm}"
    valid_premium = lambda value: np.isfinite(value) and value >= 0
    stock_valid = (np.isfinite(S_e) and S_e > 0 and np.isfinite(S_x) and S_x > 0
                   and all(valid_premium(m[k]) for m in (m_e, m_x) for k in ("C_K", "P_K")))
    cc_valid = stock_valid and all(valid_premium(m[key]) for m in (m_e, m_x))
    dS = (S_x - S_e) / S_e if stock_valid else np.nan
    short_call = -(m_x[key] - m_e[key]) / S_e if cc_valid else np.nan
    stock_cost = option_cost(m_e, m_x, ["C_K", "P_K"], S_e, haircut) if stock_valid else np.nan
    call_cost = option_cost(m_e, m_x, [key], S_e, haircut) if cc_valid else np.nan
    return {"stock_gross": dS, "covered_call_gross": dS + short_call,
            "stock_cost": stock_cost, "covered_call_cost": stock_cost + call_cost,
            "stock_net": dS - stock_cost, "covered_call_net": dS + short_call - stock_cost - call_cost,
            "incremental_net": short_call - call_cost}

def evaluate(priced, otm_pcts=None, haircut=COST_HAIRCUT):
    """Every requested horizon remains visible, including unavailable/capped exits."""
    otm_pcts = otm_pcts or OTM_GRID
    rows = []
    for pe in priced:
        i0 = CAL.get_loc(pe.t_0)
        fence = pd.Timestamp(pe.observation_end if pe.observation_end is not None else STUDY_END)
        entries = {"pre": (pe.t_pre, "close"), "full": (pe.entry_day, "close"),
                   "next_open": (next_public_open(pe.accepted_at), "open")}
        post_tradeable = (pe.accepted_at.normalize() == pe.t_0
                          and pe.accepted_at.time() < session_close_time(pe.t_0))
        entries["post"] = (pe.t_0, "close")
        for entry, (e_day, price_field) in entries.items():
            m_e = pe.marks(e_day, price_field)
            S_e = pe.synthetic_spot(e_day, m_e)
            entry_valid = np.isfinite(S_e) and S_e > 0
            implied = (m_e["C_K"] + m_e["P_K"]) / S_e if entry_valid else np.nan
            dte_sessions = sessions_between(e_day, pe.expiry_session)
            for h in HORIZONS + ["exp"]:
                requested = pe.expiry_session if h == "exp" else (CAL[i0 + h] if i0 + h < len(CAL) else pd.NaT)
                x_day = min(requested, pe.expiry_session) if pd.notna(requested) else pd.NaT
                expiry_capped = h != "exp" and pd.notna(requested) and requested > pe.expiry_session
                reasons = []
                if entry == "post" and not post_tradeable:
                    reasons.append("POST_CLOSE_NOT_TRADEABLE")
                if e_day > fence or pd.isna(x_day) or x_day > fence:
                    reasons.append("OUTSIDE_OBSERVATION_WINDOW")
                if pd.notna(x_day) and (x_day < e_day or (x_day == e_day and price_field == "close")):
                    reasons.append("EXIT_NOT_AFTER_ENTRY")
                # Never read a fenced exit and never turn an unavailable observation into zero P&L.
                m_x = pe.marks(x_day) if not reasons else {k: np.nan for k in pe.legs}
                S_x = pe.synthetic_spot(x_day, m_x) if not reasons else np.nan
                held = sessions_between(e_day, x_day) if pd.notna(x_day) else 0
                effective_held = float(held) + (1.0 if price_field == "open" else 0.0)
                maturity = float(dte_sessions) + (1.0 if price_field == "open" else 0.0)
                realized = S_x / S_e - 1 if entry_valid and np.isfinite(S_x) and S_x > 0 else np.nan
                scaled = implied * np.sqrt(effective_held / maturity) if maturity > 0 and effective_held > 0 else np.nan
                base = {"ticker": pe.ticker, "accession_number": pe.accession_number,
                        "source_tags": pe.source_tags, "event_date": pe.event_date, "t_0": pe.t_0,
                        "bucket": pe.bucket, "expiry": pe.expiry, "entry": entry,
                        "entry_date": e_day, "entry_price_field": price_field,
                        "horizon": h, "requested_exit_date": requested, "exit_date": x_day,
                        "expiry_capped": expiry_capped, "observation_end": fence,
                        "sessions_held": held, "dte_sessions": dte_sessions,
                        "S_entry": S_e, "S_exit": S_x, "realized": realized,
                        "implied_move": implied, "implied_scaled": scaled}
                for otm in otm_pcts:
                    key = f"C_U{otm}"
                    missing = reasons + [f"{side}:{k}:MISSING_OR_INVALID" for side, marks in (("entry", m_e), ("exit", m_x))
                                        for k in ("C_K", "P_K", key)
                                        if not np.isfinite(marks[k]) or marks[k] < 0]
                    if not entry_valid: missing.append("ENTRY_SPOT_INVALID")
                    if np.isfinite(S_x) and S_x <= 0: missing.append("EXIT_SPOT_INVALID")
                    pnl = strategy_pnl(m_e, m_x, S_e, S_x, otm, haircut)
                    stale = ";".join(f"{side}:{k}:{pe.legs[k].mark_status(day, field)}"
                                     for side, day, field in (("entry", e_day, price_field), ("exit", x_day, "close"))
                                     for k in ("C_K", "P_K", key)
                                     if pd.notna(day) and day <= fence and pe.legs[k].mark_status(day, field).startswith("STALE"))
                    volumes = {k: pe.legs[k].volume_on(e_day) for k in ("C_K", "P_K", key)}
                    rows.append(dict(base, otm=otm, option_volume=volumes[key],
                                     atm_call_volume=volumes["C_K"], atm_put_volume=volumes["P_K"],
                                     short_call_strike=pe.legs[key].strike,
                                     otm_selector_fallback=pe.legs[key].strike < pe.spot_pre * (1 + otm),
                                     pre_call_moneyness=pe.legs[key].strike / pe.spot_pre - 1,
                                     entry_call_moneyness=pe.legs[key].strike / S_e - 1 if entry_valid else np.nan,
                                     coverage_reason=";".join(dict.fromkeys(missing)) or "OK",
                                     stale_mark_details=stale, quote_coverage="UNAVAILABLE_DAILY_BARS", **pnl))
    if not rows:
        columns = ["ticker", "source_tags", "event_date", "t_0", "entry", "bucket", "otm", "horizon",
                   "coverage_reason", "stale_mark_details", "stock_net", "covered_call_net", "incremental_net", "ratio",
                   "stock_gross", "covered_call_gross", "stock_cost", "covered_call_cost", "option_volume",
                   "implied_move", "implied_scaled", "realized", "expiry_capped", "S_entry", "S_exit"]
        return pd.DataFrame(columns=columns)
    res = pd.DataFrame(rows)
    res["ratio"] = np.where(np.isfinite(res.implied_scaled) & (res.implied_scaled > 0),
                            res.realized.abs() / res.implied_scaled, np.nan)
    return res

def finite_values(x) -> np.ndarray:
    values = pd.to_numeric(pd.Series(x, dtype="object"), errors="coerce").to_numpy(dtype=float)
    return values[np.isfinite(values)]

def bootstrap_ci(x, n_boot: int = 2000, seed: int = 0) -> tuple[float, float]:
    values = finite_values(x)
    if len(values) < 5:
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    means = rng.choice(values, size=(n_boot, len(values)), replace=True).mean(axis=1)
    return tuple(np.percentile(means, [2.5, 97.5]).tolist())

def slice_results(res: pd.DataFrame, bucket: str, entry: str, otm: float) -> pd.DataFrame:
    if not {"bucket", "entry", "otm"}.issubset(res.columns):
        return res.iloc[0:0].copy()
    return res[(res.bucket == bucket) & (res.entry == entry) & (res.otm == otm)].copy()

def _fixed_horizons(horizons=None):
    return list(HORIZONS) + ["exp"] if horizons is None else list(horizons)

def _horizon_rows(res, horizon):
    return res.loc[res["horizon"] == horizon] if "horizon" in res else res.iloc[0:0]

def _summary(values, candidates, seed=0):
    values = finite_values(values)
    n = len(values)
    lo, hi = bootstrap_ci(values, seed=seed)
    return {"n": n, "n_candidates": candidates, "n_unavailable": candidates - n,
            "mean": float(values.mean()) if n else np.nan,
            "median": float(np.median(values)) if n else np.nan,
            "hit_rate": float((values > 0).mean()) if n else np.nan,
            "ci_lo": lo, "ci_hi": hi,
            "estimate_status": "available" if n else "unavailable",
            "ci_status": "available" if n >= 5 else "unavailable_N_lt_5"}

def scoreboard(res: pd.DataFrame, bucket: str = None, entry: str = None, otm: float = None,
               horizons=None, strategies=STRATEGIES) -> pd.DataFrame:
    r = slice_results(res, bucket if bucket is not None else BASELINE_BUCKET,
                      entry if entry is not None else ENTRY,
                      otm if otm is not None else OTM_PCT)
    rows = []
    for strategy in strategies:
        for horizon in _fixed_horizons(horizons):
            observations = _horizon_rows(r, horizon)
            values = observations[strategy] if strategy in observations else []
            rows.append({"strategy": strategy, "horizon": horizon,
                         **_summary(values, len(observations))})
    return pd.DataFrame(rows, columns=["strategy", "horizon", "n", "n_candidates", "n_unavailable",
                                      "mean", "median", "hit_rate", "ci_lo", "ci_hi",
                                      "estimate_status", "ci_status"])

def difference_board(res_a: pd.DataFrame, res_b: pd.DataFrame, bucket: str = None,
                     entry: str = None, otm: float = None, strategies=STRATEGIES,
                     seed: int = 1, horizons=None) -> pd.DataFrame:
    """Independent-sample mean difference; all horizons remain visible even when unavailable."""
    bucket = bucket if bucket is not None else BASELINE_BUCKET
    entry = entry if entry is not None else ENTRY
    otm = otm if otm is not None else OTM_PCT
    a, b = slice_results(res_a, bucket, entry, otm), slice_results(res_b, bucket, entry, otm)
    rng, rows = np.random.default_rng(seed), []
    for strategy in strategies:
        for horizon in _fixed_horizons(horizons):
            ra, rb = _horizon_rows(a, horizon), _horizon_rows(b, horizon)
            xa = finite_values(ra[strategy] if strategy in ra else [])
            xb = finite_values(rb[strategy] if strategy in rb else [])
            sa, sb = _summary(xa, len(ra), seed), _summary(xb, len(rb), seed + 1)
            row = {"strategy": strategy, "horizon": horizon,
                   "n_a": len(xa), "n_b": len(xb), "n_candidates_a": len(ra), "n_candidates_b": len(rb),
                   "n_unavailable_a": len(ra) - len(xa), "n_unavailable_b": len(rb) - len(xb),
                   "mean_a": sa["mean"], "mean_b": sb["mean"],
                   "median_a": sa["median"], "median_b": sb["median"],
                   "hit_rate_a": sa["hit_rate"], "hit_rate_b": sb["hit_rate"],
                   "ci_lo_a": sa["ci_lo"], "ci_hi_a": sa["ci_hi"],
                   "ci_lo_b": sb["ci_lo"], "ci_hi_b": sb["ci_hi"],
                   "difference": sa["mean"] - sb["mean"] if len(xa) and len(xb) else np.nan,
                   "ci_lo": np.nan, "ci_hi": np.nan,
                   "estimate_status": "available" if len(xa) and len(xb) else "unavailable",
                   "ci_status": "available" if len(xa) >= 5 and len(xb) >= 5 else "unavailable_group_N_lt_5"}
            if len(xa) >= 5 and len(xb) >= 5:
                delta = rng.choice(xa, (2000, len(xa)), replace=True).mean(1) - rng.choice(xb, (2000, len(xb)), replace=True).mean(1)
                row.update(ci_lo=float(np.percentile(delta, 2.5)), ci_hi=float(np.percentile(delta, 97.5)))
            rows.append(row)
    return pd.DataFrame(rows)

def fmt_board(board: pd.DataFrame, value: str = "mean", star_if_ci_excludes_zero: bool = True) -> pd.DataFrame:
    if board.empty:
        return pd.DataFrame(columns=[f"h={h}" if h != "exp" else "expiry" for h in _fixed_horizons()])

    def cell(row):
        v = row.get(value, np.nan)
        counts = f"N={int(row['n'])}" if "n" in row else f"N={int(row['n_a'])}/{int(row['n_b'])}"
        if not np.isfinite(v):
            return f"N/A ({counts})"
        lo, hi = row.get("ci_lo", np.nan), row.get("ci_hi", np.nan)
        star = "*" if star_if_ci_excludes_zero and np.isfinite(lo) and np.isfinite(hi) and (lo > 0 or hi < 0) else ""
        ci = f"[{lo * 100:+.2f}, {hi * 100:+.2f}]%" if np.isfinite(lo) and np.isfinite(hi) else "CI N/A"
        return f"{v * 100:+.2f}%{star} ({counts}; {ci})"

    wide = board.assign(cell=board.apply(cell, axis=1)).pivot(index="strategy", columns="horizon", values="cell")
    order = [strategy for strategy in list(STRATEGIES) + ["incremental_net"] if strategy in wide.index]
    order += [strategy for strategy in wide.index if strategy not in order]
    wide = wide.reindex(index=order, columns=_fixed_horizons()).rename(index=STRATEGY_LABEL)
    wide.columns = [f"h={h}" if h != "exp" else "expiry" for h in wide.columns]
    return wide.rename_axis("Net P&L per $1 spot", axis=0)

def _tag_set(tags):
    if isinstance(tags, (tuple, list, set, frozenset, np.ndarray)):
        return {str(tag) for tag in tags}
    if tags is None or (isinstance(tags, float) and np.isnan(tags)):
        return set()
    text = str(tags).strip("[](){} '")
    for delimiter in (";", "|", ","):
        text = text.replace(delimiter, " ")
    return {tag.strip(" '\"") for tag in text.split() if tag.strip(" '\"")}

def category_slice(res: pd.DataFrame, category: str = "union") -> pd.DataFrame:
    """An event tagged twice appears in both individual diagnostics but only once in union."""
    if category == "union":
        return res.copy()
    if "source_tags" not in res:
        return res.iloc[0:0].copy()
    return res.loc[res.source_tags.map(lambda tags: category in _tag_set(tags))].copy()

def category_boards(res: pd.DataFrame, **kwargs) -> pd.DataFrame:
    frames = []
    for category in list(EVENT_TAGS) + ["union"]:
        frames.append(scoreboard(category_slice(res, category), **kwargs).assign(category=category))
    return pd.concat(frames, ignore_index=True)

def coverage_table(res: pd.DataFrame, group: str = "events") -> pd.DataFrame:
    """Counts candidate rows and valid net observations; no silent finite-price deletion."""
    output = []
    buckets = list(EXPIRY_BUCKETS) if isinstance(EXPIRY_BUCKETS, dict) else list(res["bucket"].drop_duplicates()) if "bucket" in res else [BASELINE_BUCKET]
    entries = list(dict.fromkeys([ENTRY, "post", "next_open", "pre"] + (list(res.entry.drop_duplicates()) if "entry" in res else [])))
    for category in list(EVENT_TAGS) + ["union"]:
        selected = category_slice(res, category)
        for bucket in buckets:
            for entry in entries:
                for otm in OTM_GRID:
                    r = slice_results(selected, bucket, entry, otm)
                    for horizon in _fixed_horizons():
                        observations = _horizon_rows(r, horizon)
                        reasons = observations["coverage_reason"].fillna("UNSPECIFIED") if "coverage_reason" in observations else pd.Series(["NO_CANDIDATE_ROWS"] if observations.empty else ["UNSPECIFIED"] * len(observations), dtype=object)
                        valid = len(finite_values(observations["covered_call_net"] if "covered_call_net" in observations else []))
                        common_valid = len(finite_values(observations["incremental_net"] if "incremental_net" in observations else []))
                        for reason, count in reasons.value_counts(dropna=False).items():
                            reason_subset = observations.loc[reasons == reason] if len(observations) else observations
                            capped = int(reason_subset["expiry_capped"].fillna(False).astype(bool).sum()) if "expiry_capped" in reason_subset else 0
                            output.append({"group": group, "category": category, "bucket": bucket, "entry": entry,
                                           "otm": otm, "horizon": horizon, "coverage_reason": reason,
                                           "reason_rows": 0 if observations.empty else int(count),
                                           "reason_rows_expiry_capped": capped,
                                           "n_candidates": len(observations), "n_covered_call": valid,
                                           "n_common_incremental": common_valid,
                                           "coverage_status": "no_candidates" if observations.empty else "fully_priced" if valid == len(observations) else "partially_or_unpriced"})
    return pd.DataFrame(output)

def issuer_influence(res_a: pd.DataFrame, res_b: pd.DataFrame, bucket: str = None,
                     entry: str = None, otm: float = None, horizons=None) -> pd.DataFrame:
    """Descriptive leave-one-issuer-out, deleting that issuer from BOTH groups.

    Event contribution = event incremental net / full finite-event N. This
    decomposition sums to the event mean; theta also contains the ordinary mean.
    Percent-of-theta is descriptive and unstable near zero, never a deletion rule.
    """
    bucket, entry, otm = bucket or BASELINE_BUCKET, entry or ENTRY, otm if otm is not None else OTM_PCT
    a, b = slice_results(res_a, bucket, entry, otm), slice_results(res_b, bucket, entry, otm)
    rows = []
    for horizon in _fixed_horizons(horizons):
        ea, eb = _horizon_rows(a, horizon).copy(), _horizon_rows(b, horizon).copy()
        for frame in (ea, eb):
            if "incremental_net" not in frame:
                frame["incremental_net"] = np.nan
            if "ticker" not in frame:
                frame["ticker"] = pd.Series(dtype=object)
            frame["incremental_net"] = pd.to_numeric(frame["incremental_net"], errors="coerce")
        ea = ea[np.isfinite(ea.incremental_net)].reset_index(drop=True)
        eb = eb[np.isfinite(eb.incremental_net)].reset_index(drop=True)
        full_theta = ea.incremental_net.mean() - eb.incremental_net.mean() if len(ea) and len(eb) else np.nan
        event_mean = ea.incremental_net.mean() if len(ea) else np.nan
        top = ea.loc[ea.incremental_net.abs().idxmax()] if len(ea) else None
        contribution = float(top.incremental_net) / len(ea) if top is not None else np.nan
        tickers = sorted(set(ea.ticker.astype(str)) | set(eb.ticker.astype(str))) or ["N/A"]
        for ticker in tickers:
            xa = ea.loc[ea.ticker.astype(str) != ticker, "incremental_net"]
            xb = eb.loc[eb.ticker.astype(str) != ticker, "incremental_net"]
            leave_theta = xa.mean() - xb.mean() if len(xa) and len(xb) else np.nan
            rows.append({"horizon": horizon, "excluded_ticker": ticker, "theta_full": full_theta,
                         "n_event_full": len(ea), "n_ordinary_full": len(eb),
                         "n_event_excluded": len(ea) - len(xa), "n_ordinary_excluded": len(eb) - len(xb),
                         "n_event_remaining": len(xa), "n_ordinary_remaining": len(xb),
                         "theta_without_ticker": leave_theta,
                         "theta_shift": leave_theta - full_theta if np.isfinite(leave_theta) and np.isfinite(full_theta) else np.nan,
                         "max_abs_event_ticker": top.ticker if top is not None else "N/A",
                         "max_abs_event_accession": top.get("accession_number", "N/A") if top is not None else "N/A",
                         "max_abs_event_incremental_net": top.incremental_net if top is not None else np.nan,
                         "max_event_contribution_to_event_mean": contribution,
                         "event_contribution_denominator_N": len(ea),
                         "event_mean_denominator": event_mean,
                         "max_event_share_of_event_mean": contribution / event_mean if np.isfinite(event_mean) and abs(event_mean) > 1e-12 else np.nan,
                         "theta_denominator": full_theta,
                         "max_event_share_of_theta": contribution / full_theta if np.isfinite(full_theta) and abs(full_theta) > 1e-12 else np.nan,
                         "status": "available" if len(xa) and len(xb) else "unavailable_after_exclusion"})
    return pd.DataFrame(rows)

def yearly_theta_diagnostics(res_a: pd.DataFrame, res_b: pd.DataFrame, **kwargs) -> pd.DataFrame:
    """Same-calendar-year descriptive comparison; no year is selected by performance."""
    def years(frame):
        for column in ("t_0", "event_date", "entry_date"):
            if column in frame:
                return pd.to_datetime(frame[column], errors="coerce", utc=True).dt.year
        return pd.Series(np.nan, index=frame.index)
    ya, yb = years(res_a), years(res_b)
    configured = range(pd.Timestamp(STUDY_START).year, pd.Timestamp(STUDY_END).year + 1)
    frames = []
    for year in configured:
        table = difference_board(res_a.loc[ya == year], res_b.loc[yb == year], strategies=["incremental_net"], **kwargs)
        frames.append(table.assign(year=year, comparison="same_calendar_year"))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

def sample_placebo(ev: pd.DataFrame, tagged: pd.DataFrame, n: int, start: str, end: str,
                   gap_days: int = PLACEBO_GAP_DAYS, seed: int = 7) -> pd.DataFrame:
    """Draw dates with eligible event ticker/tag/acceptance-clock templates, not outcome matching."""
    rng = np.random.default_rng(seed)
    sessions = CAL[(CAL >= pd.Timestamp(start)) & (CAL <= pd.Timestamp(end))]
    blocked = {t: set() for t in ev.ticker.unique()}
    for row in tagged.itertuples(index=False):
        for token in row.ticker_tokens:
            ticker = canonical_filer_ticker(token)
            if ticker in blocked:
                blocked[ticker].add(row.filing_date.normalize())
    eligible_dates = {t: [d for d in sessions if all(abs((d - a).days) > gap_days for a in blocked[t])]
                      for t in blocked}
    rows, used = [], set()
    # Uniform template draws imply the frozen eligible ticker-frequency weighting.
    for i in rng.choice(np.arange(len(ev)), size=n, replace=True):
        template = ev.iloc[int(i)]
        t = template.ticker
        time_offset = template.accepted_at - template.accepted_at.normalize()
        choices = [d for d in eligible_dates[t] if (t, d) not in used
                   and acceptance_regime(d + time_offset) == acceptance_regime(template.accepted_at)
                   and first_full_session_close(d + time_offset) <= pd.Timestamp(end)]
        if not choices: continue
        d = choices[int(rng.integers(len(choices)))]
        used.add((t, d))
        accepted = d + time_offset
        rows.append({"ticker": t, "filing_date": d, "event_date": d,
                     "t_0": public_signal_session(accepted), "t_pre": pre_public_session(accepted),
                     "entry_day": first_full_session_close(accepted), "accepted_at": accepted,
                     "accession_number": None, "source_tags": template.source_tags,
                     "matched_event_accession": template.accession_number, "transaction_group": None})
    return pd.DataFrame(rows, columns=["ticker", "filing_date", "event_date", "t_0", "t_pre", "entry_day",
                                     "accepted_at", "accession_number", "source_tags", "matched_event_accession", "transaction_group"])

def decay_table(r: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for horizon in _fixed_horizons():
        observations = _horizon_rows(r, horizon)
        values = finite_values(observations["ratio"] if "ratio" in observations else [])
        lo, hi = bootstrap_ci(values)
        rows.append({"horizon": horizon, "n": len(values), "n_candidates": len(observations),
                     "n_unavailable": len(observations) - len(values),
                     "mean_ratio": float(values.mean()) if len(values) else np.nan,
                     "ci_lo": lo, "ci_hi": hi,
                     "median_ratio": float(np.median(values)) if len(values) else np.nan,
                     "share_above_1": float((values > 1).mean()) if len(values) else np.nan,
                     "estimate_status": "available" if len(values) else "unavailable",
                     "ci_status": "available" if len(values) >= 5 else "unavailable_N_lt_5"})
    return pd.DataFrame(rows).set_index("horizon")

def fmt_decay(tbl: pd.DataFrame) -> pd.DataFrame:
    out = tbl.copy()
    for column in ("mean_ratio", "ci_lo", "ci_hi", "median_ratio"):
        if column in out:
            out[column] = out[column].map(lambda value: f"{value:.2f}" if np.isfinite(value) else "N/A")
    if "share_above_1" in out:
        out["share_above_1"] = out["share_above_1"].map(lambda value: f"{value:.0%}" if np.isfinite(value) else "N/A")
    return out

def implied_realized_summary(r: pd.DataFrame) -> pd.DataFrame:
    """Matched finite observations only; zero/negative implied proxy is unavailable."""
    frames = []
    for horizon in _fixed_horizons():
        observations = _horizon_rows(r, horizon)
        if not {"implied_move", "implied_scaled", "realized"}.issubset(observations.columns):
            valid = observations.iloc[0:0]
        else:
            implied = pd.to_numeric(observations.implied_move, errors="coerce")
            scaled = pd.to_numeric(observations.implied_scaled, errors="coerce")
            realized = pd.to_numeric(observations.realized, errors="coerce")
            mask = np.isfinite(implied) & (implied > 0) & np.isfinite(scaled) & (scaled > 0) & np.isfinite(realized)
            valid = observations.loc[mask].copy()
            valid["implied_move"], valid["implied_scaled"], valid["realized"] = implied.loc[mask], scaled.loc[mask], realized.loc[mask]
        frames.append({"horizon": horizon, "n_candidates": len(observations), "n_matched": len(valid),
                       "median_implied_to_expiry": valid.implied_move.median() if len(valid) else np.nan,
                       "median_implied_scaled_to_horizon": valid.implied_scaled.median() if len(valid) else np.nan,
                       "median_abs_realized": valid.realized.abs().median() if len(valid) else np.nan,
                       "share_realized_above_scaled_implied": (valid.realized.abs() > valid.implied_scaled).mean() if len(valid) else np.nan,
                       "status": "available" if len(valid) else "unavailable"})
    return pd.DataFrame(frames)

def _portfolio_marks(pe, day, short_key):
    """Read only the three selected legs on/before this session; never use a future bar."""
    keys = ("C_K", "P_K", short_key)
    marks, ages, missing = {}, {}, []
    for key in keys:
        if key not in pe.legs:
            marks[key], ages[key] = np.nan, np.nan
            missing.append(key + ":missing_contract")
            continue
        leg = pe.legs[key]
        bars = leg.bars.loc[:pd.Timestamp(day)]
        ages[key] = sessions_between(bars.index[-1], day) if len(bars) else np.nan
        marks[key] = float(leg.mark(pd.Timestamp(day)))
        if not np.isfinite(marks[key]) or marks[key] < 0:
            missing.append(key + ":missing_or_stale_mark")
    spot = float(pe.synthetic_spot(day, marks)) if not missing else np.nan
    if not np.isfinite(spot) or spot <= 0:
        missing.append("invalid_synthetic_spot")
    return marks, spot, ages, missing

def _portfolio_volume_rows(pe, day, side, trade_id, short_key):
    """Daily contract volume is a retrospective capacity diagnostic, never an entry filter."""
    rows = []
    for key in ("C_K", "P_K", short_key):
        leg = pe.legs[key]
        exact = leg.bars.loc[leg.bars.index == pd.Timestamp(day)]
        volume = float(exact["volume"].iloc[-1]) if len(exact) and "volume" in exact else np.nan
        valid = np.isfinite(volume) and volume > 0
        rows.append({"trade_id": trade_id, "ticker": pe.ticker, "side": side,
                     "date": pd.Timestamp(day), "leg": key, "contract": leg.ticker,
                     "contracts": 1, "observed_daily_volume": volume,
                     "participation_fraction": 1.0 / volume if valid else np.nan,
                     "volume_status": "observed" if valid else "zero_or_unobserved",
                     "used_for_entry_admission": False})
    return rows

def _portfolio_metric_block(daily, initial_nav):
    """Report only: distinguish known endpoints, complete paths and observed diagnostics.

    All return/risk/turnover values are fractions internally. No missing NAV is filled,
    no return bridges a missing session, and no subset Sharpe replaces full-window Sharpe.
    Starting capital must be known and positive. A terminal zero NAV has a known -100%
    endpoint return; a negative endpoint has an arithmetic return but no defined CAGR.
    """
    n = len(daily)
    try:
        initial = float(initial_nav)
    except (TypeError, ValueError):
        initial = np.nan
    initial_valid = bool(np.isfinite(initial) and initial > 0)
    nav = pd.to_numeric(daily["nav"], errors="coerce").astype(float) if "nav" in daily else pd.Series(np.nan, index=daily.index)
    finite_nav = np.isfinite(nav)
    nonnegative_nav = finite_nav & (nav >= 0)
    gaps = int((~finite_nav).sum())
    invalid_navs = int((finite_nav & (nav < 0)).sum())
    complete_nav = bool(n and initial_valid and nonnegative_nav.all())
    out = {"sessions": n, "nav_gaps": gaps, "invalid_negative_navs": invalid_navs,
           "initial_nav": initial, "ending_nav": np.nan,
           "annual_return": np.nan, "total_net_return": np.nan,
           "annual_volatility": np.nan, "sharpe_rf0": np.nan,
           "max_drawdown": np.nan, "observed_max_drawdown_lower_bound": np.nan,
           "mean_full_calendar_nav": np.nan,
           "turnover_stock_gross": np.nan, "turnover_option_premium_gross": np.nan,
           "turnover_all_option_underlying_gross": np.nan,
           "gross_traded_stock_usd": np.nan, "gross_traded_option_premium_usd": np.nan,
           "gross_traded_option_underlying_usd": np.nan, "paid_premium_haircuts_usd": np.nan,
           "turnover_stock_initial_nav": np.nan, "turnover_option_premium_initial_nav": np.nan,
           "turnover_all_option_underlying_initial_nav": np.nan,
           "cost_fraction_initial_nav": np.nan, "cost_fraction_traded_stock": np.nan,
           "observed_adjacent_return_count": 0, "adjacent_return_coverage": np.nan,
           "complete_calendar_nav": complete_nav, "complete_adjacent_returns": False,
           "status": "OK" if complete_nav else ("PARTIAL" if n else "UNAVAILABLE")}
    status = {key: "UNAVAILABLE" for key in out if key not in ("status",)}
    status.update(sessions="OK", nav_gaps="OK", invalid_negative_navs="OK",
                  initial_nav="OK" if initial_valid else "UNAVAILABLE_NONPOSITIVE_OR_UNKNOWN_INITIAL_NAV")

    # Ending NAV and arithmetic return are endpoint observations, not full-path estimates.
    if n and finite_nav.iloc[-1]:
        ending = float(nav.iloc[-1])
        out["ending_nav"] = ending
        status["ending_nav"] = "OK" if ending >= 0 else "KNOWN_NEGATIVE_NAV_REQUIRES_REVIEW"
        if initial_valid:
            out["total_net_return"] = ending / initial - 1
            status["total_net_return"] = "OK_ENDPOINT" if ending >= 0 else "KNOWN_NEGATIVE_NAV_REQUIRES_REVIEW"
            if ending >= 0:
                out["annual_return"] = float((ending / initial) ** (252 / n) - 1)
                status["annual_return"] = "OK_ENDPOINT_CAGR_OVER_ALL_DECLARED_SESSIONS"
            else:
                status["annual_return"] = "UNAVAILABLE_NEGATIVE_END_NAV_CAGR_UNDEFINED"
    elif n:
        status["ending_nav"] = "UNAVAILABLE_END_NAV_GAP"
        status["total_net_return"] = "UNAVAILABLE_END_NAV_GAP"
        status["annual_return"] = "UNAVAILABLE_END_NAV_GAP"
    if not initial_valid:
        status["total_net_return"] = status["annual_return"] = "UNAVAILABLE_NONPOSITIVE_OR_UNKNOWN_INITIAL_NAV"

    previous = nav.shift(1)
    if n:
        previous.iloc[0] = initial
    adjacent_valid = nonnegative_nav & np.isfinite(previous) & (previous > 0)
    adjacent_returns = pd.Series(np.nan, index=daily.index, dtype=float)
    adjacent_returns.loc[adjacent_valid] = nav.loc[adjacent_valid] / previous.loc[adjacent_valid] - 1
    out["observed_adjacent_return_count"] = int(adjacent_valid.sum())
    out["adjacent_return_coverage"] = float(adjacent_valid.sum() / n) if n else np.nan
    return_complete = bool(complete_nav and adjacent_valid.all())
    out["complete_adjacent_returns"] = return_complete
    if n and not return_complete:
        out["status"] = "PARTIAL"
    status["observed_adjacent_return_count"] = "OK_ADJACENT_ONLY_NO_GAP_BRIDGING"
    status["adjacent_return_coverage"] = "OK" if n else "UNAVAILABLE_EMPTY_WINDOW"
    status["complete_calendar_nav"] = status["complete_adjacent_returns"] = "OK"

    # Observed NAV excursions understate or equal drawdown on a complete, unseen path.
    # This bound is separate from the required full-path max drawdown.
    if initial_valid and finite_nav.any():
        observed = nav.loc[finite_nav].to_numpy(dtype=float)
        observed_peaks = np.maximum.accumulate(np.r_[initial, observed])[1:]
        out["observed_max_drawdown_lower_bound"] = float(np.max(1 - observed / observed_peaks))
        status["observed_max_drawdown_lower_bound"] = "LOWER_BOUND_OBSERVED_NAV_ONLY"
    if complete_nav:
        peaks = np.maximum.accumulate(np.r_[initial, nav.to_numpy()])[1:]
        out["max_drawdown"] = float(np.max(1 - nav.to_numpy() / peaks))
        out["mean_full_calendar_nav"] = float(nav.mean())
        status["max_drawdown"] = "OK_COMPLETE_CALENDAR_PATH"
        status["mean_full_calendar_nav"] = "OK_COMPLETE_CALENDAR_PATH"
    else:
        unavailable = "UNAVAILABLE_NAV_GAPS" if gaps else ("UNAVAILABLE_INVALID_NAV" if invalid_navs else "UNAVAILABLE_INITIAL_NAV_OR_EMPTY_WINDOW")
        status["max_drawdown"] = status["mean_full_calendar_nav"] = unavailable
    if return_complete and n > 1:
        vol = float(adjacent_returns.std(ddof=1) * np.sqrt(252))
        out["annual_volatility"] = vol
        status["annual_volatility"] = "OK_COMPLETE_ADJACENT_RETURN_PATH"
        if np.isfinite(vol) and vol > 0:
            out["sharpe_rf0"] = float(adjacent_returns.mean() * 252 / vol)
            status["sharpe_rf0"] = "OK_RF0_252_UNIT_LESS"
        else:
            status["sharpe_rf0"] = "UNAVAILABLE_ZERO_VOLATILITY"
    else:
        risk_reason = ("UNAVAILABLE_INSUFFICIENT_SESSIONS" if n <= 1 else
                       "UNAVAILABLE_NAV_GAPS" if gaps else "UNAVAILABLE_INVALID_NAV_OR_RETURN_DENOMINATOR")
        status["annual_volatility"] = status["sharpe_rf0"] = risk_reason

    # Execution cash-flow totals remain observable even when valuation is missing.
    flow_fields = {"gross_traded_stock_usd": "traded_stock_gross",
                   "gross_traded_option_premium_usd": "traded_option_premium_gross",
                   "gross_traded_option_underlying_usd": "traded_option_underlying_gross",
                   "paid_premium_haircuts_usd": "paid_premium_haircuts"}
    flow_complete = {}
    for metric, column in flow_fields.items():
        if column not in daily:
            status[metric] = "UNAVAILABLE_CASHFLOW_COLUMN"
            flow_complete[metric] = False
            continue
        amounts = pd.to_numeric(daily[column], errors="coerce").astype(float)
        valid = np.isfinite(amounts) & (amounts >= 0)
        out[metric] = float(amounts.loc[valid].sum()) if n else 0.0
        flow_complete[metric] = bool(valid.all())
        status[metric] = "OK_OBSERVED_CASHFLOW_TOTAL" if valid.all() else "OBSERVED_SUBTOTAL_CASHFLOW_GAPS"
    references = (("turnover_stock_gross", "turnover_stock_initial_nav", "gross_traded_stock_usd"),
                  ("turnover_option_premium_gross", "turnover_option_premium_initial_nav", "gross_traded_option_premium_usd"),
                  ("turnover_all_option_underlying_gross", "turnover_all_option_underlying_initial_nav", "gross_traded_option_underlying_usd"))
    mean_nav = out["mean_full_calendar_nav"]
    for frozen_metric, initial_metric, flow_metric in references:
        numerator = out[flow_metric]
        if initial_valid and np.isfinite(numerator):
            out[initial_metric] = numerator / initial
            status[initial_metric] = "DIAGNOSTIC_INITIAL_CAPITAL_DENOMINATOR" if flow_complete.get(flow_metric) else "DIAGNOSTIC_OBSERVED_CASHFLOW_SUBTOTAL"
        if complete_nav and np.isfinite(mean_nav) and mean_nav > 0 and flow_complete.get(flow_metric):
            out[frozen_metric] = numerator / mean_nav
            status[frozen_metric] = "OK_TWO_SIDED_GROSS_OVER_FULL_CALENDAR_MEAN_NAV"
        else:
            status[frozen_metric] = ("UNAVAILABLE_NAV_GAPS" if gaps else
                                     "UNAVAILABLE_CASHFLOW_GAPS" if not flow_complete.get(flow_metric) else
                                     "UNAVAILABLE_INVALID_OR_ZERO_MEAN_NAV")
    costs = out["paid_premium_haircuts_usd"]
    if initial_valid and np.isfinite(costs):
        out["cost_fraction_initial_nav"] = costs / initial
        status["cost_fraction_initial_nav"] = "DIAGNOSTIC_INITIAL_CAPITAL_DENOMINATOR" if flow_complete.get("paid_premium_haircuts_usd") else "DIAGNOSTIC_OBSERVED_COST_SUBTOTAL"
    gross = out["gross_traded_stock_usd"]
    if np.isfinite(costs) and np.isfinite(gross) and gross > 0:
        out["cost_fraction_traded_stock"] = costs / gross
        status["cost_fraction_traded_stock"] = ("DIAGNOSTIC_TWO_SIDED_STOCK_GROSS_DENOMINATOR"
                                                if flow_complete.get("paid_premium_haircuts_usd") and flow_complete.get("gross_traded_stock_usd")
                                                else "DIAGNOSTIC_OBSERVED_CASHFLOW_SUBTOTAL")
    else:
        status["cost_fraction_traded_stock"] = "UNAVAILABLE_NO_KNOWN_POSITIVE_TRADED_STOCK_NOTIONAL"
    out["metric_status"] = status
    out["metric_availability"] = {key: bool(np.isscalar(value) and not isinstance(value, str) and pd.notna(value))
                                  for key, value in out.items() if key not in ("metric_status", "status")}
    return out

def portfolio_scorecard(report):
    """Compact English table: bp means fraction times 10,000; Sharpe is unitless."""
    metrics = report["metrics"]
    statuses = metrics.get("metric_status", {})
    specifications = [
        ("Total net return", "total_net_return", 10000, "bp", "Known endpoint / known starting capital - 1; no gap filling"),
        ("Annualized net return", "annual_return", 10000, "bp/year", "Endpoint CAGR over all declared sessions, 252 sessions/year"),
        ("Annualized volatility", "annual_volatility", 10000, "bp/year^0.5", "Complete adjacent daily-return path; sample stdev times sqrt(252)"),
        ("Sharpe (rf = 0)", "sharpe_rf0", 1, "unitless", "Complete path only; mean daily return times 252 / annual volatility"),
        ("Maximum drawdown", "max_drawdown", 10000, "bp", "Full valid calendar NAV path including initial NAV"),
        ("Observed drawdown lower bound", "observed_max_drawdown_lower_bound", 10000, "bp, lower bound", "Observed NAV excursions only; never substitutes for full-path max drawdown"),
        ("Two-sided stock turnover (frozen)", "turnover_stock_gross", 1, "x mean NAV", "Opening plus closing synthetic-stock gross USD / complete calendar mean NAV"),
        ("All-leg premium turnover", "turnover_option_premium_gross", 1, "x mean NAV", "All three option legs' opening plus closing premiums / complete calendar mean NAV"),
        ("All-leg underlying-reference gross turnover", "turnover_all_option_underlying_gross", 1, "x mean NAV", "All three option legs' underlying-reference gross USD / complete calendar mean NAV"),
        ("Initial NAV", "initial_nav", 1, "USD", "Declared starting capital"),
        ("Ending NAV", "ending_nav", 1, "USD", "Final declared session NAV; unavailable when final mark is missing"),
        ("Known two-sided stock gross traded", "gross_traded_stock_usd", 1, "USD", "Sum of observed opening and closing stock-reference gross amounts"),
        ("Known all-leg premiums traded", "gross_traded_option_premium_usd", 1, "USD", "Sum of observed opening and closing premium amounts across all selected legs"),
        ("Known all-leg underlying gross traded", "gross_traded_option_underlying_usd", 1, "USD", "Underlying-reference notional across all selected legs; not independent stock exposure"),
        ("Known premium haircut cost", "paid_premium_haircuts_usd", 1, "USD", "Sum of paid entry and exit premium haircuts; no inferred spread quote"),
        ("Stock turnover / initial capital", "turnover_stock_initial_nav", 1, "x initial NAV, diagnostic", "Observed two-sided stock gross / initial NAV; not frozen mean-NAV turnover"),
        ("All-leg premiums / initial capital", "turnover_option_premium_initial_nav", 1, "x initial NAV, diagnostic", "Observed all-leg premium gross / initial NAV"),
        ("All-leg underlying / initial capital", "turnover_all_option_underlying_initial_nav", 1, "x initial NAV, diagnostic", "Observed all-leg underlying-reference gross / initial NAV"),
        ("Cost / initial capital", "cost_fraction_initial_nav", 10000, "bp of initial NAV", "Known paid premium haircut USD / initial NAV times 10,000"),
        ("Cost / two-sided stock gross", "cost_fraction_traded_stock", 10000, "bp of gross traded stock, diagnostic", "Known paid premium haircut USD / opening-plus-closing stock gross USD times 10,000"),
        ("Adjacent-return coverage", "adjacent_return_coverage", 100, "% of declared sessions", "Both adjacent NAVs known; first return uses initial NAV; gaps never bridged"),
        ("NAV gaps", "nav_gaps", 1, "sessions", "Nonfinite or missing daily NAV observations"),
        ("Invalid negative NAV", "invalid_negative_navs", 1, "sessions", "Negative NAV requires proxy/accounting review; invalidates full-path risk metrics"),
    ]
    rows = [{"metric": label, "value": metrics.get(key, np.nan) * scale,
             "unit": unit, "status": statuses.get(key, "UNAVAILABLE"), "method": method}
            for label, key, scale, unit, method in specifications]
    try:
        haircut = float(report.get("config", {}).get("haircut_each_leg_each_side", np.nan))
    except (TypeError, ValueError):
        haircut = np.nan
    rows.append({"metric": "Premium haircut assumption", "value": haircut * 100,
                 "unit": "% of each option leg premium, each side",
                 "status": "ASSUMPTION" if np.isfinite(haircut) else "UNAVAILABLE",
                 "method": "Premium-based cost parameter; this percentage is not stock-notional basis points"})
    return pd.DataFrame(rows, columns=["metric", "value", "unit", "status", "method"])

def refresh_portfolio_metrics(report):
    """Return an updated deep copy using existing NAV/cash flows; never rerun admissions or trades."""
    import copy
    refreshed = copy.deepcopy(report)
    daily = refreshed["daily"]
    initial = refreshed.get("config", {}).get("initial_nav", np.nan)
    refreshed["metrics"] = _portfolio_metric_block(daily, initial)
    yearly = []
    if len(daily):
        for year, subset in daily.groupby(daily.index.year, sort=True):
            # A missing previous year endpoint is not replaced with an earlier observed NAV.
            first = daily.index.get_loc(subset.index[0])
            beginning = initial if first == 0 else daily["nav"].iloc[first - 1]
            block = _portfolio_metric_block(subset, beginning)
            yearly.append(dict(year=int(year), **block))
    refreshed["annual_metrics"] = pd.DataFrame(yearly)
    refreshed["scorecard"] = portfolio_scorecard(refreshed)
    limitations = refreshed.setdefault("limitations", [])
    note = ("Partial-report endpoints may be known despite interior NAV gaps; full-path Sharpe, volatility, "
            "max drawdown and frozen mean-NAV turnover remain unavailable. Observed drawdown is a lower bound; "
            "initial-capital turnover and cost ratios are separately labeled diagnostics.")
    if note not in limitations:
        limitations.append(note)
    return refreshed

def simulate_portfolio(priced, start, end, sector_by_ticker, initial_nav=1e6,
                       primary_horizon=21, otm=.05, haircut=.05, participation=.01):
    """A fixed-capital covered-call proxy; pure input transformation, no API/file access.

    Use the frozen 3-6m bucket, one standard contract / 100 synthetic shares, first
    full-session-close entry and t0+21 exit, capped at expiry. There is no ranking,
    leverage, future-path sizing, volume-based entry gate, or end-window liquidation.
    A fixed exit without valid marks is unresolved and permanently blocks new entries;
    it is not moved to a later favorable mark. Missing intermediate marks yield NAV gaps.
    Even valid historical daily close marks are proxies, not executable close quotes.
    A supplied manual sector grouping is not verified point-in-time industry data.
    """
    start, end = pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize()
    if start > end or initial_nav <= 0 or haircut < 0 or not 0 < participation <= 1:
        raise ValueError("Invalid portfolio dates, capital, haircut or participation.")
    if primary_horizon < 1 or int(primary_horizon) != primary_horizon:
        raise ValueError("The primary horizon must be a positive number of sessions.")
    days = CAL[(CAL >= start) & (CAL <= end)]
    if not len(days):
        raise ValueError("No calendar sessions in this window.")
    if start < CAL[0] or end > CAL[-1]:
        raise ValueError("Portfolio window exceeds the declared trading calendar.")
    short_key = f"C_U{otm}"
    prepared, ledger, volume_rows, breach_rows = [], [], [], []
    seen = set()
    # Ordering is deterministic and declared, never based on subsequent returns.
    candidates = sorted((p for p in priced if p.bucket == "3-6m"),
                        key=lambda p: (pd.Timestamp(p.entry_day), str(p.ticker), str(p.accession_number)))
    for pe in candidates:
        entry = pd.Timestamp(pe.entry_day).normalize()
        identity = (pe.ticker, pe.accession_number, pd.Timestamp(pe.t_0))
        base = {"trade_id": str(len(ledger)), "ticker": pe.ticker,
                "accession_number": pe.accession_number, "bucket": pe.bucket,
                "source_tags": pe.source_tags, "signal_session": pd.Timestamp(pe.t_0),
                "entry_date": entry, "sector": sector_by_ticker.get(pe.ticker),
                "contracts": 0, "status": "PENDING", "reason": "",
                "entry_stock_gross": np.nan, "entry_short_call_premium": np.nan,
                "entry_cost": np.nan, "exit_cost": np.nan, "net_pnl": np.nan,
                "max_loss_proxy_at_entry": np.nan, "scheduled_exit": pd.NaT,
                "actual_exit": pd.NaT, "entry_mark_ages": None, "exit_mark_ages": None,
                "entry_cash_debit": np.nan, "exit_cash_credit": np.nan}
        ledger.append(base)
        if identity in seen:
            base.update(status="SKIPPED", reason="DUPLICATE_PRICED_EVENT")
            continue
        seen.add(identity)
        if entry < start or entry > end:
            base.update(status="SKIPPED", reason="ENTRY_OUTSIDE_WINDOW")
            continue
        if entry not in CAL or pd.Timestamp(pe.t_0) not in CAL:
            base.update(status="SKIPPED", reason="SESSION_NOT_IN_CALENDAR")
            continue
        i0 = CAL.get_loc(pd.Timestamp(pe.t_0))
        if i0 + int(primary_horizon) >= len(CAL):
            base.update(status="SKIPPED", reason="EXIT_OUTSIDE_CALENDAR")
            continue
        exit_day = min(CAL[i0 + int(primary_horizon)], pd.Timestamp(pe.expiry_session))
        base["scheduled_exit"] = exit_day
        base["expiry_capped"] = exit_day < CAL[i0 + int(primary_horizon)]
        if exit_day <= entry:
            base.update(status="SKIPPED", reason="NO_POSITIVE_HOLDING_PERIOD")
            continue
        if not base["sector"] or not isinstance(base["sector"], str):
            base.update(status="SKIPPED", reason="SECTOR_MAPPING_REQUIRED")
            continue
        prepared.append((pe, base))
    entries = {}
    for pe, row in prepared:
        entries.setdefault(row["entry_date"], []).append((pe, row))
    cash, peak, paused = float(initial_nav), float(initial_nav), False
    active, daily_rows = [], []
    unresolved_exit = False

    def known_book(day):
        values, unknown = [], []
        for position in active:
            pe, row = position["pe"], position["row"]
            if row["status"] == "UNRESOLVED_EXIT":
                unknown.append(row["trade_id"] + ":unresolved_fixed_exit")
                continue
            marks, spot, ages, missing = _portfolio_marks(pe, day, short_key)
            if missing:
                unknown.append(row["trade_id"] + ":" + ";".join(missing))
            else:
                values.append((position, marks, spot, ages))
        return values, unknown

    for day in days:
        traded_gross, traded_option_premiums, traded_option_underlying, paid_costs = 0.0, 0.0, 0.0, 0.0
        # Fixed exits execute before new signals at this close; retain failed exits as unknown.
        for position in list(active):
            pe, row = position["pe"], position["row"]
            if day != row["scheduled_exit"] or row["status"] != "OPEN":
                continue
            marks, spot, ages, missing = _portfolio_marks(pe, day, short_key)
            row["exit_mark_ages"] = ages
            volume_rows.extend(_portfolio_volume_rows(pe, day, "exit", row["trade_id"], short_key))
            if missing:
                row.update(status="UNRESOLVED_EXIT", reason=";".join(missing))
                unresolved_exit = True
                continue
            exit_cost = 100 * haircut * sum(abs(v) for v in marks.values())
            credit = 100 * (spot - marks[short_key]) - exit_cost
            cash += credit
            traded_gross += 100 * spot
            traded_option_premiums += 100 * sum(abs(v) for v in marks.values())
            traded_option_underlying += 3 * 100 * spot
            paid_costs += exit_cost
            row.update(status="CLOSED", actual_exit=day, exit_cost=exit_cost,
                       exit_option_premiums={k: 100 * v for k, v in marks.items()},
                       exit_all_option_underlying_gross=3 * 100 * spot,
                       exit_cash_credit=credit, net_pnl=credit - row["entry_cash_debit"])
            active.remove(position)
        values, unknown = known_book(day)
        nav = cash + sum(100 * (spot - marks[short_key]) for _, marks, spot, _ in values) if not unknown else np.nan
        if np.isfinite(nav):
            peak = max(peak, nav)
            dd = 1 - nav / peak
            if dd >= .10:
                paused = True
            elif paused and dd < .05:
                paused = False
        else:
            dd = np.nan
        for pe, row in entries.get(day, []):
            if unknown or unresolved_exit or not np.isfinite(nav):
                row.update(status="SKIPPED", reason="UNKNOWN_PORTFOLIO_MARK_OR_UNRESOLVED_EXIT")
                continue
            if nav <= 0 or paused:
                row.update(status="SKIPPED", reason="NONPOSITIVE_NAV" if nav <= 0 else "DRAWDOWN_PAUSE")
                continue
            if any(p["pe"].ticker == pe.ticker for p in active):
                row.update(status="SKIPPED", reason="CONCURRENT_SAME_TICKER")
                continue
            marks, spot, ages, missing = _portfolio_marks(pe, day, short_key)
            row["entry_mark_ages"] = ages
            if missing:
                row.update(status="SKIPPED", reason=";".join(missing))
                continue
            gross, cost = 100 * spot, 100 * haircut * sum(abs(v) for v in marks.values())
            debit = 100 * (spot - marks[short_key]) + cost
            # Same-close proxy NAV includes the entry haircut; current marks only.
            nav_after = nav - cost
            name_gross, sector_gross = {}, {}
            for position, _, existing_spot, _ in values:
                name = position["pe"].ticker
                sector = position["row"]["sector"]
                name_gross[name] = name_gross.get(name, 0) + 100 * existing_spot
                sector_gross[sector] = sector_gross.get(sector, 0) + 100 * existing_spot
            name_gross[pe.ticker] = name_gross.get(pe.ticker, 0) + gross
            sector_gross[row["sector"]] = sector_gross.get(row["sector"], 0) + gross
            reason = ("CASH_OR_NAV_LIMIT" if nav_after <= 0 or debit > cash or debit < 0 else
                      "NAME_GROSS_LIMIT" if max(name_gross.values()) > .10 * nav_after else
                      "SECTOR_GROSS_LIMIT" if max(sector_gross.values()) > .25 * nav_after else
                      "TOTAL_GROSS_LIMIT" if sum(name_gross.values()) > nav_after else "")
            if reason:
                row.update(status="SKIPPED", reason=reason)
                continue
            cash -= debit
            traded_gross += gross
            traded_option_premiums += 100 * sum(abs(v) for v in marks.values())
            traded_option_underlying += 3 * gross
            paid_costs += cost
            row.update(status="OPEN", contracts=1, entry_stock_gross=gross,
                       entry_short_call_premium=100 * marks[short_key], entry_cost=cost,
                       entry_cash_debit=debit,
                       entry_option_premiums={k: 100 * v for k, v in marks.items()},
                       entry_all_option_underlying_gross=3 * gross,
                       max_loss_proxy_at_entry=max(debit, 0))
            active.append({"pe": pe, "row": row})
            volume_rows.extend(_portfolio_volume_rows(pe, day, "entry", row["trade_id"], short_key))
            values, unknown = known_book(day)
            nav = cash + sum(100 * (s - m[short_key]) for _, m, s, _ in values) if not unknown else np.nan
            if np.isfinite(nav):
                peak = max(peak, nav)
                dd = 1 - nav / peak
                if dd >= .10:
                    paused = True
        values, unknown = known_book(day)
        nav = cash + sum(100 * (s - m[short_key]) for _, m, s, _ in values) if not unknown else np.nan
        gross_by_ticker, gross_by_sector = {}, {}
        if not unknown:
            for position, _, spot, _ in values:
                name, sector = position["pe"].ticker, position["row"]["sector"]
                gross_by_ticker[name] = gross_by_ticker.get(name, 0) + 100 * spot
                gross_by_sector[sector] = gross_by_sector.get(sector, 0) + 100 * spot
        gross = sum(gross_by_ticker.values()) if not unknown else np.nan
        if np.isfinite(nav) and nav > 0:
            dd = 1 - nav / peak
            for label, value, limit in (("name", max(gross_by_ticker.values(), default=0), .10),
                                        ("sector", max(gross_by_sector.values(), default=0), .25),
                                        ("total", gross, 1.0)):
                if value / nav > limit:
                    breach_rows.append({"date": day, "limit": label,
                                        "observed_fraction": value / nav, "limit_fraction": limit})
        else:
            dd = np.nan
        daily_rows.append({"date": day, "cash": cash, "nav": nav,
                           "stock_gross": gross,
                           "stock_gross_fraction": gross / nav if np.isfinite(nav) and nav > 0 else np.nan,
                           "short_call_liability": sum(100 * m[short_key] for _, m, _, _ in values) if not unknown else np.nan,
                           "stock_value_less_short_call_liability": sum(100 * (s - m[short_key]) for _, m, s, _ in values) if not unknown else np.nan,
                           "gross_by_ticker": gross_by_ticker if not unknown else None,
                           "gross_by_sector": gross_by_sector if not unknown else None,
                           "drawdown": dd, "new_entries_paused": paused or bool(unknown) or unresolved_exit,
                           "open_positions": len(active), "unknown_mark_reasons": tuple(unknown),
                           "traded_stock_gross": traded_gross,
                           "traded_option_premium_gross": traded_option_premiums,
                           "traded_option_underlying_gross": traded_option_underlying,
                           "paid_premium_haircuts": paid_costs})
    for position in active:
        if position["row"]["status"] == "OPEN":
            position["row"].update(status="OPEN_AT_WINDOW_END", reason="FIXED_EXIT_AFTER_WINDOW_END")
    daily = pd.DataFrame(daily_rows).set_index("date")
    # pct_change's default forward filling is deliberately not used.
    previous_nav = daily.nav.shift(1)
    previous_nav.iloc[0] = initial_nav
    daily["net_return"] = daily.nav.div(previous_nav) - 1
    metric_block = _portfolio_metric_block(daily, float(initial_nav))
    yearly = []
    for year, subset in daily.groupby(daily.index.year):
        first = daily.index.get_loc(subset.index[0])
        beginning_nav = float(initial_nav) if first == 0 else daily.nav.iloc[first - 1]
        block = _portfolio_metric_block(subset, beginning_nav) if np.isfinite(beginning_nav) else dict(
            sessions=len(subset), nav_gaps=int(subset.nav.isna().sum()), status="UNAVAILABLE_PREVIOUS_NAV_GAP")
        yearly.append(dict(year=int(year), **block))
    capacity = pd.DataFrame(volume_rows)
    scenarios = []
    for rate in sorted(set([.005, float(participation), .01, .02])):
        if capacity.empty:
            scenarios.append({"participation_limit": rate, "executed_trades": 0,
                              "volume_assessed_trades": 0, "all_observed_sides_fit": 0,
                              "closed_trades_all_sides_fit": 0, "volume_missing_trades": 0})
            continue
        summary = []
        for trade_id, group in capacity.groupby("trade_id"):
            volumes = group.observed_daily_volume
            complete = bool(volumes.notna().all() and (volumes > 0).all())
            fits = bool(complete and (volumes * rate >= 1).all())
            contracts = int(np.floor(volumes.min() * rate)) if complete else np.nan
            row = next(r for r in ledger if r["trade_id"] == trade_id)
            entry_rows = group[group.side == "entry"]
            entry_complete = len(entry_rows) == 3 and bool((entry_rows.observed_daily_volume > 0).all())
            entry_bottleneck = float(entry_rows.observed_daily_volume.min()) if entry_complete else np.nan
            summary.append({"trade_id": trade_id, "complete": complete, "fits": fits,
                            "closed": row["status"] == "CLOSED", "contracts": contracts,
                            "entry_capacity_stock_gross": np.floor(entry_bottleneck * rate) * row["entry_stock_gross"]
                            if np.isfinite(entry_bottleneck) else np.nan})
        scenarios.append({"participation_limit": rate, "executed_trades": len(summary),
                          "volume_assessed_trades": sum(x["complete"] for x in summary),
                          "all_observed_sides_fit": sum(x["fits"] for x in summary),
                          "closed_trades_all_sides_fit": sum(x["fits"] and x["closed"] for x in summary),
                          "volume_missing_trades": sum(not x["complete"] for x in summary),
                          "per_trade_contract_capacity": {x["trade_id"]: x["contracts"] for x in summary},
                          "per_trade_entry_stock_gross_capacity": {x["trade_id"]: x["entry_capacity_stock_gross"] for x in summary}})
    return {"daily": daily, "ledger": pd.DataFrame(ledger), "metrics": metric_block,
            "annual_metrics": pd.DataFrame(yearly), "capacity": capacity,
            "capacity_scenarios": pd.DataFrame(scenarios),
            "exposure_breaches": pd.DataFrame(breach_rows),
            "config": {"initial_nav": initial_nav, "bucket": "3-6m", "primary_horizon": primary_horizon,
                       "otm": otm, "haircut_each_leg_each_side": haircut,
                       "max_contracts": 1, "one_concurrent_per_ticker": True,
                       "name_gross_limit": .10, "sector_gross_limit": .25, "total_gross_limit": 1.0,
                       "pause_drawdown": .10, "resume_drawdown_strictly_below": .05,
                       "cash_return": 0, "risk_free_for_sharpe": 0, "annual_sessions": 252,
                       "entry_order": "entry_date, ticker, accession_number",
                       "volume_conditioned_admission": False},
            "limitations": ["Synthetic parity stock and last-trade option marks are proxy valuations, not executions.",
                            "NAV includes every selected ATM call, ATM put and sold call premium haircut on each side.",
                            "Stock financing, dividends, assignment and corporate-action execution are not reconstructed.",
                            "Whole-session entry-day volume is retrospective; it does not admit/reject portfolio positions.",
                            "Capacity figures are daily-volume bottleneck scenarios, not measured NBBO, ADV or impact capacity.",
                            "Turnover is opening-plus-closing synthetic-stock gross notional / average calendar NAV.",
                            "Separate option turnover diagnostics report all three legs' premium totals and underlying-reference gross notionals.",
                            "Stock value less short-call liability is marked position value, not option-delta-adjusted net exposure.",
                            "Manual sector groups require source/provenance disclosure and are not verified historical industry classifications.",
                            "Factor beta/size/value/momentum and high-volatility regime validation require separately approved data.",
                            "A missing fixed-exit mark is unresolved; subsequent marks never manufacture a later exit.",
                            "Interior NAV gaps preserve known endpoint returns; full-path Sharpe, volatility, max drawdown and frozen mean-NAV turnover remain unavailable."]}