"""Synthetic-only V3 causality tests; never authenticate or fetch observations."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import unittest

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from causal_portfolio import simulate_causal_portfolio
from research_runtime import load_runtime


def forbidden_transport(*args, **kwargs):
    raise AssertionError("Synthetic tests may not access any transport.")


@dataclass
class SyntheticLeg:
    ticker: str
    bars: pd.DataFrame
    clock: object
    end: pd.Timestamp
    calls: list

    def mark(self, day):
        day = pd.Timestamp(day)
        if day > self.end:
            raise AssertionError("A mark after the synthetic observation fence was read.")
        self.calls.append(day)
        available = self.bars.loc[:day]
        if available.empty or self.clock.sessions_between(available.index[-1], day) > 3:
            return np.nan
        return available.close.iloc[-1]


@dataclass
class SyntheticEvent:
    ticker: str
    accession_number: str
    entry_day: pd.Timestamp
    t_0: pd.Timestamp
    t_pre: pd.Timestamp
    accepted_at: pd.Timestamp
    expiry_session: pd.Timestamp
    legs: dict
    bucket: str = "3-6m"
    source_tags: tuple = ("acquisition_agreement",)

    def synthetic_spot(self, day, marks):
        return 100.0 + marks["C_K"] - marks["P_K"]


class CausalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runtime = load_runtime(Path(__file__).resolve().parent.parent / "strategy_defs.py",
                                   forbidden_transport, forbidden_transport)
        cls.clock = cls.runtime.clock
        cls.namespace = cls.runtime.namespace

    def event(self, ticker="AA", entry="2024-01-02", end="2024-02-09", *, spot=100,
              changes=None, last_bar=None, accession=None, missing_key=None):
        entry, end = pd.Timestamp(entry), pd.Timestamp(end)
        previous = self.clock.session_before(entry)
        days = self.clock.sessions[(self.clock.sessions >= previous) & (self.clock.sessions <= end)]
        if last_bar is not None:
            days = days[days <= pd.Timestamp(last_bar)]
        prices = pd.Series(float(spot), index=days)
        for date, value in (changes or {}).items():
            prices.loc[pd.Timestamp(date)] = value
        prices = prices.sort_index()
        parts = {"C_K": np.maximum(prices-100, 0)+10,
                 "P_K": np.maximum(100-prices, 0)+10,
                 "C_U0.05": pd.Series(10.0, index=prices.index)}
        legs = {key: SyntheticLeg("SYNTHETIC:"+ticker+":"+key,
                    pd.DataFrame({"close": values, "volume": 1000.0}), self.clock, end, [])
                for key, values in parts.items() if key != missing_key}
        return SyntheticEvent(ticker, accession or ticker+str(entry.date()), entry, entry,
            previous, entry+pd.Timedelta(hours=8), self.clock.sessions[self.clock.sessions.get_loc(entry)+84], legs)

    def run_portfolio(self, events, start="2024-01-02", end="2024-02-09", sectors=None):
        return simulate_causal_portfolio(events, start, end,
            sectors or {event.ticker: event.ticker+"_industry" for event in events},
            namespace=self.namespace, clock=self.clock)

    def test_today_price_never_changes_committed_quantity_and_budget_breach_is_retained(self):
        normal = self.run_portfolio([self.event()])
        shock = self.run_portfolio([self.event(changes={"2024-01-02": 20000})])
        assert_frame_equal(normal["order_decisions"], shock["order_decisions"])
        self.assertEqual(shock["ledger"].iloc[0].contracts, 1)
        self.assertEqual(shock["ledger"].iloc[0].status, "CLOSED")
        self.assertLess(shock["daily"].iloc[0].cash, 0)
        self.assertIn("cash", set(shock["exposure_breaches"].limit))
        self.assertIn("name", set(shock["exposure_breaches"].limit))

    def test_today_existing_book_gap_does_not_cancel_new_order(self):
        # Jan 10 cutoff is three sessions after Jan 5; Jan 11 age is four.
        prior_only = self.event("AA", last_bar="2024-01-05")
        today_fresh = self.event("AA", last_bar="2024-01-05")
        for key in today_fresh.legs:
            today_fresh.legs[key].bars.loc[pd.Timestamp("2024-01-11")] = [10.0, 1000.0]
        candidate = self.event("BB", entry="2024-01-11")
        missing = self.run_portfolio([prior_only, candidate])
        known = self.run_portfolio([today_fresh, self.event("BB", entry="2024-01-11")])
        decision_missing = missing["order_decisions"].query("ticker == 'BB'").reset_index(drop=True)
        decision_known = known["order_decisions"].query("ticker == 'BB'").reset_index(drop=True)
        assert_frame_equal(decision_missing, decision_known)
        self.assertEqual(decision_missing.iloc[0].committed_contracts, 1)
        self.assertTrue(np.isnan(missing["daily"].loc["2024-01-11", "nav"]))
        self.assertTrue(np.isfinite(known["daily"].loc["2024-01-11", "nav"]))

    def test_today_exit_proceeds_do_not_fund_entry(self):
        positions = [self.event("A"+str(i), spot=900) for i in range(10)]
        exit_day = self.clock.sessions[self.clock.sessions.get_loc(pd.Timestamp("2024-01-02"))+21]
        positions.append(self.event("ZZ", entry=str(exit_day.date()), spot=700))
        report = self.run_portfolio(positions)
        decision = report["order_decisions"].query("ticker == 'ZZ'").iloc[0]
        self.assertEqual(decision.reason, "CASH_OR_NAV_LIMIT")
        self.assertAlmostEqual(decision.prior_cash, 68500.0)
        self.assertGreater(decision.estimated_entry_debit, decision.budget_cash_before)
        self.assertGreater(report["daily"].loc[exit_day, "cash"], decision.prior_cash)
        self.assertEqual(report["ledger"].query("ticker == 'ZZ'").iloc[0].contracts, 0)

    def test_today_same_ticker_exit_does_not_enable_recycling(self):
        first = self.event("AA")
        exit_day = self.clock.sessions[self.clock.sessions.get_loc(first.t_0)+21]
        second = self.event("AA", entry=str(exit_day.date()), accession="second")
        report = self.run_portfolio([first, second])
        decision = report["order_decisions"].iloc[1]
        self.assertEqual(decision.reason, "CONCURRENT_SAME_TICKER_PRIOR_OR_COMMITTED")
        self.assertEqual(report["ledger"].iloc[0].status, "CLOSED")
        self.assertEqual(report["ledger"].iloc[1].contracts, 0)

    def test_unknown_prior_book_blocks_new_order(self):
        report = self.run_portfolio([self.event("AA", last_bar="2024-01-05"),
                                    self.event("BB", entry="2024-01-12")])
        decision = report["order_decisions"].query("ticker == 'BB'").iloc[0]
        self.assertEqual(decision.committed_contracts, 0)
        self.assertEqual(decision.reason, "UNKNOWN_PRIOR_PORTFOLIO_STATE_OR_UNRESOLVED_EXIT")
        self.assertTrue(decision.prior_unknown_reasons)

    def test_unpriced_committed_execution_never_becomes_no_trade_or_known_cash(self):
        entry = pd.Timestamp("2024-01-05")
        old = self.clock.sessions[self.clock.sessions.get_loc(entry)-4]
        event = self.event("AA", entry=str(entry.date()))
        for leg in event.legs.values():
            # Prior cutoff age=3; committed entry age=4. Future exit is priceable.
            keep = leg.bars.index >= pd.Timestamp("2024-01-08")
            leg.bars = leg.bars.loc[keep]
            leg.bars.loc[old] = [10.0, 1000.0]
            leg.bars = leg.bars.sort_index()
        later = self.event("BB", entry="2024-01-08")
        report = self.run_portfolio([event, later])
        row = report["ledger"].query("ticker == 'AA'").iloc[0]
        self.assertEqual(row.contracts, 1)
        self.assertEqual(row.status, "CLOSED_WITH_UNPRICED_ENTRY")
        self.assertEqual(row.entry_execution_status, "UNPRICED_COMMITTED_ORDER")
        self.assertTrue(np.isnan(row.entry_cash_debit))
        self.assertTrue(np.isfinite(row.exit_cash_credit))
        self.assertTrue(np.isnan(row.net_pnl))
        self.assertTrue(report["daily"].loc[entry:, "cash"].isna().all())
        self.assertTrue(report["daily"].loc[entry:, "nav"].isna().all())
        self.assertTrue(np.isnan(report["metrics"]["total_net_return"]))
        self.assertEqual(report["ledger"].query("ticker == 'BB'").iloc[0].contracts, 0)
        self.assertTrue(np.isnan(report["daily"].loc[entry, "paid_premium_haircuts"]))
        self.assertTrue(np.isnan(report["daily"].loc[row.actual_exit, "paid_premium_haircuts"]))
        self.assertEqual(report["capacity_scenarios"].iloc[0].executed_trades, 0)
        self.assertEqual(report["capacity_scenarios"].iloc[0].unpriced_committed_trades, 1)

    def test_same_day_reservations_are_deterministic_and_actual_fills_do_not_feed_back(self):
        a, b = self.event("AA"), self.event("ZZ")
        normal = self.run_portfolio([b, a])
        shock = self.run_portfolio([self.event("ZZ"), self.event("AA", changes={"2024-01-02": 20000})])
        assert_frame_equal(normal["order_decisions"], shock["order_decisions"])
        decisions = shock["order_decisions"]
        self.assertEqual(list(decisions.ticker), ["AA", "ZZ"])
        self.assertEqual(list(decisions.committed_contracts), [1, 1])
        self.assertAlmostEqual(decisions.iloc[1].budget_cash_before,
                               1e6-decisions.iloc[0].estimated_entry_debit)
        self.assertAlmostEqual(decisions.iloc[1].budget_nav_before,
                               1e6-decisions.iloc[0].estimated_entry_cost)

    def test_today_loss_only_pauses_later_admissions(self):
        # Huge entry fee causes drawdown without changing the precommitted order.
        report = self.run_portfolio([self.event("AA", changes={"2024-01-02": 25000}),
                                    self.event("BB", entry="2024-01-03")])
        self.assertEqual(report["ledger"].iloc[0].contracts, 1)
        self.assertTrue(report["daily"].iloc[0].new_entries_paused)
        self.assertEqual(report["order_decisions"].iloc[1].reason, "PRIOR_DRAWDOWN_PAUSE")

    def test_missing_fixed_exit_is_not_filtered_in_advance_and_never_moved_later(self):
        event = self.event("AA")
        exit_day = self.clock.sessions[self.clock.sessions.get_loc(event.t_0)+21]
        last = self.clock.sessions[self.clock.sessions.get_loc(exit_day)-4]
        for leg in event.legs.values():
            leg.bars = leg.bars.loc[(leg.bars.index <= last) | (leg.bars.index > exit_day)]
        report = self.run_portfolio([event, self.event("BB", entry=str(self.clock.next_session(exit_day).date()))])
        row = report["ledger"].iloc[0]
        self.assertEqual(row.contracts, 1)
        self.assertEqual(row.status, "UNRESOLVED_EXIT")
        self.assertTrue(pd.isna(row.actual_exit))
        self.assertTrue(np.isnan(row.exit_cash_credit))
        self.assertEqual(report["ledger"].iloc[1].contracts, 0)
        self.assertTrue(report["daily"].loc[exit_day:, "cash"].isna().all())

    def test_end_window_open_is_not_liquidated_and_no_post_window_mark_is_read(self):
        event = self.event("AA", entry="2025-12-30", end="2025-12-31")
        report = self.run_portfolio([event], start="2025-12-29", end="2025-12-31")
        row = report["ledger"].iloc[0]
        self.assertEqual(row.status, "OPEN_AT_WINDOW_END")
        self.assertGreater(row.scheduled_exit, pd.Timestamp("2025-12-31"))
        self.assertTrue(pd.isna(row.actual_exit))
        for leg in event.legs.values():
            self.assertLessEqual(max(leg.calls), pd.Timestamp("2025-12-31"))

    def test_public_clock_and_is_fences_fail_closed(self):
        event = self.event()
        event.accepted_at = event.entry_day+pd.Timedelta(hours=10)
        with self.assertRaisesRegex(ValueError, "signal public"):
            self.run_portfolio([event])
        with self.assertRaisesRegex(ValueError, "2024-2025"):
            self.run_portfolio([], end="2026-01-02")
        with self.assertRaisesRegex(ValueError, "frozen"):
            simulate_causal_portfolio([], "2024-01-02", "2024-01-05", {}, namespace=self.namespace,
                                      clock=self.clock, haircut=.10)

    def test_first_day_initial_state_and_recorded_timestamps(self):
        report = self.run_portfolio([self.event()])
        decision = report["order_decisions"].iloc[0]
        self.assertEqual(decision.prior_cash, 1e6)
        self.assertEqual(decision.prior_nav, 1e6)
        self.assertEqual(decision.prior_open_trade_ids, ())
        self.assertEqual(decision.financial_input_cutoff,
                         pd.Timestamp("2023-12-29 16:00", tz="America/New_York"))
        self.assertEqual(decision.decision_at,
                         pd.Timestamp("2024-01-02 09:30", tz="America/New_York"))
        self.assertLessEqual(decision.signal_public_at, decision.decision_at)
        self.assertEqual(len(report["daily"]), len(self.clock.sessions[(self.clock.sessions >= "2024-01-02") & (self.clock.sessions <= "2024-02-09")]))


if __name__ == "__main__":
    unittest.main()
