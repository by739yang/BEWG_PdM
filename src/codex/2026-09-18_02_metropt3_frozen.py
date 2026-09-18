#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Recompute Codex MetroPT-3 metrics on the frozen DSH/Codex mask intersection."""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARCHIVE = Path.home() / ".cache" / "BEWG_PdM" / "metropt3" / "metropt3_dataset.zip"
DEFAULT_INTERSECTION = ROOT / "results" / "2026-09-18" / "dsh" / "minute_mask_intersection.csv.gz"
DEFAULT_OUTPUT = ROOT / "results" / "2026-09-18" / "codex"
OLD_SCRIPT = ROOT / "src" / "codex" / "2026-09-16_01_metropt3_baseline.py"
FAILURE_FILE = ROOT / "docs" / "metropt3_fault_windows.json"
PRIMARY_THRESHOLD = 6.0
DET_THRESHOLDS = sorted(set([PRIMARY_THRESHOLD, *np.arange(2.0, 15.01, 0.5).tolist(), 18.0, 22.0, 30.0]))


def load_old_impl():
    spec = importlib.util.spec_from_file_location("codex_metropt3_old", OLD_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {OLD_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_faults() -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    data = json.loads(FAILURE_FILE.read_text(encoding="utf-8"))
    return [(pd.Timestamp(x["start"]), pd.Timestamp(x["end"])) for x in data["windows"]]


def frozen_masks(intersection: pd.DataFrame, faults: list[tuple[pd.Timestamp, pd.Timestamp]]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    fault = np.zeros(len(intersection), dtype=bool)
    for start, end in faults:
        fault |= ((intersection["ts"] >= start) & (intersection["ts"] <= end)).to_numpy()
    base = (
        intersection["B_ds"] & intersection["B_cx"] & intersection["fin_ds"] & intersection["fin_cx"]
        & (~fault) & intersection["stable_ds"] & intersection["stable_cx"]
    ).to_numpy(dtype=bool)
    running = (base & intersection["run_ds"] & intersection["run_cx"]).astype(bool)
    return base, running, fault


def classify_events(events: list[tuple[pd.Timestamp, pd.Timestamp]], faults: list[tuple[pd.Timestamp, pd.Timestamp]]) -> tuple[list[dict], set[int]]:
    rows: list[dict] = []
    matched_alarm_indexes: set[int] = set()
    lead = pd.Timedelta(minutes=60)
    for event_id, (g0, g1) in enumerate(faults, 1):
        timely = [(i, start, end) for i, (start, end) in enumerate(events) if g0 - lead <= start <= g0 + lead]
        late = [(i, start, end) for i, (start, end) in enumerate(events) if g0 + lead < start <= g1]
        if timely:
            i, onset, alarm_end = min(timely, key=lambda x: x[1])
            matched_alarm_indexes.add(i)
            label = "timely"
        elif late:
            i, onset, alarm_end = min(late, key=lambda x: x[1])
            matched_alarm_indexes.add(i)
            label = "late"
        else:
            i, onset, alarm_end = None, None, None
            label = "miss"
        rows.append({
            "event_id": f"F{event_id}",
            "truth_start": g0,
            "truth_end": g1,
            "classification": label,
            "alarm_onset": onset,
            "alarm_end": alarm_end,
            "delay_minutes": (onset - g0).total_seconds() / 60.0 if onset is not None else np.nan,
        })
    return rows, matched_alarm_indexes


def alarm_mask(index: pd.DatetimeIndex, events: list[tuple[pd.Timestamp, pd.Timestamp]]) -> np.ndarray:
    mask = np.zeros(len(index), dtype=bool)
    for start, end in events:
        mask |= (index >= start) & (index < end)
    return mask


def evaluate(scored: pd.DataFrame, timeline: pd.DataFrame, base: np.ndarray, running: np.ndarray, faults: list[tuple[pd.Timestamp, pd.Timestamp]], threshold: float) -> tuple[dict, list[dict], list[tuple[pd.Timestamp, pd.Timestamp]]]:
    old = load_old_impl() if False else None
    # The caller attaches the implementation's eventizer as an attribute.
    events = evaluate.eventize(scored, threshold)  # type: ignore[attr-defined]
    classifications, matched = classify_events(events, faults)
    statuses = [r["classification"] for r in classifications]
    timeline_index = pd.DatetimeIndex(timeline["ts"])
    alarm = alarm_mask(timeline_index, events)
    false_events = sum(i not in matched for i in range(len(events)))
    all_hours = float(base.sum()) / 60.0
    run_hours = float(running.sum()) / 60.0
    result = {
        "threshold": float(threshold),
        "alarm_events": int(len(events)),
        "timely": int(statuses.count("timely")),
        "late": int(statuses.count("late")),
        "miss": int(statuses.count("miss")),
        "timely_recall": float(statuses.count("timely") / len(faults)),
        "false_alarm_events": int(false_events),
        "fp_per_hour_all_stable": float(false_events / all_hours),
        "fp_per_hour_running": float(false_events / run_hours),
        "tia_h_all_stable": float((alarm & base).sum() / base.sum()),
        "tia_h_running": float((alarm & running).sum() / running.sum()),
        "healthy_all_stable_minutes": int(base.sum()),
        "healthy_running_minutes": int(running.sum()),
    }
    return result, classifications, events


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--intersection", type=Path, default=DEFAULT_INTERSECTION)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    impl = load_old_impl()
    raw = impl.read_archive(args.archive.resolve())
    minutes = impl.make_minute_features(raw)
    scored, audits = impl.walk_forward(minutes)
    intersection = pd.read_csv(args.intersection, compression="gzip", parse_dates=["ts"])
    faults = load_faults()
    base, running, fault = frozen_masks(intersection, faults)
    if int(base.sum()) != 96270 or int(running.sum()) != 43136:
        raise RuntimeError(f"frozen denominator mismatch: all_stable={base.sum()}, running={running.sum()}")

    # Only the score stream is needed for the Codex eventizer; stable/finite are
    # already enforced by eventize on the scored walk-forward rows.
    evaluate.eventize = impl.eventize  # type: ignore[attr-defined]
    rows: list[dict] = []
    detail_rows: list[dict] = []
    by_threshold: dict[float, dict] = {}
    for threshold in DET_THRESHOLDS:
        metrics, classifications, events = evaluate(scored, intersection, base, running, faults, float(threshold))
        by_threshold[float(threshold)] = metrics
        rows.append(metrics)
        for detail in classifications:
            detail_rows.append({"threshold": float(threshold), **detail})

    result = pd.DataFrame(rows).sort_values("threshold")
    result.to_csv(args.output_dir / "metropt3_metrics_frozen.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(detail_rows).to_csv(args.output_dir / "metropt3_metrics_frozen_events.csv", index=False, encoding="utf-8-sig")

    primary = by_threshold[PRIMARY_THRESHOLD]
    best = result.sort_values(["timely_recall", "fp_per_hour_all_stable", "tia_h_all_stable", "threshold"], ascending=[False, True, True, True]).iloc[0].to_dict()
    lines = [
        "# MetroPT-3 冻结分母指标（Codex，2026-09-18）", "",
        "## 口径", "",
        "- 分母采用 `results/2026-09-18/dsh/minute_mask_intersection.csv.gz` 中双方 B 域、score finite、stable 的交集，并排除官方故障窗。",
        f"- 冻结分母：healthy_all_stable = **{int(base.sum()):,} 分钟**（{base.sum() / 60:.1f} 小时）；healthy_running = **{int(running.sum()):,} 分钟**（{running.sum() / 60:.1f} 小时）。",
        "- timely：告警起点落在 `[g0−60min, g0+60min]`；late：`(g0+60min, g1]`；其余为 miss。timely 才计主召回，late 单列。",
        "- 告警事件和得分沿用 Codex 的 MetroPT-3 state-conditioned walk-forward 与事件化实现；冻结交集只用于误报小时率和 TIA-H 分母。",
        "", "## 主阈值", "",
        f"- Codex 既有主阈值 `{PRIMARY_THRESHOLD:.1f}`：timely **{int(primary['timely'])}/4**，late **{int(primary['late'])}/4**，miss **{int(primary['miss'])}/4**；误报事件 **{int(primary['false_alarm_events'])}**；误报率 **{primary['fp_per_hour_all_stable']:.4f} 次/全稳定小时**（running：{primary['fp_per_hour_running']:.4f}）；TIA-H **{primary['tia_h_all_stable'] * 100:.1f}%**（running：{primary['tia_h_running'] * 100:.1f}%）。",
        "", "## DET 扫描", "", result.to_markdown(index=False), "",
        f"- 本次扫描中按‘最大 timely 召回、再最小全稳定小时误报率’选出的点为 threshold={best['threshold']:.4f}：timely={int(best['timely'])}/4，late={int(best['late'])}/4，miss={int(best['miss'])}/4，误报率={best['fp_per_hour_all_stable']:.4f} 次/全稳定小时，TIA-H={best['tia_h_all_stable'] * 100:.1f}%。",
        "- DSH 冻结口径参考为 timely 2/4、误报率 0.1253 次/全稳定小时、TIA-H 11.6%；两边若阈值数值不同，不应直接把阈值本身横向比较，先比较 timely/late/miss 和冻结分母下的误报、TIA-H。",
        "", "## 可复现信息", "",
        f"- 归档：`{args.archive.resolve()}`；walk-forward 评分分钟：`{len(scored):,}`，有限分数：`{int(np.isfinite(scored['score']).sum()):,}`。",
        f"- 评分审计 epoch 数：`{len(audits)}`。脚本未写入 `data/`，也未修改 `src/dsh/` 或 `results/*/dsh/`。",
    ]
    (args.output_dir / "metropt3_metrics_frozen.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(result.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
