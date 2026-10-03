"""Synthetic/offline runtime validation. Spy transports cannot read market data."""
from pathlib import Path
import json
import tempfile
import unittest

import numpy as np
import pandas as pd

from research_runtime import (ISFence, RAW_COLUMNS, ScopeViolation, load_runtime, run_is,
                              run_oos, RunResult, _source)

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "gator-quant-hacks-8k-options-challenge.ipynb"


class SpyTransport:
    def __init__(self):
        self.calls = []
        self.rows = []

    def get(self, path, params=None):
        self.calls.append((path, params))
        return {"results": self.rows.copy()}

    def all(self, path, params=None, max_pages=500):
        self.calls.append((path, params, max_pages))
        return self.rows.copy()


class FenceTests(unittest.TestCase):
    def setUp(self):
        self.spy = SpyTransport()
        self.fence = ISFence("2024-01-01", "2025-12-31", self.spy.get, self.spy.all)

    def test_oos_rejected_before_transport(self):
        with self.assertRaises(ScopeViolation):
            self.fence.get_all("/v2/aggs/ticker/O:AMD260320C00100000/range/1/day/2025-12-01/2026-01-02")
        self.assertEqual(len(self.spy.calls), 0)
        with self.assertRaises(ScopeViolation):
            ISFence("2026-01-01", "2026-08-31", self.spy.get, self.spy.all)

    def test_host_and_credentials_rejected_before_transport(self):
        for path, params in (("https://example.com/v3/reference/options/contracts", {}),
                             ("/stocks/taxonomies/vX/disclosures", {"apiKey": "synthetic-not-a-secret"})):
            with self.assertRaises(ScopeViolation):
                self.fence.get_all(path, params)
        self.assertEqual(len(self.spy.calls), 0)

    def test_unbounded_filings_rejected(self):
        with self.assertRaises(ScopeViolation):
            self.fence.get_all("/stocks/filings/8-K/vX/disclosures", {"tertiary_category": "acquisition_agreement"})
        self.assertEqual(len(self.spy.calls), 0)

    def test_future_expiration_is_historical_metadata(self):
        result = self.fence.get_all("/v3/reference/options/contracts", {"underlying_ticker": "AMD", "as_of": "2025-12-01", "expiration_date.lte": "2026-06-01"})
        self.assertEqual(result, [])
        self.assertEqual(len(self.spy.calls), 1)

    def test_bad_returned_bar_date_fails_closed(self):
        self.spy.rows = [{"t": int(pd.Timestamp("2026-01-02", tz="America/New_York").value // 1_000_000), "c": 5}]
        with self.assertRaises(ScopeViolation):
            self.fence.get_all("/v2/aggs/ticker/O:AMD260320C00100000/range/1/day/2025-12-01/2025-12-31")

    def test_unrecognized_resource_and_api_query_conflict(self):
        with self.assertRaises(ScopeViolation):
            self.fence.get_all("/v2/aggs/ticker/SPY/range/1/day/2024-01-01/2025-12-31")
        with self.assertRaises(ScopeViolation):
            self.fence.get_all("https://api.massive.com/stocks/taxonomies/vX/disclosures?limit=10", {"limit": 11})

    def test_explicit_warmup_option_only_fence(self):
        fence = ISFence("2024-01-01", "2025-12-31", self.spy.get, self.spy.all, warmup_start="2023-12-01")
        fence.get_all("/v2/aggs/ticker/O:TMO240419C00550000/range/1/day/2023-12-25/2024-01-04")
        fence.get_all("/v3/reference/options/contracts", {"underlying_ticker": "TMO", "as_of": "2023-12-29"})
        self.assertEqual(len(self.spy.calls), 2)
        self.assertTrue(all("pre_is_role" in record for record in fence.requests))
        for path, params in (("/stocks/filings/8-K/vX/disclosures", {"tertiary_category": "acquisition_agreement", "filing_date.gte": "2023-12-01", "filing_date.lte": "2024-01-01"}),
                             ("/v2/aggs/ticker/O:TMO240419C00550000/range/1/day/2023-08-01/2024-01-04", None),
                             ("/v2/aggs/ticker/O:TMO240419C00550000/range/1/day/2023-12-25/2026-01-02", None)):
            with self.assertRaises(ScopeViolation):
                fence.get_all(path, params)
        self.assertEqual(len(self.spy.calls), 2)

    def test_warmup_is_opt_in_and_cannot_include_sealed_window(self):
        with self.assertRaises(ScopeViolation):
            self.fence.get_all("/v2/aggs/ticker/O:TMO240419C00550000/range/1/day/2023-12-25/2024-01-04")
        for start in ("2023-08-01", "2024-02-01", "2023-12-01T01:00:00"):
            with self.assertRaises(ScopeViolation):
                ISFence("2024-01-01", "2025-12-31", self.spy.get, self.spy.all, warmup_start=start)
        self.assertEqual(len(self.spy.calls), 0)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.spy = SpyTransport()
        self.runtime = load_runtime(SOURCE, self.spy.get, self.spy.all)

    def test_loader_has_zero_side_effect_calls_and_no_credential_symbols(self):
        self.assertEqual(len(self.spy.calls), 0)
        self.assertTrue(self.runtime.calendar_matches_original_is)
        for name in ("API_KEY", "SESSION", "CACHE_DIR", "load_api_key", "getpass", "requests", "run_study"):
            self.assertNotIn(name, self.runtime.namespace)
        self.assertNotIn("2025-01-09", self.runtime.clock.sessions.strftime("%Y-%m-%d"))

    def test_top_level_output_or_data_code_is_not_executed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "fixture_source.py"
            path.write_text(_source(SOURCE) + "\nraise RuntimeError('top-level output cell executed')\napi_get('/forbidden')\n")
            result = load_runtime(path, self.spy.get, self.spy.all)
            self.assertEqual(result.namespace["COST_HAIRCUT"], .05)
            self.assertEqual(len(self.spy.calls), 0)

    def test_frozen_configuration_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "fixture_source.py"
            path.write_text(_source(SOURCE).replace("COST_HAIRCUT = 0.05", "COST_HAIRCUT = 0.01"))
            with self.assertRaises(ValueError):
                load_runtime(path, self.spy.get, self.spy.all)
            self.assertEqual(len(self.spy.calls), 0)

    def test_option_bar_clipping_and_pre_window_chain_unavailable(self):
        self.runtime.namespace["option_bars"]("O:AMD260320C00100000", pd.Timestamp("2023-12-20"), pd.Timestamp("2026-01-10"))
        self.assertTrue(self.spy.calls[0][0].endswith("/2024-01-01/2025-12-31"))
        self.assertEqual(len(self.runtime.fence.boundary_notes), 1)
        before = len(self.spy.calls)
        chain = self.runtime.namespace["fetch_chain"]("AMD", pd.Timestamp("2023-12-29"), 2, 180)
        self.assertTrue(chain.empty)
        self.assertEqual(len(self.spy.calls), before)

    def test_explicit_warmup_preserves_original_request_identity(self):
        runtime = load_runtime(SOURCE, self.spy.get, self.spy.all, warmup_start="2023-12-01")
        runtime.namespace["option_bars"]("O:TMO240419C00550000", pd.Timestamp("2023-12-25"), pd.Timestamp("2024-04-19"))
        self.assertTrue(self.spy.calls[0][0].endswith("/2023-12-25/2024-04-19"))
        self.assertEqual(runtime.fence.boundary_notes, [])
        self.assertEqual(runtime.namespace["STUDY_START"], "2024-01-01")

    def test_empty_corrected_manifest_is_schema_safe(self):
        result = run_is(self.runtime, event_mode="corrected_is_v2", corrected_rows=[])
        self.assertTrue(result.tables["events"].empty)
        self.assertEqual(len(result.tables["sensitivity"]), 972)
        self.assertEqual(len(result.tables["theta_board"]), 9)
        self.assertTrue(result.tables["sensitivity"].theta.isna().all())
        self.assertTrue(result.portfolio["ledger"].empty)
        self.assertTrue((result.portfolio["daily"].nav == 1_000_000).all())
        self.assertEqual(len(result.portfolio["daily"]), 502)
        self.assertEqual(len(self.spy.calls), 2)  # empty, bounded synthetic disclosure responses only
        encoded = json.dumps(result.to_private_snapshot(), allow_nan=False, default=str)
        self.assertIn("private_clean_process_IS_snapshot", encoded)

    def test_manifest_required_and_oos_function_cannot_be_enabled_by_flag(self):
        with self.assertRaises(ValueError):
            run_is(self.runtime, event_mode="corrected_is_v2")
        self.runtime.namespace["RUN_OOS"] = True
        with self.assertRaises(ScopeViolation):
            run_oos(self.runtime, frozen=True)

    def test_supplied_future_candidate_rejected_before_pricing(self):
        row = {key: None for key in RAW_COLUMNS}
        row.update(filing_date="2026-01-01", source_tag="acquisition_agreement", accession_id="0", ticker_tokens=["AMD"])
        with self.assertRaises(ScopeViolation):
            run_is(self.runtime, event_mode="corrected_is_v2", corrected_rows=[], candidate_events=pd.DataFrame([row]))
        self.assertEqual(len(self.spy.calls), 0)

    def test_general_provider_empty_output_and_public_clock_guard(self):
        from event_pipeline import EVENT_COLUMNS
        result = run_is(self.runtime, event_mode="general_auto_is", event_provider=lambda **kwargs: pd.DataFrame(columns=EVENT_COLUMNS))
        self.assertTrue(result.tables["events"].empty)
        self.assertEqual(result.manifest["event_mode"], "general_auto_is")

    def test_open_at_end_remains_open_and_fenced_exit_is_unavailable(self):
        ns = self.runtime.namespace
        days = pd.to_datetime(["2025-12-29", "2025-12-30", "2025-12-31"])
        def leg(symbol, kind, strike, premium):
            return ns["Leg"](symbol, kind, strike, pd.DataFrame({"open": premium, "close": premium, "volume": 100.}, index=days))
        legs = {"C_K": leg("O:AMD260320C00100000", "call", 100., 5.),
                "P_K": leg("O:AMD260320P00100000", "put", 100., 4.)}
        strikes = {"K": 100.}
        for pct, strike in ((.03, 103.), (.05, 105.), (.1, 110.)):
            legs[f"C_U{pct}"] = leg(f"O:AMD260320C{int(strike*1000):08d}", "call", strike, 2.)
            strikes[f"U{pct}"] = strike
        pe = ns["PricedEvent"]("AMD", days[1], days[0], days[1], days[1], pd.Timestamp("2025-12-30 08:00"),
            "SYNTHETIC", ("acquisition_agreement",), "3-6m", pd.Timestamp("2026-03-20"), pd.Timestamp("2026-03-20"),
            100., strikes, legs, pd.Timestamp("2025-12-31"))
        portfolio = ns["simulate_portfolio"]([pe], "2024-01-01", "2025-12-31", {"AMD": "Information Technology"})
        self.assertEqual(portfolio["ledger"].status.iloc[0], "OPEN_AT_WINDOW_END")
        self.assertTrue(pd.isna(portfolio["ledger"].actual_exit.iloc[0]))
        self.assertLess(portfolio["daily"].cash.iloc[-1], 1_000_000.)
        outcomes = ns["evaluate"]([pe])
        primary = outcomes[(outcomes.entry == "full") & (outcomes.horizon == 21)]
        self.assertTrue(primary.coverage_reason.str.contains("OUTSIDE_OBSERVATION_WINDOW").all())
        self.assertTrue(primary.covered_call_net.isna().all())
        self.assertEqual(len(self.spy.calls), 0)


if __name__ == "__main__":
    unittest.main()
