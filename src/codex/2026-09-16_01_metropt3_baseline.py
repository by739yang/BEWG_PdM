#!/usr/bin/env python3
"""Exploratory MetroPT-3 state-conditioned walk-forward anomaly baseline.

The implementation is intentionally independent of src/dsh.  It uses elapsed-time
windows and minute support rather than treating sample counts as seconds.
"""
from __future__ import annotations

import argparse
import json
import os
import zipfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

CACHE_ROOT = Path(os.environ["BEWG_PDM_CACHE_DIR"]).expanduser() if "BEWG_PDM_CACHE_DIR" in os.environ else Path.home() / ".cache" / "BEWG_PdM"
DEFAULT_ARCHIVE = CACHE_ROOT / "metropt3" / "metropt3_dataset.zip"
DEFAULT_OUTPUT = Path("results/2026-09-16/codex")

ANALOG = ["TP2", "TP3", "H1", "DV_pressure", "Reservoirs", "Oil_temperature", "Motor_current"]
CONTROL = ["COMP", "DV_eletric", "Towers", "MPG"]
FEATURES = ANALOG + [
    "TP3_minus_Reservoirs",
    "TP3_minus_H1",
    "loaded_fraction_60m",
    "unloaded_fraction_60m",
    "stopped_fraction_60m",
    "switches_60m",
]
STATE_NAMES = {0: "stopped", 1: "unloaded", 2: "loaded"}

FAILURES = [
    ("F1", pd.Timestamp("2020-04-18 00:00:00"), pd.Timestamp("2020-04-18 23:59:00"), "air leak / high stress"),
    ("F2", pd.Timestamp("2020-05-29 23:30:00"), pd.Timestamp("2020-05-30 06:00:00"), "air leak / high stress"),
    ("F3", pd.Timestamp("2020-06-05 10:00:00"), pd.Timestamp("2020-06-07 14:30:00"), "air leak / high stress"),
    ("F4", pd.Timestamp("2020-07-15 14:30:00"), pd.Timestamp("2020-07-15 19:00:00"), "air leak / high stress"),
]

# The 30-Apr record is temporally before F2.  We preserve it verbatim and use it
# as a reset anchor, while flagging this ambiguity in the generated report.
EPOCH_SPECS = [
    ("initial", pd.Timestamp("2020-02-01 00:00:00"), pd.Timestamp("2020-02-01 00:00:00"), pd.Timestamp("2020-02-08 00:00:00"), pd.Timestamp("2020-04-30 12:00:00")),
    ("post_maint_2020-04-30", pd.Timestamp("2020-04-30 12:00:00"), pd.Timestamp("2020-05-01 00:00:00"), pd.Timestamp("2020-05-08 00:00:00"), pd.Timestamp("2020-06-08 16:00:00")),
    ("post_maint_2020-06-08", pd.Timestamp("2020-06-08 16:00:00"), pd.Timestamp("2020-06-09 04:00:00"), pd.Timestamp("2020-06-16 04:00:00"), pd.Timestamp("2020-07-16 00:00:00")),
    ("post_maint_2020-07-16", pd.Timestamp("2020-07-16 00:00:00"), pd.Timestamp("2020-07-16 12:00:00"), pd.Timestamp("2020-07-23 12:00:00"), pd.Timestamp("2020-09-02 00:00:00")),
]

PRIMARY_THRESHOLD = 6.0
QUARANTINE_THRESHOLD = 4.0
QUARANTINE_HOURS = 2.0
HISTORY_DAYS = 14
ENTER_HOLD = pd.Timedelta(minutes=5)
EXIT_HOLD = pd.Timedelta(minutes=10)
EXIT_RATIO = 0.8
COOLDOWN = pd.Timedelta(minutes=30)
MAX_CONTIGUOUS_GAP = pd.Timedelta(minutes=2)
HIT_LEAD = pd.Timedelta(minutes=60)


@dataclass
class RobustModel:
    center: dict[int, np.ndarray]
    scale: dict[int, np.ndarray]
    counts: dict[int, int]


