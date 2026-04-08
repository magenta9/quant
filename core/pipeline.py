from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from core.assets import ASSET_DEFINITIONS, ASSET_ORDER, get_asset
from core.cma_builder import AssetAnalysisResult, run_asset_analysis
from core.contracts import CROIPSDiagnostic, CRORiskReportOutput
from core.covariance import _build_aligned_returns_matrix, estimate_covariance
from core.data_fetcher import AssetHistoryResult, YFinanceDataProvider
from core.database import (
    initialize_database,
    persist_cma_methods,
    persist_macro_view,
    persist_portfolio_stage,
)
from core.macro_analyzer import MacroStageResult, run_macro_stage
from core.portfolio_optimizer import METHOD_REGISTRY, optimize_portfolio
from core.risk_metrics import build_risk_report
from core.utils import ensure_directory, generate_run_id, write_json

MVP_PORTFOLIO_METHODS = (
    "equal_weight",
    "inverse_volatility",
    "max_sharpe",
    "global_min_variance",
    "risk_parity",
)


class Phase2DataProvider(Protocol):
    def get_macro_indicators(self) -> object: ...

    def get_asset_history(self, asset_slug: str, *, period: str = "max", interval: str = "1mo") -> object: ...


@dataclass(frozen=True, slots=True)
class Phase2PipelineResult:
    run_id: str
    run_directory: Path
    ips_assets: tuple[str, ...]
    macro_result: MacroStageResult
    asset_results: tuple[AssetAnalysisResult, ...]
    covariance_output: object
    portfolio_proposals: tuple[object, ...]
    risk_reports: tuple[object, ...]
    database_path: Path


def run_phase2_pipeline(
    *,
    ips_path: str | Path = "config/ips.md",
    output_root: str | Path = "output/runs",
    database_path: str | Path = "database/portfolio.db",
    data_provider: Phase2DataProvider | None = None,
    run_id: str | None = None,
) -> Phase2PipelineResult:
    ips_assets = parse_ips_assets(ips_path)
    if ips_assets != ASSET_ORDER:
        raise ValueError(
            f"Phase 2 expects all 18 registered assets in configured order. Found {len(ips_assets)} assets instead."
        )

    provider = _CachingPipelineProvider(data_provider or YFinanceDataProvider())
    resolved_database_path = initialize_database(database_path)
    active_run_id = run_id or generate_run_id()
    run_directory = ensure_directory(Path(output_root) / active_run_id)
    macro_directory = ensure_directory(run_directory / "macro")
    assets_directory = ensure_directory(run_directory / "assets")
    covariance_directory = ensure_directory(run_directory / "covariance")
    portfolio_directory = ensure_directory(run_directory / "portfolio")
    risk_directory = ensure_directory(run_directory / "risk")

    macro_result = run_macro_stage(output_dir=macro_directory, data_provider=provider)
    persist_macro_view(resolved_database_path, macro_result.macro_view)

    asset_results: list[AssetAnalysisResult] = []
    for asset_slug in ips_assets:
        result = run_asset_analysis(
            asset_slug=asset_slug,
            macro_view=macro_result.macro_view,
            output_dir=assets_directory / asset_slug,
            data_provider=provider,
        )
        persist_cma_methods(
            resolved_database_path,
            asset_slug=asset_slug,
            timestamp=macro_result.macro_view.timestamp,
            methods=result.cma_output.methods,
        )
        asset_results.append(result)

    histories = {asset_slug: provider.get_asset_history(asset_slug, interval="1mo") for asset_slug in ips_assets}
    covariance_output = estimate_covariance(
        histories=histories,
        asset_slugs=ips_assets,
        frequency="monthly",
        lookback_months=60,
        generated_at=macro_result.macro_view.timestamp,
    )
    write_json(covariance_directory / "covariance.json", covariance_output.to_dict())

    expected_returns = {
        result.asset_slug: result.cma_output.selected_expected_return
        for result in asset_results
    }
    historical_returns = _build_aligned_returns_matrix(
        histories=histories,
        asset_slugs=ips_assets,
        lookback_months=covariance_output.lookback_months,
        frequency="monthly",
    )
    risk_free_rate = _normalize_rate(macro_result.macro_view.key_indicators.fed_funds_rate)
    benchmark_weights = build_ips_benchmark_weights(ips_assets)
    tracking_error_budget = parse_tracking_error_budget(ips_path)

    portfolio_proposals = []
    risk_reports = []
    for method in MVP_PORTFOLIO_METHODS:
        if method not in METHOD_REGISTRY:
            raise ValueError(f"MVP portfolio method '{method}' is not registered")
        proposal = optimize_portfolio(
            method=method,
            covariance_output=covariance_output,
            expected_returns=expected_returns,
            generated_at=macro_result.macro_view.timestamp,
            risk_free_rate=risk_free_rate,
        )
        portfolio_proposals.append(proposal)

        risk_report = build_risk_report(
            method=method,
            weights=proposal.weights,
            expected_returns=expected_returns,
            covariance_matrix=covariance_output.covariance_matrix,
            historical_returns=historical_returns,
            frequency="monthly",
            benchmark_weights=benchmark_weights,
            tracking_error_budget=tracking_error_budget,
            risk_free_rate=risk_free_rate,
            factor_exposures=build_factor_exposures(ips_assets),
            asset_slugs=ips_assets,
        )
        risk_report = annotate_projection_warnings(risk_report, proposal=proposal)
        risk_reports.append(risk_report)

    portfolio_proposals = tuple(portfolio_proposals)
    risk_reports = tuple(risk_reports)
    persist_portfolio_stage(
        resolved_database_path,
        proposals=portfolio_proposals,
        risk_reports=tuple((macro_result.macro_view.timestamp, risk_report) for risk_report in risk_reports),
    )
    for proposal in portfolio_proposals:
        write_json(portfolio_directory / proposal.method / "proposal.json", proposal.to_dict())
    for risk_report in risk_reports:
        write_json(risk_directory / risk_report.method / "risk_report.json", risk_report.to_dict())

    return Phase2PipelineResult(
        run_id=active_run_id,
        run_directory=run_directory,
        ips_assets=ips_assets,
        macro_result=macro_result,
        asset_results=tuple(asset_results),
        covariance_output=covariance_output,
        portfolio_proposals=portfolio_proposals,
        risk_reports=risk_reports,
        database_path=resolved_database_path,
    )


