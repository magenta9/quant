from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from core.contracts import SerializableContract


@dataclass(frozen=True, slots=True)
class ReviewAssignment(SerializableContract):
    reviewer: str
    reviewed_method: str
    review_type: Literal["same_category", "cross_category", "fallback"]


@dataclass(frozen=True, slots=True)
class ReviewScoreBreakdown(SerializableContract):
    methodology: float
    risk_return: float
    diversification: float
    ips_compliance: float


@dataclass(frozen=True, slots=True)
class PeerReview(SerializableContract):
    reviewer: str
    reviewed_method: str
    scores: ReviewScoreBreakdown
    total_score: float
    strengths: tuple[str, ...]
    weaknesses: tuple[str, ...]
    vote_points: int
    vote_rationale: str


@dataclass(frozen=True, slots=True)
class VoteTally(SerializableContract):
    method: str
    category: str
    total_vote_points: int
    average_total_score: float
    review_count: int


def run_peer_review(
    *,
    reviewer: str,
    reviewed_method: str,
    proposal: object,
    risk_report: object,
    vote_points: int,
) -> PeerReview:
    methodology = 21.0 if proposal.metadata.get("constraint_projection_applied") else 24.0
    risk_return = min(max(10.0 + (6.0 * proposal.sharpe_ratio), 0.0), 25.0)
    diversification = min(max(4.5 * proposal.effective_n, 0.0), 25.0)
    ips_penalty = (4.0 * len(risk_report.ips_compliance.violations)) + (1.0 * len(risk_report.ips_compliance.warnings))
    ips_compliance = max(25.0 - ips_penalty, 0.0) if risk_report.ips_compliance.passes else max(12.0 - ips_penalty, 0.0)
    scores = ReviewScoreBreakdown(
        methodology=round(methodology, 2),
        risk_return=round(risk_return, 2),
        diversification=round(diversification, 2),
        ips_compliance=round(ips_compliance, 2),
    )
    total_score = round(
        scores.methodology + scores.risk_return + scores.diversification + scores.ips_compliance,
        2,
    )
    strengths = _strengths(proposal=proposal, risk_report=risk_report)
    weaknesses = _weaknesses(proposal=proposal, risk_report=risk_report)
    return PeerReview(
        reviewer=reviewer,
        reviewed_method=reviewed_method,
        scores=scores,
        total_score=total_score,
        strengths=strengths,
        weaknesses=weaknesses,
        vote_points=vote_points,
        vote_rationale=_vote_rationale(reviewed_method=reviewed_method, vote_points=vote_points, risk_report=risk_report),
    )


def generate_review_assignments(
    *,
    methods: tuple[str, ...] | list[str],
    categories: dict[str, str],
    reviews_per_reviewer: int = 2,
    seed: int = 0,
) -> tuple[ReviewAssignment, ...]:
    ordered_methods = tuple(sorted(methods))
    assignments: list[ReviewAssignment] = []

    for reviewer_index, reviewer in enumerate(ordered_methods):
        same_category = [
            method
            for method in ordered_methods
            if method != reviewer and categories.get(method) == categories.get(reviewer)
        ]
        cross_category = [
            method
            for method in ordered_methods
            if method != reviewer and categories.get(method) != categories.get(reviewer)
        ]
        same_category = _rotated(same_category, seed + reviewer_index)
        cross_category = _rotated(cross_category, seed + reviewer_index)

        chosen: list[ReviewAssignment] = []
        used: set[str] = set()

        if same_category:
            chosen.append(
                ReviewAssignment(
                    reviewer=reviewer,
                    reviewed_method=same_category[0],
                    review_type="same_category",
                )
            )
            used.add(same_category[0])
        if len(chosen) < reviews_per_reviewer and cross_category:
            next_cross = next(method for method in cross_category if method not in used)
            chosen.append(
                ReviewAssignment(
                    reviewer=reviewer,
                    reviewed_method=next_cross,
                    review_type="cross_category",
                )
            )
            used.add(next_cross)

        remaining = _rotated(
            [method for method in ordered_methods if method != reviewer and method not in used],
            seed + reviewer_index,
        )
        for method in remaining:
            if len(chosen) >= reviews_per_reviewer:
                break
            chosen.append(ReviewAssignment(reviewer=reviewer, reviewed_method=method, review_type="fallback"))
            used.add(method)

        assignments.extend(chosen)

    return tuple(assignments)


def tally_peer_reviews(
    *,
    reviews: tuple[PeerReview, ...] | list[PeerReview],
    categories: dict[str, str],
) -> dict[str, VoteTally]:
    grouped: dict[str, list[PeerReview]] = {}
    for review in reviews:
        grouped.setdefault(review.reviewed_method, []).append(review)

    tallies: dict[str, VoteTally] = {}
    for method, method_reviews in grouped.items():
        total_score = sum(review.total_score for review in method_reviews)
        tallies[method] = VoteTally(
            method=method,
            category=categories[method],
            total_vote_points=sum(review.vote_points for review in method_reviews),
            average_total_score=total_score / len(method_reviews),
            review_count=len(method_reviews),
        )
    return tallies


def select_shortlist(
    *,
    tallies: dict[str, VoteTally],
    top_n: int = 5,
    min_categories: int = 3,
) -> tuple[VoteTally, ...]:
    ranked = sorted(
        tallies.values(),
        key=lambda tally: (-tally.total_vote_points, -tally.average_total_score, tally.method),
    )
    if len(ranked) <= top_n:
        return tuple(ranked)

    shortlist: list[VoteTally] = []
    covered_categories: set[str] = set()
    categories_available = {tally.category for tally in ranked}
    target_categories = min(min_categories, len(categories_available))

    for tally in ranked:
        if len(covered_categories) >= target_categories:
            break
        if tally.category in covered_categories:
            continue
        shortlist.append(tally)
        covered_categories.add(tally.category)

    for tally in ranked:
        if len(shortlist) >= top_n:
            break
        if tally.method in {entry.method for entry in shortlist}:
            continue
        shortlist.append(tally)

    return tuple(shortlist[:top_n])


def _rotated(values: list[str], offset: int) -> list[str]:
    if not values:
        return []
    offset = offset % len(values)
    return values[offset:] + values[:offset]


def _strengths(*, proposal: object, risk_report: object) -> tuple[str, ...]:
    strengths: list[str] = []
    if proposal.sharpe_ratio >= 0.7:
        strengths.append("competitive Sharpe profile")
    if proposal.effective_n >= 3.0:
        strengths.append("broad diversification")
    if risk_report.ips_compliance.passes:
        strengths.append("IPS-compliant risk posture")
    return tuple(strengths or ["stable portfolio construction process"])


def _weaknesses(*, proposal: object, risk_report: object) -> tuple[str, ...]:
    weaknesses: list[str] = []
    if proposal.metadata.get("constraint_projection_applied"):
        weaknesses.append("required deterministic IPS projection")
    weaknesses.extend(risk_report.ips_compliance.violations)
    weaknesses.extend(risk_report.ips_compliance.warnings[:1])
    return tuple(weaknesses or ["no material structural weakness flagged"])


def _vote_rationale(*, reviewed_method: str, vote_points: int, risk_report: object) -> str:
    compliance = "passed" if risk_report.ips_compliance.passes else "failed"
    if vote_points <= -1:
        return f"{reviewed_method} received a bottom flag because its IPS posture {compliance} and the method ranked poorly."
    if vote_points >= 4:
        return f"{reviewed_method} earned a top Borda vote because it ranked near the top while its IPS posture {compliance}."
    return f"{reviewed_method} received an intermediate vote because it remained competitive while its IPS posture {compliance}."
