"""Ticker normalization and actual XNYS schedule; no API calls on import."""
from __future__ import annotations

from dataclasses import dataclass, field
from html import unescape
from html.parser import HTMLParser
from hashlib import sha256
from functools import lru_cache
from types import MappingProxyType
import re
from typing import Callable, Mapping, Sequence
from urllib.parse import urlparse

import pandas as pd

VERSION = "AUTO_TEXT_OPERATIONAL_V7_CONTROL_GUARDRAIL"
EVENT_TAGS = ("acquisition_agreement", "merger_agreement")
EVENT_COLUMNS = [
    "ticker", "target", "transaction_group", "accession_number", "source_tags",
    "filing_date", "filing_url", "supporting_text", "accepted_at", "t_pre",
    "t_0", "entry_day", "event_date", "days_since_prev_event",
]
ET = "America/New_York"
DATE_WORDS = r"(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}"


def normalize_ticker(value):
    return value.strip().upper().replace("/", ".") if isinstance(value, str) and value.strip() else None


def ticker_tokens(value):
    values = value.replace(",", " ").split() if isinstance(value, str) else value if isinstance(value, (list, tuple)) else []
    return [normalized for item in values for normalized in
            ([normalize_ticker(item)] if isinstance(item, str) else ticker_tokens(item)) if normalized]


def canonical_filer_ticker(value):
    normalized = normalize_ticker(value)
    return "GOOGL" if normalized in {"GOOG", "GOOGL"} else normalized


def accession_id(row):
    url = str(row.get("filing_url") or "")
    directory = re.search(r"/Archives/edgar/data/\d+/(\d{18})(?:/|\.)", url)
    return directory.group(1) if directory else re.sub(r"\D", "", str(row.get("accession_number") or ""))


def accepted_et(value):
    stamp = pd.Timestamp(value)
    if pd.isna(stamp):
        raise ValueError("Missing SEC acceptance timestamp.")
    return stamp.tz_localize(ET, ambiguous="raise", nonexistent="raise") if stamp.tzinfo is None else stamp.tz_convert(ET)


class NYSEClock:
    """Actual XNYS schedule; never silently fall back to generic business days."""

    def __init__(self, schedule):
        schedule = schedule.copy()
        if not {"open", "close"}.issubset(schedule):
            raise ValueError("An XNYS open/close schedule is required.")
        labels = pd.DatetimeIndex(schedule.index)
        labels = labels.tz_localize(None) if labels.tz is not None else labels
        schedule.index = labels.normalize()
        schedule["open"] = pd.to_datetime(schedule["open"], utc=True).dt.tz_convert(ET)
        schedule["close"] = pd.to_datetime(schedule["close"], utc=True).dt.tz_convert(ET)
        schedule = schedule.sort_index()
        if schedule.empty or not schedule.index.is_unique or (schedule.open >= schedule.close).any():
            raise ValueError("Invalid calendar schedule.")
        self.schedule = schedule
        self.sessions = pd.DatetimeIndex(schedule.index)

    @classmethod
    def for_window(cls, start, end, padding_days=400):
        """Calendar generation is local and contains no market observations."""
        import exchange_calendars as xcals
        start, end = pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize()
        if start > end:
            raise ValueError("Invalid event window.")
        calendar = xcals.get_calendar("XNYS", start=start - pd.Timedelta(days=padding_days),
                                     end=end + pd.Timedelta(days=padding_days))
        return cls(calendar.schedule)

    def session_on_or_after(self, day):
        day = pd.Timestamp(day).tz_localize(None).normalize()
        index = self.sessions.searchsorted(day, side="left")
        if index >= len(self.sessions):
            raise ValueError("Calendar does not cover the requested future session.")
        return self.sessions[index]

    def session_before(self, day):
        index = self.sessions.searchsorted(pd.Timestamp(day).tz_localize(None).normalize(), side="left") - 1
        if index < 0:
            raise ValueError("Calendar does not cover the prior session.")
        return self.sessions[index]

    def next_session(self, day):
        index = self.sessions.searchsorted(pd.Timestamp(day).tz_localize(None).normalize(), side="right")
        if index >= len(self.sessions):
            raise ValueError("Calendar does not cover the next session.")
        return self.sessions[index]

    def sessions_between(self, first, last):
        first, last = (pd.Timestamp(value).tz_localize(None).normalize() for value in (first, last))
        if first < self.sessions[0] or last > self.sessions[-1]:
            raise ValueError("Session count exceeds calendar coverage.")
        return int(self.sessions.searchsorted(last, side="right") - self.sessions.searchsorted(first, side="right"))

    def session_close_time(self, day):
        return self.schedule.loc[pd.Timestamp(day).tz_localize(None).normalize(), "close"].time()

    def public_signal_session(self, value):
        stamp = accepted_et(value)
        day = stamp.tz_localize(None).normalize()
        session = self.session_on_or_after(day)
        return self.next_session(session) if session == day and stamp >= self.schedule.loc[session, "close"] else session

    def first_full_session_close(self, value):
        stamp = accepted_et(value)
        day = stamp.tz_localize(None).normalize()
        session = self.session_on_or_after(day)
        return session if session != day or stamp < self.schedule.loc[session, "open"] else self.next_session(session)

    def pre_public_session(self, value):
        stamp = accepted_et(value)
        day = stamp.tz_localize(None).normalize()
        session = self.session_on_or_after(day)
        return session if session == day and stamp >= self.schedule.loc[session, "close"] else self.session_before(session)

    def next_public_open(self, value):
        return self.first_full_session_close(value)

    def acceptance_regime(self, value):
        stamp = accepted_et(value)
        day = stamp.tz_localize(None).normalize()
        if day not in self.schedule.index:
            return "NONSESSION"
        if stamp < self.schedule.loc[day, "open"]:
            return "PREMARKET"
        return "INTRADAY" if stamp < self.schedule.loc[day, "close"] else "AFTER_CLOSE"


