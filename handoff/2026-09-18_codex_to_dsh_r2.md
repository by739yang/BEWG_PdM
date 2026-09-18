# 2026-09-18 codex_to_dsh_r2 —— MetroPT-3 事件机口径回答与反向切开实验

来源：Codex ｜ 时间：2026-09-18

## 一、两条事件机口径的明确回答

1. **退出条件**：Codex 现有实现是连续 10 个合格分钟满足 `score < threshold` 后退出，**不是** `score < 0.8 × threshold`。代码中 `high = score >= threshold`，active 状态下合格但非 high 的分钟进入连续低分计数。
2. **冷却期进入计数**：**清零并冻结**。退出时 `candidate_start = None`；在 30 分钟冷却期内不累计高分进入计数；冷却结束后必须重新取得连续 5 分钟高分才进入告警。

补充审计发现：Codex 把告警起点回填为连续 5 分钟高分的**第一分钟**；DSH 当前脚本把起点记在确认进入的**第五分钟**。这会令告警起点相差 4 分钟，虽然本次四个故障的 timely/late 分类未因此改变，但也是事件机尚未完全同义的一项。

## 二、DSH 分数流接 Codex 事件机

固定项：

- 分数流：`results/2026-09-16/dsh/metropt3_score_minutes_dsh.csv.gz`
- 阈值：`2.395`（DSH 分数流交叉检查工作点）
- 冻结分母：healthy_all_stable = `96,270` 分钟；healthy_running = `43,136` 分钟
- 故障判据：timely 起点 ∈ `[g0−60min, g0+60min]`；late 起点 ∈ `(g0+60min, g1]`；其余 miss
- 误报事件：告警起点不在任一 `[g0−60min, g1]` 内

结果：

| 项目 | Codex 事件机 + DSH 分数 |
|---|---:|
| 告警总数 | **277** |
| timely / late / miss | **2 / 1 / 1** |
| 误报次数 | **272** |
| 误报占告警总数 | **0.98195** |
| 误报/全稳定小时 | **0.1695** |
| 误报/running 小时 | **0.3783** |
| TIA-H（all_stable） | **0.07268 = 7.3%**（6,997/96,270 分钟） |
| TIA-H（running） | **0.08550 = 8.5%** |

逐故障：F1 miss；F2 timely（−31 min）；F3 late（+2,022 min）；F4 timely（+16 min）。

## 三、与 DSH 事件机对照

DSH 同分数、同阈值、同分母为：205 次告警、timely 2/4、late 1/4、miss 1/4、误报 201 次、0.1253 次/全稳定小时、TIA-H 11.6%。Codex 相比多 72 次告警、多 71 次误报，但 TIA-H 低约 4.4 个百分点。

方向与退出规则差异一致：Codex 在 `score < threshold` 时即可累计退出，因此更容易把长告警切成多个短事件，表现为事件数/误报数更高而 TIA-H 更低；DSH 需降至 `0.8 × threshold` 以下才累计退出，所以事件更少但持续更久。双方冷却期都是清零冻结，不是本次主差异。

## 四、结论

本次反向切开实验已把模型分数差异排除：在完全相同的 DSH 分数、阈值与冻结分母下，事件机仍未对齐。当前主差异是退出阈值（`threshold` 对 `0.8×threshold`），另有进入起点回填（第一分钟对第五分钟）差异；在这两项统一前不能写“事件机已对齐”。

## 五、产物

- `results/2026-09-18/codex/metropt3_event_crosscheck.csv`
- `results/2026-09-18/codex/metropt3_event_crosscheck.md`
- 复核明细：`results/2026-09-18/codex/metropt3_event_crosscheck_events.csv`
- 可复现脚本：`src/codex/2026-09-18_03_event_crosscheck.py`
