from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, pstdev
from typing import Protocol

from core.assets import get_asset
from core.contracts import (
    AssetCMAOutput,
    AssetCorrelationRow,
    AssetHistoricalStats,
    AssetScenario,
    AssetSignals,
    CMAMethodEstimate,
    MacroView,
)
from core.data_fetcher import AssetHistoryResult, YFinanceDataProvider
from core.utils import write_json, write_markdown


REGIME_MULTIPLIERS = {
    "expansion": 1.2,
    "late_cycle": 0.8,
    "recovery": 1.0,
    "recession": 0.5,
}

STUB_METHODS = {
    "black_litterman": {
        "rationale": "Deferred to a later phase because it depends on cross-asset covariance and equilibrium inputs not owned by this todo.",
        "required_inputs": ("covariance_matrix", "market_cap_weights", "investor_views"),
    },
    "inverse_gordon": {
        "rationale": "Structured stub: this method needs paid/vendor data for dividend yield, earnings growth, and buyback yield.",
        "required_inputs": ("dividend_yield", "earnings_growth_consensus", "buyback_yield"),
    },
    "implied_erp": {
        "rationale": "Structured stub: this method needs paid/vendor data for CAPE and long-run valuation inputs.",
        "required_inputs": ("cape_ratio", "long_run_inflation", "valuation_mean_reversion"),
    },
    "survey_consensus": {
        "rationale": "Structured stub: this method needs paid/vendor data from survey and analyst consensus sources.",
        "required_inputs": ("wall_street_consensus", "imf_forecasts", "fed_sep"),
    },
}


class AssetDataProvider(Protocol):
    def get_asset_history(self, asset_slug: str, *, period: str = "max", interval: str = "1mo") -> AssetHistoryResult: ...


@dataclass(frozen=True, slots=True)
class AssetAnalysisResult:
    asset_slug: str
    cma_output: AssetCMAOutput
    signals: AssetSignals
    historical_stats: AssetHistoricalStats
    scenarios: tuple[AssetScenario, ...]
    correlation_row: AssetCorrelationRow
    artifact_paths: dict[str, Path]
    stubbed_methods: tuple[str, ...]


def run_asset_analysis(
    *,
    asset_slug: str,
    macro_view: MacroView,
    output_dir: str | Path,
    data_provider: AssetDataProvider | None = None,
) -> AssetAnalysisResult:
    provider = data_provider or YFinanceDataProvider()
    asset = get_asset(asset_slug)
    history = provider.get_asset_history(asset_slug, interval="1mo")
    monthly_returns = _monthly_returns(history)
    risk_free_rate = _normalize_rate(macro_view.key_indicators.fed_funds_rate)

    annual_return = _annualized_return(monthly_returns)
    annual_volatility = _annualized_volatility(monthly_returns)
    sharpe_ratio = 0.0 if annual_volatility == 0 else (annual_return - risk_free_rate) / annual_volatility
    max_drawdown = _max_drawdown(monthly_returns)

    historical_stats = AssetHistoricalStats(
        asset_slug=asset_slug,
        annual_return=round(annual_return, 4),
        annual_volatility=round(annual_volatility, 4),
        sharpe_ratio=round(sharpe_ratio, 4),
        max_drawdown=round(max_drawdown, 4),
    )
    signals = _build_signals(asset_slug, monthly_returns, macro_view)

    historical_erp = max(annual_return - risk_free_rate, -0.99)
    historical_method = CMAMethodEstimate(
        name="historical_erp",
        expected_return=round(historical_erp + risk_free_rate, 4),
        confidence=0.6,
        rationale="Historical annualized return decomposed into trailing excess return plus current risk-free rate.",
        required_inputs=("asset_history", "risk_free_rate"),
    )
    regime_adjusted_method = CMAMethodEstimate(
        name="regime_adjusted_erp",
        expected_return=round((historical_erp * REGIME_MULTIPLIERS[macro_view.regime]) + risk_free_rate, 4),
        confidence=0.7,
        rationale=f"Adjusted the trailing excess return by the {macro_view.regime} regime multiplier.",
        required_inputs=("asset_history", "risk_free_rate", "macro_regime"),
    )

    available_methods = (historical_method, regime_adjusted_method)
    auto_blend = _build_auto_blend(available_methods)
    stub_methods = tuple(_build_stub_method(name) for name in STUB_METHODS)
    methods = available_methods + stub_methods + (auto_blend,)
    selected_method, selected_expected_return, selected_confidence, notes = _select_final_cma(
        macro_view=macro_view,
        methods=methods,
    )

    cma_output = AssetCMAOutput(
        asset_slug=asset_slug,
        generated_at=macro_view.timestamp,
        selected_method=selected_method,
        selected_expected_return=selected_expected_return,
        selected_confidence=selected_confidence,
        methods=methods,
        support_signals={
            "momentum": signals.momentum,
            "trend": signals.trend,
            "mean_reversion": signals.mean_reversion,
            "valuation": signals.valuation,
        },
        notes=notes,
    )

    scenarios = _build_scenarios(cma_output.selected_expected_return, historical_stats.annual_volatility)
    correlation_row = AssetCorrelationRow(asset_slug=asset_slug, correlations={asset_slug: 1.0})

    output_root = Path(output_dir)
    stubbed_methods = tuple(method.name for method in methods if not method.available)
    cma_methods_payload = {
        "asset_slug": asset_slug,
        "generated_at": macro_view.timestamp,
        "macro_regime": macro_view.regime,
        "methods": [method.to_dict() for method in methods],
        "stubbed_methods": list(stubbed_methods),
    }
    artifact_paths = {
        "cma_methods": write_json(output_root / "cma_methods.json", cma_methods_payload),
        "cma": write_json(output_root / "cma.json", cma_output.to_dict()),
        "signals": write_json(output_root / "signals.json", signals.to_dict()),
        "historical_stats": write_json(output_root / "historical_stats.json", historical_stats.to_dict()),
        "scenarios": write_json(output_root / "scenarios.json", {"asset_slug": asset_slug, "scenarios": [scenario.to_dict() for scenario in scenarios]}),
        "correlation_row": write_json(output_root / "correlation_row.json", correlation_row.to_dict()),
        "analysis": write_markdown(
            output_root / "analysis.md",
            _render_analysis(
                asset_name=asset.name,
                asset_slug=asset_slug,
                macro_view=macro_view,
                cma_output=cma_output,
                historical_stats=historical_stats,
                stubbed_methods=stubbed_methods,
            ),
        ),
    }
    return AssetAnalysisResult(
        asset_slug=asset_slug,
        cma_output=cma_output,
        signals=signals,
        historical_stats=historical_stats,
        scenarios=scenarios,
        correlation_row=correlation_row,
        artifact_paths=artifact_paths,
        stubbed_methods=stubbed_methods,
    )