def parse_ips_assets(ips_path: str | Path) -> tuple[str, ...]:
    asset_name_to_slug = {asset.name: asset.slug for asset in ASSET_DEFINITIONS}
    discovered_assets: list[str] = []
    for raw_line in Path(ips_path).read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line.startswith("|") or line.startswith("|-------") or "Asset | Benchmark" in line:
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 4:
            continue
        asset_name = cells[0]
        slug = asset_name_to_slug.get(asset_name)
        if slug is not None:
            discovered_assets.append(slug)
    return tuple(discovered_assets)


def parse_tracking_error_budget(ips_path: str | Path) -> float | None:
    pattern = re.compile(r"Tracking Error vs 60/40\*\*: Maximum (\d+(?:\.\d+)?)% annualized")
    for raw_line in Path(ips_path).read_text(encoding="utf-8").splitlines():
        match = pattern.search(raw_line)
        if match:
            return float(match.group(1)) / 100.0
    return None


def build_ips_benchmark_weights(asset_slugs: tuple[str, ...]) -> dict[str, float]:
    equity_assets = [asset_slug for asset_slug in asset_slugs if get_asset(asset_slug).group == "equity"]
    fixed_income_assets = [asset_slug for asset_slug in asset_slugs if get_asset(asset_slug).group == "fixed_income"]
    benchmark_weights = {asset_slug: 0.0 for asset_slug in asset_slugs}

    if equity_assets:
        equity_weight = 0.60 / len(equity_assets)
        for asset_slug in equity_assets:
            benchmark_weights[asset_slug] = equity_weight
    if fixed_income_assets:
        fixed_income_weight = 0.40 / len(fixed_income_assets)
        for asset_slug in fixed_income_assets:
            benchmark_weights[asset_slug] = fixed_income_weight
    return benchmark_weights


def build_factor_exposures(asset_slugs: tuple[str, ...]) -> dict[str, dict[str, float]]:
    exposures: dict[str, dict[str, float]] = {}
    for asset_slug in asset_slugs:
        asset = get_asset(asset_slug)
        exposures[asset_slug] = {
            "equity_beta": 1.0 if asset.group == "equity" else 0.35 if asset.group == "real_assets" else 0.0,
            "duration": 8.0 if asset.category == "treasury" else 5.0 if "fixed_income" in asset.category or asset.category == "credit" else 0.0,
            "credit_spread": 1.0 if asset.category in {"credit", "international_fixed_income", "emerging_fixed_income"} else 0.0,
            "dollar_exposure": 1.0 if asset_slug != "gold" else -0.2,
        }
    return exposures


def annotate_projection_warnings(risk_report: CRORiskReportOutput, *, proposal: object) -> CRORiskReportOutput:
    if not proposal.metadata.get("constraint_projection_applied"):
        return risk_report
    warnings = risk_report.ips_compliance.warnings + (
        "optimizer raw weights breached IPS bounds; deterministic projection applied before reporting",
    )
    return CRORiskReportOutput(
        method=risk_report.method,
        ex_ante=risk_report.ex_ante,
        backtest=risk_report.backtest,
        concentration=risk_report.concentration,
        factor_tilts=risk_report.factor_tilts,
        ips_compliance=CROIPSDiagnostic(
            tracking_error=risk_report.ips_compliance.tracking_error,
            within_tracking_budget=risk_report.ips_compliance.within_tracking_budget,
            asset_bounds_ok=risk_report.ips_compliance.asset_bounds_ok,
            passes=risk_report.ips_compliance.passes,
            violations=risk_report.ips_compliance.violations,
            warnings=warnings,
        ),
    )


def _normalize_rate(raw_rate: float | None) -> float:
    if raw_rate is None:
        return 0.0
    return raw_rate / 100.0 if raw_rate > 1.0 else raw_rate


@dataclass(slots=True)
class _CachingPipelineProvider:
    inner: Phase2DataProvider
    _history_cache: dict[tuple[str, str, str], AssetHistoryResult] = field(init=False, default_factory=dict)

    def get_macro_indicators(self) -> object:
        return self.inner.get_macro_indicators()

    def get_asset_history(self, asset_slug: str, *, period: str = "max", interval: str = "1mo") -> AssetHistoryResult:
        cache_key = (asset_slug, period, interval)
        if cache_key not in self._history_cache:
            self._history_cache[cache_key] = self.inner.get_asset_history(
                asset_slug,
                period=period,
                interval=interval,
            )
        return self._history_cache[cache_key]
