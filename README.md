# Self-Driving Portfolio Agentic System

Greenfield Python repository for a self-driving multi-asset portfolio research pipeline. The target MVP combines deterministic quant stages, optional LLM narration, SQLite persistence, and run artifacts into one repeatable workflow across 18 asset classes.

## Current Phase

This branch implements the Phase 1 repository skeleton and runtime configuration. Core engines, agents, and persistence code land in later phases.

## Local Setup

1. Create and activate a Python 3.11+ virtual environment.
2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Review and adjust runtime inputs:
   - `config/ips.md` for the investment policy statement
   - `config/settings.yaml` for environment-variable-driven runtime settings
4. Export the API keys or overrides referenced in `config/settings.yaml` if you plan to enable narrative LLM steps.

## Pipeline Summary

The planned MVP follows a six-stage pipeline:

1. **Macro analysis** — classify the macro regime from free data and emit structured macro outputs.
2. **Asset CMA generation** — run all 18 asset sleeves through a shared capital-market-assumption workflow.
3. **Covariance estimation** — build cross-asset covariance and correlation views.
4. **Portfolio construction** — generate candidate portfolios from the MVP method set.
5. **Review and risk** — produce standardized CRO-style risk reports and review signals.
6. **CIO decisioning** — select the final recommendation and render a board memo.

Artifacts are expected under `output/runs/`, while SQLite persistence targets `database/portfolio.db`.

## MVP Scope

- Support the full 18-asset investment universe from the IPS.
- Use free-data-compatible methods first, with explicit stubs for workflows that require unavailable paid/vendor data.
- Keep quantitative outputs deterministic and reproducible; narrative LLM calls stay optional.
- Persist intermediate results and final recommendations so each run is auditable end to end.

## Included in This Phase

- Baseline repository documentation
- Runtime IPS document
- Environment-driven settings scaffold
- Dependency manifest for the MVP foundation
- Run-artifact root under `output/runs/`
