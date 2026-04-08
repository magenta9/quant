from __future__ import annotations

import json
import sqlite3
import unittest
from dataclasses import dataclass
from pathlib import Path

from core.assets import ASSET_ORDER
from core.data_fetcher import AssetHistoryResult, HistoricalPricePoint, MacroIndicatorValue, ProxyTickerMetadata


def _build_history(asset_slug: str, monthly_return: float, months: int = 36) -> AssetHistoryResult:
    level = 100.0
    points: list[HistoricalPricePoint] = []
    for month in range(months):
        level *= 1 + monthly_return
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

        macro_payload = json.loads((result.run_directory / "macro" / "macro_view.json").read_text(encoding="utf-8"))
        self.assertEqual(macro_payload["regime"], "late_cycle")
        self.assertTrue((result.run_directory / "assets" / "us_large_cap" / "cma.json").exists())
        self.assertTrue((result.run_directory / "assets" / "cash" / "cma_methods.json").exists())

        with sqlite3.connect(self.database_path) as connection:
            macro_count = connection.execute("SELECT COUNT(*) FROM macro_views").fetchone()[0]
            cma_count = connection.execute("SELECT COUNT(*) FROM cma_results").fetchone()[0]
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
        self.assertEqual(unavailable_rows, 18)

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
