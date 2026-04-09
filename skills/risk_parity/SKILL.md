# 风险平价组合技能

通过 `core.portfolio_optimizer.optimize_portfolio` 实现 `risk_parity` MVP 组合方法。

## 约定
- 方法名：`risk_parity`
- 输出：`PortfolioProposalOutput`
- 约束：仅做多、权重之和必须为 1，并强制执行 `core.assets` 中的 IPS 最小/最大边界
- 当受约束求解无法产生有效且符合 IPS 的组合时，该方法必须显式失败

## 方法规则
- 使用共享协方差矩阵求解各 sleeve 总风险贡献近似相等的配置
- 复用共享优化器接口、共享约束处理和共享风险指标辅助函数
- 在输出元数据中显式保留所有假设，供后续 CRO 使用
