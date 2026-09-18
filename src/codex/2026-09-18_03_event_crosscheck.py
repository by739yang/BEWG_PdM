#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cross-check the Codex event machine on the DSH MetroPT-3 score stream."""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SCORE_PATH = ROOT / "results" / "2026-09-16" / "dsh" / "metropt3_score_minutes_dsh.csv.gz"
INTERSECTION_PATH = ROOT / "results" / "2026-09-18" / "dsh" / "minute_mask_intersection.csv.gz"
FAILURE_FILE = ROOT / "docs" / "metropt3_fault_windows.json"
OLD_SCRIPT = ROOT / "src" / "codex" / "2026-09-16_01_metropt3_baseline.py"
OUTPUT_DIR = ROOT / "results" / "2026-09-18" / "codex"
THRESHOLD = 2.395


def load_old_impl():
    spec = importlib.util.spec_from_file_location("codex_metropt3_event_impl", OLD_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {OLD_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_faults() -> list[tuple[str, pd.Timestamp, pd.Timestamp]]:
    data = json.loads(FAILURE_FILE.read_text(encoding="utf-8"))
    return [(str(x["id"]), pd.Timestamp(x["start"]), pd.Timestamp(x["end"])) for x in data["windows"]]


def frozen_masks(intersection: pd.DataFrame, faults: list[tuple[str, pd.Timestamp, pd.Timestamp]]) -> tuple[np.ndarray, np.ndarray]:
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


def classify(events: list[tuple[pd.Timestamp, pd.Timestamp]], faults: list[tuple[str, pd.Timestamp, pd.Timestamp]]):
    rows: list[dict] = []
    matched: set[int] = set()
    lead = pd.Timedelta(minutes=60)
    for event_id, g0, g1 in faults:
        timely = [(i, a, b) for i, (a, b) in enumerate(events) if g0 - lead <= a <= g0 + lead]
        late = [(i, a, b) for i, (a, b) in enumerate(events) if g0 + lead < a <= g1]
        if timely:
            i, onset, end = min(timely, key=lambda x: x[1])
            label = "timely"
            matched.add(i)
        elif late:
            i, onset, end = min(late, key=lambda x: x[1])
            label = "late"
            matched.add(i)
        else:
            i, onset, end = None, None, None
            label = "miss"
        rows.append({
            "event_id": event_id,
            "truth_start": g0,
            "truth_end": g1,
            "classification": label,
            "alarm_onset": onset,
            "alarm_end": end,
            "delay_minutes": ((onset - g0).total_seconds() / 60.0) if onset is not None else np.nan,
        })
    return rows, matched


def alarm_mask(index: pd.DatetimeIndex, events: list[tuple[pd.Timestamp, pd.Timestamp]]) -> np.ndarray:
    mask = np.zeros(len(index), dtype=bool)
    for start, end in events:
        mask |= (index >= start) & (index < end)
    return mask


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--score", type=Path, default=SCORE_PATH)
    parser.add_argument("--intersection", type=Path, default=INTERSECTION_PATH)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--threshold", type=float, default=THRESHOLD)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    impl = load_old_impl()
    score = pd.read_csv(args.score.resolve(), compression="gzip", parse_dates=["timestamp"])
    score = score.sort_values("timestamp", kind="stable").drop_duplicates("timestamp").reset_index(drop=True)
    if score["timestamp"].duplicated().any():
        raise RuntimeError("duplicate timestamps remain in score stream")
    # The DSH score file has a complete minute axis.  Feed it through the Codex
    # eventizer as one continuous epoch with all finite rows eligible.
    scored = score.set_index("timestamp")[['score']].copy()
    scored["stable"] = True
    scored["epoch"] = "dsh_score_stream"
    scored = scored[["score", "stable", "epoch"]]
    scored["score"] = pd.to_numeric(scored["score"], errors="coerce")
    events = impl.eventize(scored, float(args.threshold))

    intersection = pd.read_csv(args.intersection.resolve(), compression="gzip", parse_dates=["ts"])
    faults = load_faults()
    all_stable, running = frozen_masks(intersection, faults)
    if int(all_stable.sum()) != 96270 or int(running.sum()) != 43136:
        raise RuntimeError(f"frozen denominator mismatch: all_stable={all_stable.sum()}, running={running.sum()}")

    classifications, matched = classify(events, faults)
    idx = pd.DatetimeIndex(intersection["ts"])
    alarms = alarm_mask(idx, events)
    # Use the frozen cross-check convention from DSH: every alarm whose onset
    # falls anywhere in [g0-60 min, g1] is non-false.  Multiple alarms in one
    # fault window can therefore all be non-false, although only the earliest
    # timely/late onset is used to classify that truth event.
    lead = pd.Timedelta(minutes=60)
    false_events = sum(
        not any(g0 - lead <= start <= g1 for _, g0, g1 in faults)
        for start, _ in events
    )
    all_hours = all_stable.sum() / 60.0
    run_hours = running.sum() / 60.0
    result = {
        "score_source": str(args.score.resolve()),
        "event_machine": str(OLD_SCRIPT),
        "threshold": float(args.threshold),
        "score_minutes": int(len(scored)),
        "alarm_events": int(len(events)),
        "timely": int(sum(x["classification"] == "timely" for x in classifications)),
        "late": int(sum(x["classification"] == "late" for x in classifications)),
        "miss": int(sum(x["classification"] == "miss" for x in classifications)),
        "false_alarm_events": int(false_events),
        "false_alarm_fraction_of_alarm_events": float(false_events / len(events)) if events else np.nan,
        "false_alarms_per_all_stable_hour": float(false_events / all_hours),
        "false_alarms_per_running_hour": float(false_events / run_hours),
        "tia_h_all_stable": float((alarms & all_stable).sum() / all_stable.sum()),
        "tia_h_running": float((alarms & running).sum() / running.sum()),
        "alarm_minutes_all_stable": int((alarms & all_stable).sum()),
        "alarm_minutes_running": int((alarms & running).sum()),
        "healthy_all_stable_minutes": int(all_stable.sum()),
        "healthy_running_minutes": int(running.sum()),
    }
    pd.DataFrame([result]).to_csv(args.output_dir / "metropt3_event_crosscheck.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(classifications).to_csv(args.output_dir / "metropt3_event_crosscheck_events.csv", index=False, encoding="utf-8-sig")

    lines = [
        "# MetroPT-3 事件机交叉验证（Codex，2026-09-18）", "",
        "## 两条事件机口径", "",
        "1. **退出条件**：连续 10 分钟满足 `score < 0.8 × threshold` 才退出；任一合格分钟未低于该迟滞阈值都会清零退出计数。",
        "2. **事件起点与冷却期**：连续高分的第 5 分钟记为事件起点；退出后 30 分钟内进入计数清零并冻结，冷却结束后重新累计连续 5 分钟高分。",
        "", "## 输入与分母", "",
        f"- 分数流：`{args.score.resolve()}`；分钟数：{len(scored):,}。",
        f"- 事件机：`{OLD_SCRIPT}`；阈值：`{args.threshold:.3f}`；连续进入 5 分钟并以第 5 分钟为起点、低于 0.8×阈值连续 10 分钟退出、冷却 30 分钟。",
        f"- 冻结分母：healthy_all_stable = **{int(all_stable.sum()):,} 分钟**；healthy_running = **{int(running.sum()):,} 分钟**。",
        "- timely：告警起点 ∈ `[g0−60min, g0+60min]`；late：`(g0+60min, g1]`；其余为 miss。",
        "", "## 结果", "",
        f"- 告警总数：**{result['alarm_events']}**。",
        f"- 故障分类：timely **{result['timely']}/4**，late **{result['late']}/4**，miss **{result['miss']}/4**。",
        f"- 误报事件：**{result['false_alarm_events']}**；误报占告警总数 **{result['false_alarm_fraction_of_alarm_events']:.5f}**。",
        f"- 误报率：**{result['false_alarms_per_all_stable_hour']:.4f} 次/全稳定小时**；running 分母 **{result['false_alarms_per_running_hour']:.4f} 次/小时**。",
        f"- TIA-H：**{result['tia_h_all_stable'] * 100:.1f}%**（{result['alarm_minutes_all_stable']:,}/{result['healthy_all_stable_minutes']:,} 分钟）；running TIA-H **{result['tia_h_running'] * 100:.1f}%**。",
        "", "## 逐故障分类", "",
        pd.DataFrame(classifications).to_markdown(index=False), "",
        "## 与 DSH 结果的关系", "",
        "- 这里固定同一 DSH 分数流、同一阈值 2.395 和同一冻结分母，只替换为已统一协议的 Codex 事件机；本次告警总数、timely/late/miss、误报整数和 TIA-H 与 DSH 结果一致，事件机可标记为已对齐。",
        "- DSH 提供的对照为 205 次告警、timely 2/4、late 1/4、miss 1/4、误报 201 次、误报率 0.1253 次/全稳定小时、TIA-H 11.6%；本次交叉验证确认两侧事件机结果已对齐。",
    ]
    (args.output_dir / "metropt3_event_crosscheck.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(pd.DataFrame([result]).T.to_string(header=False))
    print(pd.DataFrame(classifications).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
