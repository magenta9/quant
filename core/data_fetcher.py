from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import math
from typing import Any, Callable, Literal

from core.assets import get_asset


TickerFactory = Callable[[str], Any]


@dataclass(frozen=True, slots=True)
class DataFetchIssue:
    code: str
    message: str
    ticker: str | None = None
    indicator: str | None = None


@dataclass(frozen=True, slots=True)
class ProxyTickerMetadata:
    asset_slug: str
    ticker: str
    short_name: str | None
    currency: str | None
    exchange: str | None
    quote_type: str | None
    issues: tuple[DataFetchIssue, ...] = ()


@dataclass(frozen=True, slots=True)
class HistoricalPricePoint:
    timestamp: str
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    adj_close: float | None
    volume: int | None


@dataclass(frozen=True, slots=True)
class AssetHistoryResult:
    asset_slug: str
    ticker: str
    metadata: ProxyTickerMetadata
    points: tuple[HistoricalPricePoint, ...]
    issues: tuple[DataFetchIssue, ...] = ()


@dataclass(frozen=True, slots=True)
class MacroIndicatorValue:
    name: str
    value: float | None
    as_of: str | None
    source_ticker: str | None
    status: Literal["ok", "missing", "unsupported", "error"]
    message: str = ""


@dataclass(frozen=True, slots=True)
class _MacroIndicatorSpec:
    name: str
    ticker: str | None
    field: str = "Close"
    unsupported_message: str | None = None


