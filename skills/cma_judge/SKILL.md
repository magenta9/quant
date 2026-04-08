# CMA Judge Skill

Deterministically select the final CMA estimate for one asset while keeping unsupported methods explicit in the artifact set.

## MVP Method Availability

### Executable in Phase 2
1. **Historical ERP + Risk-Free**
2. **Regime-Adjusted ERP**
3. **Auto-Blend**

### Structured stub only in Phase 2
- `black_litterman` — later phase dependency on covariance and equilibrium inputs
- `inverse_gordon` — unavailable because it needs paid/vendor data
- `implied_erp` — unavailable because it needs paid/vendor data
- `survey_consensus` — unavailable because it needs paid/vendor data

Every unavailable method must emit a structured stub result with:
- `name`
- `available: false`
- `expected_return: null`
- `confidence: null`
- `rationale`
- `required_inputs`

Do not fabricate approximations for unavailable inputs.

## Judgment Rules

### 1. Assess dispersion across available methods
- **Tight**: spread < 3 percentage points → accept `auto_blend`
- **Moderate/Wide**: keep evaluating regime context

### 2. Apply regime logic with MVP availability constraints
- **Expansion**: default to `auto_blend`
- **Late cycle**: default to `auto_blend` unless available methods diverge materially and a defensive tilt is clearly warranted
- **Recovery**: default to `auto_blend`
- **Recession**: prefer `regime_adjusted_erp` when spread is meaningful because valuation-forward methods are not available yet

### 3. Respect method-availability limits
- If a preferred spec-era method is stubbed in MVP, do not substitute a fake proxy
- Explain that the decision was made from the available executable set only

### 4. Final constraint
- Final selected CMA must remain within the min/max range of the available executable methods

## Output Expectations

- `cma_methods.json` includes all executable methods plus structured stubs
- `cma.json` records the selected method, selected expected return, confidence, and judge notes
- The judge notes should explicitly mention when stubbed methods prevented a richer valuation-based decision
