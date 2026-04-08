# Minimum Correlation Portfolio Skill

Implement the `minimum_correlation` portfolio method through `core.portfolio_optimizer.optimize_portfolio`.

## Contract
- Method name: `minimum_correlation`
- Output: `PortfolioProposalOutput`
- Constraints: long-only, weights must sum to 1, enforce IPS min/max bounds from `core.assets`
- If the selected universe is infeasible under IPS bounds, raise an explicit error instead of silently clipping

## Method Rule
- Derive the correlation matrix from shared covariance inputs and reward assets with lower average pairwise correlation
- Normalize the resulting scores into a fully invested long-only allocation
- Reuse the shared covariance and risk-metric helpers for expected return, volatility, Sharpe, and metadata
