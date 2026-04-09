from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from core.assets import GROUPS, get_asset
from core.contracts import CIOBoardMemoOutput, CRORiskReportOutput, PortfolioProposalOutput, TopPosition
from core.risk_metrics import calculate_concentration_metrics

SUPPORTED_ENSEMBLES = ("simple_average", "composite_score_weighting")
_WEIGHT_TOLERANCE = 1e-12


@dataclass(frozen=True, slots=True)
class EnsembleCandidate:
    selected_ensemble: str
    ensemble_weights: dict[str, float]
    weights: dict[str, float]
    portfolio_summary: dict[str, float]
    allocation_by_asset_class: dict[str, float]
    top_positions: tuple[TopPosition, ...]
    key_risks_to_monitor: tuple[str, ...]
    ips_compliance_statement: str
    rationale: str


def build_ensemble_candidate(
    *,
    ensemble_method: str,
    proposals: Sequence[PortfolioProposalOutput],
    risk_reports: Sequence[CRORiskReportOutput],
) -> EnsembleCandidate:
    if ensemble_method not in SUPPORTED_ENSEMBLES:
        supported = ", ".join(SUPPORTED_ENSEMBLES)
        raise ValueError(f"Unsupported ensemble_method '{ensemble_method}'. Supported methods: {supported}")

    aligned_pairs = _align_inputs(proposals=proposals, risk_reports=risk_reports)
    ensemble_weights = _ensemble_weights(ensemble_method=ensemble_method, aligned_pairs=aligned_pairs)
    blended_weights = _blend_asset_weights(aligned_pairs=aligned_pairs, ensemble_weights=ensemble_weights)
    concentration = calculate_concentration_metrics(blended_weights)
    portfolio_summary = {
        "expected_return": _weighted_average(ensemble_weights, aligned_pairs, lambda proposal, _: proposal.expected_return),
        "expected_volatility": _weighted_average(ensemble_weights, aligned_pairs, lambda proposal, _: proposal.expected_volatility),
        "sharpe_ratio": _weighted_average(ensemble_weights, aligned_pairs, lambda proposal, _: proposal.sharpe_ratio),
        "effective_n": concentration.effective_n,
        "tracking_error_vs_60_40": _weighted_average(
            ensemble_weights,
            aligned_pairs,
            lambda _, risk_report: risk_report.ips_compliance.tracking_error,
        ),
    }
    ips_compliant = all(
        risk_report.ips_compliance.passes
        for method, (_, risk_report) in aligned_pairs.items()
        if ensemble_weights.get(method, 0.0) > _WEIGHT_TOLERANCE
    )
    ips_compliance_statement = "COMPLIANT" if ips_compliant else "NON-COMPLIANT"
    top_positions = tuple(
        TopPosition(asset=asset_slug, weight=weight, risk_contrib=risk_contrib)
        for asset_slug, weight, risk_contrib in _top_position_rows(
            aligned_pairs=aligned_pairs,
            ensemble_weights=ensemble_weights,
            blended_weights=blended_weights,
        )[:5]
    )
    supporting_methods = ", ".join(
        method
        for method, _weight in sorted(ensemble_weights.items(), key=lambda item: (-item[1], item[0]))
        if _weight > _WEIGHT_TOLERANCE
    )
    rationale = (
        f"{ensemble_method} emphasizes {supporting_methods or 'all methods equally'} "
        f"and yields {ips_compliance_statement.lower()} CIO inputs."
    )
    if supporting_methods:
        rationale = f"{rationale} Top contributors: {supporting_methods}."
    return EnsembleCandidate(
        selected_ensemble=ensemble_method,
        ensemble_weights=ensemble_weights,
        weights=blended_weights,
        portfolio_summary=portfolio_summary,
        allocation_by_asset_class=_allocation_by_asset_class(blended_weights),
        top_positions=top_positions,
        key_risks_to_monitor=_collect_key_risks(risk_reports),
        ips_compliance_statement=ips_compliance_statement,
        rationale=rationale,
    )


def select_cio_ensemble(
    *,
    proposals: Sequence[PortfolioProposalOutput],
    risk_reports: Sequence[CRORiskReportOutput],
) -> CIOBoardMemoOutput:
    selected = _select_best_candidate(proposals=proposals, risk_reports=risk_reports)
    return _candidate_to_board_memo(selected)


