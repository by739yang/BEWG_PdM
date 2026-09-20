# Q6：检测消融独立复核

## 简化链路

- 从 `data/metropt3/metropt3.csv` 独立聚合分钟中位数；工况由 Motor current 与 DV electric 分为 stopped/unloaded/loaded。
- 特征：7 个模拟量、`TP3-Reservoirs`、`TP3-H1`，以及 60 分钟三工况占比和切换次数；`V2` 仅去掉两个压力差派生特征。
- 每个维护 epoch 用首 7 天固定校准，并每日 walk-forward；历史窗 14 天，分数≥4 后隔离 2 小时；鲁棒 median/IQR 标准化。
- 聚合：默认最大三个 |z| 的 RMS；`V3` 改为单通道 max|z|。
- 为隔离开关影响，四个变体共用阈值 6.0；事件机为连续 5 点进入、连续 10 点低于 0.8×阈值退出、冷却 30 分钟；命中窗为故障前后 60 分钟，之后至故障结束算 late。
- 这是 Codex 简化/自有链路，不复用 DSH 的分数；因此只检验方向，不要求复现 DSH 数字。

## 实测结果

| variant                     |   alarm_events |   timely |   late |   miss |   false_alarm_events | event_status                        |
|:----------------------------|---------------:|---------:|-------:|-------:|---------------------:|:------------------------------------|
| V0_conditioned_derived_top3 |            557 |        2 |      0 |      2 |                  555 | F1:miss;F2:timely;F3:timely;F4:miss |
| V1_no_conditioning          |            233 |        2 |      0 |      2 |                  231 | F1:miss;F2:timely;F3:timely;F4:miss |
| V2_no_derived               |            582 |        2 |      0 |      2 |                  580 | F1:miss;F2:timely;F3:timely;F4:miss |
| V3_max_aggregation          |            593 |        1 |      0 |      3 |                  592 | F1:miss;F2:timely;F3:miss;F4:miss   |

## 对两条指定结论的判定

1. **‘不做工况条件化会 0 告警’未复现，得到反例。** V1 仍有 233 个告警、timely=2；相对 V0 的 557 个告警确实下降，但并非完全失效。说明‘0 告警’依赖 DSH 的具体尺度、特征和阈值，不能提升为跨实现定律。
2. **‘去掉 TP3-Reservoirs、TP3-H1 后 timely 归零’未复现，得到反例。** V2 timely=2，与 V0 的 2 相同，且事件状态均为 F2/F3 timely。两个派生特征在 DSH 链路中重要，但本实现的原始 TP3/H1/Reservoirs 已保留等价信息，多变量聚合并不必然依赖显式差值。
3. **聚合方式方向与 DSH 一致。** max|z| 将 timely 从 2 降至 1，误报从 555 升至 592。

## 解释与边界

本反例不是说工况条件化或派生特征无用，而是说明两条强表述对实现敏感：无工况模型仍可被跨工况尺度和其他通道触发；显式差值被删除后，原始三压力通道仍允许 top-3 聚合响应同一物理变化。四个官方故障窗使 timely 每次变化 25%，证据量很小。建议将冻结表述收窄为‘在 DSH 当前链路/阈值下观察到’，并在共同阈值与各自重新标定阈值两种公平口径下重复消融。

机器可读明细：`ablation_repro.csv`。
