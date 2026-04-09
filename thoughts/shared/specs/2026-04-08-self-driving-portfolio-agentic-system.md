---
date: 2026-04-09T00:15:00+08:00
researcher: zhang
git_commit: null
branch: main
topic: "Self-Driving Portfolio Agentic System - Detailed Specification"
tags: [research-spec, agentic-ai, portfolio-management, multi-agent]
status: in_progress
confidence: high
last_updated: 2026-04-09
last_updated_by: zhang
---

# Self-Driving Portfolio 多智能体系统详细规范

## Summary

基于论文 "The Self-Driving Portfolio: Agentic Architecture for Institutional Asset Management" 实现一套完整的机构资产管理多智能体系统。系统由约50个专用智能体组成，协调完成宏观分析、资本市场假设生成、投资组合构建、多智能体评审和CIO整合的全流程。

## 1. 智能体详细定义

### 1.1 Macro Agent (宏观分析智能体)

**类型**: Orchestrator Agent
**数量**: 1
**配置文件路径**: `agents/macro_agent/`

#### Description
```
Role: Chief Macro Economist
Slug: macro-agent
Category: Orchestrator
Step: 1 (Pipeline入口)

你是一位首席宏观经济学家，负责分析当前全球经济环境并分类经济周期。你的判断将影响所有下游资产类别分析和投资组合构建决策。

Inputs:
- IPS配置文件 (config/ips.md)
- 实时宏观数据 (通过data_fetcher获取)
- 历史市场数据

Outputs:
- macro_view.json: 包含regime分类、四个维度打分、置信度
- macro_analysis.md: 自然语言宏观分析报告

Workflow:
1. Fetch宏观指标: GDP growth, CPI, Fed Funds Rate, VIX, Credit Spreads
2. Score四个维度:
   - Growth Score (G): +2/+1/0/-1/-2 (扩张/晚周期/中性/早周期/衰退)
   - Inflation Score (I): +2/+1/0/-1/-2 (高通胀/偏高/中性/偏低/通缩)
   - Monetary Policy Score (M): +2/+1/0/-1/-2 (紧缩/趋紧/中性/宽松/零利率)
   - Financial Conditions Score (F): +2/+1/0/-1/-2 (紧张/趋紧/中性/宽松/极度宽松)
3. 计算Composite Score = 0.4*G + 0.3*I + 0.2*M + 0.1*F
4. 确定Regime:
   - Composite > 1.5: Expansion (扩张)
   - 0.5 < Composite <= 1.5: Late-Cycle (晚周期)
   - -0.5 < Composite <= 0.5: Recovery (复苏) 或 Neutral
   - Composite <= -0.5: Recession (衰退)
5. 输出置信度: Low(<60%)/Medium(60-80%)/High(>80%)
```

#### Tools
- `data_fetcher.get_macro_data()`: 获取宏观经济指标
- `data_fetcher.get_market_data()`: 获取市场数据
- `database.save_macro_view()`: 保存结果到SQLite

#### Output Contract

**macro_view.json Schema**:
```json
{
  "timestamp": "2026-04-09T12:00:00Z",
  "regime": "late_cycle",  // expansion | late_cycle | recession | recovery
  "confidence": "medium",    // low | medium | high
  "scores": {
    "growth": 1,
    "inflation": 0,
    "monetary_policy": 1,
    "financial_conditions": 0
  },
  "composite_score": 0.7,
  "recession_probability": 0.30,
  "key_indicators": {
    "gdp_growth_yoy": 2.1,
    "cpi_yoy": 2.8,
    "fed_funds_rate": 4.5,
    "vix": 18.5,
    "credit_spreads": 120
  },
  "outlook": "Stagflationary risks rising, oil supply shock concern"
}
```

**macro_analysis.md Template**:
```markdown
# Macro Analysis Report
**Date**: {timestamp}
**Regime**: {regime} (Confidence: {confidence})

## Executive Summary
{2-3 sentence宏观形势总结}

## Key Indicators
| Indicator | Value | Score | Interpretation |
|-----------|-------|-------|----------------|
| GDP Growth | {value} | {score} | {interpretation} |
| CPI | {value} | {score} | {interpretation} |
| Fed Funds | {value} | {score} | {interpretation} |
| VIX | {value} | {score} | {interpretation} |

## Regime Classification Rationale
{详细分类理由}

## Risks
- {风险点1}
- {风险点2}

## Implications for Asset Allocation
{对下游资产配置的指导意义}
```

---

### 1.2 Asset Class Agent (资产类别智能体)

**类型**: Specialist Agent
**数量**: 18 (每个资产类别一个)
**配置文件路径**: `agents/asset_class_agents/{slug}/`

#### 18个资产类别配置

| Slug | BBG Ticker | Category | Macro Sensitivity |
|------|------------|----------|------------------|
| us_large_cap | SPTR Index | US Equity | Growth(+), Rates(-), Inflation(-), Dollar(+) |
| us_small_cap | SMLTR Index | US Equity | Growth(+), Rates(-), Credit(+) |
| us_value | CSUSVALU Index | US Equity | Value(+), Rates(-), Economy(+) |
| us_growth | CSUSGRWU Index | US Equity | Growth(+), Rates(+), Risk(+) |
| intl_developed | MXWO Index | Intl Equity | Growth(+), Dollar(-), EAFE(+) |
| emg_markets | MXEF Index | Emg Equity | Growth(+), Dollar(-), Risk(+) |
| us_short_treasury | BPTXY10 Index | US Treasury | Rates(+), Credit(-) |
| us_interm_treasury | BPTXY30 Index | US Treasury | Rates(+), Credit(-) |
| us_long_treasury | BPTXY10 Index | US Treasury | Rates(+), Credit(-) |
| ig_corporate | CPATREIT Index | Credit | Rates(-), Credit(+) |
| hy_corporate | HWCI Index | Credit | Rates(-), Credit(+), Risk(+) |
| intl_sovereign |LEGATRUU Index | Intl Fixed | Rates(+), Dollar(-) |
| intl_corporate | LGCPTRUU Index | Intl Fixed | Rates(+), Credit(+) |
| usd_em_debt | EMUSTOTL Index | Emg Fixed | Dollar(+), Risk(+) |
| reits | FTV Index | Real Asset | Rates(-), Growth(+) |
| gold | XAU USD | Real Asset | Inflation(+), Dollar(-), Risk(+) |
| commodities | GSCI Index | Real Asset | Inflation(+), Growth(+) |
| cash | US0001M Index | Cash | Rates(+) |

#### Generic Asset Class Agent Template

