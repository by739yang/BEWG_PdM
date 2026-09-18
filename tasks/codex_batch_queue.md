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
- 读：results/2026-09-18/dsh/decision_policy_v6.md、decision_policy_v6.csv、decision_sensitivity_grid.csv（待 DSH 更新为 v6 网格）
- 做：自己实现"紧急单元"会计口径与三种策略对比，独立复算单台成本与紧急召回
- 产物：results/<日期>/codex/decision_v6_repro.{csv,md}
- 验收：整数与关键比例一致；若不一致，指出你认为 DSH 哪一步口径有误

### Q3 整链脚本的独立审计
- 读：DSH 即将产出的 src/dsh/2026-09-<日期>_<n>_pipeline.py（检测→诊断→RUL→决策一条命令）
- 做：只做代码与数据流审计（不重跑全链），回答三问：① 有没有信息泄漏（用未来数据）② 有没有用不存在的标签做训练/调参 ③ 有没有把仿真/占位参数当真实结果输出
- 产物：results/<日期>/codex/pipeline_audit.md

## 规则提醒（写给它看的）
- 不要改 src/dsh/ 与 results/*/dsh/；不要动 data/
- 数字必须可复现；跑不出来就写跑不出来
- 收工：logs/实验日志.md 五段式 + handoff/<日期>_codex_to_dsh.md（只把文件名告诉人，不粘贴正文）
