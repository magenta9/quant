from __future__ import annotations

import unittest

from core.data_fetcher import AssetHistoryResult, HistoricalPricePoint, ProxyTickerMetadata


def _build_history(asset_slug: str, monthly_returns: list[float]) -> AssetHistoryResult:
    level = 100.0
    points = [
        HistoricalPricePoint(
            timestamp="2023-01-31",
            open=level,
            high=level,
            low=level,
            close=level,
            adj_close=level,
            volume=1_000_000,
        )
    ]
    for offset, monthly_return in enumerate(monthly_returns, start=1):
        level *= 1 + monthly_return
        year = 2023 + ((offset) // 12)
        month = ((offset) % 12) + 1
        timestamp = f"{year:04d}-{month:02d}-28"
        points.append(
            HistoricalPricePoint(
                timestamp=timestamp,
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


class CovarianceTests(unittest.TestCase):
    def test_estimate_covariance_builds_shrunk_annualized_contract(self) -> None:
        from core.covariance import estimate_covariance

        histories = {
            "us_large_cap": _build_history("us_large_cap", [0.02, 0.01, -0.01, 0.015, 0.005, 0.018]),
            "us_interm_treasury": _build_history("us_interm_treasury", [0.005, 0.004, 0.006, 0.003, 0.004, 0.005]),
            "gold": _build_history("gold", [0.01, -0.005, 0.012, 0.008, -0.002, 0.009]),
        }

        output = estimate_covariance(
            histories,
            asset_slugs=("us_large_cap", "us_interm_treasury", "gold"),
            frequency="monthly",
            lookback_months=6,
            generated_at="2026-04-09T12:00:00Z",
        )

        self.assertEqual(output.asset_slugs, ("us_large_cap", "us_interm_treasury", "gold"))
        self.assertEqual(output.annualization_factor, 12)
        self.assertEqual(output.shrinkage_method, "ledoit_wolf")
        self.assertEqual(output.regime_adjustment, "none")
        self.assertEqual(len(output.covariance_matrix), 3)
        self.assertGreater(output.covariance_matrix[0][0], 0.0)
        self.assertAlmostEqual(output.covariance_matrix[0][1], output.covariance_matrix[1][0], places=12)
        self.assertAlmostEqual(output.correlation_matrix.values[0][0], 1.0, places=12)
        self.assertAlmostEqual(output.correlation_matrix.values[1][1], 1.0, places=12)

    def test_estimate_covariance_rejects_unknown_frequency(self) -> None:
        from core.covariance import estimate_covariance

        histories = {
            "us_large_cap": _build_history("us_large_cap", [0.02, 0.01, -0.01]),
            "us_interm_treasury": _build_history("us_interm_treasury", [0.005, 0.004, 0.006]),
        }

        with self.assertRaisesRegex(ValueError, "Unsupported frequency"):
            estimate_covariance(
                histories,
                asset_slugs=("us_large_cap", "us_interm_treasury"),
                frequency="hourly",
                lookback_months=3,
                generated_at="2026-04-09T12:00:00Z",
            )

    def test_ledoit_wolf_shrinkage_reduces_extreme_sample_covariance(self) -> None:
        from core.covariance import ledoit_wolf_shrinkage
        import numpy as np

        returns = np.array(
            [
                [0.06, 0.055],
                [-0.04, -0.045],
                [0.05, 0.052],
                [-0.03, -0.035],
                [0.07, 0.071],
            ]
        )
        sample_covariance = np.cov(returns, rowvar=False, ddof=1)

        shrunk_covariance = ledoit_wolf_shrinkage(returns)

        self.assertEqual(shrunk_covariance.shape, (2, 2))
        self.assertLessEqual(abs(shrunk_covariance[0, 1]), abs(sample_covariance[0, 1]))
        self.assertGreaterEqual(shrunk_covariance[0, 0], 0.0)
        self.assertGreaterEqual(shrunk_covariance[1, 1], 0.0)


if __name__ == "__main__":
    unittest.main()
