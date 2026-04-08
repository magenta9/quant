# Global Minimum Variance Portfolio Skill

Implement the `global_min_variance` MVP portfolio method through `core.portfolio_optimizer.optimize_portfolio`.

## Contract
- Method name: `global_min_variance`
- Output: `PortfolioProposalOutput`
- Constraints: long-only, weights must sum to 1, enforce IPS min/max bounds from `core.assets`
- The optimizer must surface infeasible IPS universes explicitly instead of silently clipping

## Method Rule
- Minimize total portfolio variance under the shared IPS constraints
- Reuse the shared covariance estimate and shared risk-metric helpers for proposal statistics
- Keep the implementation deterministic and auditable for later CRO review
