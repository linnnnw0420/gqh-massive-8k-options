"""Independent fail-closed regression cases. Synthetic cache only; no API or study."""
import ast
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from safe_transport import MassiveIS, validate_scope

HERE = Path(__file__).resolve().parent


def cache_payload(client, url, payload):
    path = client.cache / (hashlib.sha1(url.encode()).hexdigest() + ".json")
    path.write_text(json.dumps(payload), encoding="utf-8")


class PaginationFenceRegressionTests(unittest.TestCase):
    def test_same_endpoint_cursor_only_continuation_inherits_root(self):
        with tempfile.TemporaryDirectory() as folder:
            client = MassiveIS(folder, offline=True)
            initial = "https://api.massive.com/v3/reference/options/contracts?underlying_ticker=AMD&as_of=2025-12-01&limit=1000"
            continuation = "https://api.massive.com/v3/reference/options/contracts?cursor=synthetic_cursor%2Bexact"
            cache_payload(client, initial, {"results": [{"synthetic": 1}], "next_url": continuation})
            cache_payload(client, continuation, {"results": [{"synthetic": 2}]})
            self.assertEqual(client.all(initial), [{"synthetic": 1}, {"synthetic": 2}])
            self.assertEqual(client.records[1]["root_request_scope"], client.records[0]["root_request_scope"])
            self.assertIsNone(client._key)

    def test_same_endpoint_matching_explicit_filters_allowed(self):
        with tempfile.TemporaryDirectory() as folder:
            client = MassiveIS(folder, offline=True)
            initial = "https://api.massive.com/v3/reference/options/contracts?underlying_ticker=AMD&as_of=2025-12-01"
            continuation = initial + "&cursor=synthetic_cursor"
            cache_payload(client, initial, {"results": [], "next_url": continuation})
            cache_payload(client, continuation, {"results": []})
            self.assertEqual(client.all(initial), [])

    def test_continuation_cannot_switch_to_unbounded_contract_endpoint(self):
        with tempfile.TemporaryDirectory() as folder:
            client = MassiveIS(folder, offline=True)
            initial = "https://api.massive.com/stocks/filings/8-K/vX/disclosures?filing_date.gte=2024-01-01&filing_date.lte=2025-12-31"
            shifted = "https://api.massive.com/v3/reference/options/contracts?cursor=synthetic_cursor"
            cache_payload(client, initial, {"results": [], "next_url": shifted})
            cache_payload(client, shifted, {"results": [{"synthetic": True}]})
            with self.assertRaises((ValueError, RuntimeError)):
                client.all(initial)
            self.assertIsNone(client._key)

    def test_continuation_cannot_reset_initial_issuer_filter(self):
        with tempfile.TemporaryDirectory() as folder:
            client = MassiveIS(folder, offline=True)
            initial = "https://api.massive.com/v3/reference/options/contracts?underlying_ticker=AMD&as_of=2025-12-01"
            shifted = "https://api.massive.com/v3/reference/options/contracts?underlying_ticker=OTHER&as_of=2025-12-01&cursor=synthetic_cursor"
            cache_payload(client, initial, {"results": [], "next_url": shifted})
            cache_payload(client, shifted, {"results": [{"synthetic": True}]})
            with self.assertRaises((ValueError, RuntimeError)):
                client.all(initial)
            self.assertIsNone(client._key)

    def test_duplicate_date_queries_cannot_hide_outside_fence_first_value(self):
        url = "https://api.massive.com/v3/reference/options/contracts?as_of=2026-01-02&as_of=2025-12-01"
        with self.assertRaises(ValueError):
            validate_scope(url)

    def test_continuation_cannot_add_unrecognized_filters(self):
        with tempfile.TemporaryDirectory() as folder:
            client = MassiveIS(folder, offline=True)
            initial = "https://api.massive.com/v3/reference/options/contracts?underlying_ticker=AMD&as_of=2025-12-01"
            shifted = "https://api.massive.com/v3/reference/options/contracts?cursor=synthetic_cursor&as_of.gte=2026-01-01"
            cache_payload(client, initial, {"results": [], "next_url": shifted})
            with self.assertRaises(ValueError):
                client.all(initial)
            self.assertEqual(len(client.records), 1)
            self.assertIsNone(client._key)

    def test_continuation_duplicate_queries_rejected_before_second_lookup(self):
        with tempfile.TemporaryDirectory() as folder:
            client = MassiveIS(folder, offline=True)
            initial = "https://api.massive.com/v3/reference/options/contracts?as_of=2025-12-01"
            shifted = "https://api.massive.com/v3/reference/options/contracts?cursor=synthetic_cursor&as_of=2026-01-02&as_of=2025-12-01"
            cache_payload(client, initial, {"results": [], "next_url": shifted})
            with self.assertRaises(ValueError):
                client.all(initial)
            self.assertEqual(len(client.records), 1)

    def test_feature_warmup_cannot_authorize_earlier_sealed_or_future_dates(self):
        validate_scope("https://api.massive.com/v3/reference/options/contracts?as_of=2023-12-28", warmup_start="2023-12-01")
        validate_scope("https://api.massive.com/v2/aggs/ticker/O:AMD240315C00100000/range/1/day/2023-12-25/2024-01-04", warmup_start="2023-12-01")
        for url in (
            "https://api.massive.com/v3/reference/options/contracts?as_of=2023-08-01",
            "https://api.massive.com/v3/reference/options/contracts?as_of=2026-01-02",
            "https://api.massive.com/stocks/filings/8-K/vX/text?filing_date.gte=2023-12-01&filing_date.lte=2024-01-05",
        ):
            with self.assertRaises(ValueError):
                validate_scope(url, warmup_start="2023-12-01")


