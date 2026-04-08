from __future__ import annotations

from pathlib import Path
import unittest

import yaml


class PortfolioReportingAgentConfigTests(unittest.TestCase):
    def test_pc_agent_base_template_documents_shared_runtime_contract(self) -> None:
        agent_yaml = Path("agents/pc_agents/_base/agent.yaml")

        self.assertTrue(agent_yaml.exists())

        agent_text = agent_yaml.read_text(encoding="utf-8")
        agent_payload = yaml.safe_load(agent_text)

        self.assertIn("kind: pc-agent", agent_text)
        self.assertIn("module: core.portfolio_optimizer", agent_text)
        self.assertIn("callable: run_portfolio_method", agent_text)
        self.assertIn("proposal.json", agent_text)
        self.assertEqual(agent_payload["template"], True)
        self.assertEqual(agent_payload["contract"]["json_contract"], "core.contracts.PortfolioProposalOutput")
        self.assertEqual(agent_payload["runtime"]["kwargs"]["method"], "{method_slug}")
        self.assertEqual(
            agent_payload["required_metadata"],
            [
                "method_slug",
                "method_name",
                "method_category",
                "objective",
                "primary_risk_input",
                "expected_return_input",
                "solver_style",
                "skill_path",
            ],
        )

    def test_pc_method_wrappers_document_mvp_method_metadata(self) -> None:
        expected_methods = {
            "equal_weight": {
                "method_name": "Equal Weight",
                "method_category": "heuristic",
                "objective": "Allocate equal weights across all eligible assets after deterministic IPS filtering.",
                "primary_risk_input": "none",
                "expected_return_input": "optional_for_reporting",
                "solver_style": "direct_allocation",
            },
            "inverse_volatility": {
                "method_name": "Inverse Volatility",
                "method_category": "heuristic",
                "objective": "Allocate more weight to lower-volatility sleeves using deterministic volatility estimates from covariance inputs.",
                "primary_risk_input": "covariance_diagonal",
                "expected_return_input": "optional_for_reporting",
                "solver_style": "deterministic_rescaling",
            },
            "max_sharpe": {
                "method_name": "Maximum Sharpe",
                "method_category": "return_optimized",
                "objective": "Maximize ex-ante Sharpe ratio from CMA expected returns and the shared covariance estimate under MVP IPS constraints.",
                "primary_risk_input": "full_covariance_matrix",
                "expected_return_input": "asset_cma_vector",
                "solver_style": "constrained_optimization",
            },
            "global_min_variance": {
                "method_name": "Global Minimum Variance",
                "method_category": "risk_structured",
                "objective": "Minimize ex-ante portfolio variance subject to long-only, fully invested MVP constraints.",
                "primary_risk_input": "full_covariance_matrix",
                "expected_return_input": "optional_for_reporting",
                "solver_style": "constrained_optimization",
            },
            "risk_parity": {
                "method_name": "Risk Parity",
                "method_category": "risk_structured",
                "objective": "Iteratively equalize risk contributions across eligible sleeves while respecting deterministic IPS limits.",
                "primary_risk_input": "full_covariance_matrix",
                "expected_return_input": "optional_for_reporting",
                "solver_style": "iterative_optimization",
            },
            "volatility_targeting": {
                "method_name": "Volatility Targeting",
                "method_category": "risk_structured",
                "objective": "Blend toward a defensive target volatility when the unconstrained return-seeking portfolio becomes too risky.",
                "primary_risk_input": "full_covariance_matrix",
                "expected_return_input": "asset_cma_vector",
                "solver_style": "deterministic_blend",
            },
            "black_litterman": {
                "method_name": "Black-Litterman",
                "method_category": "return_optimized",
                "objective": "Blend equilibrium and CMA views into a posterior return estimate before constrained optimization.",
                "primary_risk_input": "full_covariance_matrix",
                "expected_return_input": "posterior_return_vector",
                "solver_style": "deterministic_posterior_optimization",
            },
            "robust_mean_variance": {
                "method_name": "Robust Mean-Variance",
                "method_category": "return_optimized",
                "objective": "Reduce estimation sensitivity by shrinking returns and adding a covariance ridge before optimization.",
                "primary_risk_input": "full_covariance_matrix",
                "expected_return_input": "shrunk_asset_cma_vector",
                "solver_style": "regularized_optimization",
            },
            "mean_downside_risk": {
                "method_name": "Mean Downside Risk",
                "method_category": "risk_structured",
                "objective": "Penalize downside-risk proxies while preserving positive expected-return exposure.",
                "primary_risk_input": "downside_risk_proxy",
                "expected_return_input": "asset_cma_vector",
                "solver_style": "deterministic_scoring",
            },
            "maximum_diversification": {
                "method_name": "Maximum Diversification",
                "method_category": "risk_structured",
                "objective": "Maximize a diversification-ratio proxy from the shared covariance estimate under IPS limits.",
                "primary_risk_input": "full_covariance_matrix",
                "expected_return_input": "optional_for_reporting",
                "solver_style": "closed_form_proxy",
            },
            "minimum_correlation": {
                "method_name": "Minimum Correlation",
                "method_category": "risk_structured",
                "objective": "Favor sleeves with lower average pairwise correlation while remaining long-only and fully invested.",
                "primary_risk_input": "derived_correlation_matrix",
                "expected_return_input": "optional_for_reporting",
                "solver_style": "deterministic_scoring",
            },
        }

        for slug, expected in expected_methods.items():
            agent_yaml = Path(f"agents/pc_agents/{slug}/agent.yaml")
            self.assertTrue(agent_yaml.exists(), slug)

            payload = yaml.safe_load(agent_yaml.read_text(encoding="utf-8"))

            self.assertEqual(payload["extends"], "../_base/agent.yaml")
            self.assertEqual(payload["agent"]["slug"], slug)
            self.assertEqual(payload["metadata"]["method_slug"], slug)
            self.assertEqual(payload["metadata"]["method_name"], expected["method_name"])
            self.assertEqual(payload["metadata"]["method_category"], expected["method_category"])
            self.assertEqual(payload["metadata"]["objective"], expected["objective"])
            self.assertEqual(payload["metadata"]["primary_risk_input"], expected["primary_risk_input"])
            self.assertEqual(payload["metadata"]["expected_return_input"], expected["expected_return_input"])
            self.assertEqual(payload["metadata"]["solver_style"], expected["solver_style"])
            self.assertEqual(payload["metadata"]["skill_path"], f"skills/{slug}/SKILL.md")

            skill_path = Path(payload["metadata"]["skill_path"])
            self.assertEqual(skill_path.name, "SKILL.md")
            self.assertEqual(skill_path.parent.as_posix(), f"skills/{slug}")
            if skill_path.parent.exists():
                self.assertTrue(skill_path.exists(), slug)

    def test_cro_agent_wrapper_files_document_risk_reporting_contract(self) -> None:
        agent_yaml = Path("agents/cro_agent/agent.yaml")
        prompts_md = Path("agents/cro_agent/prompts.md")

        self.assertTrue(agent_yaml.exists())
        self.assertTrue(prompts_md.exists())

        agent_text = agent_yaml.read_text(encoding="utf-8")
        agent_payload = yaml.safe_load(agent_text)
        prompt_text = prompts_md.read_text(encoding="utf-8")

        self.assertIn("kind: cro-agent", agent_text)
        self.assertIn("module: core.risk_metrics", agent_text)
        self.assertIn("callable: run_cro_stage", agent_text)
        self.assertIn("prompt_template: ./prompts.md", agent_text)
        self.assertIn("risk_report.json", agent_text)
        self.assertIn("risk_report.md", agent_text)
        self.assertEqual(agent_payload["shared_files"]["prompt_template"], "./prompts.md")
        self.assertEqual(agent_payload["contract"]["json_contract"], "core.contracts.CRORiskReportOutput")
        self.assertIn("Chief Risk Officer", prompt_text)
        self.assertIn("do not express investment views", prompt_text.lower())
        self.assertIn("ips compliance", prompt_text.lower())
        self.assertIn("deterministic", prompt_text.lower())

    def test_cio_agent_wrapper_files_document_selection_contract(self) -> None:
        agent_yaml = Path("agents/cio_agent/agent.yaml")
        prompts_md = Path("agents/cio_agent/prompts.md")

        self.assertTrue(agent_yaml.exists())
        self.assertTrue(prompts_md.exists())

        agent_text = agent_yaml.read_text(encoding="utf-8")
        agent_payload = yaml.safe_load(agent_text)
        prompt_text = prompts_md.read_text(encoding="utf-8")

        self.assertIn("kind: cio-agent", agent_text)
        self.assertIn("module: core.ensemble", agent_text)
        self.assertIn("callable: run_cio_stage", agent_text)
        self.assertIn("prompt_template: ./prompts.md", agent_text)
        self.assertIn("proposal.json", agent_text)
        self.assertIn("risk_report.json", agent_text)
        self.assertIn("macro_view.json", agent_text)
        self.assertIn("board_memo.json", agent_text)
        self.assertEqual(agent_payload["shared_files"]["prompt_template"], "./prompts.md")
        self.assertEqual(agent_payload["contract"]["json_contract"], "core.contracts.CIOBoardMemoOutput")
        self.assertIn("Chief Investment Officer", prompt_text)
        self.assertIn("recommendation rationale", prompt_text.lower())
        self.assertIn("deterministic", prompt_text.lower())
        self.assertIn("do not imply approvals", prompt_text.lower())

    def test_pc_review_agent_wrapper_documents_review_contract(self) -> None:
        agent_yaml = Path("agents/pc_review/agent.yaml")
        prompts_md = Path("agents/pc_review/prompts.md")

        self.assertTrue(agent_yaml.exists())
        self.assertTrue(prompts_md.exists())

        agent_text = agent_yaml.read_text(encoding="utf-8")
        agent_payload = yaml.safe_load(agent_text)
        prompt_text = prompts_md.read_text(encoding="utf-8").lower()

        self.assertIn("kind: pc-review-agent", agent_text)
        self.assertIn("module: core.voting", agent_text)
        self.assertIn("callable: run_peer_review", agent_text)
        self.assertEqual(agent_payload["contract"]["json_contract"], "core.voting.PeerReview")
        self.assertIn("same-category", prompt_text)
        self.assertIn("cross-category", prompt_text)
        self.assertIn("borda", prompt_text)
        self.assertIn("vote rationale", prompt_text)

    def test_meta_agent_wrapper_documents_guardrails(self) -> None:
        agent_yaml = Path("agents/meta_agent/agent.yaml")
        prompts_md = Path("agents/meta_agent/prompts.md")

        self.assertTrue(agent_yaml.exists())
        self.assertTrue(prompts_md.exists())

        agent_text = agent_yaml.read_text(encoding="utf-8")
        agent_payload = yaml.safe_load(agent_text)
        prompt_text = prompts_md.read_text(encoding="utf-8").lower()

        self.assertIn("kind: meta-agent", agent_text)
        self.assertIn("module: core.pipeline", agent_text)
        self.assertIn("callable: run_evaluation_mode", agent_text)
        self.assertEqual(agent_payload["contract"]["json_contract"], "core.pipeline.MetaEvaluationResult")
        self.assertIn("evidence", prompt_text)
        self.assertIn("rollback", prompt_text)
        self.assertIn("human review", prompt_text)
        self.assertIn("bounded", prompt_text)


if __name__ == "__main__":
    unittest.main()
