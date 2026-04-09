from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

import numpy as np

from core.assets import get_asset
from core.contracts import (
    CROBacktestMetrics,
    CROConcentrationMetrics,
    CROExAnteMetrics,
    CROFactorTilts,
    CROIPSDiagnostic,
    CRORiskReportOutput,
)
from core.utils import ANNUALIZATION_FACTORS


VAR_Z_SCORE_95 = 1.6448536269514722
VAR_PDF_95 = math.exp(-0.5 * VAR_Z_SCORE_95**2) / math.sqrt(2.0 * math.pi)
WEIGHT_TOLERANCE = 1e-8


def calculate_ex_ante_metrics(
    *,
    weights: Mapping[str, float],
    expected_returns: Mapping[str, float],
    covariance_matrix: Sequence[Sequence[float]],
    asset_slugs: Sequence[str] | None = None,
    risk_free_rate: float = 0.0,
) -> CROExAnteMetrics:
    ordered_assets = tuple(asset_slugs or weights.keys())
    weight_vector = _weight_vector(weights, ordered_assets)
    expected_return_vector = _expected_return_vector(expected_returns, ordered_assets)
    covariance = _covariance_matrix(covariance_matrix, ordered_assets)

    portfolio_return = float(weight_vector @ expected_return_vector)
    volatility = float(math.sqrt(max(weight_vector @ covariance @ weight_vector, 0.0)))
    sharpe = 0.0 if volatility == 0.0 else (portfolio_return - risk_free_rate) / volatility
    var_95 = portfolio_return - (VAR_Z_SCORE_95 * volatility)
    cvar_95 = portfolio_return - ((VAR_PDF_95 / 0.05) * volatility)
    return CROExAnteMetrics(
        volatility=volatility,
        portfolio_return=portfolio_return,
        sharpe=sharpe,
        var_95=var_95,
        cvar_95=cvar_95,
    )


def calculate_backtest_metrics(
    *,
    weights: Mapping[str, float],
    asset_returns: Sequence[Sequence[float]] | np.ndarray,
    frequency: str = "monthly",
    asset_slugs: Sequence[str] | None = None,
    risk_free_rate: float = 0.0,
) -> CROBacktestMetrics:
    factor = _annualization_factor(frequency)
    ordered_assets = tuple(asset_slugs or weights.keys())
    weight_vector = _weight_vector(weights, ordered_assets)
    returns_matrix = np.asarray(asset_returns, dtype=float)
    if returns_matrix.ndim != 2 or returns_matrix.shape[1] != len(ordered_assets):
        raise ValueError("asset_returns must be a 2D matrix with one column per asset")

    portfolio_returns = returns_matrix @ weight_vector
    periods = len(portfolio_returns)
    cumulative = np.prod(1.0 + portfolio_returns)
    annual_return = float(cumulative ** (factor / periods) - 1.0)
    annual_vol = float(np.std(portfolio_returns, ddof=1) * math.sqrt(factor)) if periods > 1 else 0.0
    sharpe = 0.0 if annual_vol == 0.0 else (annual_return - risk_free_rate) / annual_vol
    drawdown = max_drawdown(portfolio_returns)
    calmar = 0.0 if drawdown == 0.0 else annual_return / abs(drawdown)
    downside = portfolio_returns[portfolio_returns < 0.0]
    downside_vol = float(np.sqrt(np.mean(np.square(downside))) * math.sqrt(factor)) if len(downside) else 0.0
    sortino = 0.0 if downside_vol == 0.0 else (annual_return - risk_free_rate) / downside_vol
    return CROBacktestMetrics(
        annual_return=annual_return,
        annual_vol=annual_vol,
        sharpe=sharpe,
        max_drawdown=drawdown,
        calmar=calmar,
        sortino_ratio=sortino,
    )


def calculate_concentration_metrics(weights: Mapping[str, float]) -> CROConcentrationMetrics:
    ordered_weights = np.array(list(weights.values()), dtype=float)
    herfindahl = float(np.sum(np.square(ordered_weights)))
    effective_n = 0.0 if herfindahl == 0.0 else 1.0 / herfindahl
    top5 = float(np.sum(np.sort(ordered_weights)[-5:]))
    max_weight = float(np.max(ordered_weights)) if len(ordered_weights) else 0.0
    return CROConcentrationMetrics(
        effective_n=effective_n,
        herfindahl=herfindahl,
        top5_concentration=top5,
        max_weight=max_weight,
    )


def calculate_factor_tilts(
    *,
    weights: Mapping[str, float],
    factor_exposures: Mapping[str, Mapping[str, float]],
) -> CROFactorTilts:
    totals = {"equity_beta": 0.0, "duration": 0.0, "credit_spread": 0.0, "dollar_exposure": 0.0}
    for asset_slug, weight in weights.items():
        exposures = factor_exposures.get(asset_slug, {})
        for name in totals:
            totals[name] += float(weight) * float(exposures.get(name, 0.0))
    return CROFactorTilts(**totals)


def calculate_tracking_error(
    *,
    weights: Mapping[str, float],
    benchmark_weights: Mapping[str, float],
    covariance_matrix: Sequence[Sequence[float]],
    asset_slugs: Sequence[str],
) -> float:
    covariance = _covariance_matrix(covariance_matrix, asset_slugs)
    active = _weight_vector(weights, asset_slugs) - _weight_vector(benchmark_weights, asset_slugs)
    return float(math.sqrt(max(active @ covariance @ active, 0.0)))


