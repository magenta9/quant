# 稳健均值-方差组合技能

通过 `core.portfolio_optimizer.optimize_portfolio` 实现 `robust_mean_variance` 组合方法。

## 约定
- 方法名：`robust_mean_variance`
- 输出：`PortfolioProposalOutput`
- 约束：仅做多、权重之和必须为 1，并强制执行 `core.assets` 中的 IPS 最小/最大边界
- 如果所选资产范围在 IPS 边界下不可行，应显式报错，而不是静默裁剪

## 方法规则
- 在优化前将预期收益向截面均值收缩
- 在协方差估计中加入小的对角岭项，以降低估计敏感性
- 复用共享协方差与风险指标辅助函数，生成预期收益、波动率、Sharpe 和元数据
