"""Synthetic correctness checks; no real market data, API, or notebook execution."""
import unittest
import numpy as np
import pandas as pd
from risk_evidence import (calendar_evidence, factor_evidence, european_call_put,
                           synthetic_covered_call_stress, dependence_evidence, stress_entry_coverage)


class CalendarEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.dates = pd.bdate_range("2024-01-01", "2024-02-29")
        self.frame = pd.DataFrame({"nav": 100., "traded_stock_gross": 1.,
            "traded_option_premium_gross": 2., "traded_option_underlying_gross": 3.}, index=self.dates)

    def test_idle_cash_days_and_complete_statistics(self):
        report = calendar_evidence(self.frame, self.dates, 100.)
        self.assertEqual(report["total_net_return"], 0.)
        self.assertEqual(report["annualized_volatility"], 0.)
        self.assertTrue(np.isnan(report["sharpe_rf0"]))
        self.assertTrue(np.isnan(report["daily_return_skew_unbiased"]))
        self.assertEqual(report["worst_month_return"], 0.)
        self.assertAlmostEqual(report["turnover"]["traded_stock_gross"]["two_sided_over_mean_nav"], len(self.dates) / 100)

    def test_missing_row_is_not_silently_deleted(self):
        frame = self.frame.drop(self.dates[5])
        report = calendar_evidence(frame, self.dates, 100.)
        self.assertEqual(report["calendar_rows_absent"], 1)
        self.assertEqual(report["nav_gaps"], 1)
        self.assertEqual(report["daily_returns"].isna().sum(), 2)
        self.assertTrue(np.isnan(report["worst_month_return"]))
        self.assertTrue(np.isnan(report["daily_return_skew_unbiased"]))
        self.assertEqual(report["total_net_return"], 0.)

    def test_missing_month_boundary_disables_following_month(self):
        frame = self.frame.copy()
        frame.loc["2024-01-31", "nav"] = np.nan
        report = calendar_evidence(frame, self.dates, 100.)
        self.assertEqual(report["monthly"]["return"].isna().sum(), 2)

    def test_negative_nav_and_duplicate_dates_fail(self):
        frame = self.frame.copy()
        frame.iloc[2, 0] = -1
        report = calendar_evidence(frame, self.dates, 100.)
        self.assertFalse(report["complete_calendar_nav"])
        with self.assertRaises(ValueError):
            calendar_evidence(pd.concat([frame, frame.iloc[[0]]]), self.dates, 100.)

    def test_path_has_exact_skew_and_drawdown(self):
        returns = np.resize(np.array([.01, -.02, .005, 0.]), len(self.dates))
        self.frame.nav = 100 * np.cumprod(1 + returns)
        report = calendar_evidence(self.frame, self.dates, 100.)
        self.assertAlmostEqual(report["daily_return_skew_unbiased"], pd.Series(returns).skew())
        self.assertGreater(report["maximum_drawdown"], 0.)
        self.assertAlmostEqual(report["annualized_volatility"], returns.std(ddof=1) * np.sqrt(252))


class FactorTests(unittest.TestCase):
    def setUp(self):
        self.dates = pd.bdate_range("2024-01-01", periods=200)
        rng = np.random.default_rng(42)
        self.factors = pd.DataFrame(rng.normal(0, .01, (200, 3)), index=self.dates, columns=["Mkt-RF", "HML", "Mom"])
        self.factors["RF"] = .0001
        self.returns = .0002 + self.factors["RF"] + self.factors[["Mkt-RF", "HML", "Mom"]].to_numpy() @ np.array([.5, -.2, .1])

    def test_known_coefficients(self):
        report = factor_evidence(self.returns, self.factors, self.dates)
        np.testing.assert_allclose(report["coefficients"].estimate, [.0002, .5, -.2, .1], atol=1e-12)
        self.assertAlmostEqual(report["r_squared"], 1.)

    def test_incomplete_returns_and_factors_fail_closed(self):
        missing = self.returns.copy()
        missing.iloc[2] = np.nan
        self.assertEqual(factor_evidence(missing, self.factors, self.dates)["status"], "UNAVAILABLE_INCOMPLETE_PATH")
        self.assertEqual(factor_evidence(self.returns, self.factors.iloc[1:], self.dates)["status"], "UNAVAILABLE_INCOMPLETE_PATH")

    def test_rank_deficiency(self):
        self.factors["Mom"] = self.factors["HML"]
        self.assertEqual(factor_evidence(self.returns, self.factors, self.dates)["status"], "UNAVAILABLE_RANK_DEFICIENT_FACTORS")


