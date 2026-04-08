from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from core.contracts import IndicatorSnapshot, MacroScores, MacroView
from core.data_fetcher import MacroIndicatorValue, YFinanceDataProvider
from core.utils import write_json, write_markdown


class MacroDataProvider(Protocol):
    def get_macro_indicators(self) -> dict[str, MacroIndicatorValue]: ...


@dataclass(frozen=True, slots=True)
class MacroStageResult:
    macro_view: MacroView
    macro_view_path: Path
    macro_analysis_path: Path
    indicator_diagnostics: dict[str, dict[str, object | None]]
    unsupported_inputs: tuple[str, ...]
    partial_dimensions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _DimensionScore:
    score: int
    interpretation: str
    contributing_indicators: tuple[str, ...]
    partial: bool = False


_REGIME_LABELS = {
    "expansion": "Expansion",
    "late_cycle": "Late Cycle",
    "recovery": "Recovery",
    "recession": "Recession",
}


def run_macro_stage(output_dir: str | Path, data_provider: MacroDataProvider | None = None) -> MacroStageResult:
    provider = data_provider or YFinanceDataProvider()
    indicators = provider.get_macro_indicators()
    timestamp = _latest_timestamp(indicators)

    growth = _score_growth(indicators.get("gdp_growth_yoy"))
    inflation = _score_inflation(indicators.get("cpi_yoy"))
    monetary_policy = _score_monetary_policy(indicators.get("fed_funds_rate"))
    financial_conditions = _score_financial_conditions(
        indicators.get("vix"),
        indicators.get("credit_spreads"),
    )

    scores = MacroScores(
        growth=growth.score,
        inflation=inflation.score,
        monetary_policy=monetary_policy.score,
        financial_conditions=financial_conditions.score,
    )
    composite_score = round(
        0.4 * scores.growth + 0.3 * scores.inflation + 0.2 * scores.monetary_policy + 0.1 * scores.financial_conditions,
        2,
    )
    regime = _classify_regime(composite_score)

    unsupported_inputs = tuple(
        sorted(name for name, indicator in indicators.items() if indicator.status in {"unsupported", "missing", "error"})
    )
    partial_dimensions = ("financial_conditions",) if financial_conditions.partial else ()
    confidence = _confidence_label(indicators, partial_dimensions=(financial_conditions.partial,))

    macro_view = MacroView(
        timestamp=timestamp,
        regime=regime,
        confidence=confidence,
        scores=scores,
        composite_score=composite_score,
        recession_probability=_recession_probability(composite_score),
        key_indicators=IndicatorSnapshot(
            gdp_growth_yoy=_indicator_value(indicators.get("gdp_growth_yoy")),
            cpi_yoy=_indicator_value(indicators.get("cpi_yoy")),
            fed_funds_rate=_indicator_value(indicators.get("fed_funds_rate")),
            vix=_indicator_value(indicators.get("vix")),
            credit_spreads=_indicator_value(indicators.get("credit_spreads")),
        ),
        outlook=_build_outlook(regime, confidence, unsupported_inputs, partial_dimensions),
        risks=_build_risks(regime, unsupported_inputs, partial_dimensions),
        allocation_implications=_allocation_implications(regime, confidence),
    )

    diagnostics = {
        name: {
            "value": indicator.value,
            "as_of": indicator.as_of,
            "source_ticker": indicator.source_ticker,
            "status": indicator.status,
            "message": indicator.message,
        }
        for name, indicator in sorted(indicators.items())
    }
    payload = macro_view.to_dict()
    payload["indicator_diagnostics"] = diagnostics
    payload["unsupported_inputs"] = list(unsupported_inputs)
    payload["partial_dimensions"] = list(partial_dimensions)

    output_root = Path(output_dir)
    macro_view_path = write_json(output_root / "macro_view.json", payload)
    macro_analysis_path = write_markdown(
        output_root / "macro_analysis.md",
        _render_markdown(macro_view, diagnostics, growth, inflation, monetary_policy, financial_conditions),
    )
    return MacroStageResult(
        macro_view=macro_view,
        macro_view_path=macro_view_path,
        macro_analysis_path=macro_analysis_path,
        indicator_diagnostics=diagnostics,
        unsupported_inputs=unsupported_inputs,
        partial_dimensions=partial_dimensions,
    )


def _score_growth(indicator: MacroIndicatorValue | None) -> _DimensionScore:
    if _is_unavailable(indicator):
        return _DimensionScore(0, "Growth input unavailable; defaulted to neutral.", ())
    value = indicator.value or 0.0
    if value >= 3.0:
        return _DimensionScore(2, "Growth is expanding strongly.", ("gdp_growth_yoy",))
    if value >= 2.0:
        return _DimensionScore(1, "Growth is above trend.", ("gdp_growth_yoy",))
    if value >= 1.0:
        return _DimensionScore(0, "Growth is close to trend.", ("gdp_growth_yoy",))
    if value >= 0.0:
        return _DimensionScore(-1, "Growth is softening toward stall speed.", ("gdp_growth_yoy",))
    return _DimensionScore(-2, "Growth is contracting.", ("gdp_growth_yoy",))


