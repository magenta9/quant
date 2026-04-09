# Self-Driving Portfolio Agentic System Implementation Plan

## Overview

Build the system as a greenfield Python-based quant pipeline with agent and skill scaffolding, delivering a real end-to-end MVP across all 18 asset classes before layering on peer-review governance, advanced portfolio methods, and the guarded self-improving meta-agent.

The implementation should treat the spec as a contract-first architecture document rather than a requirement to build 50 independent agent runtimes on day 1. Shared quantitative kernels, schemas, persistence, and orchestration come first; agent wrappers should stay thin until the deterministic pipeline is stable.

## Current State Analysis

The repository is currently planning-only. The only substantive project artifact is the spec at `thoughts/shared/specs/2026-04-08-self-driving-portfolio-agentic-system.md`; there is no existing runtime, config, test, agent, skill, or database implementation to extend.

### Key Discoveries:
- `thoughts/shared/specs/2026-04-08-self-driving-portfolio-agentic-system.md:1536-1625` - The real architecture is a 6-stage pipeline: macro -> asset CMA -> covariance -> portfolio construction -> review/risk -> CIO memo.
- `thoughts/shared/specs/2026-04-08-self-driving-portfolio-agentic-system.md:67-120`, `:1629-1707`, `:1782-1875` - The strongest existing design assets are the JSON contracts, SQLite schema, and report templates.
- `thoughts/shared/specs/2026-04-08-self-driving-portfolio-agentic-system.md:1879-1975` - The intended repository structure is explicit, but none of it exists yet.
- `thoughts/shared/specs/2026-04-08-self-driving-portfolio-agentic-system.md:248-297`, `:458-465`, `:1995-2007` - Several methods assume Bloomberg/FactSet-style inputs even though paid data is explicitly out of scope.
- `thoughts/shared/specs/2026-04-08-self-driving-portfolio-agentic-system.md:2011-2014` - Rigorous point-in-time / DatedGPT backtesting remains unresolved and should not block the MVP.

## Scope

### In Scope
- Create the repository structure described by the spec, with pragmatic additions for shared contracts and run-artifact management.
- Deliver an MVP that supports all 18 asset classes end-to-end.
- Implement the macro engine, generic asset runner, free-data-compatible CMA methods, CMA judge, covariance/risk core, a representative first set of portfolio construction methods, CRO reporting, CIO selection, SQLite persistence, and board memo generation.
- Scaffold all agent and skill directories required by the target architecture, even when some methods remain stubbed in the MVP.
- Stub paid-data-dependent methods behind explicit interfaces so later phases can fill them in without changing public contracts.
- Plan a guarded meta-agent workflow as a later phase, including review, logging, and rollback requirements.

### Out of Scope
- Trade execution or broker integration.
- Real-time risk monitoring or intraday portfolio management.
- Paid market data integrations in the MVP.
- Rigorous point-in-time / DatedGPT backtesting in the MVP.
- Fully implementing every advanced portfolio construction method in the MVP.

## Implementation Approach

Implement the system in layers:

1. **Contracts and shared kernels first**: freeze data frequency, asset identifiers, IPS constraint semantics, artifact schemas, and SQLite writes before building agent wrappers.
2. **One generic engine per repeated concept**: the 18 asset agents should reuse one asset-analysis runner plus per-asset configuration; portfolio methods should share a registry and optimizer interface.
3. **All 18 assets in the MVP, limited method set in the MVP**: preserve the full asset universe early, but only fully implement the subset of methods that can run on free data and support an end-to-end system.
4. **Explicit stubs over fake implementations**: any method requiring unavailable data should produce a structured "not implemented with current data source" result rather than a silent approximation.
5. **Agent scaffolding follows the deterministic core**: `agents/` and `skills/` should describe and invoke the underlying Python logic, not duplicate it.

To make the repository buildable, introduce two small shared modules not listed in the original spec:
- `core/contracts.py` for typed output/input schemas and artifact helpers.
- `core/assets.py` for the 18-asset registry, proxy tickers, and asset metadata.

These additions reduce duplication across 18 asset agents and multiple portfolio methods.

## Phase 1: Foundations and Contracts

### Overview
Create the skeleton repository, configuration files, shared contracts, data access layer, and persistence model that every downstream stage depends on.

### Changes Required:

#### 1. Repository skeleton and baseline docs
**File**: `README.md`  
**Changes**: Add project overview, local setup, pipeline summary, and MVP scope.

**File**: `requirements.txt`  
**Changes**: Add the MVP dependency set: `yfinance`, `numpy`, `pandas`, `scipy`, `cvxpy`, and the chosen LLM SDKs.

