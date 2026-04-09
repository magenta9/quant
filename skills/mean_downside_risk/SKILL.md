# 均值下行风险组合技能

通过 `core.portfolio_optimizer.optimize_portfolio` 实现 `mean_downside_risk` 组合方法。

## 约定
- 方法名：`mean_downside_risk`
- 输出：`PortfolioProposalOutput`
- 约束：仅做多、权重之和必须为 1，并强制执行 `core.assets` 中的 IPS 最小/最大边界
- 如果所选资产范围在 IPS 边界下不可行，应显式报错，而不是静默裁剪

## 方法规则
- 对下行风险代理值更高的资产施加惩罚，同时奖励正的超额收益
- 如果所有下行调整后分数都失效，则回退到逆波动率组合
- 复用共享协方差与风险指标辅助函数，生成预期收益、波动率、Sharpe 和元数据
