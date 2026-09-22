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

## 批次 4（2026-09-22 派发，等王家兴说「用 Codex」时整批发）
**派发顺序与预算**：Q14（lanmai CLI 复核，约 15 分钟）→ Q13（消融两口径 + 标定期敏感性，约 40 分钟）→ Q16（污泥线闭环/扫描/决策，约 60 分钟）→ Q15（组合策略倍数敏感性，约 30 分钟）→ Q17（在线链路多轨迹，约 30 分钟，有余力再做）。
全部基于**已入库产物**，不需要重新跑 BSM1 仿真、不需要下载数据。做不完按顺序停，未完成项留在这里。

### Q14 复核 lanmai CLI（接入标定工具）
- 读：docs/10_接入标定工具使用手册.md、src/lanmai/（core.py、pipeline.py、cli.py）
- 数据：results/2026-09-21/lanmai_demo/（metropt3_prepared.csv.gz、bsm1_120d_baseline_ts.csv、bsm1_120d_degraded_ts.csv）、data/SKAB-master/data/anomaly-free/anomaly-free.csv
- 做（自己跑，**不要改 src/lanmai/**）：
  ① PYTHONPATH=src python -m lanmai selftest → 阶跃与慢漂移是否都能出告警（阶跃应全为 P2、慢漂移应出现 P1/P3）；
  ② 用 SKAB 无故障记录标定 + watch → 核对分号分隔自动识别、通道白名单是否正常；
  ③ 用 bsm1 两个 _ts.csv 复现：健康轨迹第 30-45 天标定、退化轨迹 watch → **核对冻结通道首报是否为第 40.28 天**（研究链路口径）；
  ④ 多段标定：--ref-segments 三段 + --thr-policy median/upper → 核对输出的阈值范围（最小/中位/最大/极差比）是否自洽；
  ⑤ 边界检查：故意把通道写成含 ts 的名字（如 TSS_eff）→ 核对工具**不会把它误判成时间列**（我们修过这个 bug）。
- 产物：results/2026-09-22/codex/lanmai_cli_audit.md（命令 + 观察 + 结论）
- 验收：①-⑤ 逐条给「通过/不通过 + 证据」；若发现 TSS_eff 被当时间列、或首报不是 40.28，必须给完整复现命令。

### Q13 复核消融两套口径与标定期敏感性
- 读：PROJECT_STATE.md 第 17.1 / 17.2 节；results/2026-09-19/dsh/ablation_two_regimes_report.md、calib_window_sensitivity_report.md
- 数据：data/metropt3/metropt3.csv + results/2026-09-18/dsh/minute_mask_intersection.csv.gz + results/2026-09-16/dsh/metropt3_score_minutes_dsh.csv.gz
- 做：用你自己的最小链路复核三条方向（可简化特征/标准化，但必须写明简化处与阈值口径）：
  ① 把阈值来源从「标签辅助的 DET 工作点 2.395」换成「无标签标定期 q0.995」后，timely 命中是否崩塌（我们得到 0/4）；
  ② 「无标签标定下 timely 全 0/4」在你的实现里是否也成立；
  ③ 用 4 个官方故障窗之间的 5 段健康期分别标定 → 阈值是否随所选健康段大幅变化（我们得到极差 3.5-3.9 倍、误报 1-44 次）。
- 产物：results/2026-09-22/codex/ablation_regime_repro.md
- 验收：三条方向逐条结论；方向不一致必须给证据与反例。

### Q16 复核污泥线闭环 / 幅值速率扫描 / 决策层
- 读：PROJECT_STATE.md 第 25 / 25.1 / 25.2 节；results/2026-09-21/dsh/sludge_line2_report.md、sludge_sweep_report.md、sludge_decision_report.md
- 数据：results/2026-09-21/dsh/sludge_flow_healthy.csv.gz（BSM1 剩余污泥流，w_* 21 维 + t_day）
- 做（自己算，**不要改 src/dsh/**，可用包内 bsm2_python 的 Thickener/Dewatering）：
  ① 复算污泥线：QW=385 m3/d、泥饼含固率 28%（即 280,000 mg/L）、湿泥饼产量、干固体产率 → 核对「湿泥饼产量 +62%（13.0→21.2 m3/d）、干固体产率基本不变」；
  ② 按我们的口径（退化起始第 60 天、目标含固率 28%→18%/60 天、真值失效=含固率<20% 持续 1 天）复算真值失效天数（应为第 109 天）；
  ③ 检测：只用间接量（湿泥饼产量/滤液量/滤液 TSS/干固体产率/上清液 TSS），参考域取健康运行第 30-45 天 → 核对**冻结通道首报是否为第 61.33 天**、**自适应通道是否漏检**；
  ④ RUL：泥饼含固率线性外推到 20%，比较 5/2/1 天窗（我们得到 273.08 / 63.92 / 46.68 天，真值 47.67）；
  ⑤ 决策层：用报告里的占位成本参数，重算「RUL 驱动 vs 固定周期 30/40/49/60 天」的单台年成本 → 核对 RUL 驱动是否更省、非计划失效是否为 0。
- 产物：results/2026-09-22/codex/sludge_line_repro.md（可附 csv）
- 验收：①-⑤ 逐条「一致/不一致 + 数值」；不一致要给复现命令与你的口径。

### Q15 复核组合策略倍数敏感性
- 读：PROJECT_STATE.md 第 18.5 / 18.6 / 18.7 节；results/2026-09-21/dsh/strategy_sensitivity_report.md
- 数据：results/2026-09-20/dsh 下的 12 组 BSM1 轨迹（bsm1_120d_*、bsm1_winB/C_*、bsm1_sweep_*、bsm1_R1/R2/R3_*、bsm1std_*）
- 做：自己实现「单点事件机 + 滚动中位数比值 + 与门/并集」最小链路，复核三条：
  ① 健康运行上报：与门是否**几乎等于单点**（k_and 从 1.05 提到 1.40 无变化）；
  ② 比值判据是否**只增加上报量**（k_ratio 1.15/1.25/1.40 → 76/83/96 段，单点 51；并集 127/134/147）；
  ③ 检出：单点/与门/并集是否都是 12/12、延迟中位 20.3 天。
- **硬性要求**：滚动窗必须用时间单位（rolling('3D')/('5D')），不能用裸点数 —— 我们曾因此把 5 天窗误写成 7200 点（=75 天）并得出相反结论。
- 产物：results/2026-09-22/codex/strategy_sensitivity_repro.md
- 验收：三条方向；不一致给证据。

### Q17 复核在线链路多轨迹（有余力再做）
- 读：PROJECT_STATE.md 第 21 / 22 / 23 节；results/2026-09-21/dsh/online_chain_report.md
- 数据：results/2026-09-20/dsh/bsm1_120d_*.csv、results/2026-09-21/dsh/bsm1mt_*.csv、bsm1std_*.csv、results/2026-09-20/dsh/bsm1_sweep_keep20_ramp040.csv
- 做：复核两条方向：① 因果门禁在 7 条轨迹上是否只判 3 条「挂 RUL」；② 在线 RUL 是否只在 1 条上可算（其余因告警前 5 天没有可测的机理下降段）。
- 产物：results/2026-09-22/codex/online_chain_repro.md
- 验收：方向一致；不一致给证据。

### 派发时的统一要求
- 先读 PROJECT_STATE.md 第 00 节冷启动清单与 协作约定.md 第 7、8、9 节（第 9 节是文件写入纪律）
- 每个 Q 自包含：读什么、做什么、产物路径、验收标准、禁止事项
- 不要改 src/dsh/、src/lanmai/、results/*/dsh/；不要动 data/
- 成本参数为占位值，任何产物里不得把它当真实金额
- 收工：logs/实验日志.md 追加一条（五段式）+ handoff/2026-09-22_codex_to_dsh.md（只把文件名告诉人）


