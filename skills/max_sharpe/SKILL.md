# Max Sharpe Portfolio Skill

Implement the `max_sharpe` MVP portfolio method through `core.portfolio_optimizer.optimize_portfolio`.

## Contract
- Method name: `max_sharpe`
- Output: `PortfolioProposalOutput`
- Constraints: long-only, weights must sum to 1, enforce IPS min/max bounds from `core.assets`
- The optimizer must use the shared covariance estimate plus expected returns and should fail explicitly when the constrained solve is infeasible

## Method Rule
- Solve the constrained maximum-Sharpe problem with the shared optimizer interface
- Use the supplied risk-free rate consistently in optimization and proposal metrics
- Reuse shared risk helpers so output fields align with the CRO pipeline contract
