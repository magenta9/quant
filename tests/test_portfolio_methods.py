from __future__ import annotations

import unittest
from unittest.mock import patch
from pathlib import Path


class PortfolioMethodTests(unittest.TestCase):
    def setUp(self) -> None:
        self.asset_slugs = ("us_large_cap", "us_short_treasury", "us_interm_treasury", "us_long_treasury")
        self.expected_returns = {
            "us_large_cap": 0.09,
            "us_short_treasury": 0.035,
            "us_interm_treasury": 0.04,
            "us_long_treasury": 0.045,
        }
        self.covariance_matrix = (
            (0.040, 0.002, 0.006, 0.004),
            (0.002, 0.010, 0.004, 0.003),
            (0.006, 0.004, 0.020, 0.012),
            (0.004, 0.003, 0.012, 0.025),
        )

    def test_registry_exposes_all_mvp_methods_and_valid_contract_outputs(self) -> None:
        from core.contracts import CorrelationMatrix, CovarianceOutput
        from core.portfolio_optimizer import METHOD_REGISTRY, optimize_portfolio

        covariance = CovarianceOutput(
            generated_at="2026-04-09T12:00:00Z",
            asset_slugs=self.asset_slugs,
            covariance_matrix=self.covariance_matrix,
            correlation_matrix=CorrelationMatrix(
                values=(
                    (1.0, 0.1, 0.2121320344, 0.1264911064),
                    (0.1, 1.0, 0.2828427125, 0.1897366596),
                    (0.2121320344, 0.2828427125, 1.0, 0.5366563146),
                    (0.1264911064, 0.1897366596, 0.5366563146, 1.0),
                )
            ),
            lookback_months=60,
            annualization_factor=12,
            shrinkage_method="ledoit_wolf",
            regime_adjustment="none",
        )

        self.assertEqual(
            tuple(METHOD_REGISTRY),
            (
                "equal_weight",
                "inverse_volatility",
                "max_sharpe",
                "global_min_variance",
                "risk_parity",
                "volatility_targeting",
                "black_litterman",
                "robust_mean_variance",
                "mean_downside_risk",
                "maximum_diversification",
                "minimum_correlation",
            ),
        )

        for method in METHOD_REGISTRY:
            proposal = optimize_portfolio(
                method=method,
                covariance_output=covariance,
                expected_returns=self.expected_returns,
                generated_at="2026-04-09T12:00:00Z",
                risk_free_rate=0.02,
            )

            self.assertEqual(proposal.method, method)
            self.assertAlmostEqual(sum(proposal.weights.values()), 1.0, places=8)
            self.assertTrue(all(weight >= 0 for weight in proposal.weights.values()))
            self.assertGreater(proposal.expected_volatility, 0.0)
            self.assertIn("ips_constraints", proposal.metadata)
            self.assertIsNone(proposal.max_drawdown)
            self.assertEqual(proposal.metadata["max_drawdown_available"], False)

        inverse_vol = optimize_portfolio(
            method="inverse_volatility",
            covariance_output=covariance,
            expected_returns=self.expected_returns,
            generated_at="2026-04-09T12:00:00Z",
            risk_free_rate=0.02,
        )
        self.assertGreater(inverse_vol.weights["us_short_treasury"], inverse_vol.weights["us_large_cap"])

        max_sharpe = optimize_portfolio(
            method="max_sharpe",
            covariance_output=covariance,
            expected_returns=self.expected_returns,
            generated_at="2026-04-09T12:00:00Z",
            risk_free_rate=0.02,
        )
        self.assertGreater(max_sharpe.weights["us_large_cap"], max_sharpe.weights["us_short_treasury"])

        risk_parity = optimize_portfolio(
            method="risk_parity",
            covariance_output=covariance,
            expected_returns=self.expected_returns,
            generated_at="2026-04-09T12:00:00Z",
            risk_free_rate=0.02,
        )
        risk_parity_contributions = self._risk_contributions(risk_parity.weights)
        equal_weight_contributions = self._risk_contributions(
            {
                "us_large_cap": 0.25,
                "us_short_treasury": 0.25,
                "us_interm_treasury": 0.25,
                "us_long_treasury": 0.25,
            }
        )
        self.assertLess(
            max(risk_parity_contributions) - min(risk_parity_contributions),
            max(equal_weight_contributions) - min(equal_weight_contributions),
        )
        self.assertAlmostEqual(risk_parity.weights["us_short_treasury"], 0.30, places=8)
        self.assertEqual(risk_parity.metadata["optimizer_status"], "bound_limited")

        volatility_targeting = optimize_portfolio(
            method="volatility_targeting",
            covariance_output=covariance,
            expected_returns=self.expected_returns,
            generated_at="2026-04-09T12:00:00Z",
            risk_free_rate=0.02,
        )
        self.assertIn("target_volatility", volatility_targeting.metadata)
        self.assertLess(
            volatility_targeting.weights["us_large_cap"],
            max_sharpe.weights["us_large_cap"],
        )

        black_litterman = optimize_portfolio(
            method="black_litterman",
            covariance_output=covariance,
            expected_returns=self.expected_returns,
            generated_at="2026-04-09T12:00:00Z",
            risk_free_rate=0.02,
        )
        self.assertIn("posterior_expected_returns", black_litterman.metadata)
        self.assertAlmostEqual(sum(black_litterman.weights.values()), 1.0, places=8)

        minimum_correlation = optimize_portfolio(
            method="minimum_correlation",
            covariance_output=covariance,
            expected_returns=self.expected_returns,
            generated_at="2026-04-09T12:00:00Z",
            risk_free_rate=0.02,
        )
        self.assertIn("average_correlation_by_asset", minimum_correlation.metadata)
        self.assertAlmostEqual(minimum_correlation.weights["us_short_treasury"], 0.30, places=8)
        self.assertGreater(
            minimum_correlation.weights["us_short_treasury"],
            minimum_correlation.weights["us_long_treasury"],
        )

    def test_optimizer_raises_explicit_error_when_method_weights_breach_ips_bounds(self) -> None:
        from core.contracts import CorrelationMatrix, CovarianceOutput
        from core.portfolio_optimizer import optimize_portfolio

        covariance = CovarianceOutput(
            generated_at="2026-04-09T12:00:00Z",
            asset_slugs=("us_large_cap", "gold", "cash"),
            covariance_matrix=((0.040, 0.003, 0.001), (0.003, 0.030, 0.001), (0.001, 0.001, 0.005)),
            correlation_matrix=CorrelationMatrix(values=((1.0, 0.0866025404, 0.0707106781), (0.0866025404, 1.0, 0.0816496581), (0.0707106781, 0.0816496581, 1.0))),
            lookback_months=60,
            annualization_factor=12,
            shrinkage_method="ledoit_wolf",
            regime_adjustment="none",
        )

        with self.assertRaisesRegex(ValueError, "Infeasible IPS bounds"):
            optimize_portfolio(
                method="equal_weight",
                covariance_output=covariance,
                expected_returns={"us_large_cap": 0.09, "gold": 0.05, "cash": 0.03},
                generated_at="2026-04-09T12:00:00Z",
            )

    def test_risk_parity_raises_when_iteration_budget_prevents_convergence(self) -> None:
        from core.contracts import CorrelationMatrix, CovarianceOutput
        from core.portfolio_optimizer import optimize_portfolio

        covariance = CovarianceOutput(
            generated_at="2026-04-09T12:00:00Z",
            asset_slugs=self.asset_slugs,
            covariance_matrix=self.covariance_matrix,
            correlation_matrix=CorrelationMatrix(
                values=(
                    (1.0, 0.1, 0.2121320344, 0.1264911064),
                    (0.1, 1.0, 0.2828427125, 0.1897366596),
                    (0.2121320344, 0.2828427125, 1.0, 0.5366563146),
                    (0.1264911064, 0.1897366596, 0.5366563146, 1.0),
                )
            ),
            lookback_months=60,
            annualization_factor=12,
            shrinkage_method="ledoit_wolf",
            regime_adjustment="none",
        )

        with patch("core.portfolio_optimizer.RISK_PARITY_MAX_ITERATIONS", 0):
            with self.assertRaisesRegex(ValueError, "Risk parity did not converge"):
                optimize_portfolio(
                    method="risk_parity",
                    covariance_output=covariance,
                    expected_returns=self.expected_returns,
                    generated_at="2026-04-09T12:00:00Z",
                    risk_free_rate=0.02,
                )

    def test_skill_contracts_document_shared_constraints_and_outputs(self) -> None:
        for method_name in (
            "equal_weight",
            "inverse_volatility",
            "max_sharpe",
            "global_min_variance",
            "risk_parity",
            "volatility_targeting",
            "black_litterman",
            "robust_mean_variance",
            "mean_downside_risk",
            "maximum_diversification",
            "minimum_correlation",
        ):
            path = Path(f"skills/{method_name}/SKILL.md")
            self.assertTrue(path.exists(), msg=f"missing skill doc for {method_name}")
            text = path.read_text(encoding="utf-8").lower()
            self.assertIn("long-only", text)
            self.assertIn("sum to 1", text)
            self.assertIn("portfolioproposaloutput", text)
            self.assertIn(method_name, text)

    def _risk_contributions(self, weights: dict[str, float]) -> list[float]:
        weight_vector = [weights[asset_slug] for asset_slug in self.asset_slugs]
        contributions: list[float] = []
        for row_index, asset_slug in enumerate(self.asset_slugs):
            marginal = sum(
                self.covariance_matrix[row_index][column_index] * weight_vector[column_index]
                for column_index in range(len(self.asset_slugs))
            )
            contributions.append(weights[asset_slug] * marginal)
        return contributions


if __name__ == "__main__":
    unittest.main()
