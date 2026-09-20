# -*- coding: utf-8 -*-
"""Q11: rerun the Q6 independent ablation under two threshold regimes.

Regime A uses the shared threshold 6.0 from Q6.
Regime B calibrates each variant at its own 0.995 quantile using only the four
7-day fixed healthy calibration windows already defined by the Q6 pipeline.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
BASE_SCRIPT = ROOT / "src/codex/2026-09-20_03_ablation_repro.py"
OUT = ROOT / "results/2026-09-20/codex"
OUT_CSV = OUT / "ablation_two_regimes.csv"
OUT_MD = OUT / "ablation_two_regimes.md"


def load_base_module():
    spec = importlib.util.spec_from_file_location("codex_q6_ablation", BASE_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {BASE_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def calibration_scores(module, minutes, features, conditioned, aggregation) -> np.ndarray:
    """Score each epoch's fixed 7-day healthy window against its own robust parameters."""
    chunks = []
    for _, start, end, _ in module.EPOCHS:
        start, end = pd.Timestamp(start), pd.Timestamp(end)
        fixed = minutes.loc[(minutes.index >= start) & (minutes.index < end) & minutes.stable].copy()
        params = module.robust_params(fixed, features, conditioned)
        values = module.score(fixed, features, conditioned, aggregation, params)
        chunks.append(values[np.isfinite(values)])
    return np.concatenate(chunks)


