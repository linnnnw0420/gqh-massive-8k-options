"""Auditable IS-only Massive transport; credentials never enter cached URLs/logs."""
from __future__ import annotations

import hashlib
from datetime import date
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import parse_qsl, unquote_plus, urlsplit, urlunsplit

import requests

BASE = "https://api.massive.com"
START, END = "2024-01-01", "2025-12-31"
SECRET_NAMES = {"apikey", "api_key", "key", "token", "access_token", "authorization"}
PAGINATION_NAMES = {"cursor"}
INDEX_PATH = "/stocks/filings/vX/index"


def study_bounds(window_role):
    if window_role == "is":
        return START, END, "2023-12-01", START
    if window_role == "oos":
        return "2026-01-01", "2026-08-31", "2025-12-01", START
    raise ValueError("Unknown study window; sealed execution is never supported.")


def validate_index_parameters(params, *, window_role="is"):
    """Bounded source metadata only; never a public-news coverage certificate."""
    _, upper, _, source_lower = study_bounds(window_role)
    required = {"cik", "form_type", "filing_date.gte", "filing_date.lte"}
    allowed = required | {"limit", "sort"}
    if not isinstance(params, dict) or not required <= params.keys() or params.keys() - allowed:
        raise ValueError("The 8-K index requires one bounded issuer scope.")
    if not isinstance(params["cik"], str) or not re.fullmatch(r"[0-9]{10}", params["cik"]) or int(params["cik"]) == 0:
        raise ValueError("The index requires a canonical ten-digit CIK.")
    if params["form_type"] != "8-K":
        raise ValueError("Only original 8-K index records are authorized.")
    bounds = []
    for name in ("filing_date.gte", "filing_date.lte"):
        value = params[name]
        if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            raise ValueError("Index bounds must be exact calendar dates.")
        date.fromisoformat(value)
        if not source_lower <= value <= upper:
            raise ValueError("Index date crosses the fixed IS fence.")
        bounds.append(value)
    if bounds[0] > bounds[1]:
        raise ValueError("Reversed index bounds.")
    if "limit" in params and (isinstance(params["limit"], bool)
            or not re.fullmatch(r"[0-9]{1,4}", str(params["limit"]))
            or not 1 <= int(params["limit"]) <= 1000):
        raise ValueError("Index page size must be between 1 and 1000.")
    if "sort" in params and params["sort"] != "filing_date.asc":
        raise ValueError("Index enumeration must use ascending filing date.")


def validate_index_rows(rows, params, *, window_role="is"):
    """Reject metadata outside the original page-chain identity before caching."""
    validate_index_parameters(params, window_role=window_role)
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("Index results must be a list of records.")
    for row in rows:
        filing_date = row.get("filing_date")
        if not isinstance(filing_date, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", filing_date):
            raise ValueError("Index record lacks a valid filing date.")
        date.fromisoformat(filing_date)
        if not params["filing_date.gte"] <= filing_date <= params["filing_date.lte"]:
            raise ValueError("Index record crosses the requested interval.")
        if row.get("cik") != params["cik"] or row.get("form_type") != "8-K":
            raise ValueError("Index record changes filer or form.")
        accession = row.get("accession_number")
        if not isinstance(accession, str) or not re.fullmatch(r"(?:[0-9]{18}|[0-9]{10}-[0-9]{2}-[0-9]{6})", accession):
            raise ValueError("Index record lacks a canonical accession.")
        url = row.get("filing_url")
        parsed = urlsplit(url) if isinstance(url, str) else None
        if (parsed is None or parsed.scheme != "https" or parsed.hostname not in {"sec.gov", "www.sec.gov"}
                or parsed.username or parsed.password or parsed.port not in (None, 443)
                or parsed.query or parsed.fragment):
            raise ValueError("Index source must be an official SEC Archives URL.")
        compact = accession.replace("-", "")
        dashed = compact[:10] + "-" + compact[10:12] + "-" + compact[12:]
        prefix = f"/Archives/edgar/data/{int(params['cik'])}/"
        if not (parsed.path == prefix + dashed + ".txt"
                or re.fullmatch(re.escape(prefix + compact + "/") + r"[^/]+\.(?:htm|html|txt)", parsed.path)):
            raise ValueError("Index source URL changes the filer/accession directory.")
    return rows


def unique_parameters(url):
    """Reject ambiguous query values before cache lookup or request I/O."""
    pairs = parse_qsl(urlsplit(url).query, keep_blank_values=True)
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("Duplicate API query parameters are not an auditable scope.")
        result[name] = value
    return result


def root_scope(url):
    parsed = urlsplit(url)
    return {"path": parsed.path,
            "parameters": {key: value for key, value in unique_parameters(url).items()
                           if key not in PAGINATION_NAMES}}


def validate_continuation(url, scope):
    """An opaque cursor may carry the original filters; explicit filters may not change.

    This cannot decode or independently prove the vendor's cursor contents. It
    prevents observable endpoint/filter changes and still validates returned rows
    in the caller's ISFence. Authorization is bound to the original request chain.
    """
    parsed = urlsplit(url)
    params = unique_parameters(url)
    if not isinstance(scope, dict) or parsed.path != scope.get("path"):
        raise ValueError("API continuation changed the original endpoint.")
    initial = scope.get("parameters", {})
    for key, value in params.items():
        if key in PAGINATION_NAMES:
            continue
        if key not in initial or initial[key] != value:
            raise ValueError("API continuation changed or added an explicit request filter.")


def clean_url(url):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "api.massive.com" or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError("Untrusted API continuation host.")
    # Preserve the provider's exact cursor encoding for the original URL-hash cache.
    query = "&".join(part for part in parsed.query.split("&") if unquote_plus(part.partition("=")[0]).lower() not in SECRET_NAMES)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, ""))