def _monthly_returns(history: AssetHistoryResult) -> tuple[float, ...]:
    prices = [point.adj_close if point.adj_close is not None else point.close for point in history.points]
    clean_prices = [price for price in prices if price is not None]
    if len(clean_prices) < 2:
        raise ValueError(f"Asset '{history.asset_slug}' does not have enough monthly history for CMA analysis.")
    returns = tuple((current / previous) - 1 for previous, current in zip(clean_prices, clean_prices[1:]))
    if not returns:
        raise ValueError(f"Asset '{history.asset_slug}' did not yield any monthly returns.")
    return returns


def _annualized_return(monthly_returns: tuple[float, ...]) -> float:
    cumulative = math.prod(1 + period_return for period_return in monthly_returns)
    return cumulative ** (12 / len(monthly_returns)) - 1


def _normalize_rate(raw_rate: float | None) -> float:
    if raw_rate is None:
        return 0.0
    normalized = raw_rate / 100 if raw_rate > 1 else raw_rate
    return max(normalized, 0.0)


def _annualized_volatility(monthly_returns: tuple[float, ...]) -> float:
    if len(monthly_returns) < 2:
        return 0.0
    return pstdev(monthly_returns) * math.sqrt(12)


def _max_drawdown(monthly_returns: tuple[float, ...]) -> float:
    wealth = 1.0
    peak = 1.0
    max_drawdown = 0.0
    for period_return in monthly_returns:
        wealth *= 1 + period_return
        peak = max(peak, wealth)
        max_drawdown = min(max_drawdown, (wealth / peak) - 1)
    return max_drawdown


def _build_auto_blend(methods: tuple[CMAMethodEstimate, ...]) -> CMAMethodEstimate:
    weighted_sum = sum((method.expected_return or 0.0) * (method.confidence or 0.0) for method in methods if method.available)
    total_confidence = sum(method.confidence or 0.0 for method in methods if method.available)
    confidence = 0.0 if total_confidence == 0 else sum((method.confidence or 0.0) ** 2 for method in methods if method.available) / total_confidence
    return CMAMethodEstimate(
        name="auto_blend",
        expected_return=round(weighted_sum / total_confidence, 4) if total_confidence else None,
        confidence=round(confidence, 4) if total_confidence else None,
        rationale="Confidence-weighted blend of the currently available Phase 2 CMA methods.",
        required_inputs=tuple(method.name for method in methods if method.available),
    )


