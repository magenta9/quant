from __future__ import annotations

import json
import unittest
from dataclasses import dataclass
from pathlib import Path

from core.assets import ASSET_ORDER
from core.contracts import IndicatorSnapshot, MacroScores, MacroView
from core.data_fetcher import AssetHistoryResult, HistoricalPricePoint, ProxyTickerMetadata


def _build_macro_view(*, regime: str, fed_funds_rate: float) -> MacroView:
    return MacroView(
        timestamp="2026-04-09T12:00:00Z",
        regime=regime,
        confidence="medium",
        scores=MacroScores(growth=1, inflation=0, monetary_policy=1, financial_conditions=0),
        composite_score=0.7,
        recession_probability=0.3,
        key_indicators=IndicatorSnapshot(
            gdp_growth_yoy=2.1,
            cpi_yoy=2.4,
            fed_funds_rate=fed_funds_rate,
            vix=18.5,
            credit_spreads=120.0,
        ),
        outlook="Macro backdrop for CMA testing.",
    )


def _build_history(asset_slug: str, monthly_return: float, months: int = 24) -> AssetHistoryResult:
    level = 100.0
    points: list[HistoricalPricePoint] = []
    for month in range(months):
        level *= 1 + monthly_return
        year = 2024 + (month // 12)
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
        ticker=f"{asset_slug.upper()}",
        metadata=ProxyTickerMetadata(
            asset_slug=asset_slug,
            ticker=f"{asset_slug.upper()}",
            short_name=asset_slug,
            currency="USD",
            exchange="TEST",
            quote_type="ETF",
        ),
        points=tuple(points),
    )


@dataclass(frozen=True, slots=True)
class _StubAssetProvider:
    monthly_returns: dict[str, float]

    def get_asset_history(self, asset_slug: str, *, period: str = "max", interval: str = "1mo") -> AssetHistoryResult:
        return _build_history(asset_slug, self.monthly_returns.get(asset_slug, 0.006))


class CMABuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = Path("tests_runtime") / self._testMethodName
        self.workspace.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        for path in sorted(self.workspace.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        if self.workspace.exists():
            self.workspace.rmdir()

    def test_run_asset_analysis_writes_artifacts_with_explicit_stub_methods(self) -> None:
        from core.cma_builder import run_asset_analysis

        macro_view = _build_macro_view(regime="late_cycle", fed_funds_rate=0.02)
        provider = _StubAssetProvider(monthly_returns={"us_large_cap": 0.01})

        result = run_asset_analysis(
            asset_slug="us_large_cap",
            macro_view=macro_view,
            output_dir=self.workspace,
            data_provider=provider,
        )

        self.assertEqual(result.cma_output.selected_method, "auto_blend")
        self.assertIn("inverse_gordon", result.stubbed_methods)
        self.assertIn("implied_erp", result.stubbed_methods)
        self.assertIn("survey_consensus", result.stubbed_methods)
        self.assertIn("black_litterman", result.stubbed_methods)
        self.assertEqual(set(result.artifact_paths), {"analysis", "cma", "cma_methods", "correlation_row", "historical_stats", "scenarios", "signals"})

        methods_payload = json.loads((self.workspace / "cma_methods.json").read_text(encoding="utf-8"))
        methods_by_name = {entry["name"]: entry for entry in methods_payload["methods"]}
        self.assertAlmostEqual(methods_by_name["historical_erp"]["expected_return"], 0.1268, places=4)
        self.assertAlmostEqual(methods_by_name["regime_adjusted_erp"]["expected_return"], 0.1055, places=4)
        self.assertEqual(methods_by_name["black_litterman"]["available"], False)
        self.assertIn("later phase", methods_by_name["black_litterman"]["rationale"])
        self.assertIn("paid/vendor data", methods_by_name["inverse_gordon"]["rationale"])

        cma_payload = json.loads((self.workspace / "cma.json").read_text(encoding="utf-8"))
        self.assertEqual(cma_payload["selected_method"], "auto_blend")
        self.assertAlmostEqual(cma_payload["selected_expected_return"], 0.1153, places=4)

        analysis = (self.workspace / "analysis.md").read_text(encoding="utf-8")
        self.assertIn("US Large Cap Equity", analysis)
        self.assertIn("late_cycle", analysis)
        self.assertIn("Stubbed methods", analysis)

    def test_run_asset_analysis_can_favor_regime_adjusted_method_in_recession(self) -> None:
        from core.cma_builder import run_asset_analysis

        macro_view = _build_macro_view(regime="recession", fed_funds_rate=0.02)
        provider = _StubAssetProvider(monthly_returns={"gold": 0.02})

        result = run_asset_analysis(
            asset_slug="gold",
            macro_view=macro_view,
            output_dir=self.workspace,
            data_provider=provider,
        )

        methods = {method.name: method for method in result.cma_output.methods}
        self.assertGreater(methods["historical_erp"].expected_return, methods["regime_adjusted_erp"].expected_return)
        self.assertEqual(result.cma_output.selected_method, "regime_adjusted_erp")
        self.assertLess(result.cma_output.selected_expected_return, methods["auto_blend"].expected_return)

    def test_cma_judge_skill_documents_mvp_availability_rules(self) -> None:
        skill_path = Path("skills/cma_judge/SKILL.md")

        self.assertTrue(skill_path.exists())
        skill_text = skill_path.read_text(encoding="utf-8")

        self.assertIn("Historical ERP + Risk-Free", skill_text)
        self.assertIn("Regime-Adjusted ERP", skill_text)
        self.assertIn("Auto-Blend", skill_text)
        self.assertIn("structured stub", skill_text.lower())
        self.assertIn("black_litterman", skill_text)
        self.assertIn("paid/vendor data", skill_text.lower())


if __name__ == "__main__":
    unittest.main()
