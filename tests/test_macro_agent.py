from __future__ import annotations

import json
import unittest
from dataclasses import dataclass
from pathlib import Path

from core.data_fetcher import MacroIndicatorValue
from core.macro_analyzer import run_macro_stage


@dataclass(frozen=True, slots=True)
class _StubMacroProvider:
    indicators: dict[str, MacroIndicatorValue]

    def get_macro_indicators(self) -> dict[str, MacroIndicatorValue]:
        return self.indicators


class MacroAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = Path("tests_runtime") / self._testMethodName
        self.workspace.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        for path in sorted(self.workspace.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        if self.workspace.exists():
            self.workspace.rmdir()

    def test_run_macro_stage_writes_high_confidence_artifacts_from_supported_inputs(self) -> None:
        provider = _StubMacroProvider(
            indicators={
                "gdp_growth_yoy": MacroIndicatorValue(
                    name="gdp_growth_yoy",
                    value=3.4,
                    as_of="2026-04-09T12:00:00Z",
                    source_ticker="GDP",
                    status="ok",
                ),
                "cpi_yoy": MacroIndicatorValue(
                    name="cpi_yoy",
                    value=3.4,
                    as_of="2026-04-09T12:00:00Z",
                    source_ticker="CPI",
                    status="ok",
                ),
                "fed_funds_rate": MacroIndicatorValue(
                    name="fed_funds_rate",
                    value=4.2,
                    as_of="2026-04-09T12:00:00Z",
                    source_ticker="FEDFUNDS",
                    status="ok",
                ),
                "vix": MacroIndicatorValue(
                    name="vix",
                    value=27.0,
                    as_of="2026-04-09T12:00:00Z",
                    source_ticker="^VIX",
                    status="ok",
                ),
                "credit_spreads": MacroIndicatorValue(
                    name="credit_spreads",
                    value=210.0,
                    as_of="2026-04-09T12:00:00Z",
                    source_ticker="BAMLH0A0HYM2",
                    status="ok",
                ),
            }
        )

        result = run_macro_stage(output_dir=self.workspace, data_provider=provider)

        self.assertEqual(result.macro_view.regime, "late_cycle")
        self.assertEqual(result.macro_view.confidence, "high")
        self.assertEqual(result.macro_view.scores.growth, 2)
        self.assertEqual(result.macro_view.scores.inflation, 1)
        self.assertEqual(result.macro_view.scores.monetary_policy, 1)
        self.assertEqual(result.macro_view.scores.financial_conditions, 1)
        self.assertAlmostEqual(result.macro_view.composite_score, 1.4)

        payload = json.loads((self.workspace / "macro_view.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["regime"], "late_cycle")
        self.assertEqual(payload["confidence"], "high")
        self.assertEqual(payload["scores"]["financial_conditions"], 1)
        self.assertEqual(payload["indicator_diagnostics"]["credit_spreads"]["status"], "ok")
        self.assertEqual(payload["unsupported_inputs"], [])

        report = (self.workspace / "macro_analysis.md").read_text(encoding="utf-8")
        self.assertIn("# Macro Analysis Report", report)
        self.assertIn("Late Cycle", report)
        self.assertIn("High", report)
        self.assertIn("Financial conditions are somewhat tight", report)

    def test_run_macro_stage_is_explicit_when_provider_only_supports_vix(self) -> None:
        provider = _StubMacroProvider(
            indicators={
                "gdp_growth_yoy": MacroIndicatorValue(
                    name="gdp_growth_yoy",
                    value=None,
                    as_of=None,
                    source_ticker=None,
                    status="unsupported",
                    message="No direct Yahoo Finance mapping for GDP growth in the MVP provider.",
                ),
                "cpi_yoy": MacroIndicatorValue(
                    name="cpi_yoy",
                    value=None,
                    as_of=None,
                    source_ticker=None,
                    status="unsupported",
                    message="No direct Yahoo Finance mapping for CPI in the MVP provider.",
                ),
                "fed_funds_rate": MacroIndicatorValue(
                    name="fed_funds_rate",
                    value=None,
                    as_of=None,
                    source_ticker=None,
                    status="unsupported",
                    message="No direct Yahoo Finance mapping for the Fed Funds Rate in the MVP provider.",
                ),
                "vix": MacroIndicatorValue(
                    name="vix",
                    value=32.0,
                    as_of="2026-04-09T12:00:00Z",
                    source_ticker="^VIX",
                    status="ok",
                ),
                "credit_spreads": MacroIndicatorValue(
                    name="credit_spreads",
                    value=None,
                    as_of=None,
                    source_ticker=None,
                    status="unsupported",
                    message="No direct Yahoo Finance mapping for credit spreads in the MVP provider.",
                ),
            }
        )

        result = run_macro_stage(output_dir=self.workspace, data_provider=provider)

        self.assertEqual(result.macro_view.regime, "recovery")
        self.assertEqual(result.macro_view.confidence, "low")
        self.assertEqual(result.macro_view.scores.growth, 0)
        self.assertEqual(result.macro_view.scores.inflation, 0)
        self.assertEqual(result.macro_view.scores.monetary_policy, 0)
        self.assertEqual(result.macro_view.scores.financial_conditions, 2)
        self.assertAlmostEqual(result.macro_view.composite_score, 0.2)
        self.assertIn("gdp_growth_yoy", result.unsupported_inputs)
        self.assertIn("credit_spreads", result.unsupported_inputs)
        self.assertEqual(result.partial_inputs, ("financial_conditions",))

        payload = json.loads((self.workspace / "macro_view.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["confidence"], "low")
        self.assertEqual(
            payload["unsupported_inputs"],
            ["cpi_yoy", "credit_spreads", "fed_funds_rate", "gdp_growth_yoy"],
        )
        self.assertEqual(payload["partial_inputs"], ["financial_conditions"])
        self.assertIn("unavailable", payload["outlook"].lower())
        self.assertEqual(payload["key_indicators"]["gdp_growth_yoy"], None)
        self.assertEqual(payload["indicator_diagnostics"]["vix"]["status"], "ok")

        report = (self.workspace / "macro_analysis.md").read_text(encoding="utf-8")
        self.assertIn("Unsupported or Missing Inputs", report)
        self.assertIn("No direct Yahoo Finance mapping for GDP growth", report)
        self.assertIn("Financial conditions are tight", report)

    def test_run_macro_stage_marks_financial_conditions_partial_when_vix_is_missing(self) -> None:
        provider = _StubMacroProvider(
            indicators={
                "gdp_growth_yoy": MacroIndicatorValue(
                    name="gdp_growth_yoy",
                    value=1.8,
                    as_of="2026-04-09T12:00:00Z",
                    source_ticker="GDP",
                    status="ok",
                ),
                "cpi_yoy": MacroIndicatorValue(
                    name="cpi_yoy",
                    value=2.2,
                    as_of="2026-04-09T12:00:00Z",
                    source_ticker="CPI",
                    status="ok",
                ),
                "fed_funds_rate": MacroIndicatorValue(
                    name="fed_funds_rate",
                    value=2.2,
                    as_of="2026-04-09T12:00:00Z",
                    source_ticker="FEDFUNDS",
                    status="ok",
                ),
                "vix": MacroIndicatorValue(
                    name="vix",
                    value=None,
                    as_of=None,
                    source_ticker="^VIX",
                    status="missing",
                    message="No Close value returned for ^VIX.",
                ),
                "credit_spreads": MacroIndicatorValue(
                    name="credit_spreads",
                    value=180.0,
                    as_of="2026-04-09T12:00:00Z",
                    source_ticker="BAMLH0A0HYM2",
                    status="ok",
                ),
            }
        )

        result = run_macro_stage(output_dir=self.workspace, data_provider=provider)

        self.assertIn("vix", result.unsupported_inputs)
        self.assertEqual(result.partial_inputs, ("financial_conditions",))
        payload = json.loads((self.workspace / "macro_view.json").read_text(encoding="utf-8"))
        self.assertIn("vix", payload["unsupported_inputs"])
        self.assertEqual(payload["partial_inputs"], ["financial_conditions"])

    def test_macro_agent_wrapper_files_document_runtime_contract(self) -> None:
        agent_yaml = Path("agents/macro_agent/agent.yaml")
        prompts_md = Path("agents/macro_agent/prompts.md")

        self.assertTrue(agent_yaml.exists())
        self.assertTrue(prompts_md.exists())

        agent_text = agent_yaml.read_text(encoding="utf-8")
        prompt_text = prompts_md.read_text(encoding="utf-8")

        self.assertIn("kind: macro-agent", agent_text)
        self.assertIn("module: core.macro_analyzer", agent_text)
        self.assertIn("callable: run_macro_stage", agent_text)
        self.assertIn("prompt_template: ./prompts.md", agent_text)
        self.assertIn("macro_view.json", agent_text)
        self.assertIn("macro_analysis.md", agent_text)
        self.assertIn("Chief Macro Economist", prompt_text)
        self.assertIn("deterministic", prompt_text.lower())
        self.assertIn("unsupported", prompt_text.lower())


if __name__ == "__main__":
    unittest.main()