def _build_stub_method(name: str) -> CMAMethodEstimate:
    definition = STUB_METHODS[name]
    return CMAMethodEstimate(
        name=name,
        expected_return=None,
        confidence=None,
        available=False,
        rationale=definition["rationale"],
        required_inputs=definition["required_inputs"],
    )


def _select_final_cma(*, macro_view: MacroView, methods: tuple[CMAMethodEstimate, ...]) -> tuple[str, float, float, tuple[str, ...]]:
    available_methods = {method.name: method for method in methods if method.available}
    returns = [method.expected_return for method in available_methods.values() if method.expected_return is not None]
    if not returns:
        raise ValueError("At least one available CMA method must have a numeric expected return.")
    spread = max(returns) - min(returns)
    notes: list[str] = []

    if macro_view.regime == "recession":
        if spread >= 0.03:
            notes.append("Recession regime with meaningful dispersion: favor the defensive regime-adjusted estimate.")
            chosen = available_methods["regime_adjusted_erp"]
            return chosen.name, chosen.expected_return or 0.0, chosen.confidence or 0.0, tuple(notes)
        notes.append("Recession regime observed, but available methods remain tightly clustered so the MVP judge keeps the auto-blend.")

    if spread < 0.03:
        notes.append("Available methods are tightly clustered, so the MVP judge accepts the auto-blend.")
    else:
        notes.append("Method dispersion is wider, but valuation-forward methods are stubbed in the MVP; defaulting to the blend.")
    chosen = available_methods["auto_blend"]
    return chosen.name, chosen.expected_return or 0.0, chosen.confidence or 0.0, tuple(notes)


def _build_signals(asset_slug: str, monthly_returns: tuple[float, ...], macro_view: MacroView) -> AssetSignals:
    trailing_3 = sum(monthly_returns[-3:]) if len(monthly_returns) >= 3 else sum(monthly_returns)
    trailing_12 = mean(monthly_returns[-12:]) if len(monthly_returns) >= 12 else mean(monthly_returns)
    last_return = monthly_returns[-1]
    momentum = "positive" if trailing_3 > 0.01 else "negative" if trailing_3 < -0.01 else "neutral"
    trend = "up" if trailing_12 > 0 else "down" if trailing_12 < 0 else "flat"
    mean_reversion = "stretched" if last_return > trailing_12 + 0.01 else "oversold" if last_return < trailing_12 - 0.01 else "balanced"
    valuation = "conservative" if macro_view.regime == "recession" else "balanced" if macro_view.regime == "recovery" else "watch_richness"
    return AssetSignals(
        asset_slug=asset_slug,
        momentum=momentum,
        trend=trend,
        mean_reversion=mean_reversion,
        valuation=valuation,
    )


def _build_scenarios(selected_return: float, annual_volatility: float) -> tuple[AssetScenario, ...]:
    bull = AssetScenario(name="bull", expected_return=round(selected_return + annual_volatility, 4), probability=0.2)
    base = AssetScenario(name="base", expected_return=round(selected_return, 4), probability=0.6)
    bear = AssetScenario(name="bear", expected_return=round(selected_return - annual_volatility, 4), probability=0.2)
    return (bull, base, bear)


def _render_analysis(
    *,
    asset_name: str,
    asset_slug: str,
    macro_view: MacroView,
    cma_output: AssetCMAOutput,
    historical_stats: AssetHistoricalStats,
    stubbed_methods: tuple[str, ...],
) -> str:
    return (
        f"# {asset_name} CMA Analysis\n"
        f"- Asset slug: `{asset_slug}`\n"
        f"- Macro regime: `{macro_view.regime}`\n"
        f"- Selected method: `{cma_output.selected_method}`\n"
        f"- Selected expected return: {cma_output.selected_expected_return:.2%}\n\n"
        "## Historical Summary\n"
        f"- Annual return: {historical_stats.annual_return:.2%}\n"
        f"- Annual volatility: {historical_stats.annual_volatility:.2%}\n"
        f"- Sharpe ratio: {historical_stats.sharpe_ratio:.2f}\n"
        f"- Max drawdown: {historical_stats.max_drawdown:.2%}\n\n"
        "## Judge Notes\n"
        + "\n".join(f"- {note}" for note in cma_output.notes)
        + "\n\n## Stubbed methods\n"
        + ("\n".join(f"- {name}" for name in stubbed_methods) if stubbed_methods else "- None")
        + "\n"
    )