def read_archive(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"archive not found: {path}; run 2026-09-16_00_fetch_metropt3.py")
    with zipfile.ZipFile(path) as zf:
        csv_names = [n for n in zf.namelist() if Path(n).name == "MetroPT3(AirCompressor).csv"]
        if len(csv_names) != 1:
            raise RuntimeError(f"expected one MetroPT CSV, got {csv_names}")
        usecols = ["timestamp", *ANALOG, *CONTROL]
        dtype = {c: "float32" for c in ANALOG + CONTROL}
        with zf.open(csv_names[0]) as fh:
            df = pd.read_csv(fh, usecols=usecols, dtype=dtype)
    df["timestamp"] = pd.to_datetime(df["timestamp"], format="%Y-%m-%d %H:%M:%S", errors="raise")
    df = df.sort_values("timestamp", kind="stable").reset_index(drop=True)
    return df


def make_minute_features(raw: pd.DataFrame) -> pd.DataFrame:
    # Operational state is determined before aggregation.  DV_eletric identifies
    # loaded operation; motor current separates stopped from unloaded operation.
    state = np.where(raw["Motor_current"].to_numpy() < 1.0, 0,
                     np.where((raw["DV_eletric"].to_numpy() >= 0.5) |
                              (raw["Motor_current"].to_numpy() >= 5.5), 2, 1)).astype("int8")
    minute = raw["timestamp"].dt.floor("min")
    work = raw[[*ANALOG]].copy()
    work["minute"] = minute
    work["raw_state"] = state

    med = work.groupby("minute", sort=True)[ANALOG].median()
    counts = pd.crosstab(work["minute"], work["raw_state"]).reindex(columns=[0, 1, 2], fill_value=0)
    counts.columns = ["n_stopped", "n_unloaded", "n_loaded"]
    out = med.join(counts, how="left")
    out["n_raw"] = counts.sum(axis=1).astype("int16")
    out["state"] = counts.to_numpy().argmax(axis=1).astype("int8")
    out["state_purity"] = counts.max(axis=1).to_numpy() / out["n_raw"].to_numpy()
    out["transition"] = (counts.gt(0).sum(axis=1) > 1).to_numpy()

    out["TP3_minus_Reservoirs"] = out["TP3"] - out["Reservoirs"]
    out["TP3_minus_H1"] = out["TP3"] - out["H1"]

    # Time-windowed duty features.  Rolling('60min') is based on timestamps, not
    # row counts, so missing minutes cannot silently turn into elapsed time.
    for code, name in STATE_NAMES.items():
        raw_fraction = counts[f"n_{name}"] / out["n_raw"]
        out[f"{name}_fraction_60m"] = raw_fraction.rolling("60min", min_periods=12).mean()
    prev_state = out["state"].shift(1)
    gap = out.index.to_series().diff()
    switch = ((out["state"] != prev_state) & gap.le(pd.Timedelta(minutes=2))).astype(float)
    out["switches_60m"] = switch.rolling("60min", min_periods=12).sum()
    out["feature_valid"] = out[FEATURES].notna().all(axis=1)
    out["stable"] = (~out["transition"]) & out["feature_valid"] & out["state_purity"].ge(0.999)
    out.index.name = "timestamp"
    return out


