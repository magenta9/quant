# 逆波动率组合技能

通过 `core.portfolio_optimizer.optimize_portfolio` 实现 `inverse_volatility` MVP 组合方法。

## 约定
- 方法名：`inverse_volatility`
- 输出：`PortfolioProposalOutput`
- 约束：仅做多、权重之和必须为 1，并强制执行 `core.assets` 中的 IPS 最小/最大边界
- 如果方差输入无效或 IPS 边界不可行，应显式报错，而不是静默裁剪

## 方法规则
- 使用协方差矩阵对角线上的资产逆波动率作为目标配置的信号
- 将目标权重传入共享约束层，确保输出方案符合 IPS 且具备确定性
- 复用共享协方差与风险指标辅助函数，生成摘要字段和元数据
