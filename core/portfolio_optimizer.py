from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence

import numpy as np

from core.assets import get_asset
from core.contracts import CovarianceOutput, PortfolioProposalOutput
from core.risk_metrics import calculate_concentration_metrics, calculate_ex_ante_metrics


PortfolioMethod = Callable[..., np.ndarray]
WEIGHT_TOLERANCE = 1e-8
CATEGORY_BY_METHOD = {
    "equal_weight": "heuristic",
    "inverse_volatility": "heuristic",
    "max_sharpe": "return_optimized",
    "global_min_variance": "risk_optimized",
    "risk_parity": "risk_optimized",
}


METHOD_REGISTRY: dict[str, PortfolioMethod] = {
    "equal_weight": lambda **kwargs: _equal_weight_target(kwargs["asset_slugs"]),
    "inverse_volatility": lambda **kwargs: _inverse_volatility_target(kwargs["covariance"]),
    "max_sharpe": lambda **kwargs: _max_sharpe_target(
        covariance=kwargs["covariance"],
        expected_returns=kwargs["expected_returns"],
        risk_free_rate=kwargs["risk_free_rate"],
    ),
    "global_min_variance": lambda **kwargs: _global_min_variance_target(
        covariance=kwargs["covariance"],
    ),
    "risk_parity": lambda **kwargs: _risk_parity_target(
        asset_slugs=kwargs["asset_slugs"],
        covariance=kwargs["covariance"],
    ),
}


def optimize_portfolio(
    *,
    method: str,
    covariance_output: CovarianceOutput,
    expected_returns: Mapping[str, float],
    generated_at: str,
    risk_free_rate: float = 0.0,
) -> PortfolioProposalOutput:
    try:
        optimizer = METHOD_REGISTRY[method]
    except KeyError as error:
        supported = ", ".join(METHOD_REGISTRY)
        raise ValueError(f"Unknown portfolio method '{method}'. Supported methods: {supported}") from error

    asset_slugs = covariance_output.asset_slugs
    covariance = np.asarray(covariance_output.covariance_matrix, dtype=float)
    expected_return_vector = np.array([float(expected_returns[asset_slug]) for asset_slug in asset_slugs], dtype=float)
    _validate_ips_bounds(asset_slugs)

    raw_weights = optimizer(
        asset_slugs=asset_slugs,
        covariance=covariance,
        expected_returns=expected_return_vector,
        risk_free_rate=risk_free_rate,
    )
    weights = _apply_shared_constraints(asset_slugs=asset_slugs, target_weights=raw_weights)
    weight_map = {asset_slug: float(weight) for asset_slug, weight in zip(asset_slugs, weights, strict=True)}

    ex_ante = calculate_ex_ante_metrics(
        weights=weight_map,
        expected_returns=expected_returns,
        covariance_matrix=covariance_output.covariance_matrix,
        asset_slugs=asset_slugs,
        risk_free_rate=risk_free_rate,
    )
    concentration = calculate_concentration_metrics(weight_map)
    metadata = {
        "ips_constraints": {
            asset_slug: {
                "min_weight": get_asset(asset_slug).ips_min_weight,
                "max_weight": get_asset(asset_slug).ips_max_weight,
            }
            for asset_slug in asset_slugs
        },
        "annualization_factor": covariance_output.annualization_factor,
        "shrinkage_method": covariance_output.shrinkage_method,
        "risk_free_rate": risk_free_rate,
        "max_drawdown_proxy": "var_95",
        "constraint_projection_applied": not np.allclose(raw_weights, weights),
    }
    return PortfolioProposalOutput(
        timestamp=generated_at,
        method=method,
        category=CATEGORY_BY_METHOD[method],
        weights=weight_map,
        expected_return=ex_ante.portfolio_return,
        expected_volatility=ex_ante.volatility,
        sharpe_ratio=ex_ante.sharpe,
        max_drawdown=ex_ante.var_95,
        effective_n=concentration.effective_n,
        concentration=concentration.herfindahl,
        metadata=metadata,
    )


def _equal_weight_target(asset_slugs: Sequence[str]) -> np.ndarray:
    return np.full(len(asset_slugs), 1.0 / len(asset_slugs), dtype=float)


def _inverse_volatility_target(covariance: np.ndarray) -> np.ndarray:
    diagonal = np.diag(covariance)
    if np.any(diagonal <= 0.0):
        raise ValueError("Inverse-volatility weights require strictly positive variances")
    inverse_volatility = 1.0 / np.sqrt(diagonal)
    return inverse_volatility / inverse_volatility.sum()