def fit_model(rows: pd.DataFrame) -> RobustModel:
    centers: dict[int, np.ndarray] = {}
    scales: dict[int, np.ndarray] = {}
    counts: dict[int, int] = {}
    for state in STATE_NAMES:
        x = rows.loc[(rows["state"] == state) & rows["stable"], FEATURES].to_numpy(dtype="float64")
        if len(x) < 100:
            raise RuntimeError(f"insufficient calibration rows for state={STATE_NAMES[state]}: {len(x)}")
        center = np.nanmedian(x, axis=0)
        q25, q75 = np.nanpercentile(x, [25, 75], axis=0)
        robust_sigma = (q75 - q25) / 1.349
        # A data-resolution floor prevents exact/near-exact digital-like analog
        # values from producing infinite standardized residuals.
        sorted_x = np.sort(x, axis=0)
        positive_diffs = np.diff(sorted_x, axis=0)
        positive_diffs[positive_diffs <= 0] = np.nan
        with np.errstate(all="ignore"):
            resolution = np.nanmedian(positive_diffs, axis=0)
        resolution = np.where(np.isfinite(resolution), resolution, 0.0)
        floor = np.maximum.reduce([np.full_like(center, 1e-4), np.abs(center) * 1e-4, resolution * 2.0])
        scale = np.maximum(robust_sigma, floor)
        centers[state] = center
        scales[state] = scale
        counts[state] = len(x)
    return RobustModel(centers, scales, counts)


def score_rows(rows: pd.DataFrame, model: RobustModel) -> np.ndarray:
    scores = np.full(len(rows), np.nan, dtype="float64")
    stable = rows["stable"].to_numpy()
    states = rows["state"].to_numpy()
    for state in STATE_NAMES:
        mask = stable & (states == state)
        if not mask.any():
            continue
        x = rows.loc[mask, FEATURES].to_numpy(dtype="float64")
        z = np.abs((x - model.center[state]) / model.scale[state])
        z = np.clip(z, 0.0, 50.0)
        # RMS of the three largest standardized deviations: sensitive to a
        # coherent multichannel change but less brittle than max(z).
        top3 = np.partition(z, -3, axis=1)[:, -3:]
        scores[mask] = np.sqrt(np.mean(top3 * top3, axis=1))
    return scores


def quarantine_acceptance(
    times: pd.DatetimeIndex,
    score: np.ndarray,
    stable: np.ndarray,
    quarantine_until: pd.Timestamp,
) -> tuple[np.ndarray, pd.Timestamp]:
    """Select baseline-update rows and carry quarantine across daily batches."""
    accepted = np.zeros(len(times), dtype=bool)
    duration = pd.Timedelta(hours=QUARANTINE_HOURS)
    for i, (t, s, ok) in enumerate(zip(times, score, stable)):
        if not ok or not np.isfinite(s):
            continue
        if s >= QUARANTINE_THRESHOLD:
            if t + duration > quarantine_until:
                quarantine_until = t + duration
            continue
        if t >= quarantine_until:
            accepted[i] = True
    return accepted, quarantine_until