## 批次 5（2026-09-22 派发）—— 路线 B 独立复核

> 背景：2026-09-22 当日用官方整厂类 BSM2Base 完成「BSM2 整厂 + 脱水机退化」闭环，得到**一个负结果 + 一个解法**（详见 PROJECT_STATE.md 第 27 节）。本批全部为独立复核，禁止 import src/dsh/route_b_common.py。

### Q18 独立复核路线 B 整厂仿真（必做）
- 读：PROJECT_STATE.md 第 24.1 / 27 节
- 数据/代码：src/dsh/2026-09-22_02_bsm2_route_b_sim.py、src/dsh/route_b_common.py（**只读，不要 import**）、results/2026-09-22/dsh/bsm2_route_b_{healthy,degraded}.csv.gz
- 做：自己装配官方整厂（包内 bsm2_python/bsm2_base.py 的 BSM2Base，或按包内模块自建），160 天、15 min 步长、官方初值；退化注入官方 Dewatering 的 dw_par[0]：28% → 18%、60 天线性斜坡、起始第 60 天。核对五条：
  ① 可行性与成本量级（我们：15,359 步、约 0.4 秒/模拟天、零 NaN）；
  ② 退化口径：泥饼 TSS 应等于 含固率 × 10000 mg/L（280,000 → 180,000）；
  ③ 真值失效（泥饼含固率 < 20% 持续 1 天）是否为**第 109.00 天**；
  ④ 末期湿泥饼量相对健康轨迹是否为 **+55.53%**（理论 28/18−1 = +55.56%）；
  ⑤ 全厂旁证（末 10 天同刻配对）：干固体产率 −0.013%、沼气 CH4 −0.013%、泵能耗 +0.004%、出水 TSS −0.030%、出水氨氮 −2.196%。