class SourceIdentityRegressionTests(unittest.TestCase):
    def test_cli_code_identity_pin_detects_changed_expiry_configuration(self):
        # The supported CLI, rather than the definition loader, pins the exact
        # source AST. This test computes hashes; no source definitions execute.
        from reproduce_is import FROZEN_SOURCE_AST_SHA256, _source
        source = _source(HERE.parent / "gator-quant-hacks-8k-options-challenge.ipynb")
        digest = lambda value: hashlib.sha256(ast.dump(ast.parse(value), include_attributes=False).encode()).hexdigest()
        self.assertEqual(digest(source), FROZEN_SOURCE_AST_SHA256)
        self.assertEqual(digest(_source(HERE.parent / "gator-quant-hacks-8k-options-challenge.ipynb")), FROZEN_SOURCE_AST_SHA256)
        altered = source + "\nEXPIRY_BUCKETS = {**EXPIRY_BUCKETS, '3-6m': (90, 180, 90)}\n"
        self.assertNotEqual(digest(altered), FROZEN_SOURCE_AST_SHA256)

    def test_cli_correction_identity_matches_frozen_file(self):
        from reproduce_is import CORRECTION_SHA256
        self.assertEqual(hashlib.sha256((HERE.parent / "research" / "correction_execution_v2.json").read_bytes()).hexdigest(), CORRECTION_SHA256)


class PrivateOutputRegressionTests(unittest.TestCase):
    def invoke(self, project, output):
        from reproduce_is import main
        with patch("sys.argv", ["reproduce_is.py", "--project", str(project), "--source", "SYNTHETIC_SOURCE.py",
                                "--output-dir", str(output), "--offline"]):
            main()

    def test_public_output_rejected_before_mkdir_source_or_auth(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch("reproduce_is._source", side_effect=AssertionError("No source read before output guard")), \
                 patch("reproduce_is.MassiveIS", side_effect=AssertionError("No auth/transport before output guard")):
                with self.assertRaisesRegex(ValueError, "below project/.massive_cache"):
                    self.invoke(root, "reports/public-run")
            self.assertFalse((root / "reports").exists())

    def test_cache_root_rejected_before_mkdir_source_or_auth(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch("reproduce_is._source", side_effect=AssertionError("No source read before output guard")), \
                 patch("reproduce_is.MassiveIS", side_effect=AssertionError("No auth/transport before output guard")):
                with self.assertRaisesRegex(ValueError, "below project/.massive_cache"):
                    self.invoke(root, root / ".massive_cache")
            self.assertFalse((root / ".massive_cache").exists())

    def test_private_child_accepted_until_deliberately_mocked_source_stop(self):
        # This exercises argument/path handling only. No definition loader,
        # study, private real input or transport is reached.
        class SyntheticStop(Exception):
            pass
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch("reproduce_is._source", side_effect=SyntheticStop("Dry synthetic stop")), \
                 patch("reproduce_is.MassiveIS") as transport:
                with self.assertRaises(SyntheticStop):
                    self.invoke(root, ".massive_cache/research_runs/synthetic")
                transport.assert_not_called()
            self.assertTrue((root / ".massive_cache/research_runs/synthetic").is_dir())


if __name__ == "__main__":
    unittest.main()