class StressTests(unittest.TestCase):
    def test_open_positions_remain_in_entry_stress_and_unknown_execution_is_counted(self):
        def row(status,known=True):
            return {'contracts':1,'status':status,'entry_stock_gross':10000. if known else None,
                    'entry_option_premiums':{'C_K':500.,'P_K':400.,'C_U0.05':200.} if known else None}
        rows=[row('CLOSED'),row('OPEN_AT_WINDOW_END'),row('UNRESOLVED_EXIT'),
              row('UNPRICED_EXECUTION',False),row('CLOSED_WITH_UNPRICED_ENTRY',False),
              {'contracts':0,'status':'SKIPPED'}]
        selected,coverage=stress_entry_coverage(pd.DataFrame(rows))
        self.assertEqual([item['status'] for item in selected],['CLOSED','OPEN_AT_WINDOW_END','UNRESOLVED_EXIT'])
        self.assertEqual(coverage['admitted_or_committed_positions'],5)
        self.assertEqual(coverage['positions_with_known_entry_stress'],3)
        self.assertEqual(coverage['positions_omitted'],2)
        self.assertEqual(coverage['omission_reasons'],{'UNAVAILABLE_ENTRY_MARKS':2})

    def test_put_call_parity(self):
        c, p, _, _ = european_call_put(100, 100, .5, .04, .3)
        self.assertAlmostEqual(100 * np.exp(-.04 * .5) + c - p, 100.)

    def test_default_loss_exceeds_entry_debit_and_upside_cost_unbounded(self):
        marks = {"C_K": 5., "P_K": 5., "C_U": 2.}
        scenarios = [{"name": "zero", "spot": 0., "years_remaining": 0., "volatility": .3},
                     {"name": "extreme_upside", "spot": 1e9, "years_remaining": 0., "volatility": .3}]
        r = synthetic_covered_call_stress(marks, 100, 105, .25, .04, scenarios)
        self.assertGreater(r["zero_spot_expiry_model_loss"], r["entry_cash_debit"])
        self.assertFalse(r["finite_net_max_loss_exists_under_uncapped_exit_haircut"])
        self.assertEqual(r["net_max_loss"], np.inf)
        self.assertLess(r["scenarios"].net_pnl.iloc[1], -1e8)
        self.assertAlmostEqual(r["scenarios"].net_pnl.iloc[0], -r["zero_spot_expiry_model_loss"])

    def test_no_cost_maximum_loss_and_gross_payoff_cap(self):
        r = synthetic_covered_call_stress({"C_K": 5., "P_K": 5., "C_U": 2.}, 100, 105, .25, .04,
            [{"name": "up", "spot": 1000., "years_remaining": 0., "volatility": .3}], haircut=0)
        self.assertTrue(r["finite_net_max_loss_exists_under_uncapped_exit_haircut"])
        self.assertAlmostEqual(r["scenarios"].gross_exit_value.iloc[0], 10500.)


class DependenceTests(unittest.TestCase):
    def fixture(self):
        events = pd.DataFrame({"ticker": ["A", "B", "C"], "incremental_net": [.01, .02, .03],
            "entry_day": ["2024-01-01", "2024-02-01", "2024-03-01"],
            "exit_day": ["2024-01-05", "2024-02-05", "2024-03-05"]})
        ordinary = events.copy()
        ordinary.incremental_net = 0.
        return events, ordinary

    def test_theta_and_clusters_and_reproducibility(self):
        a, b = self.fixture()
        r = dependence_evidence(a, b, n_boot=500)
        self.assertAlmostEqual(r["theta"], .02)
        self.assertEqual(r["issuer"]["clusters"], 3)
        self.assertEqual(r["overlap_interval"]["clusters"], 3)
        self.assertEqual(r["issuer"]["ci_low"], dependence_evidence(a, b, n_boot=500)["issuer"]["ci_low"])

    def test_transitive_overlap_no_fake_independence(self):
        a, b = self.fixture()
        a["exit_day"] = "2024-04-01"
        r = dependence_evidence(a, b, n_boot=100)
        self.assertEqual(r["overlap_interval"]["clusters"], 1)
        self.assertTrue(np.isnan(r["overlap_interval"]["ci_low"]))

    def test_missing_values_counted_and_clock_fails_closed(self):
        a, b = self.fixture()
        a.loc[0, "incremental_net"] = np.nan
        b.loc[1, "exit_day"] = None
        r = dependence_evidence(a, b, n_boot=100)
        self.assertEqual(r["coverage"]["event"]["finite_rows"], 2)
        self.assertEqual(r["overlap_interval"]["status"], "UNAVAILABLE_INVALID_HOLDING_INTERVALS")


if __name__ == "__main__":
    unittest.main()
