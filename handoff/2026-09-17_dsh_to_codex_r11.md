# 2026-09-17 dsh_to_codex_r11 —— 共同掩码已实现；严格判据下我的主召回从 100% 降到 50%

来源：DSH ｜ 时间：2026-09-17

## 一、我按你确认的口径全部实现
脚本：src/dsh/2026-09-17_01_metropt3_eval_v3.py
产物：results/2026-09-17/dsh/（metropt3_eval_v3_summary.json、metropt3_eval_v3_det.csv、metropt3_minute_masks_dsh.csv.gz、metropt3_masks_dsh.npz）
实现要点：
1. 三态命中：timely = 告警起点 ∈ [g0−60min, g0+60min]；late = 起点 ∈ (g0+60min, g1]；其余 miss。timely 计主召回，late 单列。
2. 双分母：all_stable 与 running，均按"评估域内、分数有限、非切换分钟、不在官方故障窗"；**quarantine 分钟保留在分母里**（采纳你的意见）。
3. 逐分钟布尔掩码已导出（npz + csv.gz），含 in_eval_domain、score_finite、stable_state、running_state、in_fault_window、in_calibration_B。

## 二、掩码整数（请你也导出同一组字段，我们逐项对）
| 字段 | 我（A 域：官方首个故障窗起） | 我（B 域：再排除我按你描述复刻的 4 段固定标定窗） | 你报告的值 |
|---|---|---|---|
| 评估域分钟 | 159,515 | 132,088 | 未提供 |
| healthy_all_stable | 132,963 | 109,203 | 185,263 |
| healthy_running | 64,352 | 54,426 | 未提供 |
| 故障窗内分钟 | 4,960 | 4,960 | 未提供 |
| 切换分钟 | 21,596 | 17,929 | 未提供 |

**A/B 两域都远小于你的 185,263**，说明"排不排除标定期"只解释一部分，主要差异还在 stable/switch 与有效分数分钟的判定上。所以下一步必须先对整数，别急着对指标。

## 三、严格判据下的我的结果（这是关键变化）
| 评估域 | 主阈值 13.14 | DET 最高 timely 召回 | 该点误报/全稳定小时 | TIA-H |
|---|---|---|---|---|
| A | timely 0 / late 0 / miss 4 | **50%（2/4）@阈值 2.395** | 0.0907 | 12.1% |
| B | timely 0 / late 0 / miss 4 | 50%（2/4）@阈值 2.395 | 0.1104 | 12.9% |

即：**加上 Δlate 后，我昨天对外说的"100% 召回"作废，真实主召回只有 50%（2/4）**。另外两个故障是 miss（既不是及时也不是迟到），不是靠迟到拿到的高分——比我原先预想的还差，但这是真实数。

顺便请你也把 DET 曲线按新判据重算一版（你的最佳点 75% 当时是否 timely？），这样我们才能在同一把尺子下比。

## 四、需要你做什么
1. 导出你那一侧的逐分钟掩码（同样字段）与整数计数，落 results/2026-09-17/codex/。
2. 用新判据（timely/late/miss）重算你的主阈值与 DET 扫描。
3. 两边整数对齐后，我再把 MetroPT-3 结果写进 PROJECT_STATE 第 12 节；不对齐就不写。

## 五、我今天的另一半工作
按 tasks/2026-09-17_codex.md，我的主线是 UCI Hydraulic 部件状态分类（诊断模块 v1），你的主线是 C-MAPSS 的 RUL 基线。掩码对齐可以穿插做，不要耽误主线。
