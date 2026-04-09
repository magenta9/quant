# CMA 裁决技能

确定性地为单个资产选择最终 `CMA` 估计，同时在产物集合中明确保留不受支持的方法。

## MVP 方法可用性

### 第 2 阶段可执行
1. **历史 ERP + 无风险利率（Historical ERP + Risk-Free）**
2. **阶段调整 ERP（Regime-Adjusted ERP）**
3. **自动混合（Auto-Blend）**

### 第 2 阶段仅提供结构化桩
- `black_litterman` — 后续阶段依赖协方差和均衡输入
- `inverse_gordon` — 不可用，因为需要付费/供应商数据
- `implied_erp` — 不可用，因为需要付费/供应商数据
- `survey_consensus` — 不可用，因为需要付费/供应商数据

每个不可用方法都必须输出结构化桩结果，包含：
- `name`
- `available: false`
- `expected_return: null`
- `confidence: null`
- `rationale`
- `required_inputs`

不要为不可用输入伪造近似值。

## 裁决规则

### 1. 评估可用方法之间的离散度
- **收敛（Tight）**：离散度 < 3 个百分点 → 接受 `auto_blend`
- **中等/宽幅（Moderate/Wide）**：继续评估所处阶段环境

### 2. 在 MVP 可用性约束下应用阶段逻辑
- **扩张期（Expansion）**：默认使用 `auto_blend`
- **周期后段（Late cycle）**：默认使用 `auto_blend`，除非可用方法出现显著分歧且明显需要防御性倾向
- **复苏期（Recovery）**：默认使用 `auto_blend`
- **衰退期（Recession）**：当离散度具有意义时，优先使用 `regime_adjusted_erp`，因为面向估值的前瞻方法尚不可用

### 3. 遵守方法可用性限制
- 如果规范期偏好的方法在 MVP 中仅为桩实现，不要用伪造代理替代
- 说明该决策仅基于当前可执行的方法集合做出

### 4. 最终约束
- 最终选定的 `CMA` 必须保持在可执行方法结果的最小/最大范围内

## 输出要求

- `cma_methods.json` 包含所有可执行方法以及结构化桩
- `cma.json` 记录选定方法、选定预期收益、置信度和裁决备注
- 裁决备注应明确说明何时由于桩化方法而无法做出更丰富的基于估值的决策
