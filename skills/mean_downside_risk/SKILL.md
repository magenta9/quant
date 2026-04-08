# Mean Downside Risk Portfolio Skill

Implement the `mean_downside_risk` portfolio method through `core.portfolio_optimizer.optimize_portfolio`.

## Contract
- Method name: `mean_downside_risk`
- Output: `PortfolioProposalOutput`
- Constraints: long-only, weights must sum to 1, enforce IPS min/max bounds from `core.assets`
- If the selected universe is infeasible under IPS bounds, raise an explicit error instead of silently clipping

## Method Rule
- Penalize assets with higher downside-risk proxies while rewarding positive excess returns
- Fall back to the inverse-volatility portfolio if all downside-adjusted scores collapse
- Reuse the shared covariance and risk-metric helpers for expected return, volatility, Sharpe, and metadata
