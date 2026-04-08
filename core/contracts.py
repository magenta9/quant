from __future__ import annotations

import math
from dataclasses import dataclass, fields
from typing import Any, Literal

VALID_MACRO_REGIMES = {"expansion", "late_cycle", "recession", "recovery"}
VALID_CONFIDENCE_LEVELS = {"low", "medium", "high"}
WEIGHT_SUM_TOLERANCE = 1e-6


def _json_ready(value: Any) -> Any:
    if isinstance(value, SerializableContract):
        return value.to_dict()
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    return value


@dataclass(frozen=True, slots=True)
class SerializableContract:
    def to_dict(self) -> dict[str, Any]:
        return {field.name: _json_ready(getattr(self, field.name)) for field in fields(self)}


@dataclass(frozen=True, slots=True)
class MacroScores(SerializableContract):
    growth: int
    inflation: int
    monetary_policy: int
    financial_conditions: int


@dataclass(frozen=True, slots=True)
class IndicatorSnapshot(SerializableContract):
    gdp_growth_yoy: float | None
    cpi_yoy: float | None
    fed_funds_rate: float | None
    vix: float | None
    credit_spreads: float | None


@dataclass(frozen=True, slots=True)
class MacroView(SerializableContract):
    timestamp: str
    regime: Literal["expansion", "late_cycle", "recession", "recovery"]
    confidence: Literal["low", "medium", "high"]
    scores: MacroScores
    composite_score: float
    recession_probability: float
    key_indicators: IndicatorSnapshot
    outlook: str
    risks: tuple[str, ...] = ()
    allocation_implications: str = ""

    def __post_init__(self) -> None:
        if self.regime not in VALID_MACRO_REGIMES:
            raise ValueError(f"regime must be one of {sorted(VALID_MACRO_REGIMES)}")
        if self.confidence not in VALID_CONFIDENCE_LEVELS:
            raise ValueError(f"confidence must be one of {sorted(VALID_CONFIDENCE_LEVELS)}")


@dataclass(frozen=True, slots=True)
class CMAMethodEstimate(SerializableContract):
    name: str
    expected_return: float | None
    confidence: float | None
    available: bool = True
    rationale: str = ""
    required_inputs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AssetCMAOutput(SerializableContract):
    asset_slug: str
    generated_at: str
    selected_method: str
    selected_expected_return: float
    selected_confidence: float
    methods: tuple[CMAMethodEstimate, ...]
    support_signals: dict[str, str]
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        low, high = self.method_return_range
        if not low <= self.selected_expected_return <= high:
            raise ValueError("selected_expected_return must lie within method_return_range")

    @property
    def method_return_range(self) -> tuple[float, float]:
        returns = [method.expected_return for method in self.methods if method.available]
        if not returns:
            raise ValueError("at least one available CMA method is required")
        return (min(returns), max(returns))

    def to_dict(self) -> dict[str, Any]:
        payload = super().to_dict()
        payload["method_return_range"] = list(self.method_return_range)
        return payload


@dataclass(frozen=True, slots=True)
class AssetSignals(SerializableContract):
    asset_slug: str
    momentum: str
    trend: str
    mean_reversion: str
    valuation: str


@dataclass(frozen=True, slots=True)
class AssetHistoricalStats(SerializableContract):
    asset_slug: str
    annual_return: float
    annual_volatility: float
    sharpe_ratio: float
    max_drawdown: float


@dataclass(frozen=True, slots=True)
class AssetScenario(SerializableContract):
    name: str
    expected_return: float
    probability: float


@dataclass(frozen=True, slots=True)
class AssetCorrelationRow(SerializableContract):
    asset_slug: str
    correlations: dict[str, float]


@dataclass(frozen=True, slots=True)
class CorrelationMatrix(SerializableContract):
    values: tuple[tuple[float, ...], ...]