def _select_best_candidate(
    *,
    proposals: Sequence[PortfolioProposalOutput],
    risk_reports: Sequence[CRORiskReportOutput],
) -> EnsembleCandidate:
    candidates = tuple(
        build_ensemble_candidate(
            ensemble_method=ensemble_method,
            proposals=proposals,
            risk_reports=risk_reports,
        )
        for ensemble_method in SUPPORTED_ENSEMBLES
    )
    selected = max(candidates, key=lambda candidate: (_candidate_rank(candidate), candidate.selected_ensemble))
    contributor_text = ", ".join(
        method
        for method, weight in sorted(selected.ensemble_weights.items(), key=lambda item: (-item[1], item[0]))
        if weight > _WEIGHT_TOLERANCE
    )
    compliance_phrase = (
        "preserved IPS compliance"
        if selected.ips_compliance_statement == "COMPLIANT"
        else "did not preserve IPS compliance"
    )
    rationale = (
        f"Selected {selected.selected_ensemble} because it {compliance_phrase} and concentrated CIO support in "
        f"{contributor_text or 'the available methods'} while keeping tracking error at "
        f"{selected.portfolio_summary['tracking_error_vs_60_40']:.2%}."
    )
    return EnsembleCandidate(
        selected_ensemble=selected.selected_ensemble,
        ensemble_weights=selected.ensemble_weights,
        weights=selected.weights,
        portfolio_summary=selected.portfolio_summary,
        allocation_by_asset_class=selected.allocation_by_asset_class,
        top_positions=selected.top_positions,
        key_risks_to_monitor=selected.key_risks_to_monitor,
        ips_compliance_statement=selected.ips_compliance_statement,
        rationale=rationale,
    )


def run_cio_stage(
    *,
    proposals: Sequence[PortfolioProposalOutput],
    risk_reports: Sequence[CRORiskReportOutput],
) -> CIOBoardMemoOutput:
    return select_cio_ensemble(proposals=proposals, risk_reports=risk_reports)


def _candidate_to_board_memo(candidate: EnsembleCandidate) -> CIOBoardMemoOutput:
    return CIOBoardMemoOutput(
        selected_ensemble=candidate.selected_ensemble,
        ensemble_weights=candidate.ensemble_weights,
        portfolio_summary=candidate.portfolio_summary,
        allocation_by_asset_class=candidate.allocation_by_asset_class,
        top_positions=candidate.top_positions,
        changes_since_last_review=(),
        key_risks_to_monitor=candidate.key_risks_to_monitor,
        rebalancing_plan=(
            "Review quarterly unless IPS drift, tracking-error breaches, or macro regime changes require an off-cycle CIO reassessment."
        ),
        ips_compliance_statement=candidate.ips_compliance_statement,
    )


def _align_inputs(
    *,
    proposals: Sequence[PortfolioProposalOutput],
    risk_reports: Sequence[CRORiskReportOutput],
) -> dict[str, tuple[PortfolioProposalOutput, CRORiskReportOutput]]:
    if not proposals:
        raise ValueError("At least one portfolio proposal is required")

    risk_reports_by_method = {risk_report.method: risk_report for risk_report in risk_reports}
    aligned_pairs: dict[str, tuple[PortfolioProposalOutput, CRORiskReportOutput]] = {}
    for proposal in proposals:
        try:
            risk_report = risk_reports_by_method[proposal.method]
        except KeyError as error:
            raise ValueError(f"Missing risk report for proposal '{proposal.method}'") from error
        aligned_pairs[proposal.method] = (proposal, risk_report)
    return aligned_pairs


def _ensemble_weights(
    *,
    ensemble_method: str,
    aligned_pairs: dict[str, tuple[PortfolioProposalOutput, CRORiskReportOutput]],
) -> dict[str, float]:
    methods = tuple(aligned_pairs)
    if ensemble_method == "simple_average":
        equal_weight = 1.0 / len(methods)
        return {method: equal_weight for method in methods}

    proposal_values = tuple(proposal for proposal, _ in aligned_pairs.values())
    risk_values = tuple(risk_report for _, risk_report in aligned_pairs.values())
    sharpe_scores = _normalize([proposal.sharpe_ratio for proposal in proposal_values])
    backtest_scores = _normalize([risk_report.backtest.sharpe for risk_report in risk_values])
    diversification_scores = _normalize([proposal.effective_n for proposal in proposal_values])
    tracking_scores = _normalize([risk_report.ips_compliance.tracking_error for risk_report in risk_values], reverse=True)
    drawdown_scores = _normalize([risk_report.backtest.max_drawdown for risk_report in risk_values])

    raw_scores: dict[str, float] = {}
    for index, method in enumerate(methods):
        _, risk_report = aligned_pairs[method]
        if not risk_report.ips_compliance.passes:
            raw_scores[method] = 0.0
            continue
        raw_scores[method] = (
            0.30 * sharpe_scores[index]
            + 0.25 * backtest_scores[index]
            + 0.20 * diversification_scores[index]
            + 0.15 * tracking_scores[index]
            + 0.10 * drawdown_scores[index]
        )

    total = sum(raw_scores.values())
    if total <= _WEIGHT_TOLERANCE:
        compliant_methods = tuple(
            method for method, (_, risk_report) in aligned_pairs.items() if risk_report.ips_compliance.passes
        )
        if compliant_methods:
            equal_weight = 1.0 / len(compliant_methods)
            return {
                method: equal_weight if method in compliant_methods else 0.0
                for method in methods
            }
        equal_weight = 1.0 / len(methods)
        return {method: equal_weight for method in methods}
    return {method: score / total for method, score in raw_scores.items()}