def _score_inflation(indicator: MacroIndicatorValue | None) -> _DimensionScore:
    if _is_unavailable(indicator):
        return _DimensionScore(0, "Inflation input unavailable; defaulted to neutral.", ())
    value = indicator.value or 0.0
    if value >= 4.0:
        return _DimensionScore(2, "Inflation is running hot.", ("cpi_yoy",))
    if value >= 3.0:
        return _DimensionScore(1, "Inflation is above target.", ("cpi_yoy",))
    if value >= 2.0:
        return _DimensionScore(0, "Inflation is near target.", ("cpi_yoy",))
    if value >= 0.0:
        return _DimensionScore(-1, "Inflation is subdued.", ("cpi_yoy",))
    return _DimensionScore(-2, "Deflationary pressure is present.", ("cpi_yoy",))


def _score_monetary_policy(indicator: MacroIndicatorValue | None) -> _DimensionScore:
    if _is_unavailable(indicator):
        return _DimensionScore(0, "Policy-rate input unavailable; defaulted to neutral.", ())
    value = indicator.value or 0.0
    if value >= 5.0:
        return _DimensionScore(2, "Policy is restrictive.", ("fed_funds_rate",))
    if value >= 3.0:
        return _DimensionScore(1, "Policy is somewhat restrictive.", ("fed_funds_rate",))
    if value >= 1.0:
        return _DimensionScore(0, "Policy is near neutral.", ("fed_funds_rate",))
    if value >= 0.5:
        return _DimensionScore(-1, "Policy is accommodative.", ("fed_funds_rate",))
    return _DimensionScore(-2, "Policy is near the zero-rate bound.", ("fed_funds_rate",))


def _score_financial_conditions(
    vix_indicator: MacroIndicatorValue | None,
    credit_spread_indicator: MacroIndicatorValue | None,
) -> _DimensionScore:
    contributions: list[int] = []
    inputs: list[str] = []

    if not _is_unavailable(vix_indicator):
        contributions.append(_score_vix(vix_indicator.value or 0.0))
        inputs.append("vix")
    if not _is_unavailable(credit_spread_indicator):
        contributions.append(_score_credit_spreads(credit_spread_indicator.value or 0.0))
        inputs.append("credit_spreads")

    if not contributions:
        return _DimensionScore(0, "Financial conditions inputs unavailable; defaulted to neutral.", (), partial=False)

    score = round(sum(contributions) / len(contributions))
    interpretation = {
        2: "Financial conditions are tight.",
        1: "Financial conditions are somewhat tight.",
        0: "Financial conditions are neutral.",
        -1: "Financial conditions are supportive.",
        -2: "Financial conditions are very easy.",
    }[max(-2, min(2, score))]
    return _DimensionScore(max(-2, min(2, score)), interpretation, tuple(inputs), partial=len(contributions) < 2)


def _score_vix(value: float) -> int:
    if value >= 30.0:
        return 2
    if value >= 22.0:
        return 1
    if value >= 15.0:
        return 0
    if value >= 10.0:
        return -1
    return -2


def _score_credit_spreads(value: float) -> int:
    if value >= 250.0:
        return 2
    if value >= 175.0:
        return 1
    if value >= 125.0:
        return 0
    if value >= 75.0:
        return -1
    return -2


def _classify_regime(composite_score: float) -> str:
    if composite_score > 1.5:
        return "expansion"
    if composite_score > 0.5:
        return "late_cycle"
    if composite_score > -0.5:
        return "recovery"
    return "recession"


def _confidence_label(
    indicators: dict[str, MacroIndicatorValue],
    *,
    partial_dimensions: tuple[bool, ...],
) -> str:
    unavailable_count = sum(1 for indicator in indicators.values() if indicator.status in {"unsupported", "missing", "error"})
    partial_count = sum(1 for partial in partial_dimensions if partial)
    if unavailable_count == 0 and partial_count == 0:
        return "high"
    if unavailable_count <= 1 and partial_count == 0:
        return "medium"
    return "low"


def _recession_probability(composite_score: float) -> float:
    probability = 0.35 - 0.15 * composite_score
    return round(max(0.05, min(0.95, probability)), 2)


def _build_outlook(
    regime: str,
    confidence: str,
    unsupported_inputs: tuple[str, ...],
    partial_dimensions: tuple[str, ...],
) -> str:
    base = {
        "expansion": "Broad macro signals still point to expansion, but downstream assets should watch for overheating.",
        "late_cycle": "The balance of growth, inflation, policy, and conditions points to a late-cycle backdrop.",
        "recovery": "The composite score sits near neutral, consistent with a recovery or transition regime.",
        "recession": "Macro conditions lean recessionary and call for a defensive downstream posture.",
    }[regime]
    limitations: list[str] = []
    if unsupported_inputs:
        limitations.append("Several macro inputs are unavailable from the current provider.")
    if partial_dimensions:
        limitations.append("Some financial-condition indicators are unavailable, so financial conditions are only partially observed.")
    if confidence == "low" and not limitations:
        limitations.append("Signal confidence is low because the available evidence is thin.")
    return " ".join([base, *limitations]).strip()


