"""Conservative, source-evidenced agreement events and an offline XNYS clock.

This is a POST-FIRST-IS operational extension, not the original manual review.
It never imports notebook code, credentials, prices, caches or an LLM. Import
and offline build_events have no network/file side effects. The API entry point
requires caller-supplied, authorized disclosure and public-SEC text transports.
Unrecognized legal language is a boundary case, never a favorable guess.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html import unescape
from html.parser import HTMLParser
import re
from typing import Callable, Mapping, Sequence
from urllib.parse import urlparse

import pandas as pd

VERSION = "AUTO_TEXT_OPERATIONAL_V2_POST_IS"
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


class _VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.hidden = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        elif not self.hidden and tag in {"p", "div", "br", "tr", "li", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)
        elif not self.hidden and tag in {"p", "div", "tr", "li"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def visible_text(value):
    parser = _VisibleText()
    parser.feed(value)
    return "\n".join(re.sub(r"\s+", " ", line).strip() for line in "".join(parser.parts).splitlines() if line.strip())


@dataclass
class FilingEvidence:
    accession_number: str
    cik: str
    company_name: str
    filing_url: str
    accepted_at: pd.Timestamp | None
    filing_date: pd.Timestamp
    form_type: str
    main_text: str
    public_exhibits: tuple[str, ...] = ()
    agreement_exhibits: tuple[str, ...] = ()
    complete_submission: bool = False
    source_notes: tuple[str, ...] = ()

    @property
    def announcement_text(self):
        return "\n".join((self.main_text,) + self.public_exhibits)


def parse_sec_submission(payload, filing_url, expected_accession=None):
    """Parse the complete SEC SGML filing, not an API label supporting excerpt."""
    validate_sec_url(filing_url)
    header = payload.split("</SEC-HEADER>", 1)[0]
    acceptance = re.search(r"<ACCEPTANCE-DATETIME>\s*(\d{14})", header)
    accession = re.search(r"ACCESSION NUMBER:\s*([\d-]+)", header)
    name = re.search(r"COMPANY CONFORMED NAME:\s*([^\r\n]+)", header)
    cik = re.search(r"CENTRAL INDEX KEY:\s*(\d+)", header)
    filed = re.search(r"FILED AS OF DATE:\s*(\d{8})", header)
    if not all((acceptance, accession, name, cik, filed)):
        raise ValueError("SEC acceptance/filer/date provenance is incomplete.")
    accession = re.sub(r"\D", "", accession.group(1))
    if expected_accession and accession != re.sub(r"\D", "", expected_accession):
        raise ValueError("SEC source accession differs from candidate.")
    main, public, agreements, form = [], [], [], None
    documents = re.findall(r"<DOCUMENT>(.*?)</DOCUMENT>", payload, flags=re.I | re.S)
    for document in documents:
        kind = re.search(r"<TYPE>\s*([^\r\n<]+)", document, flags=re.I)
        body = re.search(r"<TEXT>(.*?)</TEXT>", document, flags=re.I | re.S)
        if not kind or not body:
            continue
        kind, text = kind.group(1).strip().upper(), visible_text(body.group(1))
        if kind in {"8-K", "8-K/A"}:
            main.append(text)
            form = kind
        elif kind.startswith("EX-99"):
            public.append(text)
        elif kind.startswith("EX-2"):
            agreements.append(text)
    if not main:
        raise ValueError("The submission contains no current-report body.")
    accepted = pd.to_datetime(acceptance.group(1), format="%Y%m%d%H%M%S").tz_localize(ET)
    filing_date = pd.to_datetime(filed.group(1), format="%Y%m%d")
    if accepted.tz_localize(None).normalize() != filing_date:
        raise ValueError("SEC acceptance and filing-date metadata conflict.")
    return FilingEvidence(accession, cik.group(1).zfill(10), name.group(1).strip(),
                          filing_url, accepted, filing_date, form, "\n".join(main),
                          tuple(public), tuple(agreements), True,
                          ("SEC acceptance is the public-clock proxy; earlier IR time may be unknown.",))


def sec_submission_url(filing_url, expected_accession):
    """Derive the ordinary complete-submission TXT URL from SEC provenance."""
    validate_sec_url(filing_url)
    accession = re.sub(r"\D", "", expected_accession)
    if not re.fullmatch(r"\d{18}", accession):
        raise ValueError("Invalid complete-submission accession.")
    cik = re.search(r"/Archives/edgar/data/(\d+)/", urlparse(filing_url).path)
    if not cik:
        raise ValueError("SEC source has no filer directory.")
    dashed = accession[:10] + "-" + accession[10:12] + "-" + accession[12:]
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik.group(1))}/{dashed}.txt"


def parse_items_evidence(candidate, index_record):
    """Join filing-specific vendor identity to Items text; never invent a clock.

    The result is deliberately incomplete and cannot enter build_events. It is
    useful for semantic diagnostics when complete submissions are unavailable.
    Index issuer_name avoids future ticker-reference names or manual mappings.
    """
    accession = accession_id(candidate)
    if (not re.fullmatch(r"\d{18}", accession) or accession_id(index_record) != accession
            or candidate.get("filing_date") != index_record.get("filing_date")
            or str(candidate.get("cik", "")).zfill(10) != str(index_record.get("cik", "")).zfill(10)
            or candidate.get("form_type") != index_record.get("form_type")
            or not isinstance(index_record.get("issuer_name"), str) or not index_record["issuer_name"].strip()):
        raise ValueError("Items and filing-specific index provenance conflict.")
    validate_sec_url(candidate["filing_url"])
    validate_sec_url(index_record["filing_url"])
    return FilingEvidence(accession, str(candidate["cik"]).zfill(10), index_record["issuer_name"].strip(),
                          candidate["filing_url"], None, pd.Timestamp(candidate["filing_date"]).normalize(),
                          candidate["form_type"], candidate.get("items_text", ""), complete_submission=False,
                          source_notes=("Filing-specific issuer_name from the vendor EDGAR index.",
                                        "Core Items text lacks exact SEC acceptance and full public exhibits."))


def _flat(value):
    return re.sub(r"\s+", " ", unescape(value).replace("\u00a0", " ")).strip()


def validate_sec_url(value):
    parsed = urlparse(value)
    if (parsed.scheme != "https" or (parsed.hostname or "").lower() not in {"www.sec.gov", "sec.gov"}
            or not parsed.path.startswith("/Archives/edgar/data/")
            or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.port):
        raise ValueError("Filing provenance must be an ordinary HTTPS SEC Archives URL.")


def _identity(value):
    value = re.sub(r"\b(?:incorporated|inc|corporation|corp|limited|ltd|llc|plc)\b", " ", value, flags=re.I)
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _brand(value):
    words = _identity(value).split()
    return next((word for word in words if word != "the"), "")


def text_blocks(text):
    """Rejoin vendor soft wraps without erasing separate legal paragraphs.

    Items text sometimes wraps a sentence across many lines, whereas complete
    HTML extraction already gives paragraph lines. A line ending in a sentence
    stop, an Item heading, a table row or a blank line closes the current block.
    This is a formatting repair, not new evidence from a category or ticker.
    """
    blocks, current = [], []
    for line in text.splitlines():
        line = _flat(line)
        heading = bool(re.match(r"^(?:Item\s*\d(?:\.\d+)?|Forward.Looking|Signature|\|)", line, re.I))
        if not line or heading:
            if current:
                blocks.append(" ".join(current))
                current = []
            if line:
                blocks.append(line)
            continue
        current.append(line)
        if re.search(r"[.!?][\"”']?$", line) and not re.search(r"\b(?:Inc|Corp|Ltd|Co|L\.P|L\.L\.C)\.$", line, re.I):
            blocks.append(" ".join(current))
            current = []
    if current:
        blocks.append(" ".join(current))
    return blocks


def _defined_names(text):
    """Resolve explicit legal aliases; never use a ticker-to-target lookup."""
    names = {}
    for block in text_blocks(text):
        for match in re.finditer(r'([^()]{1,220})\((?:the\s+)?["“]([^"”]{1,70})["”]\)', block):
            prefix, alias = match.groups()
            # Jurisdiction qualifiers immediately precede many legal aliases.
            prefix = re.sub(r",\s*(?:a|an)\s+[^,()]{0,100}(?:corporation|company|partnership|entity)\s*$", "", prefix, flags=re.I)
            prefix = re.split(r"\b(?:by and among|among|with|and)\s+", prefix)[-1]
            prefix = re.sub(r"^.*?\bOn\s+" + DATE_WORDS + r",?\s+", "", prefix, flags=re.I)
            prefix = re.sub(r"^.*?(?:entered into|announced|will acquire)\s+", "", prefix, flags=re.I)
            prefix = prefix.strip(" ,")
            if prefix and len(prefix) <= 140 and not re.match(r"^(?:an?|including|subject|pursuant|referred)\b", prefix, flags=re.I):
                names.setdefault(alias.casefold(), prefix)
    return names


def _self_aliases(text, company):
    brand = _brand(company)
    aliases = {company}
    for alias, name in _defined_names(text).items():
        if brand and re.search(r"\b" + re.escape(brand) + r"\b", _identity(name)):
            aliases.add(alias)
    # Generic Company is safe only if it was not explicitly defined as another
    # party, for example the target in a filer-as-Buyer stock purchase agreement.
    names = _defined_names(text)
    if "company" not in names or "company" in {a.casefold() for a in aliases}:
        aliases.update(("Company", "registrant", "the Company", "the registrant"))
    # A filer may contract through a named subsidiary, but require that actual
    # subsidiary relationship in the current filing instead of a company map.
    for alias, name in names.items():
        pattern = (re.escape(alias) + r'[^.]{0,45}\b(?:an?\s+)?(?:(?:direct|indirect|wholly[ -]owned)\s+)*subsidiary\s+of\s+'
                   + re.escape(company))
        if re.search(pattern, _flat(text), flags=re.I):
            aliases.update((alias, name))
    return aliases


def _target_from_clause(clause, names=None, company=None):
    names = names or {}
    direct = re.search(r"\b(?:to\s+|will\s+)?(?:acquire|purchase(?!\s+agreement))[, ]+(.{3,450})", clause, flags=re.I)
    if direct:
        target = direct.group(1)
        target = re.sub(r"^through\s+one\s+of\s+(?:its|the Company.s)\s+wholly[ -]owned\s+subsidiaries,?\s*", "", target, flags=re.I)
        target = re.sub(r"^(?:an?\s+)?\d+(?:\.\d+)?\s*%\s+(?:controlling\s+|majority\s+)?(?:interest|stake)\s+in\s+(?:its\s+|the\s+)?", "", target, flags=re.I)
        target = re.sub(r"^(?:(?:all|100\s*%|one hundred percent|substantially all)(?:\s+of)?\s+(?:the\s+)?(?:(?:issued and )?outstanding\s+)?(?:shares(?: of (?:common|capital) stock)?|capital stock|equity(?: interests)?|business and assets|business|assets|interests)\s+(?:of|in)\s+)", "", target, flags=re.I)
        target = re.sub(r"^(?:a\s+)?(?:controlling|majority)\s+(?:interest|stake)\s+in\s+", "", target, flags=re.I)
        target = re.sub(r"^\d+(?:\.\d+)?\s*%\s+(?:of|interest in|stake in)\s+(?:the\s+)?", "", target, flags=re.I)
        target = re.split(r"\s+(?:for\s+\$|for a|in an|pursuant to|through a|by means|which|a leading)|\s*\(|;", target, maxsplit=1, flags=re.I)[0]
        target = re.sub(r",\s*(?:a|an|the)\s+.*$", "", target, flags=re.I)
        target = re.split(r"\.(?:\s|$)", target, maxsplit=1)[0].strip(" ,.")
        if len(_identity(target).split()) >= 1 and not re.match(r"^(?:certain|various|additional|the remaining|remaining)\b", target, flags=re.I):
            return names.get(re.sub(r"^the\s+", "", target, flags=re.I).casefold(), target[:160])
    # A merger can describe control in legal recital form instead of saying
    # "acquire". Require the named survivor to become owned by the filer; a
    # separate pre-close holding-company merger is not buyer control.
    for match in re.finditer(r"\bwith\s+([A-Z][A-Za-z0-9 '&.\-]{1,85}?)\s+surviving.{0,110}?\b(?:a\s+)?(?:direct,?\s+)?wholly[ -]owned\s+subsidiary\s+of\s+([^.;]{2,100})", clause):
        target, owner = match.groups()
        owner = re.sub(r"^the\s+", "", owner.strip(" ,"), flags=re.I)
        owner_name = names.get(owner.casefold(), owner)
        brand = _brand(company) if company else ""
        self_aliases = {re.sub(r"^the\s+", "", value, flags=re.I).casefold() for value in _self_aliases(clause, company)} if company else set()
        if owner.casefold() in self_aliases or brand and brand in _identity(owner_name).split():
            return names.get(target.casefold(), target)
    # Ordinary three-party merger recitals define the independent target last.
    defined = re.findall(r"\band\s+([A-Z][^;\n]{2,180}?)\s*\((?:the\s+)?[\"“]([^\"”]+)[\"”]\)", clause)
    for name, alias in reversed(defined):
        if alias.casefold() not in {"company", "registrant", "merger sub", "merger subsidiary", "buyer", "parent"}:
            return re.sub(r",\s*(?:a|an)\s+.*$", "", name).strip(" ,")
    return None


def _agreement_date(clause):
    dated = re.search(r"\bdated\s+(?:as\s+of\s+)?(" + DATE_WORDS + ")", clause, flags=re.I)
    signed = re.search(r"\bOn\s+(" + DATE_WORDS + ")", clause, flags=re.I)
    match = dated or signed
    return pd.Timestamp(match.group(1)).normalize() if match else None


def _company_subject(clause, company, text=None):
    match = re.search(r"\b(?:entered\s+into|signed|executed|announc(?:ed|ing|es))\b", clause, flags=re.I)
    if not match:
        return False
    subject = clause[:match.start()]
    aliases = _self_aliases(text or clause, company)
    return any(re.search(r"\b" + re.escape(alias) + r"\b", subject, flags=re.I) for alias in aliases if alias)


def _independent_news(text):
    patterns = {
        "INDEPENDENT_EARNINGS": r"\b(?:announced|reported|released)\b.{0,120}\b(?:financial results|(?:quarterly|annual) earnings|results of operations)\b",
        "INDEPENDENT_GUIDANCE": r"\b(?:raised|lowered|updated|revised|issued|reaffirm(?:ed|s)?|reiterat(?:ed|es))\b.{0,45}\b(?:full.year|annual|financial|earnings)\b.{0,30}\bguidance\b",
        "INDEPENDENT_DIVIDEND": r"\b(?:declared|increased|raised|initiated)\b.{0,45}\b(?:cash\s+|quarterly\s+|special\s+)?dividend\b",
        "INDEPENDENT_BUYBACK": r"\b(?:authorized|approved|announced)\b.{0,65}\b(?:new|additional|expanded)\b.{0,50}\b(?:repurchase|buyback)\b",
        "INDEPENDENT_BUYBACK_REAFFIRMATION": r"\b(?:reaffirm(?:ed|s)?|reiterat(?:ed|es))\b.{0,80}\b(?:repurchase|buyback)\b",
        "INDEPENDENT_SELLER_EQUITY_INVESTMENT": r"\b(?:separately|separate agreement|also entered)\b.{0,180}\b(?:invest(?:ment)?|subscribe|purchase)\b.{0,160}\b(?:newly.issued\s+(?:(?:ordinary|common)\s+)?shares|equity stake|minority interest|shares of the seller)\b",
        "PRE_ENTRY_COMPETING_OFFER": r"\b(?:received|submitted|announced)\b.{0,90}\b(?:competing|superior|rival)\s+(?:bid|proposal|offer)\b",
    }
    matches = []
    for paragraph in text_blocks(text):
        if (re.search(r"\b(?:previously announced|previously authorized|previously declared|historical)\b", paragraph, flags=re.I)
                and not re.search(r"\b(?:reaffirm(?:ed|s)?|reiterat(?:ed|es))\b", paragraph, flags=re.I)):
            continue
        for reason, pattern in patterns.items():
            match = re.search(pattern, _flat(paragraph), flags=re.I)
            if match:
                matches.append((reason, match.group(0)))
    return matches


def extract_agreement(evidence):
    """Return one unambiguous present buyer/control/business statement with spans.

    Deliberately does not equate a tag, merger form, financing plan or accretion
    forecast with operating-business control. British schemes and complex asset
    transfers are boundary cases unless the current statement is explicit.
    """
    text = evidence.announcement_text
    blocks = text_blocks(text)
    names = _defined_names(text)
    facts, exclusions, missing = [], [], []
    for paragraph in blocks:
        clause = _flat(paragraph)
        if not re.search(r"\b(?:entered\s+into|entry\s+into|signed|executed|execution\s+of|announc(?:ed|ing|es).{0,70}definitive)\b", clause, flags=re.I):
            continue
        explicit = re.search(r"\b(?:definitive\s+(?:acquisition\s+|merger\s+|purchase\s+)?agreement|agreement and plan of merger|merger agreement|(?:stock|share|asset|business|equity) purchase agreement|purchase and sale agreement)\b", clause, flags=re.I)
        executed_purchase = re.search(r"\bentered\s+into\s+an?\s+agreement\b.{0,200}\bto\s+acquire\b", clause, flags=re.I)
        if not explicit and not executed_purchase:
            continue
        if not _company_subject(clause, evidence.company_name, text):
            continue
        if re.search(r"\b(?:to sell|to divest|sell its|sell the|sale of its|dispose of)\b", clause, flags=re.I):
            exclusions.append(("SELLER_SIDE", clause))
            continue
        if re.search(r"\b(?:amend(?:ed|ment)?|previously announced|previously entered|prior agreement|original agreement)\b", clause, flags=re.I):
            exclusions.append(("UPDATE_OR_HISTORICAL_REFERENCE", clause))
            continue
        if re.search(r"\b(?:non.binding|letter of intent|memorandum of understanding)\b", clause, flags=re.I):
            exclusions.append(("NONDEFINITIVE_PROPOSAL", clause))
            continue
        if re.search(r"\b(?:acquire|purchase)\s+(?:an?\s+)?(?:minority|non.controlling)\s+(?:interest|stake|investment)\b", clause, flags=re.I):
            exclusions.append(("NO_NEW_CONTROL", clause))
            continue
        target = _target_from_clause(clause, names, evidence.company_name)
        if not target:
            missing.append({"statement": clause, "missing": ["target_identity"]})
            continue
        if _identity(target) in {_identity(evidence.company_name), "company", "the company", "registrant", "the registrant"}:
            exclusions.append(("SELLER_OR_TARGET_FILER", clause))
            continue
        if re.match(r"^(?:a\s+|the\s+)?(?:loan portfolio|receivables|mortgage portfolio|debt securities|notes|bonds|vacant land)\b", target, flags=re.I):
            exclusions.append(("PURE_FINANCIAL_OR_NONBUSINESS_ASSETS", clause))
            continue
        agreement_date = _agreement_date(clause)
        control = re.search(r"\b(?:acquire\s+100\s*%|100\s*%\s+of\s+(?:the\s+)?(?:business and assets|shares|equity)|all\s+(?:of\s+)?(?:the\s+)?(?:issued and )?outstanding\s+(?:shares|capital stock|equity)|all\s+(?:of\s+)?(?:the\s+)?(?:business and assets|equity interests)|controlling\s+(?:interest|stake)|majority\s+(?:interest|stake)|(?:will\s+become|surviving.{0,50})\s+(?:a\s+)?(?:direct,?\s+)?wholly[ -]owned\s+subsidiary)\b", clause, flags=re.I)
        percentage = re.search(r"\bacquire\s+(?:an?\s+)?(\d+(?:\.\d+)?)\s*%", clause, flags=re.I)
        if percentage and float(percentage.group(1)) > 50:
            control = percentage
        # A target's operating description must be in an announcement paragraph
        # that names that target, rather than unrelated buyer boilerplate.
        target_key = _identity(target).split()[0] if _identity(target) else ""
        operating = None
        buyer_brand = _brand(evidence.company_name)
        for description in blocks:
            named = list(re.finditer(r"\b" + re.escape(target_key) + r"\b", description, flags=re.I)) if target_key else []
            descriptors = list(re.finditer(r"\b(?:operating business|manufacturer|manufacturing|developer|provider|distributor|distribution business|railroad|railway|fund manager|asset manager|software company|technology company|purification and filtration business|bank|brokerage|insurer|insurance company|cable operator|telecommunications operator|investment adviser|(?:meal and grocery|food|grocery|meal) delivery business|streaming.{0,20}studios businesses|fiber.{0,35}network assets and related operations)\b", description, flags=re.I))
            for descriptor in descriptors:
                preceding = [name for name in named if name.start() <= descriptor.start() and descriptor.start() - name.end() <= 240]
                if preceding and not re.search(r"\b" + re.escape(buyer_brand) + r"\b", description[preceding[-1].end():descriptor.start()], flags=re.I):
                    operating = descriptor
                    break
            if operating:
                break
        if control and operating and agreement_date is not None:
            facts.append({"target": target, "agreement_date": agreement_date,
                          "definitive_buyer_span": clause, "control_span": control.group(0),
                          "operating_business_span": operating.group(0),
                          "binding_basis": "EXPLICIT_DEFINITIVE_OR_NAMED_PURCHASE_AGREEMENT" if explicit else "EXECUTED_ACQUISITION_AGREEMENT_WITH_EXPLICIT_CONTROL"})
        else:
            missing.append({"target": target, "statement": clause,
                            "missing": [key for key, value in (("control", control), ("operating_business", operating), ("signing_date", agreement_date)) if value is None]})
    # Different formulations for the same target are merged only by identity,
    # not by a similarity threshold selected using returns.
    unique = {(_identity(f["target"]), str(f["agreement_date"].date())): f for f in facts}
    if len(unique) == 1:
        return "auto_eligible", "EXPLICIT_BUYER_DEFINITIVE_OPERATING_CONTROL", next(iter(unique.values()))
    if len(unique) > 1:
        return "boundary", "MULTIPLE_TARGETS_OR_AGREEMENT_DATES", {"candidate_facts": list(unique.values())}
    if exclusions:
        return "excluded", exclusions[0][0], {"exclusion_span": exclusions[0][1]}
    if re.search(r"\b(?:credit agreement|loan agreement|refinancing|debt issuance)\b", text, flags=re.I) and not re.search(r"\b(?:acquire|merger|acquisition)\b", text, flags=re.I):
        return "excluded", "PURE_FINANCING", {}
    if re.search(r"\b(?:letter of intent|non.binding proposal|memorandum of understanding)\b", text, flags=re.I):
        return "excluded", "NONDEFINITIVE_PROPOSAL", {}
    return "boundary", "BUYER_TARGET_CONTROL_BUSINESS_OR_SIGNING_DATE_UNRESOLVED", {"unresolved_candidates": missing}


def _audit_row(accession, ticker, status, reason, evidence=None, facts=None):
    return {"accession_number": accession, "ticker": ticker, "status": status,
            "reason": reason, "classifier_version": VERSION,
            "filing_url": evidence.filing_url if evidence else None,
            "accepted_at": evidence.accepted_at if evidence else None,
            "evidence_spans": facts or {},
            "limitations": "Earlier IR/other-source firstness and unobserved news are not proved absent."}


def build_events(tags, start, end, universe, raw, evidence: Mapping[str, FilingEvidence],
                 calendar=None, screening_documents: Sequence[FilingEvidence] = ()):
    """Offline deterministic candidate classification; original notebook columns.

    auto_eligible is conditional on explicit source wording and observed source
    coverage, not identical to the pre-results human eligibility classification.
    Filings after the candidate's full-session entry close cannot affect it.
    Missing evidence/boundaries are retained in attrs['classification_audit'].
    """
    if tuple(sorted(set(tags))) != tuple(sorted(EVENT_TAGS)):
        raise ValueError("Only the committed agreement-tag union is supported.")
    start, end = pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize()
    if start > end:
        raise ValueError("Invalid event window.")
    calendar = calendar or NYSEClock.for_window(start, end)
    frame = pd.DataFrame(raw).copy()
    audit, rows, seen = [], [], {}
    if frame.empty:
        result = pd.DataFrame(columns=EVENT_COLUMNS)
        result.attrs.update(classification_audit=pd.DataFrame(), classifier_version=VERSION)
        return result
    frame["accession_id"] = frame.apply(accession_id, axis=1)
    if not frame.accession_id.str.fullmatch(r"\d{18}").all():
        raise ValueError("Disclosure accession is missing or invalid.")
    frame["filing_date"] = pd.to_datetime(frame.filing_date).dt.normalize()
    frame = frame[frame.filing_date.between(start, end)]
    universe = {normalize_ticker(ticker) for ticker in universe}
    packages = []
    for accession, group in frame.groupby("accession_id", sort=True):
        names = {canonical_filer_ticker(token) for value in group.tickers for token in ticker_tokens(value)} & universe
        if not names:
            continue
        if len(names) != 1:
            audit.append(_audit_row(accession, None, "boundary", "MULTIPLE_UNIVERSE_FILER_TICKERS"))
            continue
        ticker = next(iter(names))
        package = evidence.get(accession)
        if package is None or not package.complete_submission:
            audit.append(_audit_row(accession, ticker, "boundary", "COMPLETE_SEC_BODY_AND_EXHIBITS_MISSING", package))
            continue
        if group.filing_date.nunique() != 1 or package.filing_date != group.filing_date.iloc[0]:
            audit.append(_audit_row(accession, ticker, "boundary", "FILING_DATE_CONFLICT", package))
            continue
        if package.accession_number != accession:
            raise ValueError("Evidence accession mismatch.")
        package.cik = str(package.cik).zfill(10)
        ciks = {str(value).zfill(10) for value in group.cik.dropna()} if "cik" in group else set()
        if ciks and ciks != {package.cik}:
            audit.append(_audit_row(accession, ticker, "boundary", "FILER_CIK_CONFLICT", package))
            continue
        source_tags = tuple(sorted(set(group.source_tag if "source_tag" in group else group.tertiary_category) & set(EVENT_TAGS)))
        if not source_tags:
            continue
        packages.append((package.accepted_at, accession, ticker, source_tags, group, package))
    for _, accession, ticker, source_tags, group, package in sorted(packages, key=lambda value: (value[0], value[1])):
        if package.form_type != "8-K":
            audit.append(_audit_row(accession, ticker, "excluded", "AMENDMENT_NOT_INITIAL_8K", package))
            continue
        status, reason, facts = extract_agreement(package)
        if status != "auto_eligible":
            audit.append(_audit_row(accession, ticker, status, reason, package, facts))
            continue
        if facts["agreement_date"] > package.filing_date:
            audit.append(_audit_row(accession, ticker, "boundary", "SIGNING_DATE_AFTER_PUBLIC_FILING", package, facts))
            continue
        entry = calendar.first_full_session_close(package.accepted_at)
        cutoff = calendar.schedule.loc[entry, "close"]
        control_history = [doc for doc in screening_documents
                           if str(doc.cik).zfill(10) == package.cik and doc.accepted_at <= cutoff]
        aliases = _self_aliases(package.announcement_text, package.company_name)
        prior_control = None
        for block in text_blocks(package.announcement_text):
            for alias in aliases:
                pattern = (r"\b" + re.escape(alias) + r"\b.{0,30}\b(?:already|currently)\s+(?:owns|owned|controls|controlled)\b"
                           r"(?:.{0,60}\b(?:majority|controlling)\b)?")
                candidate = re.search(pattern, block, flags=re.I)
                if candidate:
                    # Present control is decisive. Mere current minority share
                    # ownership is not already-control evidence.
                    if re.search(r"\bcontrols|controlled|majority|controlling\b", candidate.group(0), flags=re.I):
                        prior_control = candidate
                        break
            if prior_control:
                break
        if prior_control:
            audit.append(_audit_row(accession, ticker, "excluded", "ALREADY_CONTROLLED_OR_REMAINING_MINORITY", package, {**facts, "exclusion_span": prior_control.group(0)}))
            continue
        identity = (package.cik, _identity(facts["target"]), facts["agreement_date"])
        prior = seen.get(identity)
        if prior:
            audit.append(_audit_row(accession, ticker, "excluded", "DUPLICATE_BUYER_TARGET_SIGNING_DATE", package, {**facts, "first_accession": prior}))
            continue
        # An initial announcement excluded for concurrent news still blocks
        # a later clean filing from becoming a new initial agreement.
        seen[identity] = accession
        news = _independent_news(package.announcement_text)
        for document in control_history:
            # Same filing-day earlier messages must not be missed merely because
            # their SEC acceptance precedes the agreement filing's acceptance.
            if package.filing_date <= document.accepted_at.tz_localize(None).normalize() and document.accepted_at <= cutoff:
                news.extend(_independent_news(document.announcement_text))
        target_key = _identity(facts["target"]).split()[0]
        for document in screening_documents:
            if (str(document.cik).zfill(10) != package.cik
                    and package.filing_date <= document.accepted_at.tz_localize(None).normalize()
                    and document.accepted_at <= cutoff
                    and re.search(r"\b" + re.escape(target_key) + r"\b", document.announcement_text, flags=re.I)):
                news.extend(match for match in _independent_news(document.announcement_text)
                            if match[0] == "PRE_ENTRY_COMPETING_OFFER")
        if news:
            audit.append(_audit_row(accession, ticker, "excluded", news[0][0], package, {**facts, "news_spans": news}))
            continue
        # Initial agreements in explicitly supplied pre-window history block old
        # references; unknown history is disclosed, never fabricated as complete.
        first_prior = None
        for document in control_history:
            if document.accepted_at >= package.accepted_at:
                continue
            prior_status, _, prior_facts = extract_agreement(document)
            if prior_status == "auto_eligible" and (_identity(prior_facts["target"]), prior_facts["agreement_date"]) == identity[1:]:
                first_prior = document.accession_number
                break
        if first_prior:
            audit.append(_audit_row(accession, ticker, "excluded", "PRIOR_PUBLIC_DEFINITIVE_AGREEMENT", package, {**facts, "first_accession": first_prior}))
            continue
        accepted = accepted_et(package.accepted_at)
        clock = accepted.tz_localize(None)  # Legacy schema uses naive Eastern.
        rows.append({"ticker": ticker, "target": facts["target"],
                     "transaction_group": package.cik + "/" + _identity(facts["target"]) + "/" + str(facts["agreement_date"].date()),
                     "accession_number": accession, "source_tags": source_tags,
                     "filing_date": package.filing_date, "filing_url": package.filing_url,
                     "supporting_text": str(group.supporting_text.iloc[0]) if "supporting_text" in group else facts["definitive_buyer_span"],
                     "accepted_at": clock, "t_pre": calendar.pre_public_session(accepted),
                     "t_0": calendar.public_signal_session(accepted), "entry_day": entry,
                     "event_date": package.filing_date})
        audit.append(_audit_row(accession, ticker, status, reason, package, facts))
    result = pd.DataFrame(rows, columns=EVENT_COLUMNS[:-1])
    if not result.empty:
        result = result.sort_values(["accepted_at", "accession_number"]).reset_index(drop=True)
        result["days_since_prev_event"] = result.groupby("ticker").filing_date.diff().dt.days
        assert result.accession_number.is_unique and result.transaction_group.is_unique
    else:
        result["days_since_prev_event"] = pd.Series(dtype=float)
    result.attrs.update(classification_audit=pd.DataFrame(audit), classifier_version=VERSION,
                        equivalent_to_manual_IS_review=False,
                        coverage_limitations=("Only supplied complete SEC submissions and observed pre-entry filings were screened.",
                                              "Global first-public IR history, vendor label availability and unobserved independent news remain unverified."))
    return result


def build_events_from_api(tags, start, end, universe, api_get_all: Callable,
                          public_sec_get: Callable[[str], str], calendar=None,
                          history_start=None):
    """Authorized API-key-only transport interface; no LLM key/manual whitelist.

    This function makes disclosure/text requests ONLY when explicitly called.
    The caller owns authentication, scope approval, rate limiting, secure caching
    and pagination verification. public_sec_get must return public SEC text and
    never send a Massive key to SEC. Exceptions are sanitized by the caller.
    No end-window-plus-padding market/filing records are requested.
    """
    if tuple(sorted(set(tags))) != tuple(sorted(EVENT_TAGS)):
        raise ValueError("Only the committed tag union may be requested.")
    calendar = calendar or NYSEClock.for_window(start, end)
    rows = []
    for tag in tags:
        page_rows = api_get_all("/stocks/filings/8-K/vX/disclosures", {
            "tertiary_category": tag, "filing_date.gte": start, "filing_date.lte": end,
            "limit": 1000, "sort": "filing_date.asc"})
        rows.extend({**row, "source_tag": tag} for row in page_rows
                    if row.get("filing_date") and pd.Timestamp(start) <= pd.Timestamp(row["filing_date"]) <= pd.Timestamp(end))
    frame = pd.DataFrame(rows)
    if frame.empty:
        return build_events(tags, start, end, universe, frame, {}, calendar)
    names = {normalize_ticker(ticker) for ticker in universe}
    relevant = frame[frame.tickers.map(lambda values: bool({canonical_filer_ticker(t) for t in ticker_tokens(values)} & names))]
    evidence, screening = {}, []
    for row in relevant.to_dict("records"):
        accession = accession_id(row)
        if accession in evidence:
            continue
        try:
            validate_sec_url(row["filing_url"])
            submission_url = sec_submission_url(row["filing_url"], accession)
            evidence[accession] = parse_sec_submission(public_sec_get(submission_url), submission_url, accession)
        except Exception:
            # Do not output transport messages, raw response bodies or credentials.
            continue
    # Current-window issuer text discovers concurrent SEC filings without future
    # acceptance leakage. Optional pre-window history is explicit, not automatic.
    lower = history_start if history_start is not None else start
    if pd.Timestamp(lower) > pd.Timestamp(start):
        raise ValueError("History cannot start after the requested window.")
    partial = {}
    ciks = {str(value).zfill(10) for value in relevant.cik.dropna()} if "cik" in relevant else set()
    for cik in sorted(ciks | {doc.cik for doc in evidence.values()}):
        metadata = api_get_all("/stocks/filings/vX/index", {
            "cik": cik, "form_type": "8-K", "filing_date.gte": lower, "filing_date.lte": end,
            "limit": 1000, "sort": "filing_date.asc"})
        items = api_get_all("/stocks/filings/8-K/vX/text", {
            "cik": cik, "filing_date.gte": lower, "filing_date.lte": end,
            "limit": 100, "sort": "filing_date.asc"})
        index_by_id = {accession_id(row): row for row in metadata
                       if row.get("filing_date") and pd.Timestamp(lower) <= pd.Timestamp(row["filing_date"]) <= pd.Timestamp(end)
                       and str(row.get("cik", "")).zfill(10) == cik}
        for row in items:
            accession = accession_id(row)
            if accession in index_by_id:
                try:
                    partial[accession] = parse_items_evidence(row, index_by_id[accession])
                except Exception:
                    continue
        for row in metadata:
            if not row.get("filing_date") or not pd.Timestamp(lower) <= pd.Timestamp(row["filing_date"]) <= pd.Timestamp(end):
                continue
            accession = accession_id(row)
            if accession in evidence:
                screening.append(evidence[accession])
                continue
            if not row.get("filing_url"):
                continue
            try:
                validate_sec_url(row["filing_url"])
                submission_url = sec_submission_url(row["filing_url"], accession)
                screening.append(parse_sec_submission(public_sec_get(submission_url), submission_url, accession))
            except Exception:
                continue
    events = build_events(tags, start, end, universe, frame, evidence, calendar, screening)
    events.attrs["requested_filing_history_start"] = lower
    events.attrs["prior_to_window_history_requested"] = history_start is not None and pd.Timestamp(history_start) < pd.Timestamp(start)
    events.attrs["partial_source_diagnostics"] = pd.DataFrame([
        {"accession_number": accession, "filing_date": package.filing_date,
         "issuer_name": package.company_name, "extractor_status": extract_agreement(package)[0],
         "exact_acceptance_available": False, "complete_public_exhibits_available": False,
         "primary_event_admitted": False}
        for accession, package in partial.items() if accession not in evidence])
    return events
