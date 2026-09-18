# MetroPT-3 Codex DET v2（timely / late / miss）

- 主阈值：6
- 主阈值：timely 2 / late 0 / miss 2；主召回 50.0%。
- DET 最大主召回：75.0%（3/4），threshold=30；late=0，miss=1。
- 该点误报/健康小时=0.039188，TIA-H=0.041249。

判据：timely 起点在 `[g0-60min, g0+60min]`；若无 timely 而起点在 `(g0+60min, g1]` 则 late；其余 miss。late 不计主召回。

## 主阈值逐事件

|事件|状态|告警起点|延迟(min)|
|---|---|---|---:|
|F1|miss|||
|F2|timely|2020-05-29 23:15:00|-15.0|
|F3|timely|2020-06-05 09:50:00|-10.0|
|F4|miss|||

## 掩码整数

```json
{
  "A": {
    "eval_domain": 159515,
    "score_finite": 113790,
    "stable_state": 138983,
    "running_state": 65677,
    "in_fault_window": 4960,
    "in_quarantine": 121421,
    "healthy_all_stable": 108854,
    "healthy_running": 50912
  },
  "B": {
    "eval_domain": 132088,
    "score_finite": 113790,
    "stable_state": 115087,
    "running_state": 56410,
    "in_fault_window": 4960,
    "in_quarantine": 121421,
    "healthy_all_stable": 108854,
    "healthy_running": 50912
  },
  "calibration_minutes_in_A": 27427,
  "rows": 252720
}
```

注意：A 是自首个官方故障窗起的观测分钟；B 是 A 再排除四段固定标定窗。健康计数还要求 score finite、stable 且不在故障窗。
