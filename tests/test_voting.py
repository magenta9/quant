from __future__ import annotations

import unittest


class VotingTests(unittest.TestCase):
    def test_generate_review_assignments_is_reproducible_and_excludes_self_review(self) -> None:
        from core.voting import generate_review_assignments

        methods = (
            "equal_weight",
            "inverse_volatility",
            "max_sharpe",
            "global_min_variance",
            "risk_parity",
            "maximum_diversification",
        )
        categories = {
            "equal_weight": "heuristic",
            "inverse_volatility": "heuristic",
            "max_sharpe": "return_optimized",
            "global_min_variance": "risk_structured",
            "risk_parity": "risk_structured",
            "maximum_diversification": "risk_structured",
        }

        first = generate_review_assignments(methods=methods, categories=categories, reviews_per_reviewer=2, seed=7)
        second = generate_review_assignments(methods=methods, categories=categories, reviews_per_reviewer=2, seed=7)

        self.assertEqual(first, second)
        self.assertEqual(len(first), len(methods) * 2)
        self.assertTrue(all(assignment.reviewer != assignment.reviewed_method for assignment in first))
        self.assertTrue(any(assignment.review_type == "same_category" for assignment in first))
        self.assertTrue(any(assignment.review_type == "cross_category" for assignment in first))

        counts_by_reviewer = {method: 0 for method in methods}
        for assignment in first:
            counts_by_reviewer[assignment.reviewer] += 1
        self.assertTrue(all(count == 2 for count in counts_by_reviewer.values()))

    def test_generate_review_assignments_covers_every_method_in_governance_universe(self) -> None:
        from core.voting import generate_review_assignments

        methods = (
            "equal_weight",
            "inverse_volatility",
            "max_sharpe",
            "global_min_variance",
            "risk_parity",
            "volatility_targeting",
            "black_litterman",
            "robust_mean_variance",
            "mean_downside_risk",
            "maximum_diversification",
            "minimum_correlation",
        )
        categories = {
            "equal_weight": "heuristic",
            "inverse_volatility": "heuristic",
            "max_sharpe": "return_optimized",
            "black_litterman": "return_optimized",
            "robust_mean_variance": "return_optimized",
            "global_min_variance": "risk_structured",
            "risk_parity": "risk_structured",
            "volatility_targeting": "risk_structured",
            "mean_downside_risk": "risk_structured",
            "maximum_diversification": "risk_structured",
            "minimum_correlation": "risk_structured",
        }

        assignments = generate_review_assignments(methods=methods, categories=categories, reviews_per_reviewer=2, seed=0)

        inbound_counts = {method: 0 for method in methods}
        for assignment in assignments:
            inbound_counts[assignment.reviewed_method] += 1

        self.assertTrue(all(count >= 1 for count in inbound_counts.values()), inbound_counts)

    def test_tally_peer_reviews_and_select_shortlist_enforce_diversity_rule(self) -> None:
        from core.voting import (
            PeerReview,
            ReviewScoreBreakdown,
            select_shortlist,
            tally_peer_reviews,
        )

        reviews = (
            PeerReview(
                reviewer="equal_weight",
                reviewed_method="max_sharpe",
                scores=ReviewScoreBreakdown(23.0, 24.0, 19.0, 24.0),
                total_score=90.0,
                strengths=("best Sharpe",),
                weaknesses=("projection warning",),
                vote_points=5,
                vote_rationale="Best overall risk-adjusted result.",
            ),
            PeerReview(
                reviewer="inverse_volatility",
                reviewed_method="global_min_variance",
                scores=ReviewScoreBreakdown(21.0, 20.0, 24.0, 25.0),
                total_score=90.0,
                strengths=("strong diversification",),
                weaknesses=("lower upside",),
                vote_points=4,
                vote_rationale="Most stable risk posture.",
            ),
            PeerReview(
                reviewer="risk_parity",
                reviewed_method="maximum_diversification",
                scores=ReviewScoreBreakdown(22.0, 20.0, 25.0, 23.0),
                total_score=90.0,
                strengths=("broad diversification",),
                weaknesses=("moderate return",),
                vote_points=3,
                vote_rationale="Diversification leader.",
            ),
            PeerReview(
                reviewer="global_min_variance",
                reviewed_method="volatility_targeting",
                scores=ReviewScoreBreakdown(20.0, 18.0, 22.0, 22.0),
                total_score=82.0,
                strengths=("low realized volatility",),
                weaknesses=("limited upside",),
                vote_points=2,
                vote_rationale="Useful defensive fallback.",
            ),
            PeerReview(
                reviewer="maximum_diversification",
                reviewed_method="equal_weight",
                scores=ReviewScoreBreakdown(18.0, 16.0, 17.0, 20.0),
                total_score=71.0,
                strengths=("transparent",),
                weaknesses=("weak diversification",),
                vote_points=1,
                vote_rationale="Simple but dominated.",
            ),
            PeerReview(
                reviewer="max_sharpe",
                reviewed_method="minimum_correlation",
                scores=ReviewScoreBreakdown(17.0, 15.0, 20.0, 18.0),
                total_score=70.0,
                strengths=("decorrelated sleeves",),
                weaknesses=("weak return profile",),
                vote_points=-2,
                vote_rationale="Bottom flag due to weak return profile.",
            ),
        )
        categories = {
            "max_sharpe": "return_optimized",
            "global_min_variance": "risk_structured",
            "maximum_diversification": "risk_structured",
            "volatility_targeting": "risk_structured",
            "equal_weight": "heuristic",
            "minimum_correlation": "risk_structured",
        }

        tallies = tally_peer_reviews(reviews=reviews, categories=categories)
        shortlist = select_shortlist(tallies=tallies, top_n=5, min_categories=3)

        self.assertEqual(tallies["max_sharpe"].total_vote_points, 5)
        self.assertEqual(tallies["minimum_correlation"].total_vote_points, -2)
        self.assertEqual(shortlist[0].method, "max_sharpe")
        self.assertEqual(len(shortlist), 5)
        self.assertGreaterEqual(len({entry.category for entry in shortlist}), 3)
        self.assertIn("equal_weight", {entry.method for entry in shortlist})


if __name__ == "__main__":
    unittest.main()