def get_key(project):
    key = os.environ.get("MASSIVE_API_KEY", "").strip()
    if not key:
        env_path = Path(project) / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                name, sep, value = line.partition("=")
                if sep and name.strip() == "MASSIVE_API_KEY":
                    key = value.strip().strip('"').strip("'")
                    break
    if not key:
        raise RuntimeError("Set MASSIVE_API_KEY locally; no credential prompt is emitted.")
    return key


def validate_scope(url, continuation=False, warmup_start=START, continuation_root=None, *, window_role="is"):
    first, last, feature_lower, source_lower = study_bounds(window_role)
    if warmup_start not in ((START, "2023-12-01") if window_role == "is" else ("2025-12-01",)):
        raise ValueError("Only the declared December feature warmup is supported.")
    parsed = urlsplit(url)
    params = unique_parameters(url)
    if continuation:
        validate_continuation(url, continuation_root)
    path = parsed.path
    ticker_overview = re.fullmatch(r"/v3/reference/tickers/[A-Z0-9.]+", path)
    allowed = (path in ("/stocks/taxonomies/vX/disclosures", "/stocks/filings/8-K/vX/disclosures", "/stocks/filings/8-K/vX/text", "/v3/reference/options/contracts", INDEX_PATH)
               or bool(ticker_overview)
               or bool(re.fullmatch(r"/v2/aggs/ticker/[^/]+/range/1/day/\d{4}-\d{2}-\d{2}/\d{4}-\d{2}-\d{2}", path)))
    if not allowed:
        raise ValueError("Endpoint is outside this IS reproduction scope.")
    if ticker_overview and (continuation or set(params) != {"date"}):
        raise ValueError("Ticker metadata requires one exact historical IS date and no extra filters.")
    if path == INDEX_PATH:
        validate_index_parameters(continuation_root["parameters"] if continuation else params, window_role=window_role)
    agg = re.search(r"/range/1/day/(\d{4}-\d{2}-\d{2})/(\d{4}-\d{2}-\d{2})$", path)
    if agg and not warmup_start <= agg[1] <= agg[2] <= last:
        raise ValueError("Aggregate request crosses the IS date fence.")
    date_keys = {"filing_date.gte", "filing_date.lte", "filing_date", "as_of", "date"}
    for key in date_keys.intersection(params):
        lower = warmup_start if key == "as_of" else (source_lower if path in (INDEX_PATH, "/stocks/filings/8-K/vX/text") else first)
        try:
            if date.fromisoformat(params[key]).isoformat() != params[key]:
                raise ValueError("Noncanonical date.")
        except (ValueError, TypeError):
            raise ValueError("Exact historical calendar date required.") from None
        if not lower <= params[key] <= last:
            raise ValueError("Request crosses the IS date fence.")
    if "/filings/" in path and not continuation and not ("filing_date" in params or {"filing_date.gte", "filing_date.lte"}.issubset(params)):
        raise ValueError("Filings require explicit bounded IS dates.")
    if path == "/v3/reference/options/contracts" and not continuation and "as_of" not in params:
        raise ValueError("Historical contracts require an IS as-of date.")


