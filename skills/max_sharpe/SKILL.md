# 最大 Sharpe 组合技能

通过 `core.portfolio_optimizer.optimize_portfolio` 实现 `max_sharpe` MVP 组合方法。

## 约定
- 方法名：`max_sharpe`
- 输出：`PortfolioProposalOutput`
- 约束：仅做多、权重之和必须为 1，并强制执行 `core.assets` 中的 IPS 最小/最大边界
- 优化器必须使用共享协方差估计和预期收益，并在受约束求解不可行时显式失败

## 方法规则
- 通过共享优化器接口求解受约束的最大 Sharpe 问题
- 在优化与方案指标中一致使用提供的无风险利率
- 复用共享风险辅助函数，使输出字段与 CRO 流水线约定保持一致