**Description Template**:
```
Role: {Asset Class Name} Analyst
Slug: {slug}
Category: {category}
Step: 2
Dependencies: macro_agent

你是一位专注于{资产类别名称}的投资分析师。你的职责是基于宏观观点和资产特定分析，生成该资产类别的资本市场假设(CMA)。

Inputs:
- macro_view.json (from macro_agent)
- historical_price_data (通过data_fetcher)
- current_valuation_data

Outputs:
- cma_methods.json: 7种方法的估算结果
- cma.json: 最终选择的CMA (由CMA Judge Skill产生)
- signals.json: 技术、情绪、估值信号
- historical_stats.json: 历史统计
- scenarios.json: 情景分析
- correlation_row.json: 与其他资产类别的相关性
- analysis.md: 自然语言分析报告

Workflow:
1. Load macro view from macro_view.json
2. Load historical returns (from {start_date} to present)
3. Compute historical statistics: return, vol, Sharpe, drawdowns
4. Run 6 CMA methods:
   - Method 1: Historical ERP + Rf
   - Method 2: Regime-Adjusted ERP
   - Method 3: Black-Litterman Equilibrium
   - Method 4: Inverse Gordon Model
   - Method 5: Implied ERP (CAPE-based)
   - Method 6: Survey/Analyst Consensus
5. Compute confidence-weighted Auto-Blend (Method 7)
6. Invoke CMA Judge Skill to select final CMA
7. Generate technical signals: momentum, trend, mean-reversion
8. Conduct scenario analysis: bull/base/bear cases
9. Output all files per Output Contract
```

#### CMA Methods (7种方法详细定义)

**Method 1: Historical ERP + Risk-Free Rate**
```
Formula: E[R] = Historical_ERP + Current_Rf

Historical ERP:
  - US Large Cap: Use Dimson stream, 10-year rolling window
  - Other Equity: Use respective index history

Data:
  - Risk-free rate: 3-month Treasury (US0001M Index)
  - Historical returns: Monthly returns, minimum 10 years
  - ERP = (1 + E[R_equity]) / (1 + Rf) - 1

Confidence: 0.6 (moderate, due to regime dependency)
```

**Method 2: Regime-Adjusted ERP**
```
Formula: E[R] = Base_ERP × Regime_Multiplier + Rf

Regime Multipliers:
  - Expansion: 1.2
  - Late-Cycle: 0.8
  - Recovery: 1.0
  - Recession: 0.5

Base_ERP: Long-run historical ERP (mean)

Confidence: 0.7 (accounts for regime)
```

**Method 3: Black-Litterman Equilibrium**
```
Formula: E[R] = π + δΣP

Where:
  π = Equilibrium Expected Returns (from cap-weighted market)
     π = λΣw_mkt
     λ = risk aversion coefficient (typically 2.5)
     Σ = covariance matrix
     w_mkt = market capitalization weights

  δ = investor's confidence in views (0.1 to 1.0)
  P = Pick matrix (linking views to assets)
  ΣP = variance of view

Confidence: 0.65
```

**Method 4: Inverse Gordon Growth Model**
```
Formula: E[R] = Dividend_Yield + Earnings_Growth - Valuation_Change

Components:
  - Dividend Yield: Current dividend yield
  - Earnings Growth: Expected EPS growth (analyst consensus)
  - Valuation Change: Buyback yield + dilution adjustment

Simplified:
  E[R] ≈ Dividend_Yield + Real_EPS_Growth + Inflation

Data Sources:
  - Dividend yield: Bloomberg DPS
  - EPS growth: Analyst consensus (FactSet/I/B/E/S)
  - Buyback yield: 5-year average

Confidence: 0.55 (earnings growth estimate uncertainty)
```

**Method 5: Implied ERP (CAPE-based)**
```
Formula: E[R] = 1/CAPE - Real_Rf + Adjustment

Where:
  CAPE = Cyclically Adjusted Price-to-Earnings (10-year average)
  Real_Rf = Nominal_Rf - Long_run_Inflation

Adjustment for mean reversion:
  If CAPE > Long_run_CAPE(20): Subtract (CAPE - 20) × 0.1
  If CAPE < Long_run_CAPE: Add (20 - CAPE) × 0.1

Confidence: 0.5 (CAPE has large standard error)
```

**Method 6: Survey/Analyst Consensus**
```
Data Sources:
  - Wall Street consensus (Bloomberg)
  - Fed Summary of Economic Projections
  - IMF/WB forecasts

For each source:
  - Record point estimate
  - Record confidence interval
  - Weight by recency and reputation

Final = Weighted average of sources

Confidence: 0.5 (subjectivity bias)
```

**Method 7: Auto-Blend**
```
Formula: E[R] = Σ(w_i × Method_i)

Weights:
  w_i = Confidence_i / ΣConfidence

Confidence: Same as weighted average confidence

Constraint: Final must be within [min_method, max_method]
```

#### CMA Judge Skill 详细定义

**Skill Path**: `skills/cma_judge/`

**SKILL.md Content**:
```markdown
# CMA Judge Skill

Evaluates multiple CMA methods and selects the final expected return estimate.

## Inputs
- cma_methods.json: All method estimates with confidence scores
- signals.json: Asset-level macro, technical, valuation signals
- macro_view.json: Current regime, growth, inflation, policy scores
- historical_stats.json: Trailing returns, volatility, drawdowns

## Judgment Rules

### Step 1: Assess Method Dispersion
- Tight: < 3 percentage points spread → favor auto-blend
- Moderate: 3-6 pp → apply regime/valuation logic
- Wide: > 6 pp → identify outliers, be selective

### Step 2: Apply Regime Logic
- Late-Cycle: Tilt toward valuation-based methods (BL, CAPE)
- Expansion: Accept auto-blend
- Recession: Favor BL + regime-adjusted
- Recovery: Equal weight historical + forward-looking

### Step 3: Check Valuation Context
- CAPE > 30: Strongly favor valuation methods
- CAPE < 12: Favor historical + BL
- Normal (12-30): Flag disagreement, default to blend

### Step 4: Check Signal Alignment
- If momentum positive: Cap upside for reversal risk
- If momentum negative: Don't overshoot on recovery
- Align with macro regime signals

### Step 5: Select Final
Options:
1. Single method (if clear winner)
2. Custom blend (if partial signals)
3. Accept auto-blend (if methods agree)

### Constraint
Final estimate MUST be within [min_method, max_method]
```

---

### 1.3 Covariance Agent (协方差矩阵智能体)

**类型**: Specialist Agent
**数量**: 1
**配置文件路径**: `agents/covariance_agent/`

**Description**:
```
Role: Covariance Estimation Specialist
Slug: covariance-agent
Step: 3
Dependencies: asset_class_agents

估算资产类别间的协方差矩阵。

Inputs:
- historical_returns (18 asset classes)
- macro_view.json (for regime adjustment)

Outputs:
- covariance_matrix.json: 18×18协方差矩阵
- correlation_matrix.json: 相关系数矩阵
- covariance_analysis.md

Methodology:
1. Compute sample covariance from 5-year monthly returns
2. Apply regime adjustment:
   - High vol regime: Scale up by 1.3x
   - Low vol regime: Scale down by 0.8x
3. Apply shrinkage (Ledoit-Wolf):
   Σ_shrunk = αΣ_sample + (1-α)Σ_factor
   α = 0.2 (typical)

Annualization: Convert monthly to annual (×√12)
```

---

### 1.4 Portfolio Construction (PC) Agent - 21个

**类型**: Specialist Agent + Skills
**数量**: 21 (20个方法 + 1个Researcher)
**配置文件路径**: `agents/pc_agents/{method}/`
**Skill路径**: `skills/{method}/`

#### Category A: 启发式方法 (5个)

##### A1. Equal Weight (1/N)