def evaluate_ips_compliance(
    *,
    weights: Mapping[str, float],
    covariance_matrix: Sequence[Sequence[float]],
    asset_slugs: Sequence[str],
    benchmark_weights: Mapping[str, float] | None = None,
    tracking_error_budget: float | None = None,
) -> CROIPSDiagnostic:
    weight_violations = _weight_bound_violations(weights=weights, asset_slugs=asset_slugs)
    violations = list(weight_violations)

    tracking_error = 0.0
    within_tracking_budget = True
    if benchmark_weights is not None:
        tracking_error = calculate_tracking_error(
            weights=weights,
            benchmark_weights=benchmark_weights,
            covariance_matrix=covariance_matrix,
            asset_slugs=asset_slugs,
        )
        if tracking_error_budget is not None and tracking_error > tracking_error_budget + WEIGHT_TOLERANCE:
            within_tracking_budget = False
            violations.append(
                f"tracking error {tracking_error:.4f} exceeds budget {tracking_error_budget:.4f}"
            )

    asset_bounds_ok = not weight_violations
    passes = asset_bounds_ok and within_tracking_budget and not violations
    return CROIPSDiagnostic(
        tracking_error=tracking_error,
        within_tracking_budget=within_tracking_budget,
        asset_bounds_ok=asset_bounds_ok,
        passes=passes,
        violations=tuple(violations),
    )


def build_risk_report(
    *,
    method: str,
    weights: Mapping[str, float],
    expected_returns: Mapping[str, float],
    covariance_matrix: Sequence[Sequence[float]],
    historical_returns: Sequence[Sequence[float]] | np.ndarray,
    frequency: str = "monthly",
    benchmark_weights: Mapping[str, float] | None = None,
    tracking_error_budget: float | None = None,
    factor_exposures: Mapping[str, Mapping[str, float]] | None = None,
    risk_free_rate: float = 0.0,
    asset_slugs: Sequence[str] | None = None,
) -> CRORiskReportOutput:
    ordered_assets = tuple(asset_slugs or weights.keys())
    ex_ante = calculate_ex_ante_metrics(
        weights=weights,
        expected_returns=expected_returns,
        covariance_matrix=covariance_matrix,
        asset_slugs=ordered_assets,
        risk_free_rate=risk_free_rate,
    )
    backtest = calculate_backtest_metrics(
        weights=weights,
        asset_returns=historical_returns,
        frequency=frequency,
        asset_slugs=ordered_assets,
        risk_free_rate=risk_free_rate,
    )
    concentration = calculate_concentration_metrics(weights)
    factor_tilts = calculate_factor_tilts(weights=weights, factor_exposures=factor_exposures or {})
    ips = evaluate_ips_compliance(
        weights=weights,
        covariance_matrix=covariance_matrix,
        asset_slugs=ordered_assets,
        benchmark_weights=benchmark_weights,
        tracking_error_budget=tracking_error_budget,
    )
    return CRORiskReportOutput(
        method=method,
        ex_ante=ex_ante,
        backtest=backtest,
        concentration=concentration,
        factor_tilts=factor_tilts,
        ips_compliance=ips,
    )


def max_drawdown(returns: Sequence[float] | np.ndarray) -> float:
    vector = np.asarray(returns, dtype=float)
    wealth = np.cumprod(1.0 + vector)
    peaks = np.maximum.accumulate(wealth)
    drawdowns = (wealth / peaks) - 1.0
    return float(np.min(drawdowns, initial=0.0))


def _annualization_factor(frequency: str) -> int:
    try:
        return ANNUALIZATION_FACTORS[frequency]
    except KeyError as error:
        supported = ", ".join(sorted(ANNUALIZATION_FACTORS))
        raise ValueError(f"Unsupported frequency '{frequency}'. Supported frequencies: {supported}") from error


def _weight_vector(weights: Mapping[str, float], asset_slugs: Sequence[str]) -> np.ndarray:
    return np.array([float(weights.get(asset_slug, 0.0)) for asset_slug in asset_slugs], dtype=float)


def _expected_return_vector(expected_returns: Mapping[str, float], asset_slugs: Sequence[str]) -> np.ndarray:
    missing = [asset_slug for asset_slug in asset_slugs if asset_slug not in expected_returns]
    if missing:
        raise ValueError(f"Missing expected returns for assets: {', '.join(missing)}")
    return np.array([float(expected_returns[asset_slug]) for asset_slug in asset_slugs], dtype=float)


def _covariance_matrix(covariance_matrix: Sequence[Sequence[float]], asset_slugs: Sequence[str]) -> np.ndarray:
    covariance = np.asarray(covariance_matrix, dtype=float)
    expected_shape = (len(asset_slugs), len(asset_slugs))
    if covariance.shape != expected_shape:
        raise ValueError(f"covariance_matrix must have shape {expected_shape}")
    return covariance


def _weight_bound_violations(*, weights: Mapping[str, float], asset_slugs: Sequence[str]) -> tuple[str, ...]:
    violations: list[str] = []
    for asset_slug in asset_slugs:
        asset = get_asset(asset_slug)
        weight = float(weights.get(asset_slug, 0.0))
        if weight < asset.ips_min_weight - WEIGHT_TOLERANCE:
            violations.append(f"{asset_slug} is below min weight {asset.ips_min_weight:.2%}")
        if weight > asset.ips_max_weight + WEIGHT_TOLERANCE:
            violations.append(f"{asset_slug} exceeds max weight {asset.ips_max_weight:.2%}")
    return tuple(violations)
