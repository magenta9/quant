# 全局最小方差组合技能

通过 `core.portfolio_optimizer.optimize_portfolio` 实现 `global_min_variance` MVP 组合方法。

## 约定
- 方法名：`global_min_variance`
- 输出：`PortfolioProposalOutput`
- 约束：仅做多、权重之和必须为 1，并强制执行 `core.assets` 中的 IPS 最小/最大边界
- 优化器必须显式暴露不可行的 IPS 资产范围，而不是静默裁剪

## 方法规则
- 在共享 IPS 约束下最小化组合总方差
- 复用共享协方差估计与共享风险指标辅助函数，生成方案统计信息
- 保持实现具备确定性且可审计，以便后续 CRO 复核