def _max_sharpe_target(*, covariance: np.ndarray, expected_returns: np.ndarray, risk_free_rate: float) -> np.ndarray:
    excess_returns = expected_returns - risk_free_rate
    raw = np.linalg.pinv(covariance) @ excess_returns
    raw = np.clip(raw, a_min=0.0, a_max=None)
    if raw.sum() <= WEIGHT_TOLERANCE:
        return np.full(len(expected_returns), 1.0 / len(expected_returns), dtype=float)
    return raw / raw.sum()


def _global_min_variance_target(*, covariance: np.ndarray) -> np.ndarray:
    raw = np.linalg.pinv(covariance) @ np.ones(covariance.shape[0], dtype=float)
    raw = np.clip(raw, a_min=0.0, a_max=None)
    if raw.sum() <= WEIGHT_TOLERANCE:
        return np.full(covariance.shape[0], 1.0 / covariance.shape[0], dtype=float)
    return raw / raw.sum()


def _risk_parity_target(*, asset_slugs: Sequence[str], covariance: np.ndarray) -> np.ndarray:
    lower_bounds = np.array([get_asset(asset_slug).ips_min_weight for asset_slug in asset_slugs], dtype=float)
    upper_bounds = np.array([get_asset(asset_slug).ips_max_weight for asset_slug in asset_slugs], dtype=float)
    weights = _feasible_start(lower_bounds, upper_bounds)
    for _ in range(250):
        marginal_risk = covariance @ weights
        total_risk = float(weights @ marginal_risk)
        if total_risk <= 0.0:
            break
        contributions = weights * marginal_risk
        target = total_risk / len(weights)
        adjustment = np.ones_like(weights)
        positive = contributions > WEIGHT_TOLERANCE
        adjustment[positive] = np.sqrt(target / contributions[positive])
        updated = weights * adjustment
        updated = _apply_shared_constraints(asset_slugs=asset_slugs, target_weights=updated)
        if np.linalg.norm(updated - weights, ord=1) <= 1e-10:
            return updated
        weights = updated
    return weights


def _apply_shared_constraints(*, asset_slugs: Sequence[str], target_weights: np.ndarray) -> np.ndarray:
    target = np.asarray(target_weights, dtype=float)
    if target.shape != (len(asset_slugs),):
        raise ValueError("target_weights must align with asset_slugs")

    lower_bounds = np.array([get_asset(asset_slug).ips_min_weight for asset_slug in asset_slugs], dtype=float)
    upper_bounds = np.array([get_asset(asset_slug).ips_max_weight for asset_slug in asset_slugs], dtype=float)

    if lower_bounds.sum() > 1.0 + WEIGHT_TOLERANCE or upper_bounds.sum() < 1.0 - WEIGHT_TOLERANCE:
        raise ValueError("Infeasible IPS bounds for selected asset universe")
    weights = np.clip(target, lower_bounds, upper_bounds)
    if weights.sum() <= WEIGHT_TOLERANCE:
        weights = _feasible_start(lower_bounds, upper_bounds)
    else:
        weights = weights / weights.sum()

    for _ in range(100):
        weights = np.clip(weights, lower_bounds, upper_bounds)
        total = weights.sum()
        gap = 1.0 - total
        if abs(gap) <= WEIGHT_TOLERANCE:
            return weights / weights.sum()

        adjustable = upper_bounds - weights if gap > 0.0 else weights - lower_bounds
        adjustable = np.clip(adjustable, a_min=0.0, a_max=None)
        if adjustable.sum() <= WEIGHT_TOLERANCE:
            raise ValueError("Infeasible IPS bounds for selected asset universe")
        weights = weights + (gap * (adjustable / adjustable.sum()))

    raise ValueError("Infeasible IPS bounds for selected asset universe")


def _feasible_start(lower_bounds: np.ndarray, upper_bounds: np.ndarray) -> np.ndarray:
    if lower_bounds.sum() > 1.0 + WEIGHT_TOLERANCE or upper_bounds.sum() < 1.0 - WEIGHT_TOLERANCE:
        raise ValueError("Infeasible IPS bounds for selected asset universe")
    weights = lower_bounds.copy()
    slack = upper_bounds - lower_bounds
    remaining = 1.0 - weights.sum()
    if remaining > 0.0:
        weights += remaining * (slack / slack.sum())
    return weights / weights.sum()


def _validate_ips_bounds(asset_slugs: Sequence[str]) -> None:
    minimum_total = sum(get_asset(asset_slug).ips_min_weight for asset_slug in asset_slugs)
    maximum_total = sum(get_asset(asset_slug).ips_max_weight for asset_slug in asset_slugs)
    if minimum_total > 1.0 + WEIGHT_TOLERANCE or maximum_total < 1.0 - WEIGHT_TOLERANCE:
        raise ValueError("Infeasible IPS bounds for selected asset universe")
