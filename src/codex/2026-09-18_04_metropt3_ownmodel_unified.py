#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Evaluate the Codex MetroPT-3 score stream with the unified event machine."""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCORE = ROOT / "results" / "2026-09-16" / "codex" / "metropt3_scored_minutes.csv.gz"
DEFAULT_INTERSECTION = ROOT / "results" / "2026-09-18" / "dsh" / "minute_mask_intersection.csv.gz"
DEFAULT_OUTPUT = ROOT / "results" / "2026-09-18" / "codex"
FAILURE_FILE = ROOT / "docs" / "metropt3_fault_windows.json"
EVENT_IMPL = ROOT / "src" / "codex" / "2026-09-16_01_metropt3_baseline.py"
PRIMARY_THRESHOLD = 6.0
DET_THRESHOLDS = sorted(set([PRIMARY_THRESHOLD, *np.arange(2.0, 15.01, 0.5).tolist(), 18.0, 22.0, 30.0]))


def load_eventizer():
    spec = importlib.util.spec_from_file_location("codex_unified_eventizer", EVENT_IMPL)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import event-machine implementation: {EVENT_IMPL}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_faults() -> list[tuple[str, pd.Timestamp, pd.Timestamp]]:
    data = json.loads(FAILURE_FILE.read_text(encoding="utf-8"))
    return [(str(row["id"]), pd.Timestamp(row["start"]), pd.Timestamp(row["end"])) for row in data["windows"]]


def make_frozen_masks(intersection: pd.DataFrame, faults: list[tuple[str, pd.Timestamp, pd.Timestamp]]) -> tuple[np.ndarray, np.ndarray]:
    fault = np.zeros(len(intersection), dtype=bool)
    for _, start, end in faults:
        fault |= ((intersection["ts"] >= start) & (intersection["ts"] <= end)).to_numpy()
    all_stable = (
        intersection["B_ds"] & intersection["B_cx"]
        & intersection["fin_ds"] & intersection["fin_cx"]
        & intersection["stable_ds"] & intersection["stable_cx"]
        & (~fault)
    ).to_numpy(dtype=bool)
    running = (all_stable & intersection["run_ds"] & intersection["run_cx"]).astype(bool)
    return all_stable, running


def classify_events(events: list[tuple[pd.Timestamp, pd.Timestamp]], faults: list[tuple[str, pd.Timestamp, pd.Timestamp]]) -> tuple[list[dict], set[int]]:
    """Classify each truth window; only the earliest qualifying alarm is the representative."""
    rows: list[dict] = []
    representative: set[int] = set()
    lead = pd.Timedelta(minutes=60)
    for event_id, start, end in faults:
        timely = [(i, a, b) for i, (a, b) in enumerate(events) if start - lead <= a <= start + lead]
        late = [(i, a, b) for i, (a, b) in enumerate(events) if start + lead < a <= end]
        if timely:
            i, onset, alarm_end = min(timely, key=lambda x: x[1])
            label = "timely"
            representative.add(i)
        elif late:
            i, onset, alarm_end = min(late, key=lambda x: x[1])
            label = "late"
            representative.add(i)
        else:
            i, onset, alarm_end = None, None, None
            label = "miss"
        rows.append({
            "event_id": event_id,
            "truth_start": start,
            "truth_end": end,
            "classification": label,
            "alarm_onset": onset,
            "alarm_end": alarm_end,
            "delay_minutes": (onset - start).total_seconds() / 60.0 if onset is not None else np.nan,
        })
    return rows, representative


def alarm_mask(index: pd.DatetimeIndex, events: list[tuple[pd.Timestamp, pd.Timestamp]]) -> np.ndarray:
    mask = np.zeros(len(index), dtype=bool)
    for start, end in events:
        mask |= (index >= start) & (index < end)
    return mask