def _blend_asset_weights(
    *,
    aligned_pairs: dict[str, tuple[PortfolioProposalOutput, CRORiskReportOutput]],
    ensemble_weights: dict[str, float],
) -> dict[str, float]:
    asset_slugs = sorted({asset_slug for proposal, _ in aligned_pairs.values() for asset_slug in proposal.weights})
    blended = {asset_slug: 0.0 for asset_slug in asset_slugs}
    for method, (proposal, _) in aligned_pairs.items():
        method_weight = ensemble_weights.get(method, 0.0)
        for asset_slug, weight in proposal.weights.items():
            blended[asset_slug] += method_weight * weight
    total = sum(blended.values())
    if total <= _WEIGHT_TOLERANCE:
        raise ValueError("Ensemble asset weights must sum to a positive value")
    return {asset_slug: weight / total for asset_slug, weight in blended.items()}


def _weighted_average(
    ensemble_weights: dict[str, float],
    aligned_pairs: dict[str, tuple[PortfolioProposalOutput, CRORiskReportOutput]],
    value_getter: object,
) -> float:
    weighted_total = 0.0
    total_weight = 0.0
    for method, pair in aligned_pairs.items():
        method_weight = ensemble_weights.get(method, 0.0)
        weighted_total += method_weight * value_getter(*pair)
        total_weight += method_weight
    if total_weight <= _WEIGHT_TOLERANCE:
        return 0.0
    return weighted_total / total_weight


def _allocation_by_asset_class(weights: dict[str, float]) -> dict[str, float]:
    allocation = {group: 0.0 for group in GROUPS}
    for asset_slug, weight in weights.items():
        allocation[get_asset(asset_slug).group] += weight
    return allocation


def _top_position_rows(
    *,
    aligned_pairs: dict[str, tuple[PortfolioProposalOutput, CRORiskReportOutput]],
    ensemble_weights: dict[str, float],
    blended_weights: dict[str, float],
) -> list[tuple[str, float, float]]:
    risk_proxy_by_asset = {asset_slug: 0.0 for asset_slug in blended_weights}
    for method, (proposal, _risk_report) in aligned_pairs.items():
        method_weight = ensemble_weights.get(method, 0.0)
        for asset_slug, asset_weight in proposal.weights.items():
            risk_proxy_by_asset[asset_slug] += method_weight * proposal.expected_volatility * (asset_weight**2)
    total_risk_proxy = sum(risk_proxy_by_asset.values())
    if total_risk_proxy <= _WEIGHT_TOLERANCE:
        total_risk_proxy = 1.0
    rows = [
        (asset_slug, blended_weights[asset_slug], risk_proxy_by_asset[asset_slug] / total_risk_proxy)
        for asset_slug in sorted(blended_weights, key=lambda slug: (-blended_weights[slug], slug))
    ]
    return rows


def _candidate_rank(candidate: EnsembleCandidate) -> float:
    return (
        (10.0 if candidate.ips_compliance_statement == "COMPLIANT" else 0.0)
        + candidate.portfolio_summary["sharpe_ratio"]
        + (0.05 * candidate.portfolio_summary["effective_n"])
        - candidate.portfolio_summary["tracking_error_vs_60_40"]
    )


def _collect_key_risks(risk_reports: Sequence[CRORiskReportOutput]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered_risks: list[str] = []
    for risk_report in risk_reports:
        for item in risk_report.ips_compliance.violations + risk_report.ips_compliance.warnings:
            if item not in seen:
                seen.add(item)
                ordered_risks.append(item)
    return tuple(ordered_risks[:3])


def _normalize(values: Sequence[float], *, reverse: bool = False) -> tuple[float, ...]:
    if not values:
        return ()
    low = min(values)
    high = max(values)
    if high - low <= _WEIGHT_TOLERANCE:
        return tuple(1.0 for _ in values)
    if reverse:
        return tuple((high - value) / (high - low) for value in values)
    return tuple((value - low) / (high - low) for value in values)
