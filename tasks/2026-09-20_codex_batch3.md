# tasks/2026-09-20_codex_batch3.md —— 2026-09-20 晚任务单（Codex，批次 3）

开工前必读（按顺序）：PROJECT_STATE.md（第 00 节冷启动清单）→ 协作约定.md（第 7、8 节）→ 本任务单 → tasks/codex_batch_queue.md 的「批次 3」小节（每个 Q 的完整定义在那里）。

## 今天做批次 3，按顺序推进（做不完就停，不要跳）
| 序 | 任务 | 预算 | 一句话 | 产物 |
|---|---|---|---|---|
| 1 | Q9 | 10 分钟 | 独立确认随包 raininfluent.csv 的 Q 列单位差 1000 倍 + 1 个 NaN（并实测未修正时的报错） | results/2026-09-20/codex/raininfluent_audit.md |
| 2 | Q10 | 15 分钟 | 审计 DSH 声称的 P1–P5 五处修正是否真的落地 | results/2026-09-20/codex/pipeline_fix_audit.md |
| 3 | Q12 | 10 分钟 | 在你自己的会话里跑 python run_all.py --full，与冻结文件逐项比对 | results/2026-09-20/codex/full_repro_audit.md |
| 4 | Q8 | 40 分钟 | 独立复核判据链（比值判据 + 组合报警策略）的三条方向 | results/2026-09-20/codex/ratio_rule_repro.{csv,md} |
| 5 | Q11 | 30 分钟 | Q6 后续：消融两套公平口径重跑（有余力再做） | results/2026-09-20/codex/ablation_two_regimes.{csv,md} |

本批全部基于已入库产物，**不需要重新跑 BSM1 仿真、不需要下载数据**。Q12 会跑全量（DSH 实测 18 阶段 225 秒）。

## 口径提醒（本批特别重要）
- 单点事件机在慢漂移场景的「20.3 天检出」不是预警能力（首报时刻由共同外部成分主导，见 §18.2 / §18.3）；复核时不要把它当基准真相。
- 健康运行的评估窗统一取第 45-120 天（参考窗到第 45 天才结束）；DSH 曾因把评估窗设成第 20 天起而出现「检出延迟 0.01 天」的假象，已在 §18.5 记录。
- 全部为 IWA BSM1 **仿真**数据；成本参数为占位值，不得当真实金额引用。

## 硬性约束
- 不要改 src/dsh/ 与 results/*/dsh/；不要动 data/；产物只写 src/codex/ 与 results/2026-09-20/codex/。
- 数字必须可复现；跑不出来就写跑不出来并说明卡在哪；允许简化链路但必须写明简化处。

## 收工
1. logs/实验日志.md 追加一条（五段式）；
2. handoff/2026-09-20_codex_to_dsh_r2.md 写回，只把文件名告诉项目负责人，不粘贴正文；
3. 未完成的 Q 留在 tasks/codex_batch_queue.md。
