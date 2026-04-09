# 波动率目标控制组合技能

通过 `core.portfolio_optimizer.optimize_portfolio` 实现 `volatility_targeting` 组合方法。

## 约定
- 方法名：`volatility_targeting`
- 输出：`PortfolioProposalOutput`
- 约束：仅做多、权重之和必须为 1，并强制执行 `core.assets` 中的 IPS 最小/最大边界
- 如果所选资产范围在 IPS 边界下不可行，应显式报错，而不是静默裁剪

## 方法规则
- 从最大 Sharpe 的子组合配比开始；当事前波动率超过防御性目标时，再向逆波动率组合混合
- 在元数据中记录目标波动率和未受约束的基础波动率，以保证可审计性
- 复用共享协方差与风险指标辅助函数，生成预期收益、波动率、Sharpe 和元数据
