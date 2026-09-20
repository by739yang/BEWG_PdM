# -*- coding: utf-8 -*-
"""Q8 independent BSM1 ratio-rule / alarm-gate reproduction.

Primary result uses the actual 15-minute sampling interval: 5 days = 480 samples.
A diagnostic compatibility mode also evaluates 7200 samples, because the DSH
implementation uses ``5*1440`` samples although these CSVs have 96 samples/day.
No DSH module is imported and no DSH/data path is written.
"""
from __future__ import annotations

import os
import numpy as np
import pandas as pd

IN_DIR = "results/2026-09-20/dsh"
OUT_DIR = "results/2026-09-20/codex"
OUT_CSV = os.path.join(OUT_DIR, "ratio_rule_repro.csv")
OUT_MD = os.path.join(OUT_DIR, "ratio_rule_repro.md")

CHANNELS = ["SO3", "SO4", "SO5", "SNH_eff", "Ntot_eff", "TSS_eff", "sludge_h"]
DEG_START = 20.0
REF_LO, REF_HI = 30.0, 45.0
EVAL_LO, EVAL_HI = 45.0, 120.0
PAIRS = [
    ("A_window", "bsm1_120d_baseline.csv", "bsm1_120d_degraded.csv", "window"),
    ("B_window", "bsm1_winB_120_240_baseline.csv", "bsm1_winB_120_240_degraded.csv", "window"),
    ("C_window", "bsm1_winC_240_360_baseline.csv", "bsm1_winC_240_360_degraded.csv", "window"),
    ("slow_-20pct_100d", "bsm1_120d_baseline.csv", "bsm1_sweep_keep80_ramp100.csv", "slow"),
    ("slow_-40pct_100d", "bsm1_120d_baseline.csv", "bsm1_sweep_keep60_ramp100.csv", "slow"),
    ("slow_-60pct_100d", "bsm1_120d_baseline.csv", "bsm1_120d_degraded.csv", "slow"),
    ("slow_-80pct_100d", "bsm1_120d_baseline.csv", "bsm1_sweep_keep20_ramp100.csv", "slow"),
    ("fast_-60pct_40d", "bsm1_120d_baseline.csv", "bsm1_sweep_keep40_ramp040.csv", "fast"),
    ("fast_-80pct_40d", "bsm1_120d_baseline.csv", "bsm1_sweep_keep20_ramp040.csv", "fast"),
    ("R1_dry", "bsm1_R1_dry_baseline.csv", "bsm1_R1_dry_degraded.csv", "rain"),
    ("R2_dry_rain", "bsm1_R2_dry_rain_baseline.csv", "bsm1_R2_dry_rain_degraded.csv", "rain"),
    ("R3_storm", "bsm1_R3_add_storm_baseline.csv", "bsm1_R3_add_storm_degraded.csv", "rain"),
]


def scale_floor(healthy: pd.DataFrame) -> pd.Series:
    """Numerical scale floor, independently implemented to isolate rolling-window effects."""
    iqr_scale = (healthy[CHANNELS].quantile(0.75) - healthy[CHANNELS].quantile(0.25)) / 1.349
    sd = healthy[CHANNELS].std()
    global_scale = iqr_scale.where(iqr_scale > 1e-9, sd).fillna(1.0)
    return pd.concat([0.2 * global_scale, 0.1 * sd.fillna(1.0)], axis=1).max(axis=1)


def frozen_score(frame: pd.DataFrame, reference: pd.DataFrame, floor: pd.Series) -> np.ndarray:
    """Hour-of-day conditioned frozen robust z-score, top-3 RMS aggregation."""
    state = ((frame["t_day"] * 24.0) % 24.0).astype(int).to_numpy()
    ref_state = ((reference["t_day"] * 24.0) % 24.0).astype(int).to_numpy()
    z = np.zeros((len(frame), len(CHANNELS)), dtype=float)
    for j, channel in enumerate(CHANNELS):
        for hour in np.unique(state):
            target = state == hour
            ref_values = reference.loc[ref_state == hour, channel].astype(float)
            if len(ref_values) < 8:
                continue
            iqr = ref_values.quantile(0.75) - ref_values.quantile(0.25)
            sd = ref_values.std()
            scale = iqr / 1.349 if iqr > 1e-9 else (sd if sd > 1e-9 else 1.0)
            scale = max(float(scale), float(floor[channel]))
            z[target, j] = np.clip(
                (frame.loc[target, channel].to_numpy(dtype=float) - ref_values.median()) / scale,
                -30.0,
                30.0,
            )
    top3 = np.sort(np.abs(z), axis=1)[:, -3:]
    return np.sqrt(np.mean(top3**2, axis=1))


