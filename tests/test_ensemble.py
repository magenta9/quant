from __future__ import annotations

import unittest

from core.contracts import (
    CROBacktestMetrics,
    CROConcentrationMetrics,
    CROExAnteMetrics,
    CROFactorTilts,
    CROIPSDiagnostic,
    CRORiskReportOutput,
    PortfolioProposalOutput,
)


class EnsembleTests(unittest.TestCase):
    def test_run_cio_stage_returns_board_memo_contract(self) -> None:
        from core.contracts import CIOBoardMemoOutput
        from core.ensemble import run_cio_stage

        proposals = (
            self._make_proposal("equal_weight", "heuristic", 0.20, 0.80, expected_return=0.050, volatility=0.060, sharpe=0.50, effective_n=2.0),
            self._make_proposal("inverse_volatility", "heuristic", 0.40, 0.60, expected_return=0.060, volatility=0.070, sharpe=0.57, effective_n=2.4),
            self._make_proposal("risk_parity", "risk_optimized", 0.50, 0.50, expected_return=0.070, volatility=0.080, sharpe=0.62, effective_n=2.8),
        )
        risk_reports = (
            self._make_risk_report("equal_weight", backtest_sharpe=0.45, tracking_error=0.030, passes=True),
            self._make_risk_report("inverse_volatility", backtest_sharpe=0.50, tracking_error=0.025, passes=True),
            self._make_risk_report("risk_parity", backtest_sharpe=0.55, tracking_error=0.020, passes=True),
        )

        board_memo = run_cio_stage(proposals=proposals, risk_reports=risk_reports)

        self.assertIsInstance(board_memo, CIOBoardMemoOutput)
        self.assertIn(board_memo.selected_ensemble, {"simple_average", "composite_score_weighting"})
        self.assertEqual(board_memo.ips_compliance_statement, "COMPLIANT")
        self.assertGreater(len(board_memo.rebalancing_plan), 0)
        self.assertEqual(board_memo.changes_since_last_review, ())

    def test_simple_average_ensemble_blends_weights_and_summary_metrics(self) -> None:
        from core.ensemble import build_ensemble_candidate

        proposals = (
            self._make_proposal("equal_weight", "heuristic", 0.20, 0.80, expected_return=0.050, volatility=0.060, sharpe=0.50, effective_n=2.0),
            self._make_proposal("inverse_volatility", "heuristic", 0.40, 0.60, expected_return=0.060, volatility=0.070, sharpe=0.57, effective_n=2.4),
            self._make_proposal("risk_parity", "risk_optimized", 0.50, 0.50, expected_return=0.070, volatility=0.080, sharpe=0.62, effective_n=2.8),
        )
        risk_reports = (
            self._make_risk_report("equal_weight", backtest_sharpe=0.45, tracking_error=0.030, passes=True),
            self._make_risk_report("inverse_volatility", backtest_sharpe=0.50, tracking_error=0.025, passes=True),
            self._make_risk_report("risk_parity", backtest_sharpe=0.55, tracking_error=0.020, passes=True),
        )

        candidate = build_ensemble_candidate(
            ensemble_method="simple_average",
            proposals=proposals,
            risk_reports=risk_reports,
        )

        self.assertEqual(candidate.selected_ensemble, "simple_average")
        self.assertAlmostEqual(candidate.ensemble_weights["equal_weight"], 1.0 / 3.0)
        self.assertAlmostEqual(candidate.ensemble_weights["inverse_volatility"], 1.0 / 3.0)
        self.assertAlmostEqual(candidate.ensemble_weights["risk_parity"], 1.0 / 3.0)
        self.assertAlmostEqual(candidate.weights["us_large_cap"], (0.20 + 0.40 + 0.50) / 3.0)
        self.assertAlmostEqual(candidate.weights["us_short_treasury"], (0.80 + 0.60 + 0.50) / 3.0)
        self.assertAlmostEqual(candidate.portfolio_summary["expected_return"], 0.060)
        self.assertAlmostEqual(candidate.portfolio_summary["expected_volatility"], 0.070)
        self.assertAlmostEqual(candidate.portfolio_summary["tracking_error_vs_60_40"], 0.025)
        self.assertEqual(candidate.ips_compliance_statement, "COMPLIANT")
        self.assertEqual(candidate.allocation_by_asset_class["equity"], candidate.weights["us_large_cap"])
        self.assertEqual(candidate.top_positions[0].asset, "us_short_treasury")

    def test_composite_score_weighting_favors_stronger_compliant_methods(self) -> None:
        from core.ensemble import build_ensemble_candidate

        proposals = (
            self._make_proposal("max_sharpe", "return_optimized", 0.55, 0.45, expected_return=0.082, volatility=0.100, sharpe=0.62, effective_n=3.1),
            self._make_proposal("inverse_volatility", "heuristic", 0.35, 0.65, expected_return=0.058, volatility=0.072, sharpe=0.53, effective_n=2.6),
            self._make_proposal("equal_weight", "heuristic", 0.65, 0.35, expected_return=0.052, volatility=0.095, sharpe=0.34, effective_n=1.9),
        )
        risk_reports = (
            self._make_risk_report("max_sharpe", backtest_sharpe=0.61, tracking_error=0.018, passes=True, max_drawdown=-0.12),
            self._make_risk_report("inverse_volatility", backtest_sharpe=0.46, tracking_error=0.026, passes=True, max_drawdown=-0.16),
            self._make_risk_report(
                "equal_weight",
                backtest_sharpe=0.22,
                tracking_error=0.090,
                passes=False,
                max_drawdown=-0.28,
                violations=("tracking error 0.0900 exceeds budget 0.0600",),
            ),
        )

        candidate = build_ensemble_candidate(
            ensemble_method="composite_score_weighting",
            proposals=proposals,
            risk_reports=risk_reports,
        )

        self.assertEqual(candidate.selected_ensemble, "composite_score_weighting")
        self.assertGreater(candidate.ensemble_weights["max_sharpe"], candidate.ensemble_weights["inverse_volatility"])
        self.assertEqual(candidate.ensemble_weights["equal_weight"], 0.0)
        self.assertAlmostEqual(sum(candidate.ensemble_weights.values()), 1.0)
        self.assertGreater(candidate.weights["us_large_cap"], 0.35)
        self.assertLess(candidate.portfolio_summary["tracking_error_vs_60_40"], 0.026)
        self.assertEqual(candidate.ips_compliance_statement, "COMPLIANT")
        self.assertIn("max_sharpe", candidate.rationale)

    def test_cio_selection_prefers_best_compliant_ensemble_and_explains_choice(self) -> None:
        from core.contracts import CIOBoardMemoOutput
        from core.ensemble import select_cio_ensemble

        proposals = (
            self._make_proposal("max_sharpe", "return_optimized", 0.55, 0.45, expected_return=0.082, volatility=0.100, sharpe=0.62, effective_n=3.1),
            self._make_proposal("inverse_volatility", "heuristic", 0.35, 0.65, expected_return=0.058, volatility=0.072, sharpe=0.53, effective_n=2.6),
            self._make_proposal("equal_weight", "heuristic", 0.65, 0.35, expected_return=0.052, volatility=0.095, sharpe=0.34, effective_n=1.9),
        )
        risk_reports = (
            self._make_risk_report("max_sharpe", backtest_sharpe=0.61, tracking_error=0.018, passes=True, max_drawdown=-0.12),
            self._make_risk_report("inverse_volatility", backtest_sharpe=0.46, tracking_error=0.026, passes=True, max_drawdown=-0.16),
            self._make_risk_report(
                "equal_weight",
                backtest_sharpe=0.22,
                tracking_error=0.090,
                passes=False,
                max_drawdown=-0.28,
                violations=("tracking error 0.0900 exceeds budget 0.0600",),
            ),
        )

        selected = select_cio_ensemble(proposals=proposals, risk_reports=risk_reports)

        self.assertIsInstance(selected, CIOBoardMemoOutput)
        self.assertEqual(selected.selected_ensemble, "composite_score_weighting")
        self.assertEqual(selected.key_risks_to_monitor, ("tracking error 0.0900 exceeds budget 0.0600",))
        self.assertFalse(hasattr(selected, "candidate_score"))

    def test_cio_selection_non_compliant_case_does_not_claim_preserved_ips(self) -> None:
        from core.contracts import CIOBoardMemoOutput
        from core.ensemble import select_cio_ensemble

        proposals = (
            self._make_proposal("max_sharpe", "return_optimized", 0.55, 0.45, expected_return=0.082, volatility=0.100, sharpe=0.62, effective_n=3.1),
            self._make_proposal("inverse_volatility", "heuristic", 0.35, 0.65, expected_return=0.058, volatility=0.072, sharpe=0.53, effective_n=2.6),
        )
        risk_reports = (
            self._make_risk_report(
                "max_sharpe",
                backtest_sharpe=0.61,
                tracking_error=0.081,
                passes=False,
                max_drawdown=-0.12,
                violations=("tracking error 0.0810 exceeds budget 0.0600",),
            ),
            self._make_risk_report(
                "inverse_volatility",
                backtest_sharpe=0.46,
                tracking_error=0.074,
                passes=False,
                max_drawdown=-0.16,
                violations=("tracking error 0.0740 exceeds budget 0.0600",),
            ),
        )

        selected = select_cio_ensemble(proposals=proposals, risk_reports=risk_reports)

        self.assertIsInstance(selected, CIOBoardMemoOutput)
        self.assertEqual(selected.ips_compliance_statement, "NON-COMPLIANT")

    def test_top_positions_use_concentration_proxy_not_raw_weight(self) -> None:
        from core.ensemble import build_ensemble_candidate

        proposals = (
            self._make_proposal("equal_weight", "heuristic", 0.80, 0.20, expected_return=0.050, volatility=0.060, sharpe=0.50, effective_n=1.5),
            self._make_proposal("inverse_volatility", "heuristic", 0.70, 0.30, expected_return=0.060, volatility=0.070, sharpe=0.57, effective_n=1.7),
        )
        risk_reports = (
            self._make_risk_report("equal_weight", backtest_sharpe=0.45, tracking_error=0.030, passes=True),
            self._make_risk_report("inverse_volatility", backtest_sharpe=0.50, tracking_error=0.025, passes=True),
        )

        candidate = build_ensemble_candidate(
            ensemble_method="simple_average",
            proposals=proposals,
            risk_reports=risk_reports,
        )

        self.assertNotAlmostEqual(candidate.top_positions[0].risk_contrib, candidate.top_positions[0].weight)
        self.assertAlmostEqual(sum(position.risk_contrib for position in candidate.top_positions), 1.0)

    def test_top_positions_risk_contrib_uses_method_risk_inputs_not_just_final_weights(self) -> None:
        from core.ensemble import build_ensemble_candidate

        proposals = (
            self._make_proposal("high_risk_growth", "return_optimized", 0.80, 0.20, expected_return=0.090, volatility=0.120, sharpe=0.58, effective_n=1.6),
            self._make_proposal("low_risk_defense", "risk_optimized", 0.20, 0.80, expected_return=0.045, volatility=0.030, sharpe=0.50, effective_n=1.6),
        )
        risk_reports = (
            self._make_risk_report("high_risk_growth", backtest_sharpe=0.60, tracking_error=0.030, passes=True),
            self._make_risk_report("low_risk_defense", backtest_sharpe=0.45, tracking_error=0.020, passes=True),
        )

        candidate = build_ensemble_candidate(
            ensemble_method="simple_average",
            proposals=proposals,
            risk_reports=risk_reports,
        )

        self.assertAlmostEqual(candidate.weights["us_large_cap"], 0.50)
        self.assertAlmostEqual(candidate.weights["us_short_treasury"], 0.50)
        self.assertGreater(candidate.top_positions[0].risk_contrib, candidate.top_positions[1].risk_contrib)
        self.assertEqual(candidate.top_positions[0].asset, "us_large_cap")

    def _make_proposal(
        self,
        method: str,
        category: str,
        equity_weight: float,
        treasury_weight: float,
        *,
        expected_return: float,
        volatility: float,
        sharpe: float,
        effective_n: float,
    ) -> PortfolioProposalOutput:
        return PortfolioProposalOutput(
            timestamp="2026-04-09T12:00:00Z",
            method=method,
            category=category,
            weights={
                "us_large_cap": equity_weight,
                "us_short_treasury": treasury_weight,
            },
            expected_return=expected_return,
            expected_volatility=volatility,
            sharpe_ratio=sharpe,
            max_drawdown=None,
            effective_n=effective_n,
            concentration=(equity_weight**2) + (treasury_weight**2),
            metadata={},
        )

    def _make_risk_report(
        self,
        method: str,
        *,
        backtest_sharpe: float,
        tracking_error: float,
        passes: bool,
        max_drawdown: float = -0.15,
        violations: tuple[str, ...] = (),
    ) -> CRORiskReportOutput:
        return CRORiskReportOutput(
            method=method,
            ex_ante=CROExAnteMetrics(
                volatility=0.08,
                portfolio_return=0.06,
                sharpe=0.5,
                var_95=-0.10,
                cvar_95=-0.14,
            ),
            backtest=CROBacktestMetrics(
                annual_return=0.07,
                annual_vol=0.09,
                sharpe=backtest_sharpe,
                max_drawdown=max_drawdown,
                calmar=0.4,
                sortino_ratio=0.7,
            ),
            concentration=CROConcentrationMetrics(
                effective_n=2.5,
                herfindahl=0.4,
                top5_concentration=1.0,
                max_weight=0.65,
            ),
            factor_tilts=CROFactorTilts(
                equity_beta=0.4,
                duration=4.5,
                credit_spread=0.1,
                dollar_exposure=0.9,
            ),
            ips_compliance=CROIPSDiagnostic(
                tracking_error=tracking_error,
                within_tracking_budget=passes,
                asset_bounds_ok=True,
                passes=passes,
                violations=violations,
            ),
        )


if __name__ == "__main__":
    unittest.main()
