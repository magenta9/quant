from __future__ import annotations

import json
import sqlite3
import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

from core.assets import ASSET_ORDER
from core.data_fetcher import AssetHistoryResult, HistoricalPricePoint, MacroIndicatorValue, ProxyTickerMetadata


def _build_history(asset_slug: str, monthly_return: float, months: int = 36) -> AssetHistoryResult:
    level = 100.0
    points: list[HistoricalPricePoint] = []
    for month in range(months):
        cycle_adjustment = ((month % 6) - 2.5) * 0.0003
        level *= 1 + monthly_return + cycle_adjustment
        year = 2023 + (month // 12)
        month_number = (month % 12) + 1
        points.append(
            HistoricalPricePoint(
                timestamp=f"{year:04d}-{month_number:02d}-28",
                open=level,
                high=level,
                low=level,
                close=level,
                adj_close=level,
                volume=1_000_000,
            )
        )
    return AssetHistoryResult(
        asset_slug=asset_slug,
        ticker=asset_slug.upper(),
        metadata=ProxyTickerMetadata(
            asset_slug=asset_slug,
            ticker=asset_slug.upper(),
            short_name=asset_slug,
            currency="USD",
            exchange="TEST",
            quote_type="ETF",
        ),
        points=tuple(points),
    )


@dataclass(frozen=True, slots=True)
class _StubPipelineProvider:
    monthly_returns: dict[str, float]

    def get_macro_indicators(self) -> dict[str, MacroIndicatorValue]:
        return {
            "gdp_growth_yoy": MacroIndicatorValue("gdp_growth_yoy", 2.6, "2026-04-09T12:00:00Z", "GDP", "ok"),
            "cpi_yoy": MacroIndicatorValue("cpi_yoy", 2.4, "2026-04-09T12:00:00Z", "CPI", "ok"),
            "fed_funds_rate": MacroIndicatorValue("fed_funds_rate", 3.5, "2026-04-09T12:00:00Z", "FEDFUNDS", "ok"),
            "vix": MacroIndicatorValue("vix", 20.0, "2026-04-09T12:00:00Z", "^VIX", "ok"),
            "credit_spreads": MacroIndicatorValue("credit_spreads", 140.0, "2026-04-09T12:00:00Z", "CREDIT", "ok"),
        }

    def get_asset_history(self, asset_slug: str, *, period: str = "max", interval: str = "1mo") -> AssetHistoryResult:
        return _build_history(asset_slug, self.monthly_returns.get(asset_slug, 0.005 + (ASSET_ORDER.index(asset_slug) * 0.0001)))


class PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = Path("tests_runtime") / self._testMethodName
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.database_path = self.workspace / "database" / "portfolio.db"

    def tearDown(self) -> None:
        for path in sorted(self.workspace.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        if self.workspace.exists():
            self.workspace.rmdir()

    def test_run_phase2_pipeline_writes_macro_and_all_asset_artifacts_and_persists_rows(self) -> None:
        from core.pipeline import run_phase2_pipeline

        provider = _StubPipelineProvider(monthly_returns={"cash": 0.0015, "us_large_cap": 0.009})

        result = run_phase2_pipeline(
            ips_path=Path("config/ips.md"),
            output_root=self.workspace / "output" / "runs",
            database_path=self.database_path,
            data_provider=provider,
            run_id="run-phase2-test",
        )

        self.assertEqual(result.run_id, "run-phase2-test")
        self.assertEqual(result.macro_result.macro_view.regime, "late_cycle")
        self.assertEqual(len(result.asset_results), 18)
        self.assertEqual(tuple(result.ips_assets), ASSET_ORDER)
        self.assertEqual(result.covariance_output.asset_slugs, ASSET_ORDER)
        self.assertEqual(
            tuple(proposal.method for proposal in result.portfolio_proposals),
            (
                "equal_weight",
                "inverse_volatility",
                "max_sharpe",
                "global_min_variance",
                "risk_parity",
            ),
        )
        self.assertEqual(
            tuple(report.method for report in result.risk_reports),
            (
                "equal_weight",
                "inverse_volatility",
                "max_sharpe",
                "global_min_variance",
                "risk_parity",
            ),
        )

        macro_payload = json.loads((result.run_directory / "macro" / "macro_view.json").read_text(encoding="utf-8"))
        self.assertEqual(macro_payload["regime"], "late_cycle")
        self.assertTrue((result.run_directory / "assets" / "us_large_cap" / "cma.json").exists())
        self.assertTrue((result.run_directory / "assets" / "cash" / "cma_methods.json").exists())
        covariance_payload = json.loads((result.run_directory / "covariance" / "covariance.json").read_text(encoding="utf-8"))
        self.assertEqual(tuple(covariance_payload["asset_slugs"]), ASSET_ORDER)

        for proposal in result.portfolio_proposals:
            self.assertAlmostEqual(sum(proposal.weights.values()), 1.0, places=8)
            self.assertTrue(all(weight >= 0.0 for weight in proposal.weights.values()))
            proposal_payload = json.loads(
                (result.run_directory / "portfolio" / proposal.method / "proposal.json").read_text(encoding="utf-8")
            )
            self.assertEqual(proposal_payload["method"], proposal.method)
            self.assertIn("constraint_projection_applied", proposal_payload["metadata"])

        for report in result.risk_reports:
            report_payload = json.loads(
                (result.run_directory / "risk" / report.method / "risk_report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(report_payload["method"], report.method)
            self.assertIn("ips_compliance", report_payload)
            self.assertIn("violations", report_payload["ips_compliance"])
            self.assertIn("warnings", report_payload["ips_compliance"])
        self.assertTrue(any(proposal.metadata["constraint_projection_applied"] for proposal in result.portfolio_proposals))
        self.assertTrue(
            any(
                any("projection applied" in warning for warning in report.ips_compliance.warnings)
                for report in result.risk_reports
            )
        )

        with sqlite3.connect(self.database_path) as connection:
            macro_count = connection.execute("SELECT COUNT(*) FROM macro_views").fetchone()[0]
            cma_count = connection.execute("SELECT COUNT(*) FROM cma_results").fetchone()[0]
            proposal_count = connection.execute("SELECT COUNT(*) FROM portfolio_proposals").fetchone()[0]
            risk_report_count = connection.execute("SELECT COUNT(*) FROM risk_reports").fetchone()[0]
            stored_proposal = connection.execute(
                """
                SELECT method, category, weights_json, expected_return, expected_vol
                FROM portfolio_proposals
                WHERE method = 'max_sharpe'
                """
            ).fetchone()
            stored_risk_report = connection.execute(
                """
                SELECT method, ex_ante_json, ips_compliance_json
                FROM risk_reports
                WHERE method = 'max_sharpe'
                """
            ).fetchone()
            unavailable_rows = connection.execute(
                """
                SELECT COUNT(*)
                FROM cma_results
                WHERE method = 'black_litterman'
                  AND json_extract(raw_output_json, '$.available') = 0
                """
            ).fetchone()[0]

        self.assertEqual(macro_count, 1)
        self.assertEqual(cma_count, 18 * 7)
        self.assertEqual(proposal_count, 5)
        self.assertEqual(risk_report_count, 5)
        self.assertEqual(unavailable_rows, 18)
        self.assertEqual(stored_proposal[0], "max_sharpe")
        self.assertEqual(stored_proposal[1], "return_optimized")
        self.assertAlmostEqual(sum(json.loads(stored_proposal[2]).values()), 1.0, places=8)
        self.assertGreater(stored_proposal[3], 0.0)
        self.assertGreater(stored_proposal[4], 0.0)
        self.assertEqual(stored_risk_report[0], "max_sharpe")
        self.assertIn("volatility", json.loads(stored_risk_report[1]))
        self.assertTrue(json.loads(stored_risk_report[2])["passes"])
        self.assertTrue(json.loads(stored_risk_report[2])["warnings"])

    def test_run_phase2_pipeline_uses_pinned_mvp_method_list_even_if_registry_grows(self) -> None:
        from core.pipeline import run_phase2_pipeline

        provider = _StubPipelineProvider(monthly_returns={"cash": 0.0015, "us_large_cap": 0.009})

        extra_method_name = "future_method"

        def _unexpected_method(**kwargs):
            raise AssertionError("pipeline should not execute registry methods outside the pinned MVP set")

        with patch.dict("core.pipeline.METHOD_REGISTRY", {extra_method_name: _unexpected_method}, clear=False):
            result = run_phase2_pipeline(
                ips_path=Path("config/ips.md"),
                output_root=self.workspace / "output" / "runs",
                database_path=self.database_path,
                data_provider=provider,
                run_id="run-phase2-pinned-methods",
            )

        self.assertEqual(
            tuple(proposal.method for proposal in result.portfolio_proposals),
            (
                "equal_weight",
                "inverse_volatility",
                "max_sharpe",
                "global_min_variance",
                "risk_parity",
            ),
        )

    def test_run_phase2_pipeline_keeps_portfolio_and_risk_persistence_atomic_on_method_failure(self) -> None:
        from core.pipeline import run_phase2_pipeline
        from core.portfolio_optimizer import optimize_portfolio as real_optimize_portfolio

        provider = _StubPipelineProvider(monthly_returns={"cash": 0.0015, "us_large_cap": 0.009})

        def _blow_up_on_last_method(*, method: str, **kwargs):
            if method == "risk_parity":
                raise RuntimeError("simulated phase3 method failure")
            return real_optimize_portfolio(method=method, **kwargs)

        with patch("core.pipeline.optimize_portfolio", side_effect=_blow_up_on_last_method):
            with self.assertRaisesRegex(RuntimeError, "simulated phase3 method failure"):
                run_phase2_pipeline(
                    ips_path=Path("config/ips.md"),
                    output_root=self.workspace / "output" / "runs",
                    database_path=self.database_path,
                    data_provider=provider,
                    run_id="run-phase2-atomicity-failure",
                )

        with sqlite3.connect(self.database_path) as connection:
            proposal_count = connection.execute("SELECT COUNT(*) FROM portfolio_proposals").fetchone()[0]
            risk_report_count = connection.execute("SELECT COUNT(*) FROM risk_reports").fetchone()[0]

        self.assertEqual(proposal_count, 0)
        self.assertEqual(risk_report_count, 0)
        self.assertEqual(
            list((self.workspace / "output" / "runs" / "run-phase2-atomicity-failure" / "portfolio").rglob("proposal.json")),
            [],
        )
        self.assertEqual(
            list((self.workspace / "output" / "runs" / "run-phase2-atomicity-failure" / "risk").rglob("risk_report.json")),
            [],
        )

    def test_run_phase2_pipeline_preserves_real_ips_violations_in_artifacts_and_sqlite(self) -> None:
        from core.pipeline import run_phase2_pipeline

        provider = _StubPipelineProvider(monthly_returns={"cash": 0.0015, "us_large_cap": 0.009})
        low_budget_ips = self.workspace / "strict_tracking_error_ips.md"
        low_budget_ips.write_text(
            Path("config/ips.md").read_text(encoding="utf-8").replace(
                "Tracking Error vs 60/40**: Maximum 6% annualized",
                "Tracking Error vs 60/40**: Maximum 0.001% annualized",
            ),
            encoding="utf-8",
        )

        result = run_phase2_pipeline(
            ips_path=low_budget_ips,
            output_root=self.workspace / "output" / "runs",
            database_path=self.database_path,
            data_provider=provider,
            run_id="run-phase2-strict-budget",
        )

        violating_report = next(report for report in result.risk_reports if report.ips_compliance.violations)
        self.assertFalse(violating_report.ips_compliance.passes)
        self.assertTrue(
            any("tracking error" in violation for violation in violating_report.ips_compliance.violations)
        )

        artifact_payload = json.loads(
            (result.run_directory / "risk" / violating_report.method / "risk_report.json").read_text(encoding="utf-8")
        )
        self.assertTrue(artifact_payload["ips_compliance"]["violations"])

        with sqlite3.connect(self.database_path) as connection:
            stored_violations = connection.execute(
                """
                SELECT ips_compliance_json
                FROM risk_reports
                WHERE method = ?
                """,
                (violating_report.method,),
            ).fetchone()[0]

        self.assertTrue(json.loads(stored_violations)["violations"])

    def test_run_phase2_pipeline_rejects_ips_that_do_not_cover_all_registered_assets(self) -> None:
        from core.pipeline import run_phase2_pipeline

        broken_ips = self.workspace / "ips.md"
        broken_ips.write_text(
            "# Investment Policy Statement\n\n## 1. Investment Universe\n\n### Eligible Asset Classes\n"
            "| Asset | Benchmark | Min Weight | Max Weight |\n"
            "|-------|-----------|------------|------------|\n"
            "| US Large Cap Equity | SPTR Index | 0% | 50% |\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "18 registered assets"):
            run_phase2_pipeline(
                ips_path=broken_ips,
                output_root=self.workspace / "output" / "runs",
                database_path=self.database_path,
                data_provider=_StubPipelineProvider(monthly_returns={}),
                run_id="run-bad-ips",
            )


if __name__ == "__main__":
    unittest.main()