class MassiveIS:
    def __init__(self, project, *, offline=False, warmup_start=START):
        self.project = Path(project)
        self.cache = self.project / ".massive_cache"
        self.cache.mkdir(parents=True, exist_ok=True)
        self.offline = offline
        self.window_role = "is"
        self.warmup_start = warmup_start
        self.records = []
        self._key = None
        self._continuations = {}
        self.source_index_chains = []
        self.session = requests.Session()

    def get(self, path_or_url, params=None):
        url = path_or_url if path_or_url.startswith("https://") else BASE + path_or_url
        prepared = requests.Request("GET", clean_url(url), params=params).prepare().url
        url = clean_url(prepared)
        scope = self._continuations.get(url)
        validate_scope(url, scope is not None, self.warmup_start, scope, window_role=self.window_role)
        scope = scope if scope is not None else root_scope(url)
        identity = hashlib.sha1(url.encode()).hexdigest()
        dest = self.cache / (identity + ".json")
        record = {"request_sha1": identity, "path": urlsplit(url).path,
                  "parameters": unique_parameters(url), "cache_hit": dest.exists(),
                  "root_request_scope": scope}
        self.records.append(record)
        if dest.exists():
            payload = json.loads(dest.read_text())
            record["status"] = "CACHE"
        else:
            if self.offline:
                record["status"] = "OFFLINE_CACHE_MISS"
                raise RuntimeError("IS reproduction cache miss; network was disabled.")
            if self._key is None:
                self._key = get_key(self.project)
            payload = None
            for attempt in range(3):
                record["attempts"] = attempt + 1
                try:
                    response = self.session.get(url, headers={"Authorization": "Bearer " + self._key},
                                                timeout=(10, 45), allow_redirects=False)
                    record["http_status"] = response.status_code
                    if response.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                        response.close()
                        time.sleep(2 ** attempt)
                        continue
                    if response.status_code != 200:
                        response.close()
                        raise RuntimeError("API status unavailable.")
                    payload = response.json()
                    response.close()
                    if not isinstance(payload, dict) or payload.get("status", "OK") not in ("OK", "DELAYED"):
                        raise RuntimeError("Unexpected API status/schema.")
                    break
                except Exception:
                    if attempt == 2:
                        record["status"] = "SANITIZED_REQUEST_FAILURE"
                        raise RuntimeError("Scoped API request failed; sensitive response withheld.") from None
                    time.sleep(2 ** attempt)
            record["status"] = "FETCHED"
        if not isinstance(payload, dict) or payload.get("status", "OK") not in ("OK", "DELAYED"):
            raise RuntimeError("Unexpected cached or fetched API status/schema.")
        if re.fullmatch(r"/v3/reference/tickers/[A-Z0-9.]+", scope["path"]):
            result = payload.get("results")
            expected_ticker = scope["path"].rsplit("/", 1)[-1]
            if not isinstance(result, dict) or result.get("ticker") != expected_ticker:
                raise RuntimeError("Ticker metadata response identity differs from the bounded request.")
        if self.window_role == "oos":
            validate_oos_payload_rows(payload, scope)
        if scope["path"] == INDEX_PATH:
            validate_index_rows(payload.get("results"), scope["parameters"], window_role=self.window_role)
        if payload.get("next_url"):
            payload["next_url"] = clean_url(payload["next_url"])
            validate_scope(payload["next_url"], True, self.warmup_start, scope, window_role=self.window_role)
            existing_scope = self._continuations.get(payload["next_url"])
            if existing_scope is not None and existing_scope != scope:
                raise ValueError("API continuation was ambiguously reused by different root requests.")
            self._continuations[payload["next_url"]] = scope
        if record["status"] == "FETCHED":
            dest.write_text(json.dumps(payload, allow_nan=False))
        if scope["path"] == INDEX_PATH:
            record["response_sha256"] = hashlib.sha256(dest.read_bytes()).hexdigest()
        results = payload.get("results")
        record["rows"] = len(results) if isinstance(results, list) else (1 if isinstance(results, dict) else 0)
        record["has_next"] = bool(payload.get("next_url"))
        return payload

    def all(self, path, params=None, max_pages=500):
        record_start = len(getattr(self, "records", ()))
        payload = self.get(path, params)
        values = payload.get("results") or []
        if not isinstance(values, list):
            raise RuntimeError("Expected a paginated list.")
        rows = list(values)
        seen = set()
        pages = 1
        while payload.get("next_url"):
            next_url = payload["next_url"]
            if pages >= max_pages or next_url in seen:
                raise RuntimeError("Pagination incomplete or cyclic; refusing partial coverage.")
            seen.add(next_url)
            payload = self.get(next_url)
            values = payload.get("results") or []
            if not isinstance(values, list):
                raise RuntimeError("Expected a paginated list.")
            rows.extend(values)
            pages += 1
        chain = getattr(self, "records", ())[record_start:]
        if chain and chain[0]["root_request_scope"]["path"] == INDEX_PATH:
            self.source_index_chains.append({
                "root_scope": chain[0]["root_request_scope"],
                "status": "PAGINATION_EXHAUSTED_VALIDATED_SCOPE",
                "pages": [{"request_sha1": r["request_sha1"], "response_sha256": r["response_sha256"],
                           "rows": r["rows"], "has_next": r["has_next"], "cache_hit": r["cache_hit"]} for r in chain],
                "row_count": len(rows),
                "accessions": sorted({row["accession_number"].replace("-", "") for row in rows}),
                "coverage_claim": "Bounded vendor 8-K index only; not all issuer news or first-public IR history.",
            })
        return rows

    def manifest(self):
        first, last, _, source_lower = study_bounds(self.window_role)
        return {"scope": [first, last], "source_history_start": source_lower, "feature_warmup_start": self.warmup_start, "oos_requests": self.window_role == "oos" and bool(self.records), "sealed_requests": False,
                "requests": self.records, "request_count": len(self.records),
                "cache_hits": sum(r["cache_hit"] for r in self.records),
                "credential_values_saved": False, "source_index_chains": self.source_index_chains}