- 产物：results/2026-09-22/codex_b5/route_b_sim_repro.md
- 验收：①-⑤ 逐条「一致/不一致 + 你的数值 + 你的口径」；若有多条不一致，附你自己的仿真参数表（步长、初值、积分器）。

### Q19 复核负结果：整厂尺度原始量检不出（必做）
- 读：PROJECT_STATE.md 第 27.1 节；results/2026-09-22/dsh/bsm2_route_b_detect.md
- 数据：results/2026-09-22/dsh/bsm2_route_b_{healthy,degraded}.csv.gz（15 min；通道：泥饼流量、滤液量、滤液TSS、干固体产率、浓缩池底TSS）；包内 data/dyninfluent_bsm2.csv（第 16 列 = 进水流量 m³/d）
- 做：自己实现「冻结参考域（健康第 30-45 天）+ robust z + topk3 + 事件机（4 点进入/8 点退出/0.8/8 点冷却）」最小链路，核对：
  ① 参考域 0.999 分位阈值是否 ≈ **13.149**；
  ② 健康轨迹误报次数与最高分时刻（我们：6 次、最高分在第 **66.11** 天 = 19.18），并核对该时刻**进水流量比参考域高 +23.9%**（21,494 → 26,639 m³/d）；
  ③ 零误报口径（健康轨迹最大分 × 1.02 = **19.560**）下，退化轨迹首报是否为第 **146.11** 天、检出延迟 **86.11** 天、提前量 **−37.11** 天（即晚于失效）；
  ④ 断言核对：「退化轨迹的首报时刻等于健康轨迹的某次误报时刻」是否成立。
- 产物：results/2026-09-22/codex_b5/route_b_negative_repro.md
- 验收：①②③④ 逐条；若你得到的阈值或延迟不同，给出你的分位/事件机参数。

### Q20 复核比值通道与噪声敏感性（必做，含方向稳健性）
- 读：PROJECT_STATE.md 第 27.2 节；results/2026-09-22/dsh/bsm2_route_b_detect.md / bsm2_route_b_noise.csv
- 做：
  ① 核对比值通道定义与单位：含固率代理 = 干固体产率 / 湿泥饼量 / 10（kg/d ÷ m³/d = kg/m³ → %）；无噪时它应精确等于该时刻的泥饼含固率；
  ② 核对噪声模型：流量类 2% 相对白噪声、泥饼含固率为 3% **日粒度**实验室噪声、干固体产率按 含固率 × 湿泥饼量 重算（因此比值只继承实验室噪声）；阈值 = 健康轨迹最大分 × 1.02；
  ③ 核对 8 个噪声实现：检出延迟中位 **9.80 天（5.03–11.03）**、提前量中位 **37.47 天**、健康轨迹误报出现 **0/8**；
  ④ **方向稳健性（本 Q 的重点）**：换 2–3 种别的噪声结构（例如日粒度实验室噪声改成小时粒度、把流量噪声从 2% 提到 5%、给含固率加偏置漂移），看「比值通道优于原始量通道」这个方向是否稳健；若方向翻转，给证据与适用边界。