@dataclass(frozen=True, slots=True)
class CovarianceOutput(SerializableContract):
    generated_at: str
    asset_slugs: tuple[str, ...]
    covariance_matrix: tuple[tuple[float, ...], ...]
    correlation_matrix: CorrelationMatrix
    lookback_months: int
    annualization_factor: int
    shrinkage_method: str
    regime_adjustment: str

    def __post_init__(self) -> None:
        expected = len(self.asset_slugs)
        if len(self.covariance_matrix) != expected:
            raise ValueError("covariance_matrix row count must match asset_slugs")
        if any(len(row) != expected for row in self.covariance_matrix):
            raise ValueError("covariance_matrix must be square")
        if len(self.correlation_matrix.values) != expected:
            raise ValueError("correlation_matrix row count must match asset_slugs")
        if any(len(row) != expected for row in self.correlation_matrix.values):
            raise ValueError("correlation_matrix must be square")


@dataclass(frozen=True, slots=True)
class PortfolioProposalOutput(SerializableContract):
    timestamp: str
    method: str
    category: str
    weights: dict[str, float]
    expected_return: float
    expected_volatility: float
    sharpe_ratio: float
    max_drawdown: float | None
    effective_n: float
    concentration: float
    metadata: dict[str, Any]

    def __post_init__(self) -> None:
        if any(weight < 0 for weight in self.weights.values()):
            raise ValueError("weights must be non-negative")
        if not math.isclose(sum(self.weights.values()), 1.0, rel_tol=0.0, abs_tol=WEIGHT_SUM_TOLERANCE):
            raise ValueError("weights must sum to 1 within tolerance")


@dataclass(frozen=True, slots=True)
class CROExAnteMetrics(SerializableContract):
    volatility: float
    portfolio_return: float
    sharpe: float
    var_95: float
    cvar_95: float

    def to_dict(self) -> dict[str, Any]:
        payload = super().to_dict()
        payload["return"] = payload.pop("portfolio_return")
        return payload


@dataclass(frozen=True, slots=True)
class CROBacktestMetrics(SerializableContract):
    annual_return: float
    annual_vol: float
    sharpe: float
    max_drawdown: float
    calmar: float
    sortino_ratio: float


@dataclass(frozen=True, slots=True)
class CROConcentrationMetrics(SerializableContract):
    effective_n: float
    herfindahl: float
    top5_concentration: float
    max_weight: float


@dataclass(frozen=True, slots=True)
class CROFactorTilts(SerializableContract):
    equity_beta: float
    duration: float
    credit_spread: float
    dollar_exposure: float = 0.0


@dataclass(frozen=True, slots=True)
class CROIPSDiagnostic(SerializableContract):
    tracking_error: float
    within_tracking_budget: bool
    asset_bounds_ok: bool
    passes: bool
    violations: tuple[str, ...]
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        has_failure_signal = (not self.within_tracking_budget) or (not self.asset_bounds_ok) or bool(self.violations)
        if self.passes and has_failure_signal:
            raise ValueError("passes cannot be true when component checks or violations indicate failure")
        if not self.passes and not has_failure_signal:
            raise ValueError("passes cannot be false when all component checks pass and no violations exist")


@dataclass(frozen=True, slots=True)
class CRORiskReportOutput(SerializableContract):
    method: str
    ex_ante: CROExAnteMetrics
    backtest: CROBacktestMetrics
    concentration: CROConcentrationMetrics
    factor_tilts: CROFactorTilts
    ips_compliance: CROIPSDiagnostic


@dataclass(frozen=True, slots=True)
class TopPosition(SerializableContract):
    asset: str
    weight: float
    risk_contrib: float


@dataclass(frozen=True, slots=True)
class CIOBoardMemoOutput(SerializableContract):
    selected_ensemble: str
    ensemble_weights: dict[str, float]
    portfolio_summary: dict[str, float]
    allocation_by_asset_class: dict[str, float]
    top_positions: tuple[TopPosition, ...]
    changes_since_last_review: tuple[str, ...]
    key_risks_to_monitor: tuple[str, ...]
    rebalancing_plan: str
    ips_compliance_statement: str
