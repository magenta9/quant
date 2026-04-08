from __future__ import annotations

import unittest

import numpy as np


class RiskMetricTests(unittest.TestCase):
    def test_build_risk_report_returns_standardized_contracts(self) -> None:
        from core.risk_metrics import build_risk_report

        weights = {
            "us_large_cap": 0.35,
            "us_interm_treasury": 0.30,
            "us_long_treasury": 0.25,
            "gold": 0.10,
        }
        expected_returns = {
            "us_large_cap": 0.09,
            "us_interm_treasury": 0.04,
            "us_long_treasury": 0.045,
            "gold": 0.05,
        }
        covariance_matrix = (
            (0.040, 0.006, 0.004, 0.003),
            (0.006, 0.020, 0.012, 0.002),
            (0.004, 0.012, 0.025, 0.001),
            (0.003, 0.002, 0.001, 0.030),
        )
        historical_returns = np.array(
            [
                [0.018, 0.006, 0.007, 0.011],
                [-0.012, 0.004, 0.006, -0.003],
                [0.021, 0.005, 0.004, 0.009],
                [0.010, 0.003, 0.002, 0.006],
                [-0.008, 0.004, 0.005, -0.002],
                [0.015, 0.006, 0.004, 0.007],
            ]
        )
        benchmark_weights = {
            "us_large_cap": 0.40,
            "us_interm_treasury": 0.25,
            "us_long_treasury": 0.20,
            "gold": 0.15,
        }
        factor_exposures = {
            "us_large_cap": {"equity_beta": 1.0, "duration": 0.0, "credit_spread": 0.1, "dollar_exposure": 1.0},
            "us_interm_treasury": {"equity_beta": 0.1, "duration": 6.0, "credit_spread": 0.0, "dollar_exposure": 1.0},
            "us_long_treasury": {"equity_beta": 0.05, "duration": 12.0, "credit_spread": 0.0, "dollar_exposure": 1.0},
            "gold": {"equity_beta": 0.0, "duration": 0.0, "credit_spread": 0.0, "dollar_exposure": -0.2},
        }

        report = build_risk_report(
            method="max_sharpe",
            weights=weights,
            expected_returns=expected_returns,
            covariance_matrix=covariance_matrix,
            historical_returns=historical_returns,
            frequency="monthly",
            benchmark_weights=benchmark_weights,
            tracking_error_budget=0.10,
            factor_exposures=factor_exposures,
            risk_free_rate=0.02,
        )

        self.assertEqual(report.method, "max_sharpe")
        self.assertGreater(report.ex_ante.portfolio_return, 0.0)
        self.assertGreater(report.ex_ante.volatility, 0.0)
        self.assertLess(report.ex_ante.var_95, report.ex_ante.portfolio_return)
        self.assertLess(report.backtest.max_drawdown, 0.0)
        self.assertAlmostEqual(report.concentration.max_weight, 0.35, places=12)
        self.assertTrue(report.ips_compliance.passes)
        self.assertAlmostEqual(report.factor_tilts.duration, 4.8, places=12)

    def test_evaluate_ips_compliance_surfaces_tracking_error_and_bounds_violations(self) -> None:
        from core.risk_metrics import evaluate_ips_compliance

        covariance_matrix = (
            (0.040, 0.006, 0.004),
            (0.006, 0.020, 0.012),
            (0.004, 0.012, 0.025),
        )

        diagnostic = evaluate_ips_compliance(
            weights={"us_large_cap": 0.55, "us_interm_treasury": 0.35, "gold": 0.10},
            covariance_matrix=covariance_matrix,
            asset_slugs=("us_large_cap", "us_interm_treasury", "gold"),
            benchmark_weights={"us_large_cap": 0.35, "us_interm_treasury": 0.55, "gold": 0.10},
            tracking_error_budget=0.04,
        )

        self.assertFalse(diagnostic.asset_bounds_ok)
        self.assertFalse(diagnostic.within_tracking_budget)
        self.assertFalse(diagnostic.passes)
        self.assertIn("us_large_cap exceeds max weight", diagnostic.violations[0])

    def test_calculate_concentration_metrics_matches_herfindahl_and_effective_n(self) -> None:
        from core.risk_metrics import calculate_concentration_metrics

        metrics = calculate_concentration_metrics(
            {"us_large_cap": 0.5, "us_interm_treasury": 0.3, "gold": 0.2}
        )

        self.assertAlmostEqual(metrics.herfindahl, 0.38, places=12)
        self.assertAlmostEqual(metrics.effective_n, 1 / 0.38, places=12)
        self.assertAlmostEqual(metrics.top5_concentration, 1.0, places=12)
        self.assertAlmostEqual(metrics.max_weight, 0.5, places=12)


if __name__ == "__main__":
    unittest.main()