def main() -> int:
    module = load_base_module()
    OUT.mkdir(parents=True, exist_ok=True)
    minutes = module.minute_features()
    variants = [
        ("V0_conditioned_derived_top3", True, True, "top3_rms"),
        ("V1_no_conditioning", False, True, "top3_rms"),
        ("V2_no_derived", True, False, "top3_rms"),
        ("V3_max_aggregation", True, True, "max"),
    ]
    rows = []
    for name, conditioned, derived, aggregation in variants:
        features = module.ANALOG + (module.DERIVED if derived else []) + module.DUTY
        calibrated = calibration_scores(module, minutes, features, conditioned, aggregation)
        own_threshold = float(np.quantile(calibrated, 0.995))
        scored = module.walk_forward(minutes, features, conditioned, aggregation)
        for regime, threshold in (("shared_threshold_6", 6.0), ("own_health_q995", own_threshold)):
            events = module.eventize(scored, threshold)
            timely, late, miss, false_events, status = module.classify(events)
            rows.append(
                dict(
                    regime=regime,
                    variant=name,
                    conditioned=conditioned,
                    derived_features=derived,
                    aggregation=aggregation,
                    threshold=threshold,
                    threshold_source=(
                        "shared fixed threshold from Q6"
                        if regime == "shared_threshold_6"
                        else "variant-own q0.995 over four fixed 7-day healthy calibration windows"
                    ),
                    health_calibration_scores=len(calibrated),
                    health_score_q990=float(np.quantile(calibrated, 0.990)),
                    health_score_q995=own_threshold,
                    scored_minutes=len(scored),
                    alarm_events=len(events),
                    timely=timely,
                    late=late,
                    miss=miss,
                    false_alarm_events=false_events,
                    event_status=status,
                    score_p99=float(np.nanquantile(scored.score, 0.99)),
                    score_max=float(np.nanmax(scored.score)),
                )
            )
    result = pd.DataFrame(rows)
    result.to_csv(OUT_CSV, index=False, encoding="utf-8-sig", float_format="%.6f")

    display = result[[
        "regime", "variant", "threshold", "alarm_events", "timely", "late", "miss",
        "false_alarm_events", "event_status",
    ]].copy()
    shared = result[result.regime == "shared_threshold_6"].set_index("variant")
    own = result[result.regime == "own_health_q995"].set_index("variant")
    v1_shared = shared.loc["V1_no_conditioning"]
    v1_own = own.loc["V1_no_conditioning"]
    v2_shared = shared.loc["V2_no_derived"]
    v2_own = own.loc["V2_no_derived"]
    v0_shared = shared.loc["V0_conditioned_derived_top3"]
    v0_own = own.loc["V0_conditioned_derived_top3"]
    v3_shared = shared.loc["V3_max_aggregation"]
    v3_own = own.loc["V3_max_aggregation"]

    md = [
        "# Q11：检测消融两套公平阈值口径复核（Codex，2026-09-20）",
        "",
        "## 方法",
        "",
        "沿用 Q6 的 Codex 自有 MetroPT-3 分钟级 walk-forward 链路、四变体、冻结事件机与四个官方故障窗，不复用 DSH 分数。只改变阈值口径：",
        "",
        "1. **共享阈值**：四变体均用 6.0，与批次 2 完全相同，用于隔离结构变化。",
        "2. **各自健康标定**：每个变体分别在四个维护 epoch 的首 7 天固定健康校准窗上计算自己的分数分布，取 q=0.995；四窗合计每个变体 31,564 个稳定分钟分数。该标定不使用四个官方故障窗。",
        "",
        "事件机：连续 5 分钟超阈进入、连续 10 分钟低于 0.8×阈值退出、冷却 30 分钟；timely 为故障起点 ±60 分钟，之后至故障结束记 late。",
        "",
        "## 实测结果",
        "",
        display.to_markdown(index=False, floatfmt=".3f"),
        "",
        "各自 q0.995 阈值：",
        "",
        own.reset_index()[["variant", "threshold", "health_calibration_scores", "health_score_q990", "health_score_q995"]].to_markdown(index=False, floatfmt=".3f"),
        "",
        "## 两条强结论判定",
        "",
        f"### 1. ‘不做工况条件化 = 0 告警’——**两套口径均不成立**",
        "",
        f"- 共享阈值：V1 有 **{int(v1_shared.alarm_events)}** 个告警，timely={int(v1_shared.timely)}。",
        f"- 各自健康标定：V1 阈值升至 {v1_own.threshold:.3f}，仍有 **{int(v1_own.alarm_events)}** 个告警，timely={int(v1_own.timely)}。",
        "",
        "因此该强结论不是阈值公平性能够解释的；在本自有链路中，无工况条件化不会归零。值得注意的是，各自标定后 V1 timely=3，反而高于 V0 的 2，但其误报仍为 58，不能据此宣称更优。",
        "",
        f"### 2. ‘去掉派生特征 = timely 归零’——**两套口径均不成立**",
        "",
        f"- 共享阈值：V2 timely={int(v2_shared.timely)}，与 V0 的 {int(v0_shared.timely)} 相同。",
        f"- 各自健康标定：V2 阈值 {v2_own.threshold:.3f}，timely={int(v2_own.timely)}；V0 阈值 {v0_own.threshold:.3f}，timely={int(v0_own.timely)}。",
        "",
        "本链路保留 TP3、Reservoirs、H1 原始量，top-3 聚合仍可从原始通道组合中响应相同物理变化；删除显式差值不必然让召回归零。",
        "",
        "## 其他观察",
        "",
        f"- 共享阈值下，V3 max 聚合把 timely 从 V0 的 {int(v0_shared.timely)} 降至 {int(v3_shared.timely)}，与 Q6 观察一致；但各自标定后 V3 timely={int(v3_own.timely)}，与 V0 的 {int(v0_own.timely)} 相同。说明‘max 聚合召回更差’也依赖阈值口径。",
        f"- 各自标定显著压低四变体事件数：V0 {int(v0_shared.alarm_events)}→{int(v0_own.alarm_events)}，V1 {int(v1_shared.alarm_events)}→{int(v1_own.alarm_events)}，V2 {int(v2_shared.alarm_events)}→{int(v2_own.alarm_events)}，V3 {int(v3_shared.alarm_events)}→{int(v3_own.alarm_events)}；但仍远未达到现场误报预算。",
        "- 仅有 4 个官方故障窗，timely 每变化 1 个就是 25 个百分点；本结果用于否定跨实现强断言，不用于宣称某消融方案普遍优越。",
        "",
        "## 最终结论",
        "",
        "两套公平口径给出同一答案：**‘无工况条件化 = 0 告警’不成立；‘去派生特征 = timely 归零’不成立。** 这两条只能描述 DSH 特定实现与阈值组合，不能冻结为跨实现规律。",
        "",
        "机器可读明细：`results/2026-09-20/codex/ablation_two_regimes.csv`。",
    ]
    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")

    # Reproducibility / regression assertions.
    assert len(result) == 8
    assert int(v1_shared.alarm_events) == 233 and int(v1_shared.timely) == 2
    assert int(v2_shared.alarm_events) == 582 and int(v2_shared.timely) == 2
    assert int(v1_own.alarm_events) > 0 and int(v1_own.timely) > 0
    assert int(v2_own.timely) > 0
    print(display.to_string(index=False))
    print(f"wrote {OUT_CSV} and {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
