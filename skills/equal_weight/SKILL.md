# Equal Weight Portfolio Skill

Implement the `equal_weight` MVP portfolio method through `core.portfolio_optimizer.optimize_portfolio`.

## Contract
- Method name: `equal_weight`
- Output: `PortfolioProposalOutput`
- Constraints: long-only, weights must sum to 1, enforce IPS min/max bounds from `core.assets`
- If the selected universe is infeasible under IPS bounds, raise an explicit error instead of silently clipping

## Method Rule
- Start from equal sleeve weights across the requested asset universe
- Apply the shared optimizer constraint layer so the final proposal remains auditable and IPS-safe
- Reuse the shared covariance and risk-metric helpers for expected return, volatility, Sharpe, and metadata
