# tasks/codex_batch_queue.md —— Codex 待办队列（攒批，等王家兴发话再派）

> 规则（2026-09-18 起）：DSH 只往这里追加任务，**不单独开轮次**。王家兴说「用 Codex」时，这份文件整体就是任务单。
> 每条必须自包含：读什么、做什么、产物路径、验收标准、禁止事项。DSH 不派"边聊边做"的活。

## 批次 1（待派）
### Q1 独立复核 RUL 基线（含精确斜率特征版）
- 读：results/2026-09-17/dsh/rul_baseline_metrics.csv（**精确斜率版：GBR RMSE 15.27 / PHM08 434**，已落盘）
- 做：自己从零实现 C-MAPSS FD001 的 RUL 基线（逐周期训练 + 125 截断 + 官方未截断真值），至少两模型 + 两个平凡对照
- 产物：src/codex/2026-09-<日期>_01_rul_repro.py、results/<日期>/codex/rul_repro.{csv,md}
- 验收：与 DSH 逐项偏差 ≤10%，并给出偏差归因；对照行必须保留

### Q2 独立复核决策层 v6（会计口径 + 成本敏感性）
- 读：results/2026-09-18/dsh/decision_policy_v6.md、decision_policy_v6.csv、decision_sensitivity_v6.csv、decision_sensitivity_v6.md（**v6 口径已定稿，2026-09-19 更新**）
- 做：自己实现"紧急单元"会计口径与三种策略对比，独立复算单台成本与紧急召回
- 产物：results/<日期>/codex/decision_v6_repro.{csv,md}
- 验收：整数与关键比例一致；若不一致，指出你认为 DSH 哪一步口径有误

### Q3 整链脚本的独立审计
- 读：src/dsh/2026-09-18_14_pipeline.py（检测→诊断→RUL→决策一条命令，**已产出**）与 run_all.py（一键复现）、docs/06_复现指南.md
- 做：只做代码与数据流审计（不重跑全链），回答三问：① 有没有信息泄漏（用未来数据）② 有没有用不存在的标签做训练/调参 ③ 有没有把仿真/占位参数当真实结果输出
- 产物：results/<日期>/codex/pipeline_audit.md

### Q4 独立复核诊断模块的两组结论
- 读：results/2026-09-19/dsh/cwru_adapt_metrics.csv（归一化策略对照）、results/2026-09-18/dsh/cwru_multiseverity_metrics.csv（多尺寸训练）
- 做：自己从零实现 CWRU 特征与分类（可用简化特征），复核两个结论：
  ① 多尺寸训练有效（E4 7+14→21mil 宏F1 约 0.62，明显高于 E3 7→14mil 约 0.45~0.54）
  ② 归一化要挑对象（只归相对量：跨转速 0.899、跨尺寸 +0.037；全归一化：跨转速掉到 0.550）
- 产物：results/<日期>/codex/diag_repro.{csv,md}
- 验收：结论方向一致即可（数值允许差异），若方向相反必须给出证据

### Q5 核对它自己的数字与文件一致性（10 分钟）
- 读：PROJECT_STATE.md 第 16 节双模型对比表；results/2026-09-18/codex/metropt3_ownmodel_unified_primary.json
- 做：核对表中"Codex 路线"那一行的每个数字是否与你落盘文件严格一致；不一致就指出
- 产物：results/<日期>/codex/self_consistency.md

## 规则提醒（写给它看的）
- 不要改 src/dsh/ 与 results/*/dsh/；不要动 data/
- 数字必须可复现；跑不出来就写跑不出来
- 收工：logs/实验日志.md 五段式 + handoff/<日期>_codex_to_dsh.md（只把文件名告诉人，不粘贴正文）
