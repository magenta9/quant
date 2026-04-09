# Black-Litterman 组合技能

通过 `core.portfolio_optimizer.optimize_portfolio` 实现 `black_litterman` 组合方法。

## 约定
- 方法名：`black_litterman`
- 输出：`PortfolioProposalOutput`
- 约束：仅做多、权重之和必须为 1，并强制执行 `core.assets` 中的 IPS 最小/最大边界
- 如果所选资产范围在 IPS 边界下不可行，应显式报错，而不是静默裁剪

## 方法规则
- 将协方差矩阵隐含的均衡收益与 `CMA` 预期收益向量混合，形成后验视图
- 通过共享受约束优化层优化该后验视图
- 在元数据中保留后验收益向量和隐含收益向量，以保证可审计性