class YFinanceDataProvider:
    _MACRO_INDICATORS: tuple[_MacroIndicatorSpec, ...] = (
        _MacroIndicatorSpec(
            name="gdp_growth_yoy",
            ticker=None,
            unsupported_message="No direct Yahoo Finance mapping for GDP growth in the MVP provider.",
        ),
        _MacroIndicatorSpec(
            name="cpi_yoy",
            ticker=None,
            unsupported_message="No direct Yahoo Finance mapping for CPI in the MVP provider.",
        ),
        _MacroIndicatorSpec(
            name="fed_funds_rate",
            ticker=None,
            unsupported_message="No direct Yahoo Finance mapping for the Fed Funds Rate in the MVP provider.",
        ),
        _MacroIndicatorSpec(name="vix", ticker="^VIX"),
        _MacroIndicatorSpec(
            name="credit_spreads",
            ticker=None,
            unsupported_message="No direct Yahoo Finance mapping for credit spreads in the MVP provider.",
        ),
    )

    def __init__(self, ticker_factory: TickerFactory | None = None) -> None:
        self._ticker_factory = ticker_factory or self._default_ticker_factory

    def get_macro_indicators(self) -> dict[str, MacroIndicatorValue]:
        results: dict[str, MacroIndicatorValue] = {}
        for spec in self._MACRO_INDICATORS:
            if spec.ticker is None:
                results[spec.name] = MacroIndicatorValue(
                    name=spec.name,
                    value=None,
                    as_of=None,
                    source_ticker=None,
                    status="unsupported",
                    message=spec.unsupported_message or "Unsupported indicator.",
                )
                continue

            try:
                history = self._ticker_factory(spec.ticker).history(period="1mo", interval="1d", auto_adjust=False)
            except Exception as error:
                results[spec.name] = MacroIndicatorValue(
                    name=spec.name,
                    value=None,
                    as_of=None,
                    source_ticker=spec.ticker,
                    status="error",
                    message=str(error),
                )
                continue

            latest_point = self._last_history_point(history)
            if latest_point is None or latest_point.close is None:
                results[spec.name] = MacroIndicatorValue(
                    name=spec.name,
                    value=None,
                    as_of=None if latest_point is None else latest_point.timestamp,
                    source_ticker=spec.ticker,
                    status="missing",
                    message=f"No {spec.field} value returned for {spec.ticker}.",
                )
                continue

            results[spec.name] = MacroIndicatorValue(
                name=spec.name,
                value=latest_point.close,
                as_of=latest_point.timestamp,
                source_ticker=spec.ticker,
                status="ok",
            )

        return results

    def get_asset_history(self, asset_slug: str, *, period: str = "max", interval: str = "1mo") -> AssetHistoryResult:
        asset = get_asset(asset_slug)
        metadata = self.get_proxy_ticker_metadata(asset_slug)

        if any(issue.code == "provider_error" for issue in metadata.issues):
            return AssetHistoryResult(
                asset_slug=asset_slug,
                ticker=asset.proxy_ticker,
                metadata=metadata,
                points=(),
                issues=tuple(issue for issue in metadata.issues if issue.code == "provider_error"),
            )

        try:
            history = self._ticker_factory(asset.proxy_ticker).history(period=period, interval=interval, auto_adjust=False)
        except Exception as error:
            issue = DataFetchIssue(code="provider_error", message=str(error), ticker=asset.proxy_ticker)
            return AssetHistoryResult(
                asset_slug=asset_slug,
                ticker=asset.proxy_ticker,
                metadata=metadata,
                points=(),
                issues=(issue,),
            )

        points: list[HistoricalPricePoint] = []
        issues: list[DataFetchIssue] = []
        for index, row in history.iterrows():
            point, point_issues = self._coerce_history_point(index, row, asset.proxy_ticker)
            points.append(point)
            issues.extend(point_issues)

        if not points:
            issue = DataFetchIssue(
                code="missing_history",
                message=f"No price history returned for ticker {asset.proxy_ticker}.",
                ticker=asset.proxy_ticker,
            )
            return AssetHistoryResult(
                asset_slug=asset_slug,
                ticker=asset.proxy_ticker,
                metadata=metadata,
                points=(),
                issues=(issue,),
            )

        return AssetHistoryResult(
            asset_slug=asset_slug,
            ticker=asset.proxy_ticker,
            metadata=metadata,
            points=tuple(points),
            issues=tuple(issues),
        )

    def get_proxy_ticker_metadata(self, asset_slug: str) -> ProxyTickerMetadata:
        asset = get_asset(asset_slug)
        try:
            ticker = self._ticker_factory(asset.proxy_ticker)
            info = getattr(ticker, "info", {}) or {}
            if not info:
                ticker.history(period="5d", interval="1d", auto_adjust=False)
                info = getattr(ticker, "info", {}) or {}
        except Exception as error:
            issue = DataFetchIssue(code="provider_error", message=str(error), ticker=asset.proxy_ticker)
            return ProxyTickerMetadata(
                asset_slug=asset_slug,
                ticker=asset.proxy_ticker,
                short_name=None,
                currency=None,
                exchange=None,
                quote_type=None,
                issues=(issue,),
            )

        return ProxyTickerMetadata(
            asset_slug=asset_slug,
            ticker=asset.proxy_ticker,
            short_name=info.get("shortName"),
            currency=info.get("currency"),
            exchange=info.get("exchange"),
            quote_type=info.get("quoteType"),
            issues=self._metadata_issues(asset.proxy_ticker, info),
        )

    @staticmethod
    def _default_ticker_factory(ticker: str) -> Any:
        try:
            import yfinance as yf
        except ModuleNotFoundError as error:  # pragma: no cover - environment dependent
            raise RuntimeError("yfinance is required to use YFinanceDataProvider.") from error
        return yf.Ticker(ticker)

    @staticmethod
    def _last_history_point(history: Any) -> HistoricalPricePoint | None:
        points = [YFinanceDataProvider._coerce_history_point(index, row, None)[0] for index, row in history.iterrows()]
        if not points:
            return None
        return points[-1]

    @staticmethod
    def _coerce_history_point(
        index: Any,
        row: Any,
        ticker: str | None,
    ) -> tuple[HistoricalPricePoint, tuple[DataFetchIssue, ...]]:
        row_values = row.to_dict() if hasattr(row, "to_dict") else dict(row)
        field_map = {
            "Open": YFinanceDataProvider._coerce_float(row_values.get("Open")),
            "High": YFinanceDataProvider._coerce_float(row_values.get("High")),
            "Low": YFinanceDataProvider._coerce_float(row_values.get("Low")),
            "Close": YFinanceDataProvider._coerce_float(row_values.get("Close")),
            "Adj Close": YFinanceDataProvider._coerce_float(row_values.get("Adj Close")),
            "Volume": YFinanceDataProvider._coerce_int(row_values.get("Volume")),
        }
        timestamp = YFinanceDataProvider._serialize_timestamp(index)
        issues = tuple(
            DataFetchIssue(
                code="missing_history_field",
                message=f"Missing {field_name} value for ticker {ticker} at {timestamp}.",
                ticker=ticker,
            )
            for field_name, raw_value in row_values.items()
            if field_name in field_map and raw_value is not None and field_map[field_name] is None
        )
        return HistoricalPricePoint(
            timestamp=YFinanceDataProvider._serialize_timestamp(index),
            open=field_map["Open"],
            high=field_map["High"],
            low=field_map["Low"],
            close=field_map["Close"],
            adj_close=field_map["Adj Close"],
            volume=field_map["Volume"],
        ), issues

    @staticmethod
    def _serialize_timestamp(value: Any) -> str:
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, date):
            return value.isoformat()
        return str(value)

    @staticmethod
    def _coerce_float(value: Any) -> float | None:
        if value is None or YFinanceDataProvider._is_missing_number(value):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _coerce_int(value: Any) -> int | None:
        if value is None or YFinanceDataProvider._is_missing_number(value):
            return None
        try:
            return int(value)
        except (TypeError, ValueError, OverflowError):
            return None

    @staticmethod
    def _is_missing_number(value: Any) -> bool:
        try:
            import pandas as pd
        except ModuleNotFoundError:
            pd = None

        if pd is not None:
            try:
                return bool(pd.isna(value))
            except Exception:
                pass

        try:
            return math.isnan(float(value))
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _metadata_issues(ticker: str, info: dict[str, Any]) -> tuple[DataFetchIssue, ...]:
        if any(info.get(field) is not None for field in ("shortName", "currency", "exchange", "quoteType")):
            return ()
        return (
            DataFetchIssue(
                code="missing_metadata",
                message=f"No proxy metadata fields were returned for ticker {ticker}.",
                ticker=ticker,
            ),
        )