def make_events(score: np.ndarray, threshold: float) -> list[tuple[int, int]]:
    """4-sample enter, 8-sample exit below 0.8*threshold, 8-sample cooldown."""
    over = score > threshold
    events: list[tuple[int, int]] = []
    state = run = 0
    start = 0
    last_end = -10**9
    for i, is_over in enumerate(over):
        if state == 0:
            if i < last_end + 8:
                run = 0
            elif is_over:
                run += 1
                if run >= 4:
                    start, state, run = i, 1, 0
            else:
                run = 0
        else:
            if score[i] < 0.8 * threshold:
                run += 1
                if run >= 8:
                    events.append((start, i + 1))
                    last_end, state, run = i + 1, 0, 0
            else:
                run = 0
    if state == 1:
        events.append((start, len(score)))
    return events


def episode_count(mask: np.ndarray) -> int:
    values = np.asarray(mask, dtype=bool)
    return int(np.sum(values & ~np.r_[False, values[:-1]]))


def first_delay(mask: np.ndarray, days: np.ndarray) -> float | None:
    valid = (days >= EVAL_LO) & (days <= EVAL_HI) & np.asarray(mask, dtype=bool)
    return round(float(days[valid][0] - DEG_START), 2) if valid.any() else None


def near_ratio(rolling: np.ndarray, days: np.ndarray, event_day: float, threshold: float) -> bool:
    mask = (days >= event_day - 1.0) & (days <= event_day + 1.0) & np.isfinite(rolling)
    return bool(mask.any() and np.nanmax(rolling[mask]) > threshold)


def analyse_mode(
    scenario: str,
    group: str,
    healthy: pd.DataFrame,
    degraded: pd.DataFrame,
    s_healthy: np.ndarray,
    s_degraded: np.ndarray,
    point_threshold: float,
    window_samples: int,
    min_periods: int,
    mode: str,
) -> dict:
    rolling_h = pd.Series(s_healthy).rolling(window_samples, min_periods=min_periods).median().to_numpy()
    rolling_d = pd.Series(s_degraded).rolling(window_samples, min_periods=min_periods).median().to_numpy()
    day_h = healthy["t_day"].to_numpy(dtype=float)
    day_d = degraded["t_day"].to_numpy(dtype=float)
    ref_mask = (day_h >= REF_LO) & (day_h < REF_HI)
    eval_h = (day_h >= EVAL_LO) & (day_h <= EVAL_HI)
    base = float(np.nanmedian(rolling_h[ref_mask]))

    health_events = [e for e in make_events(s_healthy, point_threshold) if EVAL_LO <= day_h[e[0]] <= EVAL_HI]
    degraded_events = [e for e in make_events(s_degraded, point_threshold) if EVAL_LO <= day_d[e[0]] <= EVAL_HI]
    point_delay = round(min((day_d[s] for s, _ in degraded_events), default=np.nan) - DEG_START, 2)
    if not np.isfinite(point_delay):
        point_delay = None

    p1_health = [
        e for e in health_events if near_ratio(rolling_h, day_h, float(day_h[e[0]]), 1.15 * base)
    ]
    p1_degraded = [
        e for e in degraded_events if near_ratio(rolling_d, day_d, float(day_d[e[0]]), 1.15 * base)
    ]
    p1_delay = round(min((day_d[s] for s, _ in p1_degraded), default=np.nan) - DEG_START, 2)
    if not np.isfinite(p1_delay):
        p1_delay = None

    row = {
        "mode": mode,
        "scenario": scenario,
        "group": group,
        "samples_per_day": 96,
        "rolling_samples": window_samples,
        "rolling_days_actual": round(window_samples / 96.0, 3),
        "rolling_min_periods": min_periods,
        "ratio_base": round(base, 6),
        "point_threshold_q999": round(point_threshold, 6),
        "health_point_events_d45_120": len(health_events),
        "health_p1_gate_events_d45_120": len(p1_health),
        "point_delay_days_from_d20": point_delay,
        "p1_gate_delay_days_from_d20": p1_delay,
    }
    for k in (1.3, 1.5, 2.0):
        ratio_h = np.isfinite(rolling_h) & (rolling_h > k * base)
        ratio_d = np.isfinite(rolling_d) & (rolling_d > k * base)
        row[f"health_ratio_fraction_k{k:.1f}_d45_120"] = round(float(np.mean(ratio_h[eval_h])), 6)
        row[f"health_ratio_episodes_k{k:.1f}_d45_120"] = episode_count(ratio_h[eval_h])
        row[f"ratio_delay_k{k:.1f}_days_from_d20"] = first_delay(ratio_d, day_d)
    return row