def walk_forward(minutes: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    pieces: list[pd.DataFrame] = []
    audits: list[dict] = []
    max_time = minutes.index.max() + pd.Timedelta(minutes=1)

    for epoch, anchor, calib_start, calib_end, eval_end in EPOCH_SPECS:
        eval_end = min(eval_end, max_time)
        calibration = minutes.loc[(minutes.index >= calib_start) & (minutes.index < calib_end)].copy()
        evaluation = minutes.loc[(minutes.index >= calib_end) & (minutes.index < eval_end)].copy()
        if calibration.empty or evaluation.empty:
            continue
        fixed_calibration = calibration.loc[calibration["stable"]].copy()
        accepted_history = fixed_calibration.iloc[0:0].copy()
        day_start = eval_start = calib_end
        epoch_scored: list[pd.DataFrame] = []
        update_no = 0
        quarantine_until = pd.Timestamp.min

        while day_start < eval_end:
            day_end = min(day_start + pd.Timedelta(days=1), eval_end)
            current = evaluation.loc[(evaluation.index >= day_start) & (evaluation.index < day_end)].copy()
            if current.empty:
                day_start = day_end
                continue
            recent_cut = day_start - pd.Timedelta(days=HISTORY_DAYS)
            recent = accepted_history.loc[accepted_history.index >= recent_cut]
            training = pd.concat([fixed_calibration, recent], axis=0)
            training = training[~training.index.duplicated(keep="last")]
            model = fit_model(training)
            current["score"] = score_rows(current, model)
            accepted_update, quarantine_until = quarantine_acceptance(
                current.index,
                current["score"].to_numpy(),
                current["stable"].to_numpy(),
                quarantine_until,
            )
            current["accepted_update"] = accepted_update
            current["epoch"] = epoch
            current["evaluation"] = True
            epoch_scored.append(current)
            accepted_history = pd.concat([accepted_history, current.loc[current["accepted_update"]]], axis=0)
            update_no += 1
            day_start = day_end

        scored = pd.concat(epoch_scored).sort_index()
        pieces.append(scored)
        audits.append({
            "epoch": epoch,
            "anchor": anchor.isoformat(sep=" "),
            "calibration_start": calib_start.isoformat(sep=" "),
            "calibration_end": calib_end.isoformat(sep=" "),
            "evaluation_end": eval_end.isoformat(sep=" "),
            "calibration_stable_minutes": int(len(fixed_calibration)),
            "evaluation_minutes": int(len(scored)),
            "evaluation_stable_minutes": int(scored["stable"].sum()),
            "accepted_update_minutes": int(scored["accepted_update"].sum()),
            "daily_updates": update_no,
        })

    all_scored = pd.concat(pieces).sort_index()
    return all_scored, audits


def eventize(scored: pd.DataFrame, threshold: float) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Convert a minute-score stream to alarm events using the frozen state machine.

    Holds and cooldown are counted in score rows (one row = one minute in the
    protocol stream).  An event starts on the fifth consecutive score above the
    threshold.  While active, ten consecutive scores below 0.8 * threshold are
    included in the event; it ends immediately after the tenth low row.  The
    following 30 rows are a frozen cooldown with the entry counter held at zero.
    """
    events: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    active = False
    enter_count = 0
    exit_count = 0
    cooldown_remaining = 0
    alarm_start: pd.Timestamp | None = None
    last_time: pd.Timestamp | None = None
    prev_epoch: str | None = None
    enter_samples = int(ENTER_HOLD / pd.Timedelta(minutes=1))
    exit_samples = int(EXIT_HOLD / pd.Timedelta(minutes=1))
    cooldown_samples = int(COOLDOWN / pd.Timedelta(minutes=1))

    for t, row in scored.iterrows():
        epoch = str(row["epoch"])
        eligible = bool(row["stable"]) and np.isfinite(row["score"])
        value = float(row["score"]) if eligible else np.nan
        high = eligible and value > threshold
        low = eligible and value < EXIT_RATIO * threshold

        # Maintenance/walk-forward epochs remain hard reset boundaries.  Missing
        # clock minutes inside an epoch do not create a second event-machine
        # convention: the protocol counts rows in the supplied minute stream.
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
                    event_end = t + pd.Timedelta(minutes=1)
                    events.append((alarm_start, event_end))
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


def in_failure(t: pd.Timestamp) -> bool:
    return any(start <= t <= end for _, start, end, _ in FAILURES)


def evaluate(scored: pd.DataFrame, threshold: float) -> tuple[dict, list[dict], list[tuple[pd.Timestamp, pd.Timestamp]]]:
    alarms = eventize(scored, threshold)
    event_rows: list[dict] = []
    hit_alarm_indexes: set[int] = set()
    delays: list[float] = []

    for event_id, start, end, fault in FAILURES:
        candidates = [(i, a, b) for i, (a, b) in enumerate(alarms) if start - HIT_LEAD <= a <= end]
        if candidates:
            i, onset, alarm_end = min(candidates, key=lambda x: x[1])
            hit_alarm_indexes.add(i)
            delay = (onset - start).total_seconds() / 60.0
            delays.append(delay)
            hit = 1
            onset_text = onset.isoformat(sep=" ")
            alarm_end_text = alarm_end.isoformat(sep=" ")
        else:
            hit = 0
            delay = np.nan
            onset_text = ""
            alarm_end_text = ""
        eligible_event = scored.loc[(scored.index >= start) & (scored.index <= end), "stable"].sum()
        event_rows.append({
            "event_id": event_id,
            "truth_start": start.isoformat(sep=" "),
            "truth_end": end.isoformat(sep=" "),
            "fault": fault,
            "threshold": threshold,
            "hit": hit,
            "alarm_onset": onset_text,
            "alarm_end": alarm_end_text,
            "delay_minutes": delay,
            "eligible_event_minutes": int(eligible_event),
        })

    false_count = sum(1 for i in range(len(alarms)) if i not in hit_alarm_indexes)
    eligible = scored["stable"].to_numpy() & np.isfinite(scored["score"].to_numpy())
    healthy = np.array([not in_failure(t) for t in scored.index], dtype=bool)
    healthy_eligible = eligible & healthy

    alarm_mask = np.zeros(len(scored), dtype=bool)
    times = scored.index
    for start, end in alarms:
        alarm_mask |= (times >= start) & (times < end)
    healthy_minutes = int(healthy_eligible.sum())
    healthy_alarm_minutes = int((healthy_eligible & alarm_mask).sum())
    healthy_hours = healthy_minutes / 60.0
    hits = sum(r["hit"] for r in event_rows)
    metrics = {
        "threshold": threshold,
        "truth_events": len(FAILURES),
        "hit_events": hits,
        "event_recall": hits / len(FAILURES),
        "alarm_events": len(alarms),
        "false_alarm_events": false_count,
        "healthy_minutes": healthy_minutes,
        "healthy_hours": healthy_hours,
        "false_alarm_events_per_healthy_hour": false_count / healthy_hours if healthy_hours else np.nan,
        "healthy_alarm_minutes": healthy_alarm_minutes,
        "TIA_H": healthy_alarm_minutes / healthy_minutes if healthy_minutes else np.nan,
        "median_delay_minutes": float(np.median(delays)) if delays else np.nan,
    }
    return metrics, event_rows, alarms


def write_report(output: Path, raw: pd.DataFrame, minutes: pd.DataFrame, scored: pd.DataFrame,
                 audits: list[dict], primary: dict, event_rows: list[dict], det: pd.DataFrame,
                 archive: Path) -> None:
    state_counts = scored.loc[scored["stable"], "state"].value_counts().to_dict()
    best_recall = det[det["event_recall"] == det["event_recall"].max()].copy()
    best_recall = best_recall.sort_values(["false_alarm_events_per_healthy_hour", "TIA_H", "threshold"]).iloc[0]
    lines = [
        "# MetroPT-3 工况条件化 walk-forward 基线（探索性，2026-09-16）",
        "",
        "## 可复现命令",
        "",
        "```powershell",
        "python src/codex/2026-09-16_00_fetch_metropt3.py",
        "python src/codex/2026-09-16_01_metropt3_baseline.py",
        "```",
        "",
        f"- 输入归档：`{archive}`",
        f"- 原始行数：{len(raw):,}；分钟桶数：{len(minutes):,}；进入评估的分钟桶数：{len(scored):,}。",
        f"- 原始时间范围：{raw['timestamp'].min()} 至 {raw['timestamp'].max()}。",
        "",
        "## 方法定义",
        "",
        "1. **时间窗口**：原始记录先按自然分钟聚合；职责周期特征使用 pandas `rolling('60min')`，不是固定点数。每个可用分钟按 1 分钟观测支持计入分母，数据缺口不补时长。",
        "2. **工况条件化**：`Motor_current < 1 A` 为停机；否则 `DV_eletric=1` 或 `Motor_current>=5.5 A` 为加载；其余为卸载。含多种原始状态的分钟标作切换并完全排除告警与健康分母。",
        "3. **特征/分数**：7 个模拟量、`TP3-Reservoirs`、`TP3-H1`、60 分钟三状态占比和切换次数；每个工况分别做 median/IQR 鲁棒标准化，分数为最大三个 |z| 的 RMS。",
        "4. **标定**：初始段固定为 2020-02-01 至 02-08（无此前维护记录，明确是部署回退）；维护锚点后等待 12 小时，再取固定 7 天健康标定。锚点为官方资料中的 2020-04-30 12:00、2020-06-08 16:00、2020-07-16 00:00。",
        "5. **walk-forward**：每 24 小时仅用过去数据重估；固定标定集加过去 14 天获准更新样本。分数>=4 的分钟触发 2 小时 quarantine，候选及 quarantine 内样本不更新模型。",
        "6. **事件状态机**：连续高分满 5 分钟并以第 5 分钟为起点，连续低于 0.8×阈值满 10 分钟退出，退出后冷却 30 分钟；全部是经过时间规则。主工作点阈值预先固定为 6.0。",
        "7. **命中**：因官方标签是粗时间区间，告警起点落在 `[故障开始-60min, 故障结束]` 才命中；延迟可为负（提前预警）。持续很久并在更早开始的告警不会自动并入故障。",
        "8. **健康指标**：独立误报事件按未匹配真值的告警事件计数；TIA-H 是健康、稳定、可评估分钟中的告警占比。二者必须成对报告。",
        "",
        "## 主工作点结果（threshold=6.0）",
        "",
        f"- 事件召回：{primary['hit_events']}/{primary['truth_events']} = {primary['event_recall']:.3f}",
        f"- 独立误报事件：{primary['false_alarm_events']}；健康小时：{primary['healthy_hours']:.3f}；误报事件/健康小时：{primary['false_alarm_events_per_healthy_hour']:.6f}",
        f"- TIA-H：{primary['healthy_alarm_minutes']}/{primary['healthy_minutes']} = {primary['TIA_H']:.6f}",
        f"- 命中事件延迟中位数：{primary['median_delay_minutes']:.3f} 分钟" if np.isfinite(primary["median_delay_minutes"]) else "- 命中事件延迟中位数：N/A（无命中）",
        "",
        "逐事件：",
        "",
        "|事件|真值区间|命中|告警起点|延迟(min)|事件内可评估分钟|",
        "|---|---|---:|---|---:|---:|",
    ]
    for r in event_rows:
        delay = "" if not np.isfinite(r["delay_minutes"]) else f"{r['delay_minutes']:.3f}"
        lines.append(f"|{r['event_id']}|{r['truth_start']} — {r['truth_end']}|{r['hit']}|{r['alarm_onset']}|{delay}|{r['eligible_event_minutes']}|")
    lines += [
        "",
        "## DET 扫描",
        "",
        f"- 扫描点数：{len(det)}；完整数据见 `metropt3_det.csv`。",
        f"- 扫描中的最大召回工作点（同召回下先取最低误报率）：threshold={best_recall['threshold']:.3f}，recall={best_recall['event_recall']:.3f}，false events/healthy hour={best_recall['false_alarm_events_per_healthy_hour']:.6f}，TIA-H={best_recall['TIA_H']:.6f}。",
        "- 只有 4 个粗粒度故障事件，召回率步长为 0.25；该 DET 只能作探索性第二数据集，不应解释成稳定总体性能。",
        "- 事件召回不保证随阈值单调：低阈值可能让告警过早开始或把多个时段合并，起点落到 −60 分钟命中窗之外；TIA-H 会同时暴露这种长期告警。",
        "",
        "## 标定/状态审计",
        "",
        f"- 稳定评估分钟按工况：stopped={state_counts.get(0, 0)}，unloaded={state_counts.get(1, 0)}，loaded={state_counts.get(2, 0)}。",
        "- 各 epoch 的标定、评估、更新计数见 `metropt3_epoch_audit.csv`。",
        "- 2020-04-30 12:00 维护记录早于 F2（2020-05-29）；本实现不改写原始资料，只把它解释为 F1 后的维护重置锚点。这一解释仍需数据方确认。",
        "",
        "## 与 SKAB 口径的差异",
        "",
        "- SKAB 是 1 Hz、逐文件、点标签扩展的协议；MetroPT-3 约 0.1 Hz 且时间轴有缺口，因此本实现使用自然时间滚动、分钟观测支持和跨月 walk-forward。",
        "- SKAB 的标定窗由每个短文件的位置给出；MetroPT-3 用明确日期的初始健康段/维护后健康段，并在维护后重置。",
        "- MetroPT-3 真值是公司报告的粗故障区间，不是逐点异常标签；因此命中使用 60 分钟提前窗，延迟以分钟计，且允许负值。",
        "- 工况切换分钟在 MetroPT-3 中从告警和健康分母同时排除；不能把压力/电流的正常模态切换当故障。",
        "- 两套数据都同时报告独立误报事件率与 TIA-H，避免‘一直报警只有一个事件’的刷分漏洞。",
        "",
        "## 限制",
        "",
        "- 这是单一鲁棒距离基线，不是已冻结协议；状态阈值、60 分钟命中窗和维护解释均需双方复核后才能冻结。",
        "- 维修后的 7 天仅依据公开故障表中没有重叠故障来视作确认健康；原始资料没有逐分钟维修验收标签。",
        "- 分钟聚合会丢失秒级瞬态，但与约 10 秒采样间隔和粗故障标签相匹配。",
        "",
        "## 机器可读参数",
        "",
        "```json",
        json.dumps({
            "primary_threshold": PRIMARY_THRESHOLD,
            "quarantine_threshold": QUARANTINE_THRESHOLD,
            "quarantine_hours": QUARANTINE_HOURS,
            "history_days": HISTORY_DAYS,
            "enter_hold_minutes": ENTER_HOLD.total_seconds() / 60,
            "exit_hold_minutes": EXIT_HOLD.total_seconds() / 60,
            "exit_ratio": EXIT_RATIO,
            "cooldown_minutes": COOLDOWN.total_seconds() / 60,
            "hit_lead_minutes": HIT_LEAD.total_seconds() / 60,
            "features": FEATURES,
        }, ensure_ascii=False, indent=2),
        "```",
    ]
    (output / "metropt3_baseline.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--primary-threshold", type=float, default=PRIMARY_THRESHOLD)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)

    print(f"reading {args.archive}", flush=True)
    raw = read_archive(args.archive.resolve())
    print(f"raw rows={len(raw):,}", flush=True)
    minutes = make_minute_features(raw)
    print(f"minute buckets={len(minutes):,}", flush=True)
    scored, audits = walk_forward(minutes)
    print(f"evaluated minute buckets={len(scored):,}", flush=True)

    thresholds = sorted(set([args.primary_threshold, *np.arange(2.0, 15.01, 0.5).tolist(), 18.0, 22.0, 30.0]))
    det_rows = []
    primary_metrics = None
    primary_events = None
    primary_alarms = None
    for threshold in thresholds:
        metrics, event_rows, alarms = evaluate(scored, float(threshold))
        det_rows.append(metrics)
        if abs(threshold - args.primary_threshold) < 1e-12:
            primary_metrics, primary_events, primary_alarms = metrics, event_rows, alarms
    assert primary_metrics is not None and primary_events is not None and primary_alarms is not None

    pd.DataFrame(primary_events).to_csv(output / "metropt3_baseline.csv", index=False, encoding="utf-8-sig")
    det = pd.DataFrame(det_rows).sort_values("threshold")
    det.to_csv(output / "metropt3_det.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(audits).to_csv(output / "metropt3_epoch_audit.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(primary_alarms, columns=["alarm_start", "alarm_end"]).to_csv(
        output / "metropt3_primary_alarm_events.csv", index=False, encoding="utf-8-sig"
    )
    compact = scored[["state", "state_purity", "transition", "stable", "score", "accepted_update", "epoch"]].copy()
    compact.to_csv(output / "metropt3_scored_minutes.csv.gz", compression="gzip", encoding="utf-8-sig")
    write_report(output, raw, minutes, scored, audits, primary_metrics, primary_events, det, args.archive.resolve())

    print(json.dumps(primary_metrics, ensure_ascii=False, indent=2), flush=True)
    print(f"outputs={output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())