- 产物：results/2026-09-22/codex_b5/route_b_ratio_noise_repro.md
- 验收：①-③ 数值一致/不一致；④ 必须给出你自己的噪声结构表与结论（方向是否稳健）。

### Q23 静态审计：新脚本 / 文档 / 演示页（必做）
- 读：src/dsh/route_b_common.py、src/dsh/2026-09-22_02/03/04_*.py、PROJECT_STATE.md 第 27 节与设计原则⑦、docs/07_BP四栏大纲.md 路线 B 行与原则 7、docs/08 第 27 节行、docs/09 路线 B 行、demo/lanmai_demo.html 的路线 B 卡片、run_all.py 的新阶段
- 做：
  ① 逐项核对代码与文档数字一致（13.149 / 19.560 / 2.693 / 9.80 / 37.47 / 26.47 / 13.85 / 86.11 / −37.11 / 109.00 / +55.53%）；
  ② 找出**过强表述**（例如「检不出」「免疫工况漂移」「0 误报」这类全称量词）并给出更稳的措辞；
  ③ 检查局限是否写明：理想单元无堵塞/无动力学、单轨迹 + 6 场景、只含白噪声未含传感器漂移标定、成本未整厂重跑；
  ④ run_all.py 新增 3 个阶段能否直接跑；产物文件名含中文（如 bsm2_route_b_sweep_0_速率30天.csv.gz）是否有跨平台风险；
  ⑤ 明确指出任何「结论超出证据」之处。
- 产物：results/2026-09-22/codex_b5/route_b_static_audit.md
- 验收：每项给出「有问题/无问题 + 证据（文件路径与行号）」。

### Q21 复核 RUL 窗长扫描（含噪）
- 读：PROJECT_STATE.md 第 27.4 节；results/2026-09-22/dsh/bsm2_route_b_rul_window.csv
- 做：自己实现「比值通道首报处 → 用含噪含固率代理线性外推到 20%」的 RUL，窗长取 1/2/5/10 天并比较 3 日平滑；核对误差中位 **26.47 / 29.62 / 18.06 / 13.85 天**；回答「含噪下窗长应如何选」的可辩护规则。
- 产物：results/2026-09-22/codex_b5/route_b_rul_window_repro.md
- 验收：四个窗长的误差数值 + 规则表述；不一致给口径。

### Q22 复核 6 场景扫描的单调性与断言
- 读：PROJECT_STATE.md 第 27.3 节；results/2026-09-22/dsh/bsm2_route_b_sweep.{csv,md}
- 数据：results/2026-09-22/dsh/bsm2_route_b_sweep_*.csv.gz（6 条轨迹，文件名含中文）
- 做：核对四条：① 比值通道含噪延迟中位随速率单调（斜坡 30/60/120 天 → 5.53/9.80/18.53 天）；② 随幅值单调（终值 22/20/18% → 14.03/10.93/9.80 天）；③ **原始量首报全部落在健康轨迹的误报时刻（94.11 / 146.11 天）**；④ 末期湿泥饼量 +55.53%（18% 终值）/ +39.98%（20%）/ +27.26%（22%）。
- 产物：results/2026-09-22/codex_b5/route_b_sweep_repro.md
- 验收：四条方向；不一致给证据。

### 派发时的统一要求
- 先读 PROJECT_STATE.md 第 00 节冷启动清单与 协作约定.md 第 7、8、9 节（第 9 节是文件写入纪律：先算内容再写临时文件并原子替换，写完复查行数）
- 每个 Q 自包含：读什么、做什么、产物路径、验收标准、禁止事项
- 不要改 src/dsh/、src/lanmai/、results/*/dsh/；不要动 data/
- 成本参数为占位值，任何产物里不得把它当真实金额
- 收工：logs/实验日志.md 追加一条（五段式）+ handoff/2026-09-22_codex_to_dsh_r2.md（只把文件名告诉人）
