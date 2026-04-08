# Maximum Diversification Portfolio Skill

Implement the `maximum_diversification` portfolio method through `core.portfolio_optimizer.optimize_portfolio`.

## Contract
- Method name: `maximum_diversification`
- Output: `PortfolioProposalOutput`
- Constraints: long-only, weights must sum to 1, enforce IPS min/max bounds from `core.assets`
- If the selected universe is infeasible under IPS bounds, raise an explicit error instead of silently clipping

## Method Rule
- Maximize a diversification-ratio proxy using the covariance matrix and asset volatilities
- Fall back to inverse-volatility weights if the raw diversification solution degenerates
- Reuse the shared covariance and risk-metric helpers for expected return, volatility, Sharpe, and metadata