**Skill Path**: `skills/equal_weight/`

```markdown
# Equal Weight (1/N) Skill

## Method Description
最简单的组合方法，每个资产赋予相等权重。

## Algorithm
w_i = 1/N for all i

Where N = number of assets = 18

## Constraints
- Long only: w_i >= 0
- Weights sum to 1: Σw_i = 1

## Parameters
- None required

## Output Schema
{
  "method": "equal_weight",
  "weights": {asset: weight},
  "expected_return": float,
  "expected_volatility": float,
  "sharpe_ratio": float,
  "max_drawdown": float (backtest),
  "effective_n": 18,
  "concentration": 1/N for all
}
```

##### A2. Market-Cap Weight

**Skill Path**: `skills/market_cap_weight/`

```markdown
# Market-Cap Weight Skill

## Method Description
按照市场规模加权。

## Algorithm
w_i = MarketCap_i / ΣMarketCap_j

## Data Sources
- US Large Cap: S&P 500 total market cap
- US Small Cap: Russell 2000 total market cap
- US Value/Growth: Respective indexes
- Intl Developed: MSCI EAFE free float
- Emg Markets: MSCI EM free float
- Fixed Income: Bloomberg aggregate market value
- Others: Respective benchmarks

## Constraints
- Long only: w_i >= 0
- Weights sum to 1: Σw_i = 1

## Output Schema
{
  "method": "market_cap_weight",
  ...
}
```

##### A3. Inverse Volatility

**Skill Path**: `skills/inverse_volatility/`

```markdown
# Inverse Volatility Skill

## Method Description
低波动资产赋予更高权重。

## Algorithm
w_i = (1/σ_i) / Σ(1/σ_j)

Where σ_i = realized volatility of asset i (annualized)

## Constraints
- Long only: w_i >= 0
- Weights sum to 1: Σw_i = 1

## Parameters
- lookback_period: 252 days (default)
- annualize: true

## Output Schema
{
  "method": "inverse_volatility",
  ...
}
```

##### A4. Inverse Variance

**Skill Path**: `skills/inverse_variance/`

```markdown
# Inverse Variance Skill

## Method Description
方差倒数加权，考虑资产间相关性。

## Algorithm
w ∝ Σ^(-1) 1

Where 1 = vector of ones
Σ^(-1) = inverse covariance matrix

More precisely:
1. Compute precision matrix: P = Σ^(-1)
2. Weight = row sum of P: w_i = Σ_j P_ij
3. Normalize: w_i = w_i / Σw_j

## Constraints
- Long only: w_i >= 0
- Weights sum to 1: Σw_i = 1

## Output Schema
{
  "method": "inverse_variance",
  ...
}
```

##### A5. Volatility Targeting

**Skill Path**: `skills/volatility_targeting/`

```markdown
# Volatility Targeting Skill

## Method Description
Target a fixed volatility level (e.g., 8% annualized).

## Algorithm
1. Compute current portfolio volatility: σ_p = √(w'Σw)
2. Compute weight scaling factor: λ = target_vol / σ_p
3. Scale weights: w_scaled = λ × w_base

Where w_base = equal weight or market cap weight

## Parameters
- target_vol: 0.08 (8%) - from IPS
- base_method: equal_weight (default)
- max_leverage: 2.0

## Constraints
- Long only: w_i >= 0
- Weight scaling capped at max_leverage

## Output Schema
{
  "method": "volatility_targeting",
  "target_vol": 0.08,
  "scaling_factor": float,
  "leverage_used": float,
  ...
}
```

#### Category B: 收益优化方法 (5个)

##### B1. Maximum Sharpe Ratio (Mean-Variance)

**Skill Path**: `skills/max_sharpe/`

```markdown
# Maximum Sharpe Ratio Skill

## Method Description
优化夏普比率组合（Markowitz 1952）。

## Algorithm
max_w: (w'μ - r_f) / √(w'Σw)

Subject to:
  Σw_i = 1
  w_i >= 0

Where:
  μ = expected returns vector (from CMAs)
  Σ = covariance matrix
  r_f = risk-free rate

## Solution
Quadratic optimization:
min_w: w'Σw - λ(w'μ - r_f)

Where λ = risk aversion parameter

## Parameters
- risk_aversion: 1.0 (default)
- allow_short: false

## Output Schema
{
  "method": "max_sharpe",
  "risk_aversion": float,
  "mu_used": "cma_weighted",
  "sigma_used": "covariance_agent",
  ...
}
```

##### B2. Black-Litterman

**Skill Path**: `skills/black_litterman/`

```markdown
# Black-Litterman Skill

## Method Description
融合均衡收益与主动观点的贝叶斯方法。

## Algorithm
1. Compute equilibrium returns: π = λΣw_mkt
2. Define view: Pμ = q + ε, where ε ~ N(0, τΣ)
3. Posterior: μ_posterior = [(τΣ)^(-1) + P'Ω^(-1)P]^(-1)[(τΣ)^(-1)π + P'Ω^(-1)q]
4. Optimize with posterior μ

Where:
  λ = risk aversion coefficient (2.5)
  w_mkt = market cap weights
  τ = 1/T (T = number of years, ~0.025)
  Ω = diagonal matrix of view uncertainties
  P = pick matrix (link views to assets)
  q = view returns

## Views Input
- Format: [{"assets": ["us_large_cap"], "return": 0.08, "confidence": 0.5}]
- Confidence affects Ω: higher confidence → lower ω

## Parameters
- lambda (risk aversion): 2.5
- tau: 0.025 (1/40)

## Output Schema
{
  "method": "black_litterman",
  "views_used": int,
  "equilibrium_returns": [...],
  "posterior_returns": [...],
  ...
}
```

##### B3. Robust Mean-Variance

**Skill Path**: `skills/robust_mean_variance/`

```markdown
# Robust Mean-Variance Skill

## Method Description
考虑预期收益不确定性的鲁棒优化。

## Algorithm
min_w: max_μ∈U w'Σw - λw'μ

Where U = uncertainty ellipsoid:
U = {μ: (μ-μ̂)'Ω^(-1)(μ-μ̂) ≤ κ²}

This is equivalent to:
min_w: w'Σw + κ√(w'Ωw) - λw'μ̂

## Parameters
- kappa (uncertainty size): 2.0 (default)
- omega_type: "diagonal" | "full"
- lambda: 1.0 (risk aversion)

## Output Schema
{
  "method": "robust_mean_variance",
  "kappa": float,
  "omega_type": string,
  ...
}
```

##### B4. Resampled Efficient Frontier

**Skill Path**: `skills/resampled_efficient_frontier/`

```markdown
# Resampled Efficient Frontier Skill

## Method Description
Michaud (1998)重采样有效前沿，通过蒙特卡洛模拟处理估计误差。

## Algorithm
1. For k = 1 to K (K = 500 simulations):
   a. Draw random returns: μ_k ~ N(μ̂, Σ/T)
   b. Solve MVO for each return target → w_k
2. Average across simulations: w* = (1/K)Σw_k
3. Compute efficient frontier statistics

## Parameters
- n_simulations: 500
- n_points: 50 (frontier resolution)
- risk_aversion_grid: [0.1, 0.2, ..., 5.0]

## Output Schema
{
  "method": "resampled_efficient_frontier",
  "n_simulations": 500,
  "frontier_points": [{"return": float, "vol": float, "weight": {...}}],
  "resampled_weights": {...},
  ...
}
```

