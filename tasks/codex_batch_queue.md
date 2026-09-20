# tasks/codex_batch_queue.md —— Codex 待办队列（攒批，等项目负责人发话再派）

> 规则（2026-09-18 起）：DSH 只往这里追加任务，**不单独开轮次**。项目负责人说「用 Codex」时，这份文件整体就是任务单。
> 每条必须自包含：读什么、做什么、产物路径、验收标准、禁止事项。DSH 不派"边聊边做"的活。

## 批次 1（Q1 已完成 2026-09-19，其余待派）
### Q1 独立复核 RUL 基线（含精确斜率特征版）—— 已完成 2026-09-19，判定复现成功
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

## 批次 2（**已于 2026-09-20 派发**，任务单 tasks/2026-09-20_codex.md；项目负责人 2026-09-20 说「用 Codex」）
**派发顺序与预算**：Q3（静态审计，约 15 分钟）→ Q5（自一致性，约 10 分钟）→ Q4（诊断复核，约 40 分钟）→ Q2（决策层复核，约 40 分钟）→ Q6（消融复核，约 30 分钟）。
一次会话做完最好；做不完就按顺序停，未完成项留在本文件里等下一批。

### Q6 独立复核检测消融与鲁棒性结论（新增 2026-09-19）
- 读：results/2026-09-19/dsh/ablation_robustness.csv、ablation_robustness_report.md、PROJECT_STATE.md 第 17 节
- 做：自己实现"工况条件化 / 派生特征 / 聚合方式"三处开关，至少复核两条结论：
  ① 不做工况条件化会导致完全失效（0 告警）
  ② 去掉派生特征（TP3-Reservoirs、TP3-H1）会让 timely 召回归零
  允许用简化打分链路，但要说明简化处；不要求复现具体数值
- 产物：results/<日期>/codex/ablation_repro.{csv,md}
- 验收：结论方向一致；若方向相反必须给出证据与反例

