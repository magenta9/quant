import unittest

from core.contracts import (
    AssetCMAOutput,
    CMAMethodEstimate,
    CIOBoardMemoOutput,
    CorrelationMatrix,
    CovarianceOutput,
    CROBacktestMetrics,
    CROConcentrationMetrics,
    CROExAnteMetrics,
    CROFactorTilts,
    CROIPSDiagnostic,
    CRORiskReportOutput,
    IndicatorSnapshot,
    MacroScores,
    MacroView,
    PortfolioProposalOutput,
    TopPosition,
)


class ContractTests(unittest.TestCase):
    def test_macro_view_serializes_expected_shape(self) -> None:
        macro_view = MacroView(
            timestamp="2026-04-09T12:00:00Z",
            regime="late_cycle",
            confidence="medium",
            scores=MacroScores(growth=1, inflation=0, monetary_policy=1, financial_conditions=0),
            composite_score=0.7,
            recession_probability=0.3,
            key_indicators=IndicatorSnapshot(
                gdp_growth_yoy=2.1,
                cpi_yoy=2.8,
                fed_funds_rate=4.5,
                vix=18.5,
                credit_spreads=120,
            ),
            outlook="Stagflationary risks rising",
            risks=("oil shock", "policy error"),
            allocation_implications="Lean defensive but stay diversified.",
        )

        payload = macro_view.to_dict()

        self.assertEqual(payload["regime"], "late_cycle")
        self.assertEqual(payload["scores"]["growth"], 1)
        self.assertEqual(payload["key_indicators"]["vix"], 18.5)
        self.assertEqual(payload["risks"], ["oil shock", "policy error"])

    def test_asset_cma_output_captures_method_range_and_selected_estimate(self) -> None:
        methods = (
            CMAMethodEstimate(name="historical_erp", expected_return=0.08, confidence=0.6),
            CMAMethodEstimate(name="regime_adjusted", expected_return=0.06, confidence=0.7),
            CMAMethodEstimate(name="auto_blend", expected_return=0.07, confidence=0.65),
        )
        cma_output = AssetCMAOutput(
            asset_slug="us_large_cap",
            generated_at="2026-04-09T12:00:00Z",
            selected_method="auto_blend",
            selected_expected_return=0.07,
            selected_confidence=0.65,
            methods=methods,
            support_signals={"momentum": "positive", "valuation": "fair"},
            notes=("Methods tightly clustered.",),
        )

        self.assertEqual(cma_output.method_return_range, (0.06, 0.08))
        self.assertEqual(cma_output.to_dict()["selected_method"], "auto_blend")

    def test_portfolio_and_risk_outputs_roundtrip_to_contract_dicts(self) -> None:
        proposal = PortfolioProposalOutput(
            timestamp="2026-04-09T12:00:00Z",
            method="max_sharpe",
            category="return_optimized",
            weights={"us_large_cap": 0.25, "us_short_treasury": 0.75},
            expected_return=0.06,
            expected_volatility=0.08,
            sharpe_ratio=0.5,
            max_drawdown=-0.18,
            effective_n=1.6,
            concentration=0.625,
            metadata={"mu_used": "cma_weighted", "sigma_used": "covariance_agent"},
        )
        risk_report = CRORiskReportOutput(
            method="max_sharpe",
            ex_ante=CROExAnteMetrics(volatility=0.08, portfolio_return=0.06, sharpe=0.5, var_95=-0.12, cvar_95=-0.16),
            backtest=CROBacktestMetrics(
                annual_return=0.07,
                annual_vol=0.09,
                sharpe=0.55,
                max_drawdown=-0.2,
                calmar=0.35,
                sortino_ratio=0.72,
            ),
            concentration=CROConcentrationMetrics(effective_n=1.6, herfindahl=0.625, top5_concentration=1.0, max_weight=0.75),
            factor_tilts=CROFactorTilts(equity_beta=0.4, duration=5.8, credit_spread=0.2, dollar_exposure=0.9),
            ips_compliance=CROIPSDiagnostic(tracking_error=0.03, within_tracking_budget=True, asset_bounds_ok=True, passes=True, violations=()),
        )
        board_memo = CIOBoardMemoOutput(
            selected_ensemble="composite_score_weighting",
            ensemble_weights={"max_sharpe": 0.7, "inverse_volatility": 0.3},
            portfolio_summary={
                "expected_return": 0.06,
                "expected_volatility": 0.08,
                "sharpe_ratio": 0.5,
                "effective_n": 6.2,
                "tracking_error_vs_60_40": 0.03,
            },
            allocation_by_asset_class={"equity": 0.45, "fixed_income": 0.42, "real_assets": 0.05, "cash": 0.08},
            top_positions=(TopPosition(asset="us_large_cap", weight=0.12, risk_contrib=0.18),),
            changes_since_last_review=("Raised cash by 2%.",),
            key_risks_to_monitor=("Growth shock",),
            rebalancing_plan="Review quarterly unless drift exceeds thresholds.",
            ips_compliance_statement="COMPLIANT",
        )

        self.assertEqual(proposal.to_dict()["timestamp"], "2026-04-09T12:00:00Z")
        self.assertEqual(proposal.to_dict()["category"], "return_optimized")
        self.assertEqual(proposal.to_dict()["metadata"]["mu_used"], "cma_weighted")
        self.assertEqual(risk_report.to_dict()["ex_ante"]["return"], 0.06)
        self.assertEqual(risk_report.to_dict()["backtest"]["sortino_ratio"], 0.72)
        self.assertEqual(risk_report.to_dict()["ips_compliance"]["passes"], True)
        self.assertEqual(board_memo.to_dict()["top_positions"][0]["asset"], "us_large_cap")

    def test_covariance_output_preserves_labels_and_matrices(self) -> None:
        covariance = CovarianceOutput(
            generated_at="2026-04-09T12:00:00Z",
            asset_slugs=("us_large_cap", "us_short_treasury"),
            covariance_matrix=((0.04, 0.01), (0.01, 0.02)),
            correlation_matrix=CorrelationMatrix(values=((1.0, 0.35), (0.35, 1.0))),
            lookback_months=60,
            annualization_factor=12,
            shrinkage_method="ledoit_wolf",
            regime_adjustment="late_cycle_high_vol",
        )

        payload = covariance.to_dict()
        self.assertEqual(payload["asset_slugs"], ["us_large_cap", "us_short_treasury"])
        self.assertEqual(payload["correlation_matrix"]["values"][0][1], 0.35)

    def test_asset_cma_output_rejects_selected_value_outside_method_range(self) -> None:
        with self.assertRaisesRegex(ValueError, "selected_expected_return"):
            AssetCMAOutput(
                asset_slug="us_large_cap",
                generated_at="2026-04-09T12:00:00Z",
                selected_method="auto_blend",
                selected_expected_return=0.10,
                selected_confidence=0.65,
                methods=(
                    CMAMethodEstimate(name="historical_erp", expected_return=0.08, confidence=0.6),
                    CMAMethodEstimate(name="regime_adjusted", expected_return=0.06, confidence=0.7),
                ),
                support_signals={},
            )

    def test_asset_cma_output_requires_available_method(self) -> None:
        with self.assertRaisesRegex(ValueError, "available CMA method"):
            AssetCMAOutput(
                asset_slug="us_large_cap",
                generated_at="2026-04-09T12:00:00Z",
                selected_method="stub",
                selected_expected_return=0.0,
                selected_confidence=0.0,
                methods=(CMAMethodEstimate(name="survey", expected_return=0.0, confidence=0.0, available=False),),
                support_signals={},
            ).method_return_range

    def test_covariance_output_rejects_jagged_matrices(self) -> None:
        with self.assertRaisesRegex(ValueError, "covariance_matrix"):
            CovarianceOutput(
                generated_at="2026-04-09T12:00:00Z",
                asset_slugs=("us_large_cap", "us_short_treasury"),
                covariance_matrix=((0.04,), (0.01, 0.02)),
                correlation_matrix=CorrelationMatrix(values=((1.0, 0.35), (0.35, 1.0))),
                lookback_months=60,
                annualization_factor=12,
                shrinkage_method="ledoit_wolf",
                regime_adjustment="late_cycle_high_vol",
            )

    def test_covariance_output_rejects_non_square_correlation_matrix(self) -> None:
        with self.assertRaisesRegex(ValueError, "correlation_matrix"):
            CovarianceOutput(
                generated_at="2026-04-09T12:00:00Z",
                asset_slugs=("us_large_cap", "us_short_treasury"),
                covariance_matrix=((0.04, 0.01), (0.01, 0.02)),
                correlation_matrix=CorrelationMatrix(values=((1.0,), (0.35, 1.0))),
                lookback_months=60,
                annualization_factor=12,
                shrinkage_method="ledoit_wolf",
                regime_adjustment="late_cycle_high_vol",
            )

    def test_supporting_asset_contracts_serialize_consistently(self) -> None:
        from core.contracts import AssetCorrelationRow, AssetHistoricalStats, AssetScenario, AssetSignals

        signals = AssetSignals(asset_slug="gold", momentum="positive", trend="up", mean_reversion="neutral", valuation="rich")
        historical_stats = AssetHistoricalStats(
            asset_slug="gold",
            annual_return=0.05,
            annual_volatility=0.16,
            sharpe_ratio=0.28,
            max_drawdown=-0.19,
        )
        scenarios = (
            AssetScenario(name="bull", expected_return=0.12, probability=0.2),
            AssetScenario(name="base", expected_return=0.06, probability=0.6),
            AssetScenario(name="bear", expected_return=-0.08, probability=0.2),
        )
        correlation_row = AssetCorrelationRow(
            asset_slug="gold",
            correlations={"us_large_cap": 0.1, "us_short_treasury": -0.05},
        )

        self.assertEqual(signals.to_dict()["valuation"], "rich")
        self.assertEqual(historical_stats.to_dict()["annual_volatility"], 0.16)
        self.assertEqual(scenarios[1].to_dict()["name"], "base")
        self.assertEqual(correlation_row.to_dict()["correlations"]["us_short_treasury"], -0.05)


if __name__ == "__main__":
    unittest.main()
