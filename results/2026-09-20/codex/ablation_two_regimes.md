# Q11：检测消融两套公平阈值口径复核（Codex，2026-09-20）

## 方法

沿用 Q6 的 Codex 自有 MetroPT-3 分钟级 walk-forward 链路、四变体、冻结事件机与四个官方故障窗，不复用 DSH 分数。只改变阈值口径：

1. **共享阈值**：四变体均用 6.0，与批次 2 完全相同，用于隔离结构变化。
2. **各自健康标定**：每个变体分别在四个维护 epoch 的首 7 天固定健康校准窗上计算自己的分数分布，取 q=0.995；四窗合计每个变体 31,564 个稳定分钟分数。该标定不使用四个官方故障窗。

事件机：连续 5 分钟超阈进入、连续 10 分钟低于 0.8×阈值退出、冷却 30 分钟；timely 为故障起点 ±60 分钟，之后至故障结束记 late。

## 实测结果

| regime             | variant                     |   threshold |   alarm_events |   timely |   late |   miss |   false_alarm_events | event_status                          |
|:-------------------|:----------------------------|------------:|---------------:|---------:|-------:|-------:|---------------------:|:--------------------------------------|
| shared_threshold_6 | V0_conditioned_derived_top3 |       6.000 |            557 |        2 |      0 |      2 |                  555 | F1:miss;F2:timely;F3:timely;F4:miss   |
| own_health_q995    | V0_conditioned_derived_top3 |      24.072 |            110 |        2 |      0 |      2 |                  108 | F1:miss;F2:timely;F3:timely;F4:miss   |
| shared_threshold_6 | V1_no_conditioning          |       6.000 |            233 |        2 |      0 |      2 |                  231 | F1:miss;F2:timely;F3:timely;F4:miss   |
| own_health_q995    | V1_no_conditioning          |      41.509 |             61 |        3 |      0 |      1 |                   58 | F1:timely;F2:timely;F3:timely;F4:miss |
| shared_threshold_6 | V2_no_derived               |       6.000 |            582 |        2 |      0 |      2 |                  580 | F1:miss;F2:timely;F3:timely;F4:miss   |
| own_health_q995    | V2_no_derived               |      22.420 |            111 |        2 |      0 |      2 |                  109 | F1:miss;F2:timely;F3:timely;F4:miss   |
| shared_threshold_6 | V3_max_aggregation          |       6.000 |            593 |        1 |      0 |      3 |                  592 | F1:miss;F2:timely;F3:miss;F4:miss     |
| own_health_q995    | V3_max_aggregation          |      33.504 |            108 |        2 |      0 |      2 |                  106 | F1:miss;F2:timely;F3:timely;F4:miss   |

各自 q0.995 阈值：

| variant                     |   threshold |   health_calibration_scores |   health_score_q990 |   health_score_q995 |
|:----------------------------|------------:|----------------------------:|--------------------:|--------------------:|
| V0_conditioned_derived_top3 |      24.072 |                       31564 |              17.317 |              24.072 |
| V1_no_conditioning          |      41.509 |                       31564 |              41.509 |              41.509 |
| V2_no_derived               |      22.420 |                       31564 |              17.317 |              22.420 |
| V3_max_aggregation          |      33.504 |                       31564 |              27.655 |              33.504 |

## 两条强结论判定

### 1. ‘不做工况条件化 = 0 告警’——**两套口径均不成立**

- 共享阈值：V1 有 **233** 个告警，timely=2。
- 各自健康标定：V1 阈值升至 41.509，仍有 **61** 个告警，timely=3。

因此该强结论不是阈值公平性能够解释的；在本自有链路中，无工况条件化不会归零。值得注意的是，各自标定后 V1 timely=3，反而高于 V0 的 2，但其误报仍为 58，不能据此宣称更优。

### 2. ‘去掉派生特征 = timely 归零’——**两套口径均不成立**

- 共享阈值：V2 timely=2，与 V0 的 2 相同。
- 各自健康标定：V2 阈值 22.420，timely=2；V0 阈值 24.072，timely=2。

本链路保留 TP3、Reservoirs、H1 原始量，top-3 聚合仍可从原始通道组合中响应相同物理变化；删除显式差值不必然让召回归零。

## 其他观察

- 共享阈值下，V3 max 聚合把 timely 从 V0 的 2 降至 1，与 Q6 观察一致；但各自标定后 V3 timely=2，与 V0 的 2 相同。说明‘max 聚合召回更差’也依赖阈值口径。
- 各自标定显著压低四变体事件数：V0 557→110，V1 233→61，V2 582→111，V3 593→108；但仍远未达到现场误报预算。
- 仅有 4 个官方故障窗，timely 每变化 1 个就是 25 个百分点；本结果用于否定跨实现强断言，不用于宣称某消融方案普遍优越。

## 最终结论

两套公平口径给出同一答案：**‘无工况条件化 = 0 告警’不成立；‘去派生特征 = timely 归零’不成立。** 这两条只能描述 DSH 特定实现与阈值组合，不能冻结为跨实现规律。

机器可读明细：`results/2026-09-20/codex/ablation_two_regimes.csv`。
