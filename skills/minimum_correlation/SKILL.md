# 最小相关性组合技能

通过 `core.portfolio_optimizer.optimize_portfolio` 实现 `minimum_correlation` 组合方法。

## 约定
- 方法名：`minimum_correlation`
- 输出：`PortfolioProposalOutput`
- 约束：仅做多、权重之和必须为 1，并强制执行 `core.assets` 中的 IPS 最小/最大边界
- 如果所选资产范围在 IPS 边界下不可行，应显式报错，而不是静默裁剪

## 方法规则
- 基于共享协方差输入推导相关矩阵，并奖励平均两两相关性更低的资产
- 将得到的分数标准化为满仓的仅做多配置
- 复用共享协方差与风险指标辅助函数，生成预期收益、波动率、Sharpe 和元数据