##### B5. Mean-Downside Risk (Sortino)

**Skill Path**: `skills/mean_downside_risk/`

```markdown
# Mean-Downside Risk (Sortino) Skill

## Method Description
使用下行偏差而非方差作为风险度量。

## Algorithm
max_w: (w'μ - MAR) / TDD

Where:
  MAR = Minimum Acceptable Return (default = risk-free rate)
  TDD = Target Downside Deviation = √(E[max(MAR - w'R, 0)]²)

## Constraints
- Σw_i = 1
- w_i >= 0
- TDD constraint (optional)

## Parameters
- mar: 0.0 (default, use risk-free rate)
- target_return: float (optional constraint)

## Output Schema
{
  "method": "mean_downside_risk",
  "sortino_ratio": float,
  "tdd": float,
  "mar": float,
  ...
}
```

#### Category C: 风险结构化方法 (5个)

##### C1. Global Minimum Variance (GMV)

**Skill Path**: `skills/global_min_variance/`

```markdown
# Global Minimum Variance Skill

## Method Description
最小化组合方差，不考虑预期收益。

## Algorithm
min_w: w'Σw

Subject to:
  Σw_i = 1
  w_i >= 0

## Solution
Closed form (no optimization needed for long-only):
w* ∝ Σ^(-1)1

## Output Schema
{
  "method": "global_min_variance",
  "expected_return": float (will be lower than market),
  "volatility": float (minimum achievable),
  ...
}
```

##### C2. Risk Parity (Equal Risk Contribution)

**Skill Path**: `skills/risk_parity/`

```markdown
# Risk Parity Skill

## Method Description
每个资产对组合总风险的贡献相等。

## Algorithm
RiskContribution_i = w_i × (∂σ_p/∂w_i) / σ_p
                   = w_i × (Σw)_i / (σ_p × w'Σw)

Set RiskContribution_i = 1/N for all i

Iterative solver:
1. Initialize w = 1/N
2. Compute risk contributions
3. Adjust weights: w_new = w_old × (1/N) / RC
4. Normalize to sum to 1
5. Repeat until convergence

## Parameters
- tol: 1e-6 (convergence tolerance)
- max_iter: 1000

## For bonds (duration adjustment)
- Convert bond vol to equity-equivalent vol using duration
- σ_equity_equiv = σ_bond × Duration / Duration_equity

## Output Schema
{
  "method": "risk_parity",
  "risk_contributions": {...},
  "balance_check": float (max deviation from equal),
  ...
}
```

##### C3. Hierarchical Risk Parity (HRP)

**Skill Path**: `skills/hrp/`

```markdown
# Hierarchical Risk Parity Skill

## Method Description
使用层次聚类和无协方差矩阵求逆的组合优化。

## Algorithm
1. Compute correlation matrix: ρ
2. Compute distance matrix: d_ij = √(0.5(1-ρ_ij))
3. Hierarchical clustering (Ward method)
4. Quasi-diagonalization of covariance matrix
5. Recursive bisection allocation:
   - At each node, allocate risk based on inverse variance
   - Proceed recursively until leaf nodes

## Steps
```
def hrp(cov, corr):
    # Step 1: Distance matrix
    dist = sqrt(0.5 * (1 - corr))

    # Step 2: Hierarchical clustering
    link = linkage(dist, method='ward')

    # Step 3: Quasi-diagonalization
    sort_idx = leaves_list(link)

    # Step 4: Recursive allocation
    def allocate(node, cov_sub):
        if len(node) == 1:
            return {node[0]: 1.0}
        left, right = split(node)
        cov_l, cov_r = split_cov(cov_sub)
        vol_l = sqrt(var_portfolio(weights_left, cov_l))
        vol_r = sqrt(var_portfolio(weights_right, cov_r))
        alpha = vol_r / (vol_l + vol_r)
        alloc_left = allocate(left) * alpha
        alloc_right = allocate(right) * (1 - alpha)
        return merge(alloc_left, alloc_right)
```

## Parameters
- linkage_method: "ward" (default)
- distance_metric: "correlation"

## Output Schema
{
  "method": "hierarchical_risk_parity",
  "cluster_order": [...],
  "dendrogram": string (optional, for visualization),
  ...
}
```

##### C4. Maximum Diversification

**Skill Path**: `skills/max_diversification/`

```markdown
# Maximum Diversification Skill

## Method Description
最大化组合分散化程度。

## Algorithm
max_w: D = (w'σ) / √(w'Σw)

Where:
  σ = vector of individual asset volatilities
  D = diversification ratio

Maximizing D is equivalent to minimizing:
min_w: √(w'Σw) / (w'σ)

## Constraints
- Σw_i = 1
- w_i >= 0

## Interpretation
- D = 1: No diversification (perfect correlation)
- D > 1: Positive diversification benefit
- D = N: Perfect diversification (uncorrelated assets)

## Output Schema
{
  "method": "maximum_diversification",
  "diversification_ratio": float,
  "weighted_avg_vol": float,
  "portfolio_vol": float,
  ...
}
```

##### C5. Minimum Correlation

**Skill Path**: `skills/min_correlation/`

```markdown
# Minimum Correlation Skill

## Method Description
最小化组合加权平均相关系数。

## Algorithm
min_w: Σ_i Σ_j w_i w_j ρ_ij

Subject to:
  Σw_i = 1
  w_i >= 0

## Alternative Formulation
1. Compute average pairwise correlation matrix
2. Sort assets by average correlation
3. Weight inversely to average correlation
4. Optimize for Sharpe (given these weights)

## Output Schema
{
  "method": "minimum_correlation",
  "avg_pairwise_correlation": float,
  ...
}
```

#### Category D: 非传统方法 (5个)

##### D1. CVaR Optimization

**Skill Path**: `skills/cvar_optimization/`

```markdown
# CVaR Optimization Skill

## Method Description
条件风险价值(CVaR)优化，比VaR更关注尾部风险。

## Algorithm
min_w: CVaR_α(w) = (1/(1-α)) ∫_{R≤VaR_α} |R - VaR_α| p(R) dR

For discrete distribution (historical returns):
min_w: (1/(T(1-α))) Σ_t max(VaR_α - R_t, 0)

Subject to:
  Σw_i = 1
  w_i >= 0
  CVaR <= target

## Parameters
- alpha: 0.95 (95% confidence level)
- target_cvar: float (from IPS or risk budget)
- solver: "cvxpy" or "scipy"

## Output Schema
{
  "method": "cvar_optimization",
  "cvar_95": float,
  "var_95": float,
  ...
}
```

##### D2. Max Drawdown-Constrained

**Skill Path**: `skills/max_drawdown_constrained/`

