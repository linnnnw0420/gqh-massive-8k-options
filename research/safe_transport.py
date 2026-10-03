"""Auditable IS-only Massive transport; credentials never enter cached URLs/logs."""
from __future__ import annotations

import hashlib
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


def validate_scope(url, continuation=False, warmup_start=START, continuation_root=None):
    if warmup_start not in (START, "2023-12-01"):
        raise ValueError("Only the declared December feature warmup is supported.")
    parsed = urlsplit(url)
    params = unique_parameters(url)
    if continuation:
        validate_continuation(url, continuation_root)
    path = parsed.path
    allowed = (path in ("/stocks/taxonomies/vX/disclosures", "/stocks/filings/8-K/vX/disclosures", "/stocks/filings/8-K/vX/text", "/v3/reference/options/contracts")
               or bool(re.fullmatch(r"/v2/aggs/ticker/[^/]+/range/1/day/\d{4}-\d{2}-\d{2}/\d{4}-\d{2}-\d{2}", path)))
    if not allowed:
        raise ValueError("Endpoint is outside this IS reproduction scope.")
    agg = re.search(r"/range/1/day/(\d{4}-\d{2}-\d{2})/(\d{4}-\d{2}-\d{2})$", path)
    if agg and not warmup_start <= agg[1] <= agg[2] <= END:
        raise ValueError("Aggregate request crosses the IS date fence.")
    date_keys = {"filing_date.gte", "filing_date.lte", "filing_date", "as_of"}
    for key in date_keys.intersection(params):
        lower = warmup_start if key == "as_of" else START
        if not lower <= params[key] <= END:
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
        self.warmup_start = warmup_start
        self.records = []
        self._key = None
        self._continuations = {}
        self.session = requests.Session()

    def get(self, path_or_url, params=None):
        url = path_or_url if path_or_url.startswith("https://") else BASE + path_or_url
        prepared = requests.Request("GET", clean_url(url), params=params).prepare().url
        url = clean_url(prepared)
        scope = self._continuations.get(url)
        validate_scope(url, scope is not None, self.warmup_start, scope)
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
        if payload.get("next_url"):
            payload["next_url"] = clean_url(payload["next_url"])
            validate_scope(payload["next_url"], True, self.warmup_start, scope)
            existing_scope = self._continuations.get(payload["next_url"])
            if existing_scope is not None and existing_scope != scope:
                raise ValueError("API continuation was ambiguously reused by different root requests.")
            self._continuations[payload["next_url"]] = scope
        if record["status"] == "FETCHED":
            dest.write_text(json.dumps(payload, allow_nan=False))
        record["rows"] = len(payload.get("results") or [])
        record["has_next"] = bool(payload.get("next_url"))
        return payload

    def all(self, path, params=None, max_pages=500):
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
        return rows

    def manifest(self):
        return {"scope": [START, END], "feature_warmup_start": self.warmup_start, "oos_requests": False, "sealed_requests": False,
                "requests": self.records, "request_count": len(self.records),
                "cache_hits": sum(r["cache_hit"] for r in self.records),
                "credential_values_saved": False}
