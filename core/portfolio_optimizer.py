from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from core.assets import get_asset
from core.contracts import CovarianceOutput, PortfolioProposalOutput
from core.risk_metrics import calculate_concentration_metrics, calculate_ex_ante_metrics


@dataclass(frozen=True, slots=True)
class MethodOptimizationResult:
    weights: np.ndarray
    metadata: dict[str, object]


PortfolioMethod = Callable[..., MethodOptimizationResult]
WEIGHT_TOLERANCE = 1e-8
RISK_PARITY_MAX_ITERATIONS = 5000
RISK_PARITY_TOLERANCE = 5e-4
CATEGORY_BY_METHOD = {
    "equal_weight": "heuristic",
    "inverse_volatility": "heuristic",
    "max_sharpe": "return_optimized",
    "global_min_variance": "risk_structured",
    "risk_parity": "risk_structured",
    "volatility_targeting": "risk_structured",
    "black_litterman": "return_optimized",
    "robust_mean_variance": "return_optimized",
    "mean_downside_risk": "risk_structured",
    "maximum_diversification": "risk_structured",
    "minimum_correlation": "risk_structured",
}


METHOD_REGISTRY: dict[str, PortfolioMethod] = {
    "equal_weight": lambda **kwargs: MethodOptimizationResult(
        weights=_equal_weight_target(kwargs["asset_slugs"]),
        metadata={"optimizer_status": "converged"},
    ),
    "inverse_volatility": lambda **kwargs: MethodOptimizationResult(
        weights=_inverse_volatility_target(kwargs["covariance"]),
        metadata={"optimizer_status": "converged"},
    ),
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
    "volatility_targeting": lambda **kwargs: _volatility_target(
        covariance=kwargs["covariance"],
        expected_returns=kwargs["expected_returns"],
        risk_free_rate=kwargs["risk_free_rate"],
    ),
    "black_litterman": lambda **kwargs: _black_litterman_target(
        covariance=kwargs["covariance"],
        expected_returns=kwargs["expected_returns"],
        risk_free_rate=kwargs["risk_free_rate"],
    ),
    "robust_mean_variance": lambda **kwargs: _robust_mean_variance_target(
        covariance=kwargs["covariance"],
        expected_returns=kwargs["expected_returns"],
        risk_free_rate=kwargs["risk_free_rate"],
    ),
    "mean_downside_risk": lambda **kwargs: _mean_downside_risk_target(
        covariance=kwargs["covariance"],
        expected_returns=kwargs["expected_returns"],
        risk_free_rate=kwargs["risk_free_rate"],
    ),
    "maximum_diversification": lambda **kwargs: _maximum_diversification_target(
        covariance=kwargs["covariance"],
    ),
    "minimum_correlation": lambda **kwargs: _minimum_correlation_target(
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

    optimization_result = optimizer(
        asset_slugs=asset_slugs,
        covariance=covariance,
        expected_returns=expected_return_vector,
        risk_free_rate=risk_free_rate,
    )
    raw_weights = optimization_result.weights
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
        "max_drawdown_available": False,
        "constraint_projection_applied": not np.allclose(raw_weights, weights),
    }
    metadata.update(optimization_result.metadata)
    return PortfolioProposalOutput(
        timestamp=generated_at,
        method=method,
        category=CATEGORY_BY_METHOD[method],
        weights=weight_map,
        expected_return=ex_ante.portfolio_return,
        expected_volatility=ex_ante.volatility,
        sharpe_ratio=ex_ante.sharpe,
        max_drawdown=None,
        effective_n=concentration.effective_n,
        concentration=concentration.herfindahl,
        metadata=metadata,
    )


def run_portfolio_method(
    *,
    method: str,
    covariance_output: CovarianceOutput,
    expected_returns: Mapping[str, float],
    generated_at: str,
    risk_free_rate: float = 0.0,
) -> PortfolioProposalOutput:
    return optimize_portfolio(
        method=method,
        covariance_output=covariance_output,
        expected_returns=expected_returns,
        generated_at=generated_at,
        risk_free_rate=risk_free_rate,
    )


def _equal_weight_target(asset_slugs: Sequence[str]) -> np.ndarray:
    return np.full(len(asset_slugs), 1.0 / len(asset_slugs), dtype=float)


def _inverse_volatility_target(covariance: np.ndarray) -> np.ndarray:
    diagonal = np.diag(covariance)
    if np.any(diagonal <= 0.0):
        raise ValueError("Inverse-volatility weights require strictly positive variances")
    inverse_volatility = 1.0 / np.sqrt(diagonal)
    return inverse_volatility / inverse_volatility.sum()


def _max_sharpe_target(*, covariance: np.ndarray, expected_returns: np.ndarray, risk_free_rate: float) -> MethodOptimizationResult:
    excess_returns = expected_returns - risk_free_rate
    raw = np.linalg.pinv(covariance) @ excess_returns
    raw = np.clip(raw, a_min=0.0, a_max=None)
    if raw.sum() <= WEIGHT_TOLERANCE:
        weights = np.full(len(expected_returns), 1.0 / len(expected_returns), dtype=float)
    else:
        weights = raw / raw.sum()
    return MethodOptimizationResult(weights=weights, metadata={"optimizer_status": "converged"})


def _global_min_variance_target(*, covariance: np.ndarray) -> MethodOptimizationResult:
    raw = np.linalg.pinv(covariance) @ np.ones(covariance.shape[0], dtype=float)
    raw = np.clip(raw, a_min=0.0, a_max=None)
    if raw.sum() <= WEIGHT_TOLERANCE:
        weights = np.full(covariance.shape[0], 1.0 / covariance.shape[0], dtype=float)
    else:
        weights = raw / raw.sum()
    return MethodOptimizationResult(weights=weights, metadata={"optimizer_status": "converged"})


def _risk_parity_target(*, asset_slugs: Sequence[str], covariance: np.ndarray) -> MethodOptimizationResult:
    lower_bounds = np.array([get_asset(asset_slug).ips_min_weight for asset_slug in asset_slugs], dtype=float)
    upper_bounds = np.array([get_asset(asset_slug).ips_max_weight for asset_slug in asset_slugs], dtype=float)
    weights = _feasible_start(lower_bounds, upper_bounds)
    best_weights = weights.copy()
    best_residual = float("inf")
    for _ in range(RISK_PARITY_MAX_ITERATIONS):
        marginal_risk = covariance @ weights
        total_risk = float(weights @ marginal_risk)
        if total_risk <= 0.0:
            raise ValueError("Risk parity did not converge: non-positive portfolio risk encountered")
        contributions = weights * marginal_risk
        target = total_risk / len(weights)
        residual = float(np.max(np.abs(contributions - target)))
        if residual < best_residual:
            best_residual = residual
            best_weights = weights.copy()
        if residual <= RISK_PARITY_TOLERANCE:
            return MethodOptimizationResult(weights=weights, metadata={"optimizer_status": "converged"})
        positive = contributions > WEIGHT_TOLERANCE
        if not np.any(positive):
            raise ValueError("Risk parity did not converge: non-positive risk contributions encountered")
        adjustment = np.ones_like(weights)
        adjustment[positive] = np.sqrt(target / contributions[positive])
        updated = weights * adjustment
        updated = _apply_shared_constraints(asset_slugs=asset_slugs, target_weights=updated)
        if np.linalg.norm(updated - weights, ord=1) <= 1e-8 and np.any(np.isclose(updated, upper_bounds, atol=WEIGHT_TOLERANCE)):
            return MethodOptimizationResult(
                weights=best_weights,
                metadata={
                    "optimizer_status": "bound_limited",
                    "risk_parity_max_residual": best_residual,
                },
            )
        weights = updated
    raise ValueError("Risk parity did not converge within iteration budget")


def _volatility_target(
    *,
    covariance: np.ndarray,
    expected_returns: np.ndarray,
    risk_free_rate: float,
) -> MethodOptimizationResult:
    max_sharpe = _max_sharpe_target(
        covariance=covariance,
        expected_returns=expected_returns,
        risk_free_rate=risk_free_rate,
    ).weights
    inverse_vol = _inverse_volatility_target(covariance)
    current_volatility = _portfolio_volatility(covariance=covariance, weights=max_sharpe)
    target_volatility = min(
        float(np.median(np.sqrt(np.diag(covariance)))),
        current_volatility * 0.85,
    )
    if current_volatility <= WEIGHT_TOLERANCE:
        weights = inverse_vol
    else:
        blend_to_defensive = min(1.0, target_volatility / current_volatility)
        weights = (blend_to_defensive * max_sharpe) + ((1.0 - blend_to_defensive) * inverse_vol)
        weights = weights / weights.sum()
    return MethodOptimizationResult(
        weights=weights,
        metadata={
            "optimizer_status": "converged",
            "target_volatility": target_volatility,
            "base_portfolio_volatility": current_volatility,
        },
    )


def _black_litterman_target(
    *,
    covariance: np.ndarray,
    expected_returns: np.ndarray,
    risk_free_rate: float,
) -> MethodOptimizationResult:
    equilibrium_weights = np.full(len(expected_returns), 1.0 / len(expected_returns), dtype=float)
    implied_returns = covariance @ equilibrium_weights
    implied_returns = implied_returns / max(float(np.mean(implied_returns)), WEIGHT_TOLERANCE)
    implied_returns = implied_returns * float(np.mean(expected_returns))
    posterior = (0.65 * expected_returns) + (0.35 * implied_returns)
    result = _max_sharpe_target(
        covariance=covariance,
        expected_returns=posterior,
        risk_free_rate=risk_free_rate,
    )
    metadata = dict(result.metadata)
    metadata["posterior_expected_returns"] = posterior.tolist()
    metadata["implied_equilibrium_returns"] = implied_returns.tolist()
    return MethodOptimizationResult(weights=result.weights, metadata=metadata)


def _robust_mean_variance_target(
    *,
    covariance: np.ndarray,
    expected_returns: np.ndarray,
    risk_free_rate: float,
) -> MethodOptimizationResult:
    mean_return = float(np.mean(expected_returns))
    shrunk_returns = (0.5 * expected_returns) + (0.5 * mean_return)
    ridge = (np.trace(covariance) / covariance.shape[0]) * 0.05
    robust_covariance = covariance + (ridge * np.eye(covariance.shape[0], dtype=float))
    result = _max_sharpe_target(
        covariance=robust_covariance,
        expected_returns=shrunk_returns,
        risk_free_rate=risk_free_rate,
    )
    metadata = dict(result.metadata)
    metadata["expected_return_shrinkage"] = 0.5
    metadata["covariance_ridge_penalty"] = ridge
    return MethodOptimizationResult(weights=result.weights, metadata=metadata)


def _mean_downside_risk_target(
    *,
    covariance: np.ndarray,
    expected_returns: np.ndarray,
    risk_free_rate: float,
) -> MethodOptimizationResult:
    downside_proxy = np.sqrt(np.diag(covariance))
    excess_returns = np.clip(expected_returns - risk_free_rate, a_min=0.0, a_max=None)
    score = excess_returns / np.maximum(downside_proxy**2, WEIGHT_TOLERANCE)
    if score.sum() <= WEIGHT_TOLERANCE:
        weights = _inverse_volatility_target(covariance)
    else:
        weights = score / score.sum()
    return MethodOptimizationResult(
        weights=weights,
        metadata={
            "optimizer_status": "converged",
            "downside_risk_proxy": downside_proxy.tolist(),
        },
    )


def _maximum_diversification_target(*, covariance: np.ndarray) -> MethodOptimizationResult:
    asset_volatility = np.sqrt(np.diag(covariance))
    raw = np.linalg.pinv(covariance) @ asset_volatility
    raw = np.clip(raw, a_min=0.0, a_max=None)
    if raw.sum() <= WEIGHT_TOLERANCE:
        weights = _inverse_volatility_target(covariance)
    else:
        weights = raw / raw.sum()
    return MethodOptimizationResult(
        weights=weights,
        metadata={
            "optimizer_status": "converged",
            "diversification_objective": "maximize_diversification_ratio",
        },
    )


def _minimum_correlation_target(*, covariance: np.ndarray) -> MethodOptimizationResult:
    asset_volatility = np.sqrt(np.diag(covariance))
    denominator = np.outer(asset_volatility, asset_volatility)
    correlation = np.divide(
        covariance,
        denominator,
        out=np.eye(covariance.shape[0], dtype=float),
        where=denominator > WEIGHT_TOLERANCE,
    )
    average_correlation = (correlation.sum(axis=1) - 1.0) / max(covariance.shape[0] - 1, 1)
    raw = 1.0 / np.maximum(average_correlation * np.maximum(asset_volatility, WEIGHT_TOLERANCE), 0.01)
    weights = raw / raw.sum()
    return MethodOptimizationResult(
        weights=weights,
        metadata={
            "optimizer_status": "converged",
            "average_correlation_by_asset": average_correlation.tolist(),
        },
    )


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


def _portfolio_volatility(*, covariance: np.ndarray, weights: np.ndarray) -> float:
    return float(np.sqrt(max(weights @ covariance @ weights, 0.0)))
