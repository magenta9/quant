# Robust Mean-Variance Portfolio Skill

Implement the `robust_mean_variance` portfolio method through `core.portfolio_optimizer.optimize_portfolio`.

## Contract
- Method name: `robust_mean_variance`
- Output: `PortfolioProposalOutput`
- Constraints: long-only, weights must sum to 1, enforce IPS min/max bounds from `core.assets`
- If the selected universe is infeasible under IPS bounds, raise an explicit error instead of silently clipping

## Method Rule
- Shrink expected returns toward the cross-sectional mean before optimization
- Add a small diagonal ridge to the covariance estimate to reduce estimation sensitivity
- Reuse the shared covariance and risk-metric helpers for expected return, volatility, Sharpe, and metadata
