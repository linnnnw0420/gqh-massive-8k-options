"""Synthetic liquidity/capacity tests. No credentials, network, or market inputs."""
import copy
import unittest
import math
import pandas as pd
from capacity_evidence import pre_entry_volume_evidence, capacity_screen, endpoint_quote_evidence, derive_capacity
from quote_valuation import LEGS


def bar(day, volume):
    timestamp = int(pd.Timestamp(day).tz_localize("America/New_York").value // 1_000_000)
    return {"t": timestamp, "v": volume}


class VolumeTests(unittest.TestCase):
    def setUp(self):
        self.calendar = pd.bdate_range("2024-01-02", periods=25)
        self.entry = self.calendar[20]
        self.record = {"status": "OK", "contract": "C", "entry": str(self.entry.date()),
                       "start": str(self.calendar[0].date()), "exit": str(self.calendar[-1].date()),
                       "rows": [bar(d, 10) for d in self.calendar[:20]]}

    def audit(self):
        return pre_entry_volume_evidence(self.record, self.calendar, self.entry, "C")

    def test_exact_twenty_sessions_and_entry_excluded(self):
        self.record["rows"].append(bar(self.entry, 1_000_000))
        r = self.audit()
        self.assertEqual(r["strict_20session_adv"], 10.)
        self.assertEqual(r["observed_bar_sessions"], 20)
        self.assertEqual(r["lookback_end"], str(self.calendar[19].date()))

    def test_missing_bar_not_asserted_as_zero(self):
        self.record["rows"].pop(0)
        r = self.audit()
        self.assertTrue(math.isnan(r["strict_20session_adv"]))
        self.assertEqual(r["conditional_absent_bar_zero_adv"], 9.5)
        self.assertEqual(r["observed_bar_mean_diagnostic"], 10.)
        self.assertFalse(r["listing_date_verified"])

    def test_explicit_zero_volume_is_observed(self):
        self.record["rows"][0]["v"] = 0
        r = self.audit()
        self.assertEqual(r["strict_20session_adv"], 9.5)
        self.assertEqual(r["observed_positive_volume_sessions"], 19)

    def test_missing_volume_is_not_absent_bar_zero(self):
        self.record["rows"][0]["v"] = None
        r = self.audit()
        self.assertEqual(r["invalid_volume_sessions"], 1)
        self.assertTrue(math.isnan(r["conditional_absent_bar_zero_adv"]))

    def test_unlisted_history_cannot_be_invented(self):
        self.record["rows"] = []
        r = self.audit()
        self.assertTrue(math.isnan(r["strict_20session_adv"]))
        self.assertEqual(r["conditional_absent_bar_zero_adv"], 0.)
        self.assertEqual(r["status"], "PARTIAL_BAR_HISTORY_ZERO_CONVENTION_ONLY")

    def test_duplicate_and_request_identity_fail(self):
        self.record["rows"].append(self.record["rows"][0].copy())
        self.assertEqual(self.audit()["status"], "DUPLICATE_SESSION_BARS")
        self.record["contract"] = "OTHER"
        self.assertEqual(self.audit()["status"], "SOURCE_IDENTITY_MISMATCH")

    def test_full_lookback_request_required(self):
        self.record["start"] = str(self.calendar[1].date())
        self.assertEqual(self.audit()["status"], "UNAVAILABLE_REQUEST_DOES_NOT_COVER_LOOKBACK")


class ScreenTests(unittest.TestCase):
    def test_three_leg_bottleneck_integer_lots(self):
        r = capacity_screen(dict(zip(LEGS, [1000., 300., 150.])), 10_000.)
        self.assertEqual([x["volume_screen_contracts_integer"] for x in r], [0, 1, 3])
        self.assertEqual([x["volume_screen_entry_gross_usd"] for x in r], [0., 10_000., 30_000.])

    def test_missing_adv_fails_not_drop_leg(self):
        r = capacity_screen(dict(zip(LEGS, [1000., math.nan, 150.])), 10_000.)
        self.assertTrue(all(x["volume_screen_contracts_integer"] is None for x in r))

    def test_displayed_units_are_not_assumed(self):
        adv = dict(zip(LEGS, [1000., 300., 150.]))
        r = capacity_screen(adv, 10_000., displayed_size_raw=1)
        self.assertTrue(all(x["combined_volume_display_contracts"] is None for x in r))
        verified = capacity_screen(adv, 10_000., displayed_size_raw=1, displayed_sizes_are_contracts=True)
        self.assertEqual([x["combined_volume_display_contracts"] for x in verified], [0, 1, 1])


class EndpointTests(unittest.TestCase):
    def fixture(self, dates=None):
        dates = dates or ["2024-01-10", "2024-01-11", "2024-01-12"]
        row = {"trade_id": "trade1", "accession_number": "A", "ticker": "FAKE", "contracts": 1,
               "status": "CLOSED", "entry_date": dates[0], "actual_exit": dates[-1], "scheduled_exit": dates[-1],
               "entry_stock_gross": 10_000., "entry_cost": 20., "exit_cost": 30.}
        ledger = pd.DataFrame([row]).to_dict("split")
        pe = {"accession_number": "A", "ticker": "FAKE", "expiry": "2024-02-16", "strikes": {"K": 100.},
              "legs": {"C_K": {"ticker": "CK", "kind": "call", "strike": 100.},
                       "P_K": {"ticker": "PK", "kind": "put", "strike": 100.},
                       "C_U0.05": {"ticker": "CU", "kind": "call", "strike": 105.}}}
        snapshot = {"oos_read": False, "portfolio": {"daily": pd.DataFrame({"nav": [100.] * len(dates)}, index=dates).to_dict("split"),
                                  "ledger": ledger}, "priced_primary": [pe]}
        quotes, metadata = {}, {}
        for day in dates:
            close = int((pd.Timestamp(day).tz_localize("America/New_York") + pd.Timedelta(hours=16)).value)
            for leg, bid, ask, bs, ass in (("C_K", 5., 6., 1, 20), ("P_K", 4., 4.2, 30, 2), ("C_U0.05", 2., 2.2, 40, 3)):
                key = pe["legs"][leg]["ticker"] + "|" + day
                quotes[key] = {"status": "OK", "key": key, "rows": [{"sip_timestamp": close-10_000_000_000,
                    "bid_price": bid, "ask_price": ask, "bid_size": bs, "ask_size": ass}]}
                metadata[key] = {"ticker": pe["legs"][leg]["ticker"], "contract_type": pe["legs"][leg]["kind"],
                    "strike_price": pe["legs"][leg]["strike"], "expiration_date": pe["expiry"],
                    "underlying_ticker": "FAKE", "shares_per_contract": 100}
        inputs = {"quotes": quotes, "metadata": metadata,
                  "actions": [{"kind": "splits", "key": "FAKE", "status": "OK", "rows": []}]}
        return snapshot, inputs

    def make_open(self, snapshot):
        ledger = snapshot['portfolio']['ledger']
        row, cols = ledger['data'][0], ledger['columns']
        row[cols.index('status')] = 'OPEN_AT_WINDOW_END'
        row[cols.index('actual_exit')] = None
        row[cols.index('scheduled_exit')] = '2026-01-05'
        return snapshot

    def test_open_has_entry_only_and_never_looks_up_future_or_final_mark(self):
        snapshot, inputs = self.fixture()
        self.make_open(snapshot)
        class OnlyEntryQuotes(dict):
            def get(self, key, default=None):
                if not key.endswith('|2024-01-10'):
                    raise AssertionError('A scope-end mark or future date is not an executed endpoint.')
                return super().get(key, default)
        inputs['quotes'] = OnlyEntryQuotes(inputs['quotes'])
        rows = endpoint_quote_evidence(snapshot, inputs, 60)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['side'], 'entry')
        self.assertEqual(rows[0]['observed_scope_end'], '2024-01-12')
        self.assertEqual(rows[0]['position_status'], 'OPEN_AT_WINDOW_END')

    def test_open_split_audit_ends_at_observed_scope_without_future_effect(self):
        snapshot, inputs = self.fixture()
        self.make_open(snapshot)
        inputs['actions'][0]['rows'] = [{'execution_date':'2026-01-02'}]
        self.assertEqual(endpoint_quote_evidence(snapshot, inputs, 60)[0]['status'], 'AVAILABLE_INDICATIVE_PARITY_MARK')
        inputs['actions'][0]['rows'] = [{'execution_date':'2024-01-11'}]
        self.assertEqual(endpoint_quote_evidence(snapshot, inputs, 60)[0]['status'], 'UNVERIFIED_OR_CHANGED_DELIVERABLE_DURING_HOLD')

    def test_open_capacity_uses_all_twenty_preentry_sessions_and_no_roundtrip(self):
        calendar = pd.bdate_range('2024-02-01', periods=23)
        dates = [str(day.date()) for day in calendar[20:]]
        snapshot, inputs = self.fixture(dates)
        self.make_open(snapshot)
        snapshot['portfolio']['daily'] = pd.DataFrame({'nav':[100.] * len(calendar)}, index=calendar).to_dict('split')
        records = [{'key':'trade1|'+leg, 'status':'OK', 'contract':contract,
                    'entry':dates[0], 'start':str(calendar[0].date()), 'exit':dates[-1],
                    'rows':[bar(day, 500) for day in calendar[:20]] + [bar(calendar[20], 1_000_000)]}
                   for leg, contract in zip(LEGS, ['CK','PK','CU'])]
        summary, private = derive_capacity(snapshot, inputs, {'records':records})
        self.assertEqual(summary['actual_entered_positions'], 1)
        self.assertEqual(summary['closed_positions'], 0)
        self.assertEqual(summary['open_at_window_end_positions'], 1)
        self.assertEqual(summary['all_twenty_bars_observed_leg_count'], 3)
        self.assertTrue(all(row['strict_20session_adv'] == 500 for row in private['volume_details']))
        self.assertTrue(all(row['positions_expected'] == 1 for row in summary['capacity_screens']))
        for row in summary['quote_endpoint_summaries']:
            self.assertEqual(row['expected_endpoints'], 1)
            self.assertEqual(row['expected_realized_exit_endpoints'], 0)
            self.assertEqual(row['available_endpoints'], 1)
            self.assertEqual(row['fully_covered_roundtrips'], 0)
            self.assertIsNone(row['full_ledger_roundtrip_halfspread_usd'])
            self.assertEqual(row['complete_roundtrip_subset_halfspread_usd'], 0)

    def test_mixed_ledger_counts_only_closed_realized_exits(self):
        snapshot, inputs = self.fixture()
        ledger = snapshot['portfolio']['ledger']
        row, cols = copy.deepcopy(ledger['data'][0]), ledger['columns']
        row[cols.index('trade_id')] = 'open2'
        row[cols.index('status')] = 'OPEN_AT_WINDOW_END'
        row[cols.index('actual_exit')] = None
        row[cols.index('scheduled_exit')] = '2026-01-05'
        ledger['data'].append(row); ledger['index'].append(1)
        summary, _ = derive_capacity(snapshot, inputs, {'records':[]})
        self.assertEqual(summary['actual_entered_positions'], 2)
        self.assertEqual(summary['closed_positions'], 1)
        self.assertEqual(summary['open_at_window_end_positions'], 1)
        for row in summary['quote_endpoint_summaries']:
            self.assertEqual(row['expected_endpoints'], 3)
            self.assertEqual(row['available_endpoints'], 3)
            self.assertEqual(row['fully_covered_roundtrips'], 1)
            self.assertAlmostEqual(row['complete_roundtrip_subset_halfspread_usd'], 140.)
            self.assertIsNone(row['full_ledger_roundtrip_halfspread_usd'])

    def test_contradictory_open_actual_exit_fails_closed(self):
        snapshot, inputs = self.fixture()
        ledger = snapshot['portfolio']['ledger']
        ledger['data'][0][ledger['columns'].index('status')] = 'OPEN_AT_WINDOW_END'
        with self.assertRaises(ValueError):
            derive_capacity(snapshot, inputs, {'records':[]})

    def test_only_endpoints_and_directional_sizes(self):
        snapshot, inputs = self.fixture()
        rows = endpoint_quote_evidence(snapshot, inputs, 60)
        self.assertEqual(len(rows), 2)
        self.assertEqual([r["side"] for r in rows], ["entry", "exit"])
        self.assertEqual([r["directional_display_bottleneck_raw"] for r in rows], [20, 1])
        self.assertAlmostEqual(rows[0]["three_leg_halfspread_usd"], 70.)
        self.assertAlmostEqual(rows[0]["midpoint_premium_haircut_usd"], 58.5)
        self.assertAlmostEqual(rows[0]["halfspread_to_original_haircut"], 3.5)

    def test_stale_leg_is_not_replaced_by_old_valid_quote(self):
        snapshot, inputs = self.fixture()
        inputs["quotes"]["CU|2024-01-10"]["rows"][0]["sip_timestamp"] -= 60_000_000_000
        rows = endpoint_quote_evidence(snapshot, inputs, 60)
        self.assertIn("STALE", rows[0]["status"])
        self.assertTrue(math.isnan(rows[0]["three_leg_halfspread_usd"]))
        sensitivity = endpoint_quote_evidence(snapshot, inputs, 300)
        self.assertEqual(sensitivity[0]["status"], "AVAILABLE_INDICATIVE_PARITY_MARK")

    def test_missing_metadata_or_corporate_action_audit_blocks(self):
        snapshot, inputs = self.fixture()
        inputs["metadata"].pop("CU|2024-01-10")
        self.assertIn("METADATA_UNAVAILABLE", endpoint_quote_evidence(snapshot, inputs, 60)[0]["status"])
        snapshot, inputs = self.fixture()
        inputs["actions"] = []
        self.assertEqual(endpoint_quote_evidence(snapshot, inputs, 60)[0]["status"], "UNVERIFIED_OR_CHANGED_DELIVERABLE_DURING_HOLD")

    def test_standing_state_is_a_distinct_labeled_diagnostic(self):
        snapshot, inputs = self.fixture()
        inputs["quotes"]["CU|2024-01-10"]["rows"][0]["sip_timestamp"] -= 90_000_000_000
        self.assertEqual(endpoint_quote_evidence(snapshot, inputs, 300)[0]["status"], "ASYNCHRONOUS_THREE_LEG_STATE")
        standing = endpoint_quote_evidence(snapshot, inputs, math.inf)[0]
        self.assertEqual(standing["status"], "AVAILABLE_INDICATIVE_PARITY_MARK")
        self.assertEqual(standing["policy_label"], "post-coverage same-session standing-NBBO assumption")


if __name__ == "__main__":
    unittest.main()
