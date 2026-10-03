import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from safe_transport import MassiveIS, clean_url, validate_scope


class SafetyTests(unittest.TestCase):
    def test_secret_free_continuation(self):
        result = clean_url("https://api.massive.com/v3/reference/options/contracts?cursor=abc&apiKey=EXAMPLE_NOT_A_KEY")
        self.assertEqual(result, "https://api.massive.com/v3/reference/options/contracts?cursor=abc")

    def test_host_redirect_and_credentials_rejected(self):
        for url in ("http://api.massive.com/x", "https://evil.test/x", "https://user@api.massive.com/x", "https://api.massive.com:444/x"):
            with self.assertRaises(ValueError):
                clean_url(url)

    def test_oos_and_unbounded_rejected(self):
        for path in ("/v2/aggs/ticker/O:X/range/1/day/2025-12-01/2026-01-01", "/stocks/filings/8-K/vX/disclosures?filing_date.gte=2024-01-01", "/v3/reference/options/contracts?as_of=2026-02-01", "/v3/reference/options/contracts"):
            with self.assertRaises(ValueError):
                validate_scope("https://api.massive.com" + path)

    def test_expiry_metadata_may_extend_but_asof_must_be_is(self):
        validate_scope("https://api.massive.com/v3/reference/options/contracts?as_of=2025-12-05&expiration_date.lte=2026-05-05")

    def test_opt_in_warmup_never_expands_filings_or_sealed_history(self):
        validate_scope("https://api.massive.com/v2/aggs/ticker/O:X/range/1/day/2023-12-25/2024-01-04", warmup_start="2023-12-01")
        for path in ("/stocks/filings/8-K/vX/disclosures?filing_date.gte=2023-12-01&filing_date.lte=2024-01-05", "/v2/aggs/ticker/O:X/range/1/day/2023-08-01/2024-01-04"):
            with self.assertRaises(ValueError):
                validate_scope("https://api.massive.com" + path, warmup_start="2023-12-01")

    def test_offline_cache_never_authenticates(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = MassiveIS(tmp, offline=True)
            url = "https://api.massive.com/stocks/taxonomies/vX/disclosures?limit=1000"
            (client.cache / (hashlib.sha1(url.encode()).hexdigest() + ".json")).write_text(json.dumps({"results": [{"x": 1}]}))
            self.assertEqual(client.all("/stocks/taxonomies/vX/disclosures", {"limit": 1000}), [{"x": 1}])
            self.assertIsNone(client._key)
            with self.assertRaises(RuntimeError):
                client.all("/stocks/taxonomies/vX/disclosures", {"limit": 500})

    def test_pagination_rejects_cap_without_silently_truncating(self):
        client = MassiveIS.__new__(MassiveIS)
        client.get = lambda *args: {"results": [1], "next_url": "https://api.massive.com/stocks/taxonomies/vX/disclosures?cursor=2"}
        with self.assertRaises(RuntimeError):
            client.all("unused", max_pages=1)


if __name__ == "__main__":
    unittest.main()
