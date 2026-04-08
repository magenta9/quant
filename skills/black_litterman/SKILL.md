# Black-Litterman Portfolio Skill

Implement the `black_litterman` portfolio method through `core.portfolio_optimizer.optimize_portfolio`.

## Contract
- Method name: `black_litterman`
- Output: `PortfolioProposalOutput`
- Constraints: long-only, weights must sum to 1, enforce IPS min/max bounds from `core.assets`
- If the selected universe is infeasible under IPS bounds, raise an explicit error instead of silently clipping

## Method Rule
- Blend equilibrium returns implied by the covariance matrix with the CMA expected-return vector to form a posterior view
- Optimize the posterior view through the shared constrained optimizer layer
- Preserve posterior and implied return vectors in metadata for auditability