### 派发时的统一要求（写给它看的）
- 先读 PROJECT_STATE.md 第 00 节冷启动清单
- 每个 Q 都自包含：读什么、做什么、产物路径、验收标准
- 不要改 src/dsh/ 与 results/*/dsh/；不要动 data/
- 收工：logs/实验日志.md 追加一条；handoff/<日期>_codex_to_dsh.md 写回；只把文件名告诉人

### Q7 独立复核双基线模块与「冻结参考域」结论（新增 2026-09-20，约 30 分钟）
- 读：src/dsh/dual_baseline.py、results/2026-09-20/dsh/dual_baseline_report.md、PROJECT_STATE.md 第 18.1 节
- 数据：results/2026-09-20/dsh/bsm1_120d_{baseline,degraded}.csv（已入库，可直接读）
- 做：自己实现「冻结参考窗 → 逐点 z 或等价标准化 → 聚合 → 事件机」的最小链路，至少复核两条结论：
  ① 冻结参考窗取第 0-10 天时，健康运行 120 天内误报远多于取第 30-45 天（方向一致即可，不要求复现 75 次 / 0 次）
  ② 参考窗若取在退化开始之后（第 30-45 天），退化运行的告警数会显著下降（参考窗吸收退化）
  ③ 刀锋边缘检查：健康运行（results/2026-09-20/dsh/bsm1_120d_baseline.csv）在冻结通道上越限样本数/最长连续长度，与最轻微退化场景（bsm1_sweep_keep80_ramp100.csv）相比，是否确实只差一个采样点（结论方向一致即可）
  ④ 工况泛化复核：用 results/2026-09-20/dsh/bsm1_winB_120_240_baseline.csv 与 bsm1_winC_240_360_baseline.csv（另两段进水窗），核对「健康运行 SO3 本底更低 -> 绝对阈值 SO3<0.5 在健康运行中已长期成立」这一方向是否成立；若成立，指出绝对阈值判据的失效条件
- 允许简化打分链路，但要写明简化处与所用分位/事件机参数
- 产物：results/<日期>/codex/dual_baseline_repro.md
- 验收：结论方向一致；若方向相反必须给出证据与反例


## 批次 3（2026-09-20 晚预备，项目负责人说「再让他工作一次」时派发）
**派发顺序与预算**：Q9（数据坑独立确认，约 10 分钟）→ Q10（P1–P5 修正审计，约 15 分钟）→ Q12（全量复现审计，约 10 分钟）→ Q8（判据链独立复核，约 40 分钟）→ Q11（消融两口径，约 30 分钟，有余力再取）。
前四项都是对**已入库产物**的独立核对，不需要重新仿真、不需要下载数据。做不完按顺序停，未完成项留在这里等下一批。

### Q9 独立确认 raininfluent.csv 的数据坑（新增 2026-09-20）
- 读：src/dsh/2026-09-20_12_bsm1_rain_storm.py 的 load() 注释；PROJECT_STATE.md 第 18.4 节；results/2026-09-20/dsh/bsm1_rain_storm_report.md
- 做：从 bsm2_python 包数据目录（用 python 命令行打印 os.path.dirname(bsm2_python.__file__) 定位）**独立核对**三件事：
  ① raininfluent.csv 与 dryinfluent.csv 的第 16 列（1-based，即去掉时间列后的 Q 列）量级差异（报出两文件第 0 行与该列均值的实际数字）；
  ② raininfluent.csv 中 NaN 的列号与行号、个数；
  ③ 实测一次：把未修正的 rain 数据喂给 bsm2_python.BSM1OL 短跑若干步，记录报错文本与出现步数（跑不动就说明卡在哪）
- 产物：results/2026-09-20/codex/raininfluent_audit.md（含实测数字与报错原文）
- 验收：给出实测数字；与 DSH 的说法（Q 列小 1000 倍、Q 列第 996 行 1 个 NaN）一致或指出不一致

### Q10 审计 DSH 声称的 P1–P5 修正是否真的落地（新增 2026-09-20）
- 读：src/dsh/2026-09-18_14_pipeline.py、results/2026-09-18/dsh/pipeline_summary.json、results/2026-09-18/dsh/pipeline_run.md、PROJECT_STATE.md 第 16 节与第 19 节
- 做：逐条核对 DSH 在批次 2 之后声称修好的 5 处，每处给「已生效 / 未生效 / 部分生效」+ 证据（文件与行号）：
  ① 阈值来源文案：应写「2.395 为官方 4 故障窗标签辅助选出的 DET 工作点」，且明确无标签 0.995 标定分位为 13.139（不是旧文案「标定期 0.995 分位」）
  ② 自动审计清单里应新增「是否独立前瞻验证 = 否」一行
  ③ RUL 门禁应标注为事后（retrospective）且说明不可用于在线决策
  ④ 诊断输出应改标为「数据集级故障类型占位」，不得写成模型诊断结果
  ⑤ 误报应改为按冻结口径直接计算（告警起点不在任何命中窗内）且等于 201，与 results/2026-09-18/dsh/metropt3_metrics_frozen_dsh.json 的 det_best.fp_events 一致；摘要 JSON 应有 cost_parameters_are_placeholders / 口径版本 / 输入哈希字段
- 产物：results/2026-09-20/codex/pipeline_fix_audit.md
- 验收：逐条判定 + 证据；若发现只是文案改了但数字/口径没变，明确指出

### Q12 独立复现审计（另一套会话里跑一遍全链）（新增 2026-09-20）
- 读：run_all.py、docs/06_复现指南.md、results/2026-09-20/dsh/full_repro_log.txt（DSH 实跑：18 阶段 225 秒全通过）
- 做：在你自己会话里跑 python run_all.py --full，然后核对关键数字与冻结文件是否一致：
  ① results/2026-09-18/dsh/metropt3_metrics_frozen_dsh.json 的 det_best（timely 2 / 误报 201 / 0.1253 / TIA-H 11.6%）与 main_threshold（13.139）
  ② results/2026-09-17/dsh/rul_baseline_metrics.csv 的 GBR RMSE 与 PHM08
  ③ results/2026-09-20/dsh/ 下 BSM1 系列 CSV 是否被重跑覆盖且行列数不变（报出你观察到的文件数与总耗时）
- 产物：results/2026-09-20/codex/full_repro_audit.md（含你的阶段耗时表与不一致项）
- 验收：给出「与 DSH 日志一致 / 不一致」的逐项判定；环境差异（缺数据集等）如实写明

### Q8 独立复核判据链：比值判据与组合报警策略（新增 2026-09-20）
- 读：results/2026-09-20/dsh/bsm1_ratio_rule_report.md、alarm_strategy_report.md、PROJECT_STATE.md 第 18.5 / 18.6 节
- 数据（已入库，直接读）：results/2026-09-20/dsh/bsm1_120d_{baseline,degraded}.csv、bsm1_win{B,C}_*_{baseline,degraded}.csv、bsm1_sweep_*.csv、bsm1_R{1,2,3}_*_{baseline,degraded}.csv
- 做：用你自己的最小链路（冻结参考域取健康运行第 30-45 天、按一天中的时段分层或你等效的做法、滚动 5 天中位数、基线取该参考窗），复核三条方向：
  ① 健康运行第 45-120 天的越限时长（k=1.3~2.0）接近 0，而单点事件机式阈值告警在部分工况的健康运行上明显更多
  ② 比值判据的检出延迟显著大于单点事件机式判据（同一批退化轨迹）
  ③ 「单点 且 比值已抬升」的与门能减少健康上报，但会漏掉慢漂移档（-20%~-80%/100 天）
- 允许简化链路，但必须写明：分层方式、滚动窗长度、基线估计口径、事件/越限判定参数
- 产物：results/2026-09-20/codex/ratio_rule_repro.csv、ratio_rule_repro.md
- 验收：三条方向逐条给结论；方向相反必须给出证据与反例

### Q11 消融两口径重跑（Q6 的后续，有余力再做）
- 读：results/2026-09-20/codex/ablation_repro.md（你自己批次 2 的反例）、src/codex/2026-09-20_03_ablation_repro.py
- 做：在同一条自有链路上，把四个变体（V0 基线 / V1 无工况条件化 / V2 去派生特征 / V3 max 聚合）跑**两套公平口径**：
  ① 四变体共用同一阈值（批次 2 已做，保留作对照）
  ② 每个变体用自己的健康期重新标定阈值（0.995 分位或等价口径）
  报出两套口径下的 timely / late / miss / 误报事件数，并回答：「无工况条件化 = 0 告警」「去派生特征 = timely 归零」在任何一套口径下是否成立
- 产物：results/2026-09-20/codex/ablation_two_regimes.{csv,md}
- 验收：两套口径数字齐全；对两条强结论给出「成立 / 不成立 / 取决于口径」的明确判定
