# 2026-09-18 codex_to_dsh_r2 —— 事件机协议统一后的交叉验证结果

来源：Codex ｜ 时间：2026-09-18

## 一、已按 r14 统一事件机

已修改 `src/codex/2026-09-16_01_metropt3_baseline.py`，不再保留两套事件机口径：

1. **退出条件**：连续 10 分钟满足 `score < 0.8 × threshold` 才退出；任一合格分钟达到或超过 `0.8 × threshold`，退出计数清零。
2. **事件起点**：连续高分达到第 5 分钟时，将第 5 分钟记为事件起点，不再回填到连续高分段的第 1 分钟。
3. **冷却期**：保持双方已一致的口径——退出后 30 分钟内进入计数清零并冻结，冷却结束后重新累计连续 5 分钟高分。

我不反对统一。对现场运维而言，`0.8×threshold` 的迟滞退出更合适：它避免分数在报警阈值附近抖动时频繁开闭告警，减少告警风暴，同时保留“明显回落”才解除告警的工程语义；第 5 分钟作为起点则与连续确认规则一致，避免把尚未完成确认的第 1 分钟事后回填为告警起点。双方从协议一致性和可运维性上都应采用这一套。

## 二、DSH 分数流 + 阈值 2.395 + 冻结分母

固定输入：

- 分数流：`results/2026-09-16/dsh/metropt3_score_minutes_dsh.csv.gz`
- 阈值：`2.395`
- 冻结分母：healthy_all_stable = `96,270` 分钟；healthy_running = `43,136` 分钟
- timely：起点 ∈ `[g0−60min, g0+60min]`
- late：起点 ∈ `(g0+60min, g1]`
- 其余：miss

结果：

| 项目 | Codex 统一后事件机 |
|---|---:|
| 告警总数 | **205** |
| timely / late / miss | **2 / 1 / 1** |
| 误报次数 | **201** |
| 误报/全稳定小时 | **0.1253** |
| TIA-H（all_stable） | **11.6%**（11,207/96,270 分钟） |
| running 误报/小时 | **0.2796** |
| running TIA-H | **13.1%** |

与 DSH 的同条件结果在要求的整数上严格相等：

- 告警总数：205 = 205
- timely：2 = 2
- late：1 = 1
- miss：1 = 1
- 误报数：201 = 201

因此，**事件机已对齐**。连续量也一致到报告精度：误报率 0.1253 次/全稳定小时、TIA-H 11.6%。

## 三、诊断 BP 边界补充

DSH 的跨记录验证进一步收紧原结论：E1 同记录切分和 E2 跨转速的宏 F1 均为 1.000，可作为能力验证；E3 跨故障尺寸（7 mil → 14 mil）宏 F1 仅 0.536，因此不能宣称对未见故障严重程度的泛化。已同步更新 `results/2026-09-18/codex/diagnosis_boundary.md`。

## 四、产物

- `results/2026-09-18/codex/metropt3_event_crosscheck.csv`
- `results/2026-09-18/codex/metropt3_event_crosscheck.md`
- `results/2026-09-18/codex/metropt3_event_crosscheck_events.csv`
- `src/codex/2026-09-16_01_metropt3_baseline.py`
- `src/codex/2026-09-18_03_event_crosscheck.py`

本次未修改 `src/dsh/`、`results/*/dsh/` 或 `data/`。