```markdown
# Max Drawdown-Constrained Skill

## Method Description
约束最大回撤的组合优化。

## Algorithm
max_w: E[R(w)]

Subject to:
  Σw_i = 1
  w_i >= 0
  MaxDrawdown(w) <= target

## MaxDrawdown Computation
For historical returns R_1, ..., R_T:
1. Compute cumulative returns: C_t = Π(1+R_i)
2. Running maximum: M_t = max(C_1, ..., C_t)
3. Drawdown: D_t = (M_t - C_t) / M_t
4. Max Drawdown = max(D_t)

## Constraint Handling
- Direct constraint: Non-convex, hard to optimize
- Relaxed form: Limit expected short-fall or use penalty

## Parameters
- target_max_dd: 0.25 (25%, from IPS)
- lookback: 2520 days (10 years)
- penalty_factor: 10.0 (for soft constraint)

## Output Schema
{
  "method": "max_drawdown_constrained",
  "expected_max_drawdown": float,
  "worst_case_loss": float,
  ...
}
```

##### D3. Tail Risk Parity

**Skill Path**: `skills/tail_risk_parity/`

```markdown
# Tail Risk Parity Skill

## Method Description
每个资产对组合尾部风险的贡献相等。

## Algorithm
1. Compute tail risk measure for each asset:
   - TTR_i = CVaR_95(asset_i)
   - Or: Expected loss when return < 5th percentile

2. Equalize tail risk contribution:
   TRC_i = w_i × TTR_i / Σ(w_j × TTR_j) = 1/N

3. Solve iteratively for w

## Alternative: Forward-looking Tail Risk
Use option-implied tail risk from put spreads

## Parameters
- tail_percentile: 5 (5th percentile)
- confidence_level: 0.95
- tol: 1e-6

## Output Schema
{
  "method": "tail_risk_parity",
  "tail_risk_contributions": {...},
  "tail_correlation_matrix": {...},
  ...
}
```

##### D4. Total Portfolio Allocation (TPA)

**Skill Path**: `skills/total_portfolio_allocation/`

```markdown
# Total Portfolio Allocation (TPA) Skill

## Method Description
不基于传统资产类别，而是基于风险因子配置。

## Algorithm
1. Identify two primary factors:
   - Equity factor: Market risk premium
   - Duration factor: Interest rate risk

2. For each asset, decompose exposure:
   - β_equity = correlation with equity factor
   - β_duration = DV01 or modified duration

3. Allocate to factors, then within each factor

4. Two-factor model:
   min_w: Var(r_p) = β_equity² × σ_equity² + β_duration² × σ_duration² + ε

## Factor Exposures (典型值)
| Asset | β_equity | β_duration |
|-------|----------|-------------|
| US Large Cap | 1.0 | 0.0 |
| Long Treasury | 0.0 | 1.0 |
| IG Corporate | 0.3 | 0.5 |
| Gold | 0.0 | 0.0 |

## Parameters
- factor_model: "equity_bond" (default)
- target_equity_risk: 0.6 (60% of total risk)
- target_duration_risk: 0.4 (40%)

## Output Schema
{
  "method": "total_portfolio_allocation",
  "equity_beta": float,
  "duration_beta": float,
  "factor_risk_contributions": {...},
  ...
}
```

##### D5. Adversarial Diversifier

**Skill Path**: `skills/adversarial_diversifier/`

```markdown
# Adversarial Diversifier Skill

## Method Description
构造与主流组合正交的组合，用于增强分散化。

## Algorithm
max_w: TrackingVariance(w, w_centroid)

Where:
  TrackingVariance = (w - w_centroid)' Σ (w - w_centroid)
  w_centroid = mean(weights of other 20 PC methods)

Subject to:
  Σw_i = 1
  w_i >= 0
  Sharpe(w) >= 0.75 × Sharpe(w_max_sharpe)

## Intuition
- Find portfolio most different from consensus
- But maintain minimum quality threshold
- Provides diversification at meta-level

## Parameters
- sharpe_floor: 0.75
- centroid_weights: from other PC agents

## Output Schema
{
  "method": "adversarial_diversifier",
  "tracking_variance": float,
  "correlation_to_centroid": float,
  "similarity_to_nearest_neighbor": float,
  ...
}
```

#### PC Researcher Agent

**类型**: Research Agent
**配置文件路径**: `agents/pc_researcher/`

```markdown
# PC Researcher Agent

## Role
探索新的投资组合构建方法，不被当前21种方法覆盖。

## Workflow
1. Search academic literature for new portfolio methods
2. Scan industry practices for innovative approaches
3. Evaluate novelty vs. existing methods
4. Propose implementation of promising new methods
5. In March 2026 run: Proposed Maximum Entropy method

## Example: Maximum Entropy
E[R] = Σw_i × ln(w_i)  (Shannon entropy, maximized)
Subject to:
  Σw_i = 1
  w_i >= 0
  Sharpe(w) >= target_floor

## Output
- Proposed method name
- Mathematical formulation
- Python implementation
- Backtest results
- Recommendation to add to registry
```

---

### 1.5 CRO Agent (首席风险官智能体)

**类型**: Specialist Agent
**数量**: 1
**配置文件路径**: `agents/cro_agent/`

```markdown
# CRO Agent

## Role
Chief Risk Officer - 生成标准化风险报告

## Description
你是一位首席风险官，负责评估每个投资组合候选方案的风险特征。你的评估是客观的，只报告风险指标，不发表投资观点。

## Inputs
- PC agent's proposed portfolio weights
- covariance_matrix.json
- historical_returns (18 assets)
- IPS constraints

## Outputs
- risk_report_{pc_method}.json
- risk_report_{pc_method}.md

## Risk Metrics Computed

### 1. Ex-Ante Metrics
- Expected Volatility: σ_p = √(w'Σw) × √252
- Expected Return: μ_p = w'μ
- Sharpe Ratio: (μ_p - r_f) / σ_p
- Value at Risk (VaR 95%): Percentile of return distribution
- CVaR (Expected Shortfall): E[R | R < VaR]

### 2. Backtest Metrics (1996-2026)
- Annualized Return
- Annualized Volatility
- Sharpe Ratio (realized)
- Maximum Drawdown
- Calmar Ratio: Return / MaxDD
- Sortino Ratio

### 3. Concentration Metrics
- Effective N: 1 / Σ(w_i²)
- Herfindahl Index: Σ(w_i²)
- Top 5 concentration: Σ w_top5
- Max single asset weight

### 4. Factor Tilts
- Equity beta
- Duration
- Credit spread exposure
- Dollar exposure

### 5. IPS Compliance Check
- Tracking error vs 60/40: √((w - w_60_40)'Σ(w - w_60_40))
- Asset class bounds compliance
- Single asset max weight
- Risk budget compliance

## Output Schema
{
  "method": string,
  "ex_ante": {
    "volatility": float,
    "return": float,
    "sharpe": float,
    "var_95": float,
    "cvar_95": float
  },
  "backtest": {
    "annual_return": float,
    "annual_vol": float,
    "sharpe": float,
    "max_drawdown": float,
    "calmar": float
  },
  "concentration": {
    "effective_n": float,
    "herfindahl": float,
    "top5_concentration": float,
    "max_weight": float
  },
  "factor_tilts": {
    "equity_beta": float,
    "duration": float,
    "credit_spread": float
  },
  "ips_compliance": {
    "tracking_error": float,
    "within_tracking_budget": bool,
    "asset_bounds_ok": bool,
    "passes": bool,
    "violations": []
  }
}
```

