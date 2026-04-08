from __future__ import annotations

import math
import unittest
from datetime import UTC, datetime

from core.data_fetcher import YFinanceDataProvider


class _FakeFrame:
    def __init__(self, rows: list[tuple[datetime, dict[str, float | int]]]) -> None:
        self._rows = rows

    @property
    def empty(self) -> bool:
        return not self._rows

    def iterrows(self):
        return iter(self._rows)


class _FakeTicker:
    def __init__(
        self,
        *,
        history_rows=None,
        info=None,
        history_error: Exception | None = None,
        history_errors: list[Exception | None] | None = None,
        info_after_history=None,
    ) -> None:
        self._history_rows = history_rows or []
        self.info = info or {}
        self._history_error = history_error
        self._history_errors = list(history_errors or [])
        self._info_after_history = info_after_history

    def history(self, *, period: str, interval: str, auto_adjust: bool = False):
        if self._history_errors:
            next_error = self._history_errors.pop(0)
            if next_error is not None:
                raise next_error
        if self._history_error is not None:
            raise self._history_error
        if self._info_after_history is not None:
            self.info = self._info_after_history
        return _FakeFrame(self._history_rows)


class YFinanceDataProviderTests(unittest.TestCase):
    def test_get_asset_history_returns_proxy_metadata_and_price_points(self) -> None:
        rows = [
            (
                datetime(2026, 4, 1, tzinfo=UTC),
                {
                    "Open": 100.0,
                    "High": 101.0,
                    "Low": 99.0,
                    "Close": 100.5,
                    "Adj Close": 100.4,
                    "Volume": 1000,
                },
            ),
            (
                datetime(2026, 4, 2, tzinfo=UTC),
                {
                    "Open": 101.0,
                    "High": 103.0,
                    "Low": 100.0,
                    "Close": 102.0,
                    "Adj Close": 101.9,
                    "Volume": 1200,
                },
            ),
        ]
        provider = YFinanceDataProvider(
            ticker_factory=lambda ticker: _FakeTicker(
                history_rows=rows,
                info={
                    "shortName": "Vanguard Total Stock Market ETF",
                    "currency": "USD",
                    "exchange": "NYSEArca",
                    "quoteType": "ETF",
                },
            )
        )

        result = provider.get_asset_history("us_large_cap", period="1mo", interval="1d")

        self.assertEqual(result.asset_slug, "us_large_cap")
        self.assertEqual(result.ticker, "VTI")
        self.assertEqual(result.metadata.short_name, "Vanguard Total Stock Market ETF")
        self.assertEqual(result.points[0].close, 100.5)
        self.assertEqual(result.points[1].volume, 1200)
        self.assertEqual(result.issues, ())

    def test_get_asset_history_reports_missing_history_without_guessing(self) -> None:
        provider = YFinanceDataProvider(ticker_factory=lambda ticker: _FakeTicker())

        result = provider.get_asset_history("gold", period="1mo", interval="1d")

        self.assertEqual(result.ticker, "GLD")
        self.assertEqual(result.points, ())
        self.assertEqual(result.issues[0].code, "missing_history")
        self.assertIn("No price history returned", result.issues[0].message)

    def test_get_macro_indicators_reports_supported_and_unsupported_values_explicitly(self) -> None:
        provider = YFinanceDataProvider(
            ticker_factory=lambda ticker: _FakeTicker(
                history_rows=[
                    (
                        datetime(2026, 4, 2, tzinfo=UTC),
                        {
                            "Close": 18.5,
                        },
                    )
                ]
            )
        )

        result = provider.get_macro_indicators()

        self.assertEqual(result["vix"].value, 18.5)
        self.assertEqual(result["vix"].status, "ok")
        self.assertEqual(result["gdp_growth_yoy"].status, "unsupported")
        self.assertIn("No direct Yahoo Finance mapping", result["gdp_growth_yoy"].message)

    def test_get_macro_indicators_reports_vix_history_errors(self) -> None:
        provider = YFinanceDataProvider(
            ticker_factory=lambda ticker: _FakeTicker(history_error=RuntimeError("vix feed unavailable"))
        )

        result = provider.get_macro_indicators()

        self.assertEqual(result["vix"].status, "error")
        self.assertIn("vix feed unavailable", result["vix"].message)

    def test_get_proxy_ticker_metadata_reports_provider_errors(self) -> None:
        provider = YFinanceDataProvider(
            ticker_factory=lambda ticker: _FakeTicker(history_error=RuntimeError("upstream unavailable"))
        )

        result = provider.get_proxy_ticker_metadata("reits")

        self.assertEqual(result.ticker, "VNQ")
        self.assertEqual(result.short_name, None)
        self.assertEqual(result.issues[0].code, "provider_error")
        self.assertIn("upstream unavailable", result.issues[0].message)

    def test_get_asset_history_keeps_prices_when_metadata_is_missing_but_explicitly_flags_it(self) -> None:
        provider = YFinanceDataProvider(
            ticker_factory=lambda ticker: _FakeTicker(
                history_rows=[
                    (
                        datetime(2026, 4, 2, tzinfo=UTC),
                        {
                            "Close": 42.0,
                            "Volume": 500,
                        },
                    )
                ],
                info={},
            )
        )

        result = provider.get_asset_history("commodities", period="1mo", interval="1d")

        self.assertEqual(result.points[0].close, 42.0)
        self.assertEqual(result.metadata.issues[0].code, "missing_metadata")

    def test_get_proxy_ticker_metadata_rechecks_info_after_history_fallback(self) -> None:
        provider = YFinanceDataProvider(
            ticker_factory=lambda ticker: _FakeTicker(
                info={},
                info_after_history={},
            )
        )

        result = provider.get_proxy_ticker_metadata("reits")

        self.assertEqual(result.issues[0].code, "missing_metadata")

    def test_get_macro_indicators_treats_nan_values_as_missing(self) -> None:
        provider = YFinanceDataProvider(
            ticker_factory=lambda ticker: _FakeTicker(
                history_rows=[
                    (
                        datetime(2026, 4, 2, tzinfo=UTC),
                        {
                            "Close": math.nan,
                        },
                    )
                ]
            )
        )

        result = provider.get_macro_indicators()

        self.assertEqual(result["vix"].status, "missing")
        self.assertIsNone(result["vix"].value)

    def test_get_asset_history_surfaces_nan_fields_as_explicit_issues(self) -> None:
        provider = YFinanceDataProvider(
            ticker_factory=lambda ticker: _FakeTicker(
                history_rows=[
                    (
                        datetime(2026, 4, 2, tzinfo=UTC),
                        {
                            "Open": math.nan,
                            "Close": 42.0,
                            "Volume": math.nan,
                        },
                    )
                ],
                info={"shortName": "Invesco DB Commodity Index Tracking Fund"},
            )
        )

        result = provider.get_asset_history("commodities", period="1mo", interval="1d")

        self.assertIsNone(result.points[0].open)
        self.assertIsNone(result.points[0].volume)
        self.assertEqual(
            [issue.code for issue in result.issues],
            [
                "missing_history_field",
                "missing_history_field",
                "missing_history_field",
                "missing_history_field",
                "missing_history_field",
            ],
        )

    def test_get_asset_history_treats_invalid_numeric_values_as_missing(self) -> None:
        provider = YFinanceDataProvider(
            ticker_factory=lambda ticker: _FakeTicker(
                history_rows=[
                    (
                        datetime(2026, 4, 2, tzinfo=UTC),
                        {
                            "Open": "bad-open",
                            "Close": 42.0,
                            "Volume": "bad-volume",
                        },
                    )
                ],
                info={"shortName": "Invesco DB Commodity Index Tracking Fund"},
            )
        )

        result = provider.get_asset_history("commodities", period="1mo", interval="1d")

        self.assertIsNone(result.points[0].open)
        self.assertIsNone(result.points[0].volume)
        self.assertEqual(
            [issue.code for issue in result.issues],
            [
                "missing_history_field",
                "missing_history_field",
                "missing_history_field",
                "missing_history_field",
                "missing_history_field",
            ],
        )

    def test_get_asset_history_still_fetches_prices_when_metadata_probe_errors(self) -> None:
        provider = YFinanceDataProvider(
            ticker_factory=lambda ticker: _FakeTicker(
                history_rows=[
                    (
                        datetime(2026, 4, 2, tzinfo=UTC),
                        {
                            "Close": 42.0,
                            "Volume": 500,
                        },
                    )
                ],
                info={},
                history_errors=[RuntimeError("metadata probe failed"), None],
            )
        )

        result = provider.get_asset_history("commodities", period="1mo", interval="1d")

        self.assertEqual(result.points[0].close, 42.0)
        self.assertEqual(result.metadata.issues[0].code, "provider_error")
        self.assertEqual(
            [issue.code for issue in result.issues],
            [
                "missing_history_field",
                "missing_history_field",
                "missing_history_field",
                "missing_history_field",
            ],
        )

    def test_get_asset_history_reports_missing_fields_when_source_fields_are_absent_or_none(self) -> None:
        provider = YFinanceDataProvider(
            ticker_factory=lambda ticker: _FakeTicker(
                history_rows=[
                    (
                        datetime(2026, 4, 2, tzinfo=UTC),
                        {
                            "Close": 42.0,
                            "Adj Close": None,
                        },
                    )
                ],
                info={"shortName": "Invesco DB Commodity Index Tracking Fund"},
            )
        )

        result = provider.get_asset_history("commodities", period="1mo", interval="1d")

        self.assertIsNone(result.points[0].open)
        self.assertIsNone(result.points[0].adj_close)
        self.assertEqual(
            [issue.code for issue in result.issues],
            [
                "missing_history_field",
                "missing_history_field",
                "missing_history_field",
                "missing_history_field",
                "missing_history_field",
            ],
        )


if __name__ == "__main__":
    unittest.main()
