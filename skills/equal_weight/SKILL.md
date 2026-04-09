# 等权重组合技能

通过 `core.portfolio_optimizer.optimize_portfolio` 实现 `equal_weight` MVP 组合方法。

## 约定
- 方法名：`equal_weight`
- 输出：`PortfolioProposalOutput`
- 约束：仅做多、权重之和必须为 1，并强制执行 `core.assets` 中的 IPS 最小/最大边界
- 如果所选资产范围在 IPS 边界下不可行，应显式报错，而不是静默裁剪

## 方法规则
- 从请求的资产范围各 sleeve 等权重开始
- 应用共享优化器约束层，确保最终方案可审计且符合 IPS
- 复用共享协方差与风险指标辅助函数，生成预期收益、波动率、Sharpe 和元数据