class MassiveSubmission(MassiveIS):
    """Explicit bounded transport for the separately adopted literal-tag variant.

    Construction performs no authentication/request. Every root and continuation
    is validated against its supplied SubmissionFence before I/O/cache writes.
    Contestant one-shot authorization is enforced by the calling root runner.
    """
    def __init__(self, project, *, fence, offline=False):
        from research_runtime import SubmissionFence
        if not isinstance(fence, SubmissionFence):
            raise ValueError("A bounded SubmissionFence is required.")
        super().__init__(project, offline=offline, warmup_start=str(fence.feature_start.date()))
        self.fence = fence
        self.window_role = "submission"
        self.cache = self.project/".massive_cache"/"literal_tag_union_v4"
        self.cache.mkdir(parents=True,exist_ok=True)

    def get(self, path_or_url, params=None):
        url = path_or_url if path_or_url.startswith("https://") else BASE+path_or_url
        url = clean_url(requests.Request("GET",clean_url(url),params=params).prepare().url)
        scope = self._continuations.get(url)
        if scope is not None:
            validate_continuation(url,scope)
        else:
            scope = root_scope(url)
        metadata = self.fence._request(scope["path"],scope["parameters"])
        identity=hashlib.sha1(url.encode()).hexdigest()
        destination=self.cache/(identity+".json")
        legacy=self.project/".massive_cache"/(identity+".json")
        cached=destination if destination.exists() else legacy
        record={"request_sha1":identity,"path":scope["path"],"parameters":scope["parameters"],
                "cache_hit":cached.exists(),"root_request_scope":scope,
                "legacy_immutable_cache_reused":cached == legacy and legacy.exists()}
        self.records.append(record)
        if cached.exists():
            payload=json.loads(cached.read_text())
            record["status"]="CACHE"
        else:
            if self.offline:
                raise RuntimeError("Bounded submission cache miss; network disabled.")
            if self._key is None:
                self._key=get_key(self.project)
            payload=None
            for attempt in range(3):
                try:
                    response=self.session.get(url,headers={"Authorization":"Bearer "+self._key},
                                              timeout=(10,45),allow_redirects=False)
                    record["http_status"]=response.status_code
                    retry=response.status_code in (429,500,502,503,504) and attempt<2
                    if retry:
                        response.close();time.sleep(2**attempt);continue
                    if response.status_code!=200:
                        response.close();raise RuntimeError("Scoped API status unavailable.")
                    payload=response.json();response.close();break
                except Exception:
                    if attempt==2:
                        raise RuntimeError("Scoped API request failed; response and secrets withheld.") from None
                    time.sleep(2**attempt)
            record["status"]="FETCHED"
        if not isinstance(payload,dict) or payload.get("status","OK") not in ("OK","DELAYED"):
            raise RuntimeError("Unexpected API schema/status.")
        self.fence._validate_rows(payload.get("results") or [],metadata)
        payload=dict(payload)
        if payload.get("next_url"):
            next_url=clean_url(payload["next_url"])
            validate_continuation(next_url,scope)
            existing=self._continuations.get(next_url)
            if existing is not None and existing!=scope:
                raise ValueError("Continuation reused under a different root scope.")
            self._continuations[next_url]=scope
            payload["next_url"]=next_url
        if record["status"]=="FETCHED":
            destination.write_text(json.dumps(payload,allow_nan=False))
        record.update(rows=len(payload.get("results") or []),has_next=bool(payload.get("next_url")))
        return payload

    def manifest(self):
        return {"scope":[str(self.fence.start.date()),str(self.fence.end.date())],
                "feature_warmup_start":self.warmup_start,"requests":self.records,
                "request_count":len(self.records),"credential_values_saved":False,
                "variant":"LITERAL_TAG_UNION_POST_IS_V4"}

