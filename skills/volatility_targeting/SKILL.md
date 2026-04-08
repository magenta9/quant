# Volatility Targeting Portfolio Skill

Implement the `volatility_targeting` portfolio method through `core.portfolio_optimizer.optimize_portfolio`.

## Contract
- Method name: `volatility_targeting`
- Output: `PortfolioProposalOutput`
- Constraints: long-only, weights must sum to 1, enforce IPS min/max bounds from `core.assets`
- If the selected universe is infeasible under IPS bounds, raise an explicit error instead of silently clipping

## Method Rule
- Start from the maximum-Sharpe sleeve mix, then blend toward the inverse-volatility portfolio when ex-ante volatility exceeds the defensive target
- Record the target volatility and the unconstrained base volatility in metadata for auditability
- Reuse the shared covariance and risk-metric helpers for expected return, volatility, Sharpe, and metadata