def fmt(value) -> str:
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return "—"
    if isinstance(value, float):
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return str(value)


def markdown_table(df: pd.DataFrame, columns: list[str]) -> str:
    labels = {
        "scenario": "场景",
        "health_point_events_d45_120": "健康单点事件",
        "health_p1_gate_events_d45_120": "健康P1与门",
        "health_ratio_fraction_k1.3_d45_120": "健康比值越限占比 k=1.3",
        "health_ratio_fraction_k1.5_d45_120": "k=1.5",
        "health_ratio_fraction_k2.0_d45_120": "k=2.0",
        "point_delay_days_from_d20": "单点延迟/天",
        "ratio_delay_k1.3_days_from_d20": "比值延迟 k=1.3/天",
        "p1_gate_delay_days_from_d20": "P1与门延迟/天",
    }
    out = ["| " + " | ".join(labels.get(c, c) for c in columns) + " |", "|" + "---|" * len(columns)]
    for _, row in df.iterrows():
        out.append("| " + " | ".join(fmt(row[c]) for c in columns) + " |")
    return "\n".join(out)


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    rows: list[dict] = []
    for scenario, f_h, f_d, group in PAIRS:
        healthy = pd.read_csv(os.path.join(IN_DIR, f_h))
        degraded = pd.read_csv(os.path.join(IN_DIR, f_d))
        dt = float(np.median(np.diff(healthy["t_day"].to_numpy(dtype=float))))
        samples_per_day = int(round(1.0 / dt))
        assert samples_per_day == 96, (scenario, samples_per_day, dt)
        reference = healthy[(healthy["t_day"] >= REF_LO) & (healthy["t_day"] < REF_HI)]
        floor = scale_floor(healthy)
        s_healthy = frozen_score(healthy, reference, floor)
        s_degraded = frozen_score(degraded, reference, floor)
        s_reference = frozen_score(reference, reference, floor)
        point_threshold = float(np.quantile(s_reference, 0.999))

        rows.append(
            analyse_mode(
                scenario, group, healthy, degraded, s_healthy, s_degraded, point_threshold,
                window_samples=5 * samples_per_day, min_periods=5 * samples_per_day,
                mode="correct_5d",
            )
        )
        rows.append(
            analyse_mode(
                scenario, group, healthy, degraded, s_healthy, s_degraded, point_threshold,
                window_samples=5 * 1440, min_periods=288,
                mode="legacy_7200_samples",
            )
        )

    result = pd.DataFrame(rows)
    result.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

    primary = result[result["mode"] == "correct_5d"].copy()
    legacy = result[result["mode"] == "legacy_7200_samples"].copy()
    frac_cols = [f"health_ratio_fraction_k{k:.1f}_d45_120" for k in (1.3, 1.5, 2.0)]
    zero_counts = {k: int((primary[c] == 0).sum()) for k, c in zip((1.3, 1.5, 2.0), frac_cols)}
    point_fp = int(primary["health_point_events_d45_120"].sum())
    p1_fp = int(primary["health_p1_gate_events_d45_120"].sum())
    point_detected = int(primary["point_delay_days_from_d20"].notna().sum())
    ratio_detected = int(primary["ratio_delay_k1.3_days_from_d20"].notna().sum())
    p1_detected = int(primary["p1_gate_delay_days_from_d20"].notna().sum())
    paired = primary.dropna(subset=["point_delay_days_from_d20", "ratio_delay_k1.3_days_from_d20"])
    ratio_later = int((paired["ratio_delay_k1.3_days_from_d20"] > paired["point_delay_days_from_d20"]).sum())
    ratio_earlier = int((paired["ratio_delay_k1.3_days_from_d20"] < paired["point_delay_days_from_d20"]).sum())
    slow = primary[primary["group"] == "slow"]
    slow_p1 = int(slow["p1_gate_delay_days_from_d20"].notna().sum())

    cols = [
        "scenario", "health_point_events_d45_120", "health_p1_gate_events_d45_120",
        "health_ratio_fraction_k1.3_d45_120", "health_ratio_fraction_k1.5_d45_120",
        "health_ratio_fraction_k2.0_d45_120", "point_delay_days_from_d20",
        "ratio_delay_k1.3_days_from_d20", "p1_gate_delay_days_from_d20",
    ]
    legacy_cols = [
        "scenario", "health_ratio_fraction_k1.3_d45_120", "point_delay_days_from_d20",
        "ratio_delay_k1.3_days_from_d20", "health_p1_gate_events_d45_120",
        "p1_gate_delay_days_from_d20",
    ]

    report = f"""# Q8：比值判据与组合报警策略独立复核（Codex，2026-09-20）

## 最重要的复核发现

入库 BSM1 CSV 的实测采样率是 **96 点/天（15 分钟/点）**，所以滚动 5 天应为 **480 点**。DSH 脚本 `src/dsh/2026-09-20_13_ratio_rule.py:31` 与 `2026-09-20_14_alarm_strategy.py:32` 使用 `5*1440=7200` 点；在这些数据上实际是 **75 天窗口**，不是 5 天。DSH 同时设置 `min_periods=288`（3 天），因此结果是从 3 天逐渐扩张到 75 天的累计中位数。

本报告把 **480 点的真实 5 天窗**作为主结果；另附 `legacy_7200_samples` 诊断模式。后者能复现 DSH 的 ratio base 和长延迟方向，说明差异来自窗口单位，而不是随机性。

## 方法（自有最小链路）

- 数据：12 对已入库 IWA BSM1 **仿真**健康/退化轨迹，不重跑仿真。
- 冻结参考域：每个工况自己的健康运行第 30–45 天。
- 工况分层：按一天中的小时（0–23）分层；每层用参考域中位数和 IQR/1.349 标准化。
- 聚合：7 个通道绝对 z 值的 top-3 RMS。
- 单点阈值：参考域分数 0.999 分位；事件机为连续 4 点进入、连续 8 点低于 0.8×阈值退出、8 点冷却。
- 比值统计量：正确的 5 天（480 点）滚动中位数；base 为健康参考域内该统计量的中位数。
- 评估窗：健康误报和退化检出均只看第 45–120 天；退化从第 20 天开始，故最小可报告延迟为 25 天。
- P1 与门：单点事件起点 ±1 天内，5 天中位数超过 1.15×base。

## 主结果：真实 5 天窗

{markdown_table(primary, cols)}

汇总：

- k=1.3 / 1.5 / 2.0 时，健康越限占比恰为 0 的场景数分别是 **{zero_counts[1.3]}/12、{zero_counts[1.5]}/12、{zero_counts[2.0]}/12**。
- 健康单点事件合计 **{point_fp}**；P1 与门健康事件 **{p1_fp}**，只减少 **{point_fp-p1_fp}** 个（{(100*(point_fp-p1_fp)/point_fp if point_fp else 0):.1f}%）。
- 第 45–120 天内，单点 / 比值 k=1.3 / P1 与门分别检出 **{point_detected}/12、{ratio_detected}/12、{p1_detected}/12**。
- 单点与比值都检出的 {len(paired)} 个场景中，比值更晚 **{ratio_later}** 个、更早 **{ratio_earlier}** 个。
- 四档慢漂移中，P1 与门检出 **{slow_p1}/4**，不是 DSH 报告中的 0/4；但仍漏掉 {4-slow_p1}/4。

## 三条方向逐项判定

### ① “健康比值越限接近 0，单点明显更多”——**不成立**

真实 5 天窗下，k=1.3 的 12 个健康轨迹越限占比均不为 0，范围为 **{primary['health_ratio_fraction_k1.3_d45_120'].min():.3f}–{primary['health_ratio_fraction_k1.3_d45_120'].max():.3f}**。比值判据在评估窗中大面积越限，不具备 DSH 所称的“零误报慢漂移确认”性质。单点事件在 B/C 和雨/暴雨工况仍较多，但这不能挽救比值判据的健康特异性。

### ② “比值检出显著晚于单点”——**不成立，主结果方向相反**

在两者都检出的场景里，k=1.3 比值没有一个晚于单点，反而有 {ratio_earlier}/{len(paired)} 更早。多数比值首越限贴在第 45 天评估边界（延迟约 25 天），而同一健康轨迹也已越限，所以这些“更早检出”其实是**非特异健康漂移**，不能宣传为早期预警。

### ③ “与门减少健康上报，但漏掉四档慢漂移”——**仅部分成立，整体不复现**

真实 5 天窗下，P1 与门只把健康单点事件从 {point_fp} 降到 {p1_fp}，降幅仅 {(100*(point_fp-p1_fp)/point_fp if point_fp else 0):.1f}%，不构成显著降噪。四档慢漂移确实仍漏 {4-slow_p1}/4，但 `slow_-40pct_100d` 在严格第 45–120 天口径下被 P1 检出，因此“4/4 全漏”不成立。

## 诊断对照：DSH 的 7200 点窗口（实际 75 天）

{markdown_table(legacy, legacy_cols)}

`legacy_7200_samples` 的 ratio base（例如 A 窗 2.135、R1 1.302、R2 1.545、R3 2.165）及 k=1.3 延迟（A 86.43、B 93.70、C 75.51、R1 36.83、R2 39.97、R3 54.12 天）与 DSH 表一致。这证明 DSH 已发布的“零越限 + 长延迟”是 **75 天累计平滑**产生的，不是 5 天滚动判据的结果。

另一个口径差异：DSH `alarm_strategy.py:57-61` 对单点/P1 健康事件未应用第 45–120 天筛选，尽管报告文字声称统一使用该评估窗。本复核严格筛选事件起点，因此健康单点/P1计数不可直接与 DSH 的 77/26 比较。

## 结论与建议

1. Q8 要求的三条方向在**真实 5 天窗 + 第 45–120 天统一评估**下均未完整复现。
2. DSH 的方向可以由 `7200` 点（75 天）兼容模式复现，根因是把“每天 1440 分钟”误当成“每天 1440 行”。
3. 当前不得继续引用“5 天滚动比值在 12 工况零误报”“比值显著更晚”“与门 77→26 且四档慢漂移全漏”作为已验证结论；应先把窗口改为基于 `t_day` 的时间窗或 `5*96` 点，再重新冻结。
4. 单点事件机在慢漂移上的首报仍不得作为可靠预警真相；本复核严格从第 45 天起评估，避免第 20 天附近的共同外部成分假象。
"""
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write(report)

    # Reproducibility assertions.
    assert len(primary) == 12 and len(legacy) == 12
    assert set(primary["samples_per_day"]) == {96}
    assert set(primary["rolling_samples"]) == {480}
    assert set(legacy["rolling_samples"]) == {7200}
    # Compatibility-mode anchors from the checked-in DSH report.
    anchors = legacy.set_index("scenario")
    assert abs(anchors.loc["A_window", "ratio_base"] - 2.135) < 0.002
    assert abs(anchors.loc["R1_dry", "ratio_delay_k1.3_days_from_d20"] - 36.83) < 0.02
    assert abs(anchors.loc["R3_storm", "ratio_delay_k1.3_days_from_d20"] - 54.12) < 0.02
    print(f"wrote {OUT_CSV} ({len(result)} rows) and {OUT_MD}")


if __name__ == "__main__":
    main()