---

### 1.6 PC Strategy Review Agent (互评智能体)

**类型**: Review Agent
**数量**: 42 (每个PC Agent评审2个同伴)
**配置文件路径**: `agents/pc_review/`

```markdown
# PC Strategy Review Agent

## Role
Peer reviewer for PC agents' portfolios

## Description
你是一位投资组合评审专家。你的任务是批判性地评估同伴PC方法提出的组合，并提供建设性反馈。

## Assignment
- Intra-category review: 1 peer from same category
- Inter-category review: 1 peer from different category
- Randomized assignment with recorded seed

## Review Criteria

### 1. Methodological Soundness (25%)
- Is the optimization correctly specified?
- Are assumptions reasonable?
- Are constraints properly applied?

### 2. Risk-Return Characteristics (25%)
- Is the risk profile appropriate for the regime?
- Is expected return estimate reasonable?
- Is Sharpe ratio competitive?

### 3. Diversification Quality (25%)
- Are there concentration risks?
- Is effective N reasonable?
- Does it offer true diversification?

### 4. IPS Compliance (25%)
- Tracking error within budget?
- Asset bounds respected?
- Risk budget respected?

## Voting Protocol
Borda Count:
- Top 5 ranking: 5, 4, 3, 2, 1 points
- Bottom flag: -2 points
- Cannot vote for self

## Output
{
  "reviewer": string,
  "reviewed_method": string,
  "scores": {
    "methodology": float (0-25),
    "risk_return": float (0-25),
    "diversification": float (0-25),
    "ips_compliance": float (0-25)
  },
  "total_score": float,
  "strengths": string[],
  "weaknesses": string[],
  "vote_points": int (-2 to 5),
  "vote_rationale": string
}
```

---

### 1.7 CIO Agent (首席投资官智能体)

**类型**: Orchestrator Agent
**数量**: 1
**配置文件路径**: `agents/cio_agent/`

```markdown
# CIO Agent

## Role
Chief Investment Officer - 最终组合选择与Ensemble

## Description
你是一位首席投资官，负责整合21个PC方法的建议，选择最终组合。你有7种Ensemble技术可用，你需要选择最适合当前宏观环境的方法。

## Inputs
- 21 PC portfolio proposals (weights, metrics)
- 42 peer reviews
- CRO risk reports
- Vote tallies
- Metric scores
- macro_view.json

## Scoring Dimensions (6维)
| Dimension | Weight | Description |
|-----------|--------|-------------|
| Backtest Sharpe | 25% | Realized risk-adjusted return |
| IPS Compliance | 15% | IPS约束满足程度 |
| Diversification | 15% | 分散化质量 |
| Regime Fit | 20% | 与当前宏观周期匹配度 |
| Estimation Robustness | 15% | 对估计误差的稳健性 |
| CMA Utilization | 10% | 对资本市场假设的利用 |

## Ensemble Methods (7种)

### 1. Simple Average
w_ensemble = (1/21) Σ w_i

### 2. Inverse Tracking Error
w_i_weight ∝ 1 / TE_i
TE_i = tracking error vs centroid

### 3. Backtest Sharpe Weighting
w_i_weight ∝ Sharpe_i / Σ Sharpe_j

### 4. Meta-Optimization
Treat PC portfolios as "assets" in second-level MVO
min_w2: w2'Σ_2 w2 - λw2'μ_2
Where Σ_2 = correlation matrix of PC returns

### 5. Regime-Conditional Weighting
Adjust weights based on macro regime:
- Expansion: Favor return-optimized (B)
- Late-Cycle: Favor risk-structured (C)
- Recession: Favor low-vol (A, C)
- Recovery: Balanced

### 6. Composite Score Weighting
w_i_weight ∝ CompositeScore_i

### 7. Trimmed Mean
Remove top/bottom 2 outliers by Sharpe
Average remaining 17 portfolios

## Selection Logic
1. Evaluate each ensemble on diagnostic suite
2. Check IPS compliance (non-negotiable)
3. Select ensemble method best suited for current regime
4. Provide written rationale

## Output Schema
{
  "selected_ensemble": string,
  "ensemble_weights": {...},
  "portfolio_summary": {
    "expected_return": float,
    "expected_volatility": float,
    "sharpe_ratio": float,
    "effective_n": float,
    "tracking_error_vs_60_40": float
  },
  "allocation_by_asset_class": {
    "equity": float,
    "fixed_income": float,
    "real_assets": float,
    "cash": float
  },
  "top_positions": [{asset, weight, risk_contrib}],
  "changes_since_last_review": string[],
  "key_risks_to_monitor": string[],
  "rebalancing_plan": string,
  "ips_compliance_statement": string
}
```

---

### 1.8 Meta Agent (元智能体)

**类型**: Learning Agent
**数量**: 1
**配置文件路径**: `agents/meta_agent/`

```markdown
# Meta Agent

## Role
Self-learning and improvement agent

## Description
对比历史预测与实际收益，自动识别系统性弱点，并修改Skill代码和Agent提示词以改进未来表现。

## Workflow

### Step 1: Compute Feedback
Compare against realized returns over rolling 3-year window:
- Regime classification accuracy
- Cross-sectional rank correlation of expected returns
- Signal hit rates
- Per-method prediction error by asset class and regime

### Step 2: Analyze Feedback
- Identify systematic weaknesses
- Research potential improvements through backtesting
- Find statistical significance of changes

### Step 3: Implement Improvements
Modify files:
- Skill methodology documents
- Agent prompt descriptions
- Python code in core modules

### Step 4: Document Changes
Structured record:
- Evidence base
- Reasoning
- Exact modifications

## Constraints
- All changes logged for human review
- Human sets bounds on self-improvement
- Revert capability maintained

## Output Schema
{
  "period_analyzed": {start, end},
  "feedback_summary": {
    "regime_accuracy": float,
    "return_rank_correlation": float,
    "signal_hit_rate": float,
    "method_errors": {...}
  },
  "changes_made": [{
    "file": string,
    "change_type": "methodology | prompt | code",
    "description": string,
    "rationale": string,
    "evidence": string
  }],
  "recommended_review": boolean
}
```

---

## 2. Pipeline 数据流