**File**: `config/ips.md`  
**Changes**: Materialize the IPS from the spec as the runtime input document.

**File**: `config/settings.yaml`  
**Changes**: Add environment-driven settings for data provider, output paths, database location, model settings, and run-mode toggles.

#### 2. Shared contracts and asset registry
**File**: `core/contracts.py`  
**Changes**: Define typed structures/helpers for:
- `macro_view`
- per-asset CMA outputs
- covariance outputs
- portfolio proposal outputs
- CRO risk report outputs
- CIO board memo outputs

**File**: `core/assets.py`  
**Changes**: Define all 18 asset slugs, benchmark labels, free-data proxy tickers, group/category tags, and IPS min/max constraints.

**File**: `core/utils.py`  
**Changes**: Add shared filesystem helpers, JSON/Markdown write helpers, annualization constants, and run-id generation.

#### 3. Persistence and artifact conventions
**File**: `core/database.py`  
**Changes**: Implement SQLite initialization and table creation for the spec schema, using migration-safe create-if-missing logic.

**File**: `database/portfolio.db`  
**Changes**: Created at runtime; do not commit the generated database file.

**File**: `output/runs/.gitkeep`  
**Changes**: Establish a run-artifact root for intermediate JSON/Markdown outputs.

#### 4. Data abstraction
**File**: `core/data_fetcher.py`  
**Changes**: Implement a provider abstraction over `yfinance` for:
- macro indicators
- asset history
- proxy ticker metadata
- safe missing-data/error reporting

### Success Criteria:

#### Automated Verification:
- [ ] `python -m pytest tests/test_macro_agent.py`
- [ ] `python -m pytest tests/test_pipeline.py`
- [ ] `python -c "from core.database import initialize_database; initialize_database()"`

#### Manual Verification:
- [ ] Inspect `config/ips.md` and confirm all 18 assets and constraints are represented.
- [ ] Run database initialization and confirm the expected SQLite tables exist.
- [ ] Run a sample data fetch and confirm each asset slug resolves to a free-data proxy or an explicit stub state.

---

## Phase 2: Macro and 18-Asset CMA Pipeline

### Overview
Implement the first executable investment-analysis slice: macro regime classification plus per-asset CMA generation for all 18 asset classes using the MVP method set.

### Changes Required:

#### 1. Macro engine
**File**: `core/macro_analyzer.py`  
**Changes**: Implement deterministic regime scoring for growth, inflation, monetary policy, and financial conditions; produce `macro_view.json` and `macro_analysis.md`.

**File**: `agents/macro_agent/agent.yaml`  
**Changes**: Describe inputs, outputs, and runtime entrypoint for the macro stage.

**File**: `agents/macro_agent/prompts.md`  
**Changes**: Add the narrative agent prompt that wraps the deterministic macro engine.

#### 2. Asset-agent scaffolding
**File**: `agents/asset_class_agents/_template/agent.yaml`  
**Changes**: Create the shared asset-agent template.

**File**: `agents/asset_class_agents/_template/prompts.md`  
**Changes**: Create the shared prompt template for asset analysis.

**File**: `agents/asset_class_agents/{slug}/agent.yaml`  
**Changes**: Generate 18 asset directories that reference shared templates plus asset-specific metadata.

#### 3. CMA core
**File**: `core/cma_builder.py`  
**Changes**: Implement the generic asset-runner pipeline for all 18 assets with:
- historical ERP + risk-free
- regime-adjusted ERP
- auto-blend
- structured placeholders for inverse Gordon, implied ERP, survey consensus, and any other unavailable-data methods

**File**: `skills/cma_judge/SKILL.md`  
**Changes**: Materialize the rule set from the spec and align it to the MVP method availability rules.

#### 4. Output generation and storage
**File**: `core/pipeline.py`  
**Changes**: Add stage orchestration for:
- loading IPS
- running macro
- running all 18 asset analyses
- writing run artifacts
- persisting macro/CMA rows to SQLite

### Success Criteria:

#### Automated Verification:
- [ ] `python -m pytest tests/test_macro_agent.py`
- [ ] `python -m pytest tests/test_cma_methods.py`
- [ ] `python -m pytest tests/test_pipeline.py`

#### Manual Verification:
- [ ] Run the pipeline and confirm all 18 asset directories produce artifacts under a single run folder.
- [ ] Confirm `macro_view.json` matches the documented schema and includes regime/confidence output.
- [ ] Confirm each asset produces a final `cma.json` plus explicit stub records for methods blocked by unavailable paid data.

---

## Phase 3: Risk and Portfolio Construction MVP

### Overview
Add the quantitative core needed to turn 18 asset-level CMAs into actual portfolio candidates and risk diagnostics.

### Changes Required:

#### 1. Covariance and shared risk metrics
**File**: `core/covariance.py`  
**Changes**: Implement covariance/correlation estimation, Ledoit-Wolf shrinkage, and frequency-safe annualization rules.

**File**: `core/risk_metrics.py`  
**Changes**: Implement ex-ante volatility, return, Sharpe, drawdown, concentration, factor tilt, and tracking-error helpers used by PC methods and CRO.

#### 2. Portfolio optimizer registry
**File**: `core/portfolio_optimizer.py`  
**Changes**: Implement a common interface for portfolio methods with shared IPS constraint enforcement.

**File**: `skills/equal_weight/SKILL.md`  
**Changes**: Add the MVP implementation contract for equal weight.

**File**: `skills/inverse_volatility/SKILL.md`  
**Changes**: Add the MVP implementation contract for inverse volatility.

**File**: `skills/max_sharpe/SKILL.md`  
**Changes**: Add the MVP implementation contract for max Sharpe.

**File**: `skills/global_min_variance/SKILL.md`  
**Changes**: Add the MVP implementation contract for global minimum variance.

**File**: `skills/risk_parity/SKILL.md`  
**Changes**: Add the MVP implementation contract for risk parity.

**File**: `agents/pc_agents/_base/agent.yaml`  
**Changes**: Create the shared PC-agent base config.

**File**: `agents/pc_agents/{method}/agent.yaml`  
**Changes**: Create agent directories for the first implemented PC methods.

#### 3. CRO risk reporting
**File**: `agents/cro_agent/agent.yaml`  
**Changes**: Define CRO entrypoint and artifact contract.

**File**: `agents/cro_agent/prompts.md`  
**Changes**: Wrap risk metrics in the reporting narrative.

**File**: `core/pipeline.py`  
**Changes**: Extend orchestration to:
- run covariance
- run the MVP portfolio-method set
- generate risk reports for each portfolio proposal
- persist portfolio proposals and risk reports

### Success Criteria:

#### Automated Verification:
- [ ] `python -m pytest tests/test_portfolio_methods.py`
- [ ] `python -m pytest tests/test_pipeline.py`
- [ ] `python -m pytest tests/test_voting.py`

#### Manual Verification:
- [ ] Confirm the MVP PC methods each emit valid long-only weights summing to 1 across all 18 assets.
- [ ] Confirm each proposal receives a standardized CRO risk report.
- [ ] Confirm IPS violations are surfaced explicitly in artifacts rather than silently clipped away.

---

## Phase 4: CIO Orchestration and Board Outputs

### Overview
Turn raw portfolio candidates into one final recommendation with persisted artifacts, a board memo, and repeatable end-to-end execution.

### Changes Required:

#### 1. Ensemble and CIO layer
**File**: `core/ensemble.py`  
**Changes**: Implement the MVP ensemble set:
- simple average
- composite-score weighting

**File**: `agents/cio_agent/agent.yaml`  
**Changes**: Define CIO inputs, outputs, and selection entrypoint.

**File**: `agents/cio_agent/prompts.md`  
**Changes**: Add the CIO narrative for summarizing recommendation rationale.

#### 2. Final outputs
**File**: `output/board_memos/.gitkeep`  
**Changes**: Establish the memo output location.

**File**: `core/pipeline.py`  
**Changes**: Extend orchestration to:
- choose the final ensemble
- write board memo markdown
- persist board memo rows
- provide a single CLI-friendly run entrypoint

#### 3. Test coverage
**File**: `tests/test_macro_agent.py`  
**Changes**: Cover regime scoring thresholds and schema validation.

**File**: `tests/test_cma_methods.py`  
**Changes**: Cover method calculations, stubs, and judge selection behavior.

**File**: `tests/test_portfolio_methods.py`  
**Changes**: Cover optimizer outputs, constraints, and numerical stability.

**File**: `tests/test_pipeline.py`  
**Changes**: Cover end-to-end orchestration through board memo output.

### Success Criteria:

#### Automated Verification:
- [ ] `python -m pytest`
- [ ] `python -m pytest tests/test_pipeline.py`

#### Manual Verification:
- [ ] Run a full sample pipeline and confirm a board memo is written to `output/board_memos/`.
- [ ] Confirm SQLite contains macro views, CMA results, portfolio proposals, risk reports, and board memo rows for the run.
- [ ] Review the board memo and confirm it includes allocation, macro rationale, risk metrics, and IPS compliance sections.

---

## Phase 5: Governance and Expansion

### Overview
Add the higher-complexity orchestration features that make the system resemble the full institutional architecture described in the spec.

### Changes Required:

#### 1. Peer review and voting
**File**: `agents/pc_review/agent.yaml`  
**Changes**: Define the review-agent contract for same-category and cross-category review assignments.

**File**: `agents/pc_review/prompts.md`  
**Changes**: Add review criteria, scoring language, and vote rationale format.

**File**: `core/voting.py`  
**Changes**: Implement assignment generation, Borda-count tallying, diversity constraints, and shortlist production.

#### 2. Portfolio-method expansion
**File**: `skills/{advanced_method}/SKILL.md`  
**Changes**: Add remaining portfolio methods in a controlled order:
- volatility targeting
- black-litterman
- robust mean-variance
- mean downside risk
- maximum diversification
- minimum correlation
- then the more complex/non-convex methods

**File**: `agents/pc_agents/{advanced_method}/agent.yaml`  
**Changes**: Add agent wrappers as each method becomes executable.

#### 3. Meta-agent with guardrails
**File**: `agents/meta_agent/agent.yaml`  
**Changes**: Define a guarded workflow that never edits production logic without explicit review gates.

**File**: `agents/meta_agent/prompts.md`  
**Changes**: Require evidence-based proposals, logged diffs, and revert plans.

**File**: `core/pipeline.py`  
**Changes**: Add a separated evaluation mode for historical feedback and proposed improvements.

#### 4. Backtesting hardening
**File**: `core/data_fetcher.py`  
**Changes**: Add interfaces for later point-in-time data/backtest improvements without breaking the MVP interface.

**File**: `tests/test_pipeline.py`  
**Changes**: Expand to cover replay/backtest modes and governance flows.

### Success Criteria:

#### Automated Verification:
- [ ] `python -m pytest`
- [ ] `python -m pytest tests/test_voting.py`
- [ ] `python -m pytest tests/test_pipeline.py`

#### Manual Verification:
- [ ] Confirm peer review assignments are generated reproducibly and exclude self-review.
- [ ] Confirm top-5 selection satisfies the diversity rule from the spec.
- [ ] Confirm meta-agent proposals produce logged evidence, bounded changes, and a rollback path before any code modification is accepted.

---

## Testing Strategy

### Unit Tests
- Macro scoring thresholds, regime mapping, and confidence rules.
- IPS parsing, asset registry integrity, and proxy ticker mapping for all 18 assets.
- CMA method calculations, method stubs, and judge-selection logic.
- Covariance estimation and annualization consistency.
- Portfolio method constraints: long-only, sum-to-one, IPS bounds, and tracking-error checks.
- CRO metric calculations and serialization.
- CIO ensemble selection and board memo rendering.

### Manual Testing Steps:
1. Populate `config/settings.yaml` with local runtime settings and run a full pipeline against the sample IPS.
2. Verify that one run folder contains macro, per-asset, covariance, portfolio, risk, and CIO artifacts.
3. Inspect one asset with a free-data-compatible CMA path and one asset/method that is intentionally stubbed due to unavailable vendor data.
4. Inspect the generated board memo and confirm the recommendation is traceable back to stored structured outputs.

## Performance Considerations

- The expensive part of the MVP is repeated per-asset/per-method data access, not LLM narration. Cache normalized market data per run before fanning out to 18 assets.
- Keep the quantitative core vectorized with NumPy/Pandas and avoid repeated recomputation of covariance and shared risk metrics.
- Run per-asset CMA generation and per-method portfolio construction in parallel only after artifact paths and database writes are made idempotent.
- Keep narrative agent calls optional for the MVP so the system can run in a mostly deterministic mode during tests and backfills.

## Migration Notes

- This is a greenfield implementation, so there is no legacy production migration.
- Treat SQLite schema creation as versioned from the first implementation so later additions can use forward-only migrations.
- Keep vendor-data methods behind stable interfaces now so they can be implemented later without breaking the artifact contracts established in the MVP.
- Reserve rigorous point-in-time backtesting as a later migration of the data layer rather than coupling it to the first executable release.

## References

- Original requirements: `thoughts/shared/specs/2026-04-08-self-driving-portfolio-agentic-system.md`
- Pipeline architecture: `thoughts/shared/specs/2026-04-08-self-driving-portfolio-agentic-system.md:1536-1625`
- Database schema: `thoughts/shared/specs/2026-04-08-self-driving-portfolio-agentic-system.md:1629-1707`
- IPS and constraints: `thoughts/shared/specs/2026-04-08-self-driving-portfolio-agentic-system.md:1711-1776`
- Intended repository layout: `thoughts/shared/specs/2026-04-08-self-driving-portfolio-agentic-system.md:1879-1975`
- Acceptance criteria: `thoughts/shared/specs/2026-04-08-self-driving-portfolio-agentic-system.md:1979-1993`