def _build_risks(
    regime: str,
    unsupported_inputs: tuple[str, ...],
    partial_dimensions: tuple[str, ...],
) -> tuple[str, ...]:
    risks = {
        "expansion": ["Inflation could re-accelerate and provoke tighter policy.", "Rich risk-asset pricing could amplify drawdowns."],
        "late_cycle": ["Policy stays restrictive for longer.", "Funding conditions tighten abruptly if volatility rises."],
        "recovery": ["Mixed data can flip the regime classification quickly.", "Growth momentum may fade before inflation fully normalizes."],
        "recession": ["Earnings revisions may lag the downturn.", "Credit conditions can deteriorate faster than macro releases imply."],
    }[regime]
    if unsupported_inputs:
        risks.append("Unsupported macro series reduce conviction in the regime call.")
    if partial_dimensions:
        risks.append("Credit-spread blind spots can understate funding stress.")
    return tuple(risks[:4])


def _allocation_implications(regime: str, confidence: str) -> str:
    base = {
        "expansion": "Favor pro-growth sleeves while respecting IPS bounds and valuation discipline.",
        "late_cycle": "Lean modestly defensive, emphasize quality, and be selective with duration risk.",
        "recovery": "Keep allocations diversified because the macro picture is balanced rather than decisive.",
        "recession": "Prefer defense, liquidity, and high-quality duration while reviewing cyclical risk budgets.",
    }[regime]
    if confidence == "low":
        return f"{base} Keep changes incremental until more macro series become observable."
    return base


def _render_markdown(
    macro_view: MacroView,
    diagnostics: dict[str, dict[str, object | None]],
    growth: _DimensionScore,
    inflation: _DimensionScore,
    monetary_policy: _DimensionScore,
    financial_conditions: _DimensionScore,
) -> str:
    indicator_rows = [
        ("GDP Growth", diagnostics["gdp_growth_yoy"].get("value"), macro_view.scores.growth, growth.interpretation),
        ("CPI", diagnostics["cpi_yoy"].get("value"), macro_view.scores.inflation, inflation.interpretation),
        (
            "Fed Funds",
            diagnostics["fed_funds_rate"].get("value"),
            macro_view.scores.monetary_policy,
            monetary_policy.interpretation,
        ),
        ("VIX / Credit", _format_financial_value(diagnostics), macro_view.scores.financial_conditions, financial_conditions.interpretation),
    ]
    unsupported_lines = [
        f"- `{name}`: {info['message'] or info['status']}"
        for name, info in diagnostics.items()
        if info["status"] != "ok"
    ]
    unsupported_section = "\n".join(unsupported_lines) if unsupported_lines else "- None"
    risks = "\n".join(f"- {risk}" for risk in macro_view.risks)
    return (
        "# Macro Analysis Report\n"
        f"**Date**: {macro_view.timestamp}\n"
        f"**Regime**: {_REGIME_LABELS[macro_view.regime]} (Confidence: {macro_view.confidence.title()})\n\n"
        "## Executive Summary\n"
        f"{macro_view.outlook}\n\n"
        "## Key Indicators\n"
        "| Indicator | Value | Score | Interpretation |\n"
        "|-----------|-------|-------|----------------|\n"
        + "\n".join(
            f"| {label} | {value if value is not None else 'Unavailable'} | {score:+d} | {interpretation} |"
            for label, value, score, interpretation in indicator_rows
        )
        + "\n\n## Unsupported or Missing Inputs\n"
        + unsupported_section
        + "\n\n## Regime Classification Rationale\n"
        + (
            f"Composite score = {macro_view.composite_score:.2f}, which maps to {_REGIME_LABELS[macro_view.regime]}. "
            "The macro engine keeps unsupported inputs explicit instead of estimating them from unrelated series.\n\n"
        )
        + "## Risks\n"
        + risks
        + "\n\n## Implications for Asset Allocation\n"
        + macro_view.allocation_implications
        + "\n"
    )


def _format_financial_value(diagnostics: dict[str, dict[str, object | None]]) -> str:
    vix = diagnostics["vix"].get("value")
    credit = diagnostics["credit_spreads"].get("value")
    return f"VIX={vix if vix is not None else 'Unavailable'}, Credit={credit if credit is not None else 'Unavailable'}"


def _latest_timestamp(indicators: dict[str, MacroIndicatorValue]) -> str:
    timestamps = [indicator.as_of for indicator in indicators.values() if indicator.as_of]
    if timestamps:
        return max(timestamps)
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _indicator_value(indicator: MacroIndicatorValue | None) -> float | None:
    if indicator is None:
        return None
    return indicator.value


def _is_unavailable(indicator: MacroIndicatorValue | None) -> bool:
    return indicator is None or indicator.status in {"unsupported", "missing", "error"} or indicator.value is None