```
                    ┌─────────────────┐
                    │   IPS (Markdown)│
                    └────────┬────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────┐
│                   STEP 1: MACRO AGENT                     │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ Input: IPS, Macro Data (Yahoo Finance)             │  │
│  │ Output: macro_view.json, macro_analysis.md        │  │
│  │ - Regime: {expansion | late_cycle | recession |    │  │
│  │           recovery}                                 │  │
│  │ - 4-dimension scores + composite                   │  │
│  └─────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
                             │
            ┌────────────────┼────────────────┐
            ▼                ▼                ▼
┌──────────────────────────────────────────────────────────┐
│              STEP 2: ASSET CLASS AGENTS (18)            │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐        │
│  │US LC    │ │US SC    │ │Intl Dev │ │Emg Mkt  │ ...    │
│  │(7 CMA)  │ │(7 CMA)  │ │(7 CMA)  │ │(7 CMA)  │        │
│  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘        │
│       └────────────┴────────────┴────────────┘           │
│                         │                                 │
│                         ▼                                 │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ CMA JUDGE SKILL (per asset class)                   │  │
│  │ - Evaluates 7 methods                               │  │
│  │ - Selects/combines final CMA                       │  │
│  │ - Outputs: cma.json, signals.json                  │  │
│  └─────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────┐
│              STEP 3: COVARIANCE AGENT                     │
│  Input: Historical returns (18 assets, 5 years)          │
│  Output: covariance_matrix.json, correlation_matrix.json │
│  Method: Sample covariance + Ledoit-Wolf shrinkage      │
└──────────────────────────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────┐
│           STEP 4: PORTFOLIO CONSTRUCTION (21)             │
│  ┌──────────────────────────────────────────────────┐    │
│  │ Category A (5): Equal Weight, Mkt Cap, Inv Vol,  │    │
│  │                Inv Var, Vol Targeting             │    │
│  │ Category B (5): Max Sharpe, BL, Robust MV, REF,  │    │
│  │                Mean-Downside                      │    │
│  │ Category C (5): GMV, Risk Parity, HRP, Max Div,  │    │
│  │                Min Corr                          │    │
│  │ Category D (5): CVaR, MaxDD, Tail RP, TPA,      │    │
│  │                Adversarial                       │    │
│  │ Researcher: Max Entropy (proposed new method)    │    │
│  └──────────────────────────────────────────────────┘    │
│  Each outputs: weights.json, metrics.json                │
└──────────────────────────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────┐
│           STEP 5: PC STRATEGY REVIEW                      │
│  ┌────────────────────────────────────────────────────┐  │
│  │ CRO Agent: Risk Report for each portfolio          │  │
│  │ - 42 peer reviews (each PC reviews 2 peers)       │  │
│  │ - Borda count voting                              │  │
│  │ - Top 5 shortlist (diversity constraint)          │  │
│  │ - Revision round                                  │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────┐
│                    STEP 6: CIO AGENT                      │
│  Input: 21 proposals, reviews, votes, risk reports       │
│  7 Ensemble Methods evaluated                            │
│  Select best based on regime + metrics                  │
│  Output: Board Memo (Markdown)                          │
└──────────────────────────────────────────────────────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  BOARD MEMO     │
                    │  (Markdown)     │
                    └─────────────────┘
```

---

## 3. 数据库Schema

### SQLite Tables

```sql
-- Macro views history
CREATE TABLE macro_views (
    id INTEGER PRIMARY KEY,
    timestamp TEXT NOT NULL,
    regime TEXT NOT NULL,
    confidence TEXT,
    composite_score REAL,
    recession_probability REAL,
    scores_json TEXT NOT NULL,
    key_indicators_json TEXT NOT NULL
);

-- CMA results per asset class
CREATE TABLE cma_results (
    id INTEGER PRIMARY KEY,
    timestamp TEXT NOT NULL,
    asset_slug TEXT NOT NULL,
    method TEXT NOT NULL,
    expected_return REAL NOT NULL,
    confidence REAL,
    raw_output_json TEXT
);

-- Portfolio proposals
CREATE TABLE portfolio_proposals (
    id INTEGER PRIMARY KEY,
    timestamp TEXT NOT NULL,
    method TEXT NOT NULL,
    category TEXT NOT NULL,
    weights_json TEXT NOT NULL,
    expected_return REAL,
    expected_vol REAL,
    sharpe_ratio REAL,
    max_drawdown REAL,
    effective_n REAL,
    review_score REAL,
    vote_points INTEGER,
    in_top5 BOOLEAN
);

-- Risk reports
CREATE TABLE risk_reports (
    id INTEGER PRIMARY KEY,
    timestamp TEXT NOT NULL,
    method TEXT NOT NULL,
    ex_ante_json TEXT,
    backtest_json TEXT,
    concentration_json TEXT,
    factor_tilts_json TEXT,
    ips_compliance_json TEXT
);

-- Board memos
CREATE TABLE board_memos (
    id INTEGER PRIMARY KEY,
    timestamp TEXT NOT NULL,
    selected_ensemble TEXT,
    portfolio_summary_json TEXT,
    allocation_by_class_json TEXT,
    top_positions_json TEXT,
    memo_content TEXT NOT NULL
);

-- Meta agent feedback
CREATE TABLE meta_feedback (
    id INTEGER PRIMARY KEY,
    timestamp TEXT NOT NULL,
    period_start TEXT,
    period_end TEXT,
    feedback_summary_json TEXT,
    changes_json TEXT,
    recommended_review BOOLEAN
);
```

---

## 4. IPS配置格式

**config/ips.md**:
```markdown
# Investment Policy Statement
**Version**: 2026-04-09
**Institution**: Self-Driving Portfolio System

## 1. Investment Universe

### Eligible Asset Classes
| Asset | Benchmark | Min Weight | Max Weight |
|-------|-----------|------------|------------|
| US Large Cap Equity | SPTR Index | 0% | 50% |
| US Small Cap Equity | SMLTR Index | 0% | 15% |
| US Value Equity | CSUSVALU Index | 0% | 20% |
| US Growth Equity | CSUSGRWU Index | 0% | 20% |
| Intl Developed Equity | MXWO Index | 0% | 30% |
| Emg Markets Equity | MXEF Index | 0% | 20% |
| US Short Treasury | BPTXY10 Index | 0% | 30% |
| US Interm Treasury | BPTXY30 Index | 0% | 40% |
| US Long Treasury | BPTXY10 Index | 0% | 30% |
| IG Corporate | CPATREIT Index | 0% | 20% |
| HY Corporate | HWCI Index | 0% | 15% |
| Intl Sovereign | LEGATRUU Index | 0% | 20% |
| Intl Corporate | LGCPTRUU Index | 0% | 15% |
| USD Emg Debt | EMUSTOTL Index | 0% | 15% |
| REITs | FTV Index | 0% | 15% |
| Gold | XAU USD | 0% | 10% |
| Commodities | GSCI Index | 0% | 15% |
| Cash | US0001M Index | 0% | 20% |

## 2. Objectives

### Return Target
- **Real Return**: CPI + 3.0% to 4.0%
- **Nominal Equivalent**: ~5.5% to 6.5% (assuming 2.5% inflation)

### Risk Budget
- **Expected Volatility**: 8% to 12% annualized
- **Maximum Drawdown**: -25% peak-to-trough

## 3. Active Risk Budget
- **Tracking Error vs 60/40**: Maximum 6% annualized
- **Benchmark**: 60% MSCI ACWI / 40% Bloomberg Aggregate

## 4. Constraints

### Asset Class Bounds
- See table above (Min/Max Weight)

### Concentration Limits
- Single asset max: See table above
- Effective N (diversification): Minimum 5

### Liquidity Requirements
- All positions must be liquid (ETF-based)
- No private markets, PE, or illiquid alternatives

## 5. Rebalancing Policy
- **Review Frequency**: Quarterly
- **Off-cycle triggers**:
  - Tracking error > 6%
  - Single asset > max weight + 5%
  - Regime change (Macro Agent signal)
```

---

## 5. 输出格式

### Board Memo Template

