from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from core.contracts import CorrelationMatrix, CovarianceOutput
from core.data_fetcher import AssetHistoryResult
from core.utils import ANNUALIZATION_FACTORS


SUPPORTED_FREQUENCIES = frozenset(ANNUALIZATION_FACTORS)


def annualization_factor_for_frequency(frequency: str) -> int:
    try:
        return ANNUALIZATION_FACTORS[frequency]
    except KeyError as error:
        supported = ", ".join(sorted(SUPPORTED_FREQUENCIES))
        raise ValueError(f"Unsupported frequency '{frequency}'. Supported frequencies: {supported}") from error


def ledoit_wolf_shrinkage(returns: np.ndarray) -> np.ndarray:
    matrix = np.asarray(returns, dtype=float)
    if matrix.ndim != 2:
        raise ValueError("returns must be a 2D array")
    sample_count, feature_count = matrix.shape
    if sample_count < 2:
        raise ValueError("at least two return observations are required")

    centered = matrix - matrix.mean(axis=0, keepdims=True)
    sample_covariance = (centered.T @ centered) / sample_count
    mu = float(np.trace(sample_covariance) / feature_count)
    target = mu * np.eye(feature_count)

    delta = float(np.sum((sample_covariance - target) ** 2))
    if delta <= 0.0:
        return sample_covariance

    beta = 0.0
    for row in centered:
        beta += float(np.sum((np.outer(row, row) - sample_covariance) ** 2))
    beta /= sample_count**2

    shrinkage = min(max(beta / delta, 0.0), 1.0)
    return (shrinkage * target) + ((1.0 - shrinkage) * sample_covariance)


def estimate_covariance(
    histories: Mapping[str, AssetHistoryResult],
    *,
    asset_slugs: Sequence[str],
    frequency: str = "monthly",
    lookback_months: int = 60,
    generated_at: str,
    shrinkage_method: str = "ledoit_wolf",
    regime_adjustment: str = "none",
) -> CovarianceOutput:
    factor = annualization_factor_for_frequency(frequency)
    returns_matrix = _build_aligned_returns_matrix(
        histories=histories,
        asset_slugs=asset_slugs,
        lookback_months=lookback_months,
        frequency=frequency,
    )

    if shrinkage_method != "ledoit_wolf":
        raise ValueError("Only ledoit_wolf shrinkage is supported in the MVP")

    covariance = ledoit_wolf_shrinkage(returns_matrix) * factor
    correlation = covariance_to_correlation(covariance)

    return CovarianceOutput(
        generated_at=generated_at,
        asset_slugs=tuple(asset_slugs),
        covariance_matrix=tuple(tuple(float(value) for value in row) for row in covariance),
        correlation_matrix=CorrelationMatrix(
            values=tuple(tuple(float(value) for value in row) for row in correlation)
        ),
        lookback_months=lookback_months,
        annualization_factor=factor,
        shrinkage_method=shrinkage_method,
        regime_adjustment=regime_adjustment,
    )


def covariance_to_correlation(covariance: np.ndarray) -> np.ndarray:
    matrix = np.asarray(covariance, dtype=float)
    diagonal = np.sqrt(np.clip(np.diag(matrix), a_min=0.0, a_max=None))
    denominator = np.outer(diagonal, diagonal)
    with np.errstate(divide="ignore", invalid="ignore"):
        correlation = np.divide(matrix, denominator, out=np.zeros_like(matrix), where=denominator > 0.0)
    np.fill_diagonal(correlation, 1.0)
    return correlation


def _build_aligned_returns_matrix(
    *,
    histories: Mapping[str, AssetHistoryResult],
    asset_slugs: Sequence[str],
    lookback_months: int,
    frequency: str,
) -> np.ndarray:
    if lookback_months <= 0:
        raise ValueError("lookback_months must be positive")

    return_maps = {slug: _history_returns_by_timestamp(histories[slug]) for slug in asset_slugs}
    common_timestamps = set.intersection(*(set(values) for values in return_maps.values()))
    if not common_timestamps:
        raise ValueError("No overlapping return timestamps were found for the requested assets")

    ordered_timestamps = sorted(common_timestamps)
    lookback_periods = max(2, round(lookback_months * annualization_factor_for_frequency(frequency) / 12))
    selected_timestamps = ordered_timestamps[-lookback_periods:]
    if len(selected_timestamps) < 2:
        raise ValueError("At least two aligned return observations are required to estimate covariance")

    return np.array(
        [[return_maps[slug][timestamp] for slug in asset_slugs] for timestamp in selected_timestamps],
        dtype=float,
    )


def _history_returns_by_timestamp(history: AssetHistoryResult) -> dict[str, float]:
    prices: list[tuple[str, float]] = []
    for point in history.points:
        price = _extract_price(point)
        if price is None:
            continue
        prices.append((point.timestamp, price))

    if len(prices) < 2:
        raise ValueError(f"Asset history for {history.asset_slug} does not contain enough price points")

    returns: dict[str, float] = {}
    for previous, current in zip(prices, prices[1:]):
        previous_timestamp, previous_price = previous
        current_timestamp, current_price = current
        if previous_price <= 0.0:
            raise ValueError(f"Asset history for {history.asset_slug} contains a non-positive price at {previous_timestamp}")
        returns[current_timestamp] = (current_price / previous_price) - 1.0
    return returns


def _extract_price(point: Any) -> float | None:
    if point.adj_close is not None:
        return float(point.adj_close)
    if point.close is not None:
        return float(point.close)
    return None
