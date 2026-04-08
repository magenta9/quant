# Risk Parity Portfolio Skill

Implement the `risk_parity` MVP portfolio method through `core.portfolio_optimizer.optimize_portfolio`.

## Contract
- Method name: `risk_parity`
- Output: `PortfolioProposalOutput`
- Constraints: long-only, weights must sum to 1, enforce IPS min/max bounds from `core.assets`
- The method must fail explicitly when the constrained solve cannot produce a valid IPS-safe portfolio

## Method Rule
- Solve for approximately equal total risk contributions across sleeves using the shared covariance matrix
- Reuse the shared optimizer interface, shared constraint handling, and shared risk-metric helpers
- Keep all assumptions explicit in output metadata for later CRO consumption
