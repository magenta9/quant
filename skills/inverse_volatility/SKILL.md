# Inverse Volatility Portfolio Skill

Implement the `inverse_volatility` MVP portfolio method through `core.portfolio_optimizer.optimize_portfolio`.

## Contract
- Method name: `inverse_volatility`
- Output: `PortfolioProposalOutput`
- Constraints: long-only, weights must sum to 1, enforce IPS min/max bounds from `core.assets`
- If variance inputs are invalid or IPS bounds are infeasible, raise an explicit error instead of silently clipping

## Method Rule
- Use inverse asset volatility from the covariance diagonal as the target allocation signal
- Pass the target weights through the shared constraint layer so the emitted proposal stays IPS-safe and deterministic
- Reuse the shared covariance and risk-metric helpers for summary fields and metadata