def fast_eventize(scored: pd.DataFrame, threshold: float) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Numpy-backed translation of the frozen event machine."""
    events: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    active = False
    enter_count = 0
    exit_count = 0
    cooldown_remaining = 0
    alarm_start: pd.Timestamp | None = None
    last_time: pd.Timestamp | None = None
    prev_epoch: str | None = None
    enter_samples, exit_samples, cooldown_samples = 5, 10, 30
    times = scored.index.to_pydatetime()
    values = pd.to_numeric(scored["score"], errors="coerce").to_numpy(dtype=float)
    stable = scored["stable"].to_numpy(dtype=bool)
    epochs = scored["epoch"].astype(str).to_numpy()
    for raw_t, value, is_stable, epoch in zip(times, values, stable, epochs):
        t = pd.Timestamp(raw_t)
        eligible = bool(is_stable) and np.isfinite(value)
        high = eligible and value > threshold
        low = eligible and value < 0.8 * threshold
        if prev_epoch is not None and epoch != prev_epoch:
            if active and alarm_start is not None and last_time is not None:
                events.append((alarm_start, last_time + pd.Timedelta(minutes=1)))
            active = False
            enter_count = 0
            exit_count = 0
            cooldown_remaining = 0
            alarm_start = None
        if active:
            if low:
                exit_count += 1
                if exit_count >= exit_samples:
                    assert alarm_start is not None
                    events.append((alarm_start, t + pd.Timedelta(minutes=1)))
                    active = False
                    alarm_start = None
                    enter_count = 0
                    exit_count = 0
                    cooldown_remaining = cooldown_samples
            else:
                exit_count = 0
        else:
            if cooldown_remaining > 0:
                cooldown_remaining -= 1
                enter_count = 0
            elif high:
                enter_count += 1
                if enter_count >= enter_samples:
                    active = True
                    alarm_start = t
                    enter_count = 0
                    exit_count = 0
            else:
                enter_count = 0
        prev_epoch = epoch
        last_time = t
    if active and alarm_start is not None and last_time is not None:
        events.append((alarm_start, last_time + pd.Timedelta(minutes=1)))
    return events

def evaluate_one(scored: pd.DataFrame, timeline: pd.DataFrame, all_stable: np.ndarray, running: np.ndarray,
                 faults: list[tuple[str, pd.Timestamp, pd.Timestamp]], threshold: float, eventize) -> tuple[dict, list[dict], list[tuple[pd.Timestamp, pd.Timestamp]]]:
    events = eventize(scored, float(threshold))
    details, representative = classify_events(events, faults)
    status = [row["classification"] for row in details]
    idx = pd.DatetimeIndex(timeline["ts"])
    alarms = alarm_mask(idx, events)
    lead = pd.Timedelta(minutes=60)
    # The unified cross-check convention treats every alarm onset in a truth
    # window's [g0-60 min, g1] interval as non-false.  The representative event
    # remains the earliest timely event, or earliest late event if no timely one.
    false_by_window = sum(
        not any(start - lead <= onset <= end for _, start, end in faults)
        for onset, _ in events
    )
    false_by_representative = sum(i not in representative for i in range(len(events)))
    delays = np.asarray([row["delay_minutes"] for row in details if np.isfinite(row["delay_minutes"])], dtype=float)
    all_hours = float(all_stable.sum()) / 60.0
    running_hours = float(running.sum()) / 60.0
    result = {
        "threshold": float(threshold),
        "alarm_events": int(len(events)),
        "timely": int(status.count("timely")),
        "late": int(status.count("late")),
        "miss": int(status.count("miss")),
        "timely_recall": float(status.count("timely") / len(faults)),
        "false_alarm_events": int(false_by_window),
        "false_alarm_events_representative_rule": int(false_by_representative),
        "false_alarm_fraction_of_alarm_events": float(false_by_window / len(events)) if events else np.nan,
        "false_alarms_per_all_stable_hour": float(false_by_window / all_hours),
        "false_alarms_per_running_hour": float(false_by_window / running_hours),
        "tia_h_all_stable": float((alarms & all_stable).sum() / all_stable.sum()),
        "tia_h_running": float((alarms & running).sum() / running.sum()),
        "alarm_minutes_all_stable": int((alarms & all_stable).sum()),
        "alarm_minutes_running": int((alarms & running).sum()),
        "healthy_all_stable_minutes": int(all_stable.sum()),
        "healthy_running_minutes": int(running.sum()),
        "delay_count": int(len(delays)),
        "delay_min_minutes": float(np.min(delays)) if len(delays) else np.nan,
        "delay_p25_minutes": float(np.percentile(delays, 25)) if len(delays) else np.nan,
        "delay_median_minutes": float(np.median(delays)) if len(delays) else np.nan,
        "delay_p75_minutes": float(np.percentile(delays, 75)) if len(delays) else np.nan,
        "delay_max_minutes": float(np.max(delays)) if len(delays) else np.nan,
        "delay_mean_minutes": float(np.mean(delays)) if len(delays) else np.nan,
    }
    return result, details, events


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--score", type=Path, default=DEFAULT_SCORE)
    parser.add_argument("--intersection", type=Path, default=DEFAULT_INTERSECTION)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--primary-threshold", type=float, default=PRIMARY_THRESHOLD)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    impl = load_eventizer()
    score = pd.read_csv(args.score.resolve(), compression="gzip", parse_dates=["timestamp"])
    required = {"timestamp", "stable", "score", "epoch"}
    missing = required.difference(score.columns)
    if missing:
        raise RuntimeError(f"score stream missing columns: {sorted(missing)}")
    score = score.sort_values("timestamp", kind="stable").drop_duplicates("timestamp").reset_index(drop=True)
    scored = score.set_index("timestamp")[["score", "stable", "epoch"]].copy()
    scored["score"] = pd.to_numeric(scored["score"], errors="coerce")
    scored["stable"] = scored["stable"].astype(bool)
    if not scored.index.is_monotonic_increasing or scored.index.duplicated().any():
        raise RuntimeError("score stream timestamp axis is not unique and increasing")

    intersection = pd.read_csv(args.intersection.resolve(), compression="gzip", parse_dates=["ts"])
    faults = load_faults()
    all_stable, running = make_frozen_masks(intersection, faults)
    if int(all_stable.sum()) != 96270 or int(running.sum()) != 43136:
        raise RuntimeError(f"frozen denominator mismatch: all_stable={all_stable.sum()}, running={running.sum()}")

    thresholds = sorted(set([float(args.primary_threshold), *np.arange(2.0, 15.01, 0.5).tolist(), 18.0, 22.0, 30.0]))
    metrics: list[dict] = []
    all_details: list[dict] = []
    primary: dict | None = None
    primary_details: list[dict] | None = None
    primary_events: list[tuple[pd.Timestamp, pd.Timestamp]] | None = None
    for threshold in thresholds:
        result, details, events = evaluate_one(scored, intersection, all_stable, running, faults, threshold, fast_eventize)
        metrics.append(result)
        all_details.extend({"threshold": threshold, **detail} for detail in details)
        if abs(threshold - float(args.primary_threshold)) < 1e-12:
            primary, primary_details, primary_events = result, details, events
    if primary is None or primary_details is None or primary_events is None:
        raise RuntimeError("primary threshold was not included in DET grid")
    reference_events = impl.eventize(scored, float(args.primary_threshold))
    if reference_events != primary_events:
        raise RuntimeError("fast eventizer differs from the reference unified eventizer")

    det = pd.DataFrame(metrics).sort_values("threshold").reset_index(drop=True)
    det.to_csv(args.output_dir / "metropt3_ownmodel_unified.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(all_details).to_csv(args.output_dir / "metropt3_ownmodel_unified_events.csv", index=False, encoding="utf-8-sig")

    delay_rows = pd.DataFrame(primary_details)
    primary_json = {k: (None if pd.isna(v) else v) for k, v in primary.items()}
    (args.output_dir / "metropt3_ownmodel_unified_primary.json").write_text(json.dumps(primary_json, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")

    d = det[det["threshold"].eq(float(args.primary_threshold))].iloc[0]
    lines = [
        "# MetroPT-3 Codex 自有模型：统一事件机复评（2026-09-18）", "",
        "## 可复现命令", "",
        "```powershell",
        "python src/codex/2026-09-16_01_metropt3_baseline.py",
        "python src/codex/2026-09-18_04_metropt3_ownmodel_unified.py",
        "```", "",
        "## 输入与冻结口径", "",
        f"- 自有模型分数流：`{args.score.resolve()}`；评分分钟数：**{len(scored):,}**；有限分数：**{int(np.isfinite(scored['score']).sum()):,}**。",
        f"- 事件机实现：`{EVENT_IMPL}`；连续 5 个 `score > threshold` 后，以第 5 分钟为事件起点；连续 10 个 `score < 0.8×threshold` 退出；退出后冷却 30 分钟。",
        f"- 冻结分母：healthy_all_stable = **{int(all_stable.sum()):,} 分钟**；healthy_running = **{int(running.sum()):,} 分钟**。",
        "- 命中：timely 为起点落在 `[g0−60min, g0+60min]`；late 为 `(g0+60min, g1]`；其余 miss。主召回只计 timely。",
        "- 误报口径：告警起点不落入任一 `[g0−60min, g1]` 的告警事件计误报；同时保留代表事件规则计数，便于审计重复命中。",
        "", "## 主工作点（threshold=6.0）", "",
        f"- 告警总数：**{int(d['alarm_events'])}**。",
        f"- 故障分类：timely **{int(d['timely'])}/4**，late **{int(d['late'])}/4**，miss **{int(d['miss'])}/4**。",
        f"- 误报事件：**{int(d['false_alarm_events'])}**（占告警总数 {d['false_alarm_fraction_of_alarm_events']:.5f}）；代表事件规则为 **{int(d['false_alarm_events_representative_rule'])}**。",
        f"- 误报率：**{d['false_alarms_per_all_stable_hour']:.4f} 次/全稳定小时**；running 分母 **{d['false_alarms_per_running_hour']:.4f} 次/小时**。",
        f"- TIA-H：**{d['tia_h_all_stable'] * 100:.1f}%**（{int(d['alarm_minutes_all_stable']):,}/{int(d['healthy_all_stable_minutes']):,} 分钟）；running TIA-H **{d['tia_h_running'] * 100:.1f}%**（{int(d['alarm_minutes_running']):,}/{int(d['healthy_running_minutes']):,} 分钟）。",
        f"- 延迟分布（{int(d['delay_count'])} 个命中事件，分钟）：min **{d['delay_min_minutes']:.1f}**，P25 **{d['delay_p25_minutes']:.1f}**，中位 **{d['delay_median_minutes']:.1f}**，P75 **{d['delay_p75_minutes']:.1f}**，max **{d['delay_max_minutes']:.1f}**，均值 **{d['delay_mean_minutes']:.1f}**。负值代表提前预警。",
        "", "### 主工作点逐故障延迟", "", delay_rows.to_markdown(index=False),
        "", "## 30 点 DET（统一事件机）", "", det.to_markdown(index=False),
        "", "## 与 DSH 冻结工作点的并列解释", "",
        "- DSH 在阈值 2.395 上的冻结结果为 205 次告警、timely/late/miss = 2/1/1、误报 201 次、0.1253 次/全稳定小时、TIA-H 11.6%；本表是 Codex 自有分数流，不应比较阈值数值本身。",
        "- 两套结果已经使用同一冻结分母、同一三态命中判据和同一事件机；剩余差异应归因于分数流/模型实现，而不是评价机口径。",
        "- 4 个官方故障窗样本量极小，DET 每个及时召回步长为 25%；这些结果只能作为探索性公开基准证据，不能直接等同于污水厂现场性能。",
        "", "## 产物", "",
        "- `metropt3_ownmodel_unified.csv`：30 个阈值点及主工作点字段。",
        "- `metropt3_ownmodel_unified_events.csv`：逐故障分类与延迟；`metropt3_ownmodel_unified_primary.json`：主工作点机器可读摘要。",
        "- 脚本未写入 `data/`，未修改 `src/dsh/` 或 `results/*/dsh/`。",
    ]
    (args.output_dir / "metropt3_ownmodel_unified.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(det.to_string(index=False))
    print("\nPrimary event details:")
    print(delay_rows.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