```markdown
# Board Memo: Strategic Asset Allocation
**Date**: {date}
**Period**: {quarter}
**Prepared by**: CIO Agent
**Status**: APPROVED / DRAFT

## Executive Summary

{2-3 paragraph summary of recommendation}

## Recommended Allocation

| Asset Class | Weight | Change from Prior |
|-------------|--------|-------------------|
| US Large Cap | 8.9% | -1.2% |
| ... | ... | ... |

### Asset Class Summary
- **Equity**: 44.9% (vs 60% in 60/40 benchmark)
- **Fixed Income**: 41.7% (vs 40%)
- **Real Assets**: 5.1%
- **Cash**: 8.1%

## Macro Rationale

{2-3 paragraphs on why this allocation fits the macro environment}

## Changes Since Last Review

### Major Changes
- {list of significant allocation changes}

### Rationale for Changes
{explain why changes were made}

## Risk Analysis

### Expected Risk Metrics
| Metric | Value |
|--------|-------|
| Expected Return | 6.87% |
| Expected Volatility | 7.54% |
| Sharpe Ratio | 0.43 |
| Max Drawdown (backtest) | -25.6% |
| Tracking Error vs 60/40 | 2.41% |

### Key Risks to Monitor
1. {risk 1}
2. {risk 2}
3. {risk 3}

## Portfolio Construction Details

### Method Selection
The CIO selected **{ensemble_method}** from among 7 ensemble techniques.

### Top Portfolio Contributors
1. {method 1}: {weight}%
2. {method 2}: {weight}%
3. {method 3}: {weight}%

## Rebalancing Plan

### Quarterly Review
- Review date: {date + 3 months}
- Trigger conditions: See IPS

### Off-Cycle Monitoring
- Tracking error breach: > 6%
- Drift trigger: Any asset > weight + 5%
- Regime change: Macro Agent signal

## IPS Compliance Statement

**COMPLIANT** / **NON-COMPLIANT**

The recommended portfolio:
- [ ] Meets real return target of CPI + 3-4%
- [ ] Expected volatility within 8-12% band
- [ ] Maximum drawdown expected < -25%
- [ ] Tracking error < 6% vs benchmark
- [ ] All asset class bounds respected
- [ ] Effective N >= 5

## Dissenting Views

{any minority views from PC agent voting}

---
*This memo was generated by an AI agentic system. Human review required before implementation.*
```

---

## 6. 项目文件结构

```
/Users/zhang/code/ai/quant/
├── config/
│   ├── ips.md                    # 投资政策声明
│   └── settings.yaml             # 系统配置 (LLM API keys, etc.)
├── agents/                       # 智能体定义 (Claude Code Agent format)
│   ├── macro_agent/
│   │   ├── agent.yaml            # Agent配置
│   │   └── prompts.md            # 角色描述
│   ├── asset_class_agents/
│   │   ├── _template/            # 通用模板
│   │   ├── us_large_cap/
│   │   ├── us_small_cap/
│   │   ├── us_value/
│   │   ├── us_growth/
│   │   ├── intl_developed/
│   │   ├── emg_markets/
│   │   ├── us_short_treasury/
│   │   ├── us_interm_treasury/
│   │   ├── us_long_treasury/
│   │   ├── ig_corporate/
│   │   ├── hy_corporate/
│   │   ├── intl_sovereign/
│   │   ├── intl_corporate/
│   │   ├── usd_em_debt/
│   │   ├── reits/
│   │   ├── gold/
│   │   ├── commodities/
│   │   └── cash/
│   ├── covariance_agent/
│   ├── pc_agents/
│   │   ├── _base/                # PC agent基类
│   │   ├── equal_weight/
│   │   ├── market_cap_weight/
│   │   ├── inverse_volatility/
│   │   ├── inverse_variance/
│   │   ├── volatility_targeting/
│   │   ├── max_sharpe/
│   │   ├── black_litterman/
│   │   ├── robust_mean_variance/
│   │   ├── resampled_frontier/
│   │   ├── mean_downside_risk/
│   │   ├── global_min_variance/
│   │   ├── risk_parity/
│   │   ├── hrp/
│   │   ├── max_diversification/
│   │   ├── min_correlation/
│   │   ├── cvar_optimization/
│   │   ├── max_drawdown_constrained/
│   │   ├── tail_risk_parity/
│   │   ├── tpa/
│   │   ├── adversarial_diversifier/
│   │   └── pc_researcher/
│   ├── cro_agent/
│   ├── pc_review/
│   ├── cio_agent/
│   └── meta_agent/
├── skills/                       # 独立Skills
│   ├── cma_judge/
│   │   └── SKILL.md
│   ├── equal_weight/
│   │   └── SKILL.md
│   ├── max_sharpe/
│   │   └── SKILL.md
│   ├── risk_parity/
│   │   └── SKILL.md
│   └── ... (其他16+个)
├── core/                         # 核心模块
│   ├── __init__.py
│   ├── pipeline.py              # 主管道协调
│   ├── database.py              # SQLite接口
│   ├── data_fetcher.py          # Yahoo Finance
│   ├── macro_analyzer.py         # 宏观分析逻辑
│   ├── cma_builder.py           # CMA构建
│   ├── covariance.py             # 协方差估算
│   ├── portfolio_optimizer.py    # 优化器接口
│   ├── voting.py                # 投票逻辑
│   ├── ensemble.py              # Ensemble方法
│   ├── risk_metrics.py          # 风险指标计算
│   └── utils.py
├── output/                       # 输出
│   └── board_memos/
│       └── YYYY-MM-DD.md
├── database/
│   └── portfolio.db            # SQLite数据库
├── tests/
│   ├── test_macro_agent.py
│   ├── test_cma_methods.py
│   ├── test_portfolio_methods.py
│   ├── test_voting.py
│   └── test_pipeline.py
├── CLAUDE.md
├── requirements.txt
└── README.md
```

---

## 7. Acceptance Criteria

- [ ] Macro Agent正确分类经济周期，输出置信度
- [ ] 18个Asset Class Agent每生成7个CMA方法结果
- [ ] CMA Judge Skill根据regime和valuation选择正确方法
- [ ] Covariance Agent输出18×18协方差矩阵
- [ ] 21个PC Agent产生有效组合权重
- [ ] CRO Agent为每个组合生成标准化风险报告
- [ ] 42个peer review完成，投票正确统计
- [ ] Top 5满足diversity约束(来自≥3个category)
- [ ] CIO Agent选择合适ensemble方法
- [ ] Board Memo包含所有必需section
- [ ] IPS约束被正确执行
- [ ] SQLite数据库正确存储所有中间结果
```

## Non-goals

- 不实现交易执行模块
- 不实现风控实时监控系统
- 不接入Bloomberg等付费数据源

## Dependencies

- yfinance (Yahoo Finance数据)
- numpy, pandas (数据处理)
- scipy, cvxpy (优化)
- sqlite3 (数据库)
- anthropic SDK / openai SDK (LLM调用)

## Open Questions

- [x] 50个智能体同时调用LLM的成本控制策略
- [x] Meta Agent自我修改代码的安全边界
- [ ] 历史回测的lookahead bias处理（论文提到的DatedGPT方案）
