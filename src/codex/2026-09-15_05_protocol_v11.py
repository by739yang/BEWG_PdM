"""Independent blind-run implementation of frozen SKAB PROTOCOL_v1.1.

Implements F0, F2, F3, the event state machine, event metrics, and DET scan.
This implementation is based only on docs/PROTOCOL_v1.1.md and raw SKAB CSVs.
"""
from __future__ import annotations

import argparse
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA

CAL_START = 120
CAL_END_FIXED = 480
MIN_CAL = 300
SCALER_WINDOW = 120
FEATURE_WINDOW = 60
CONSEC_IN = 10
CONSEC_OUT = 30
EXIT_RATIO = 0.8
COOLDOWN = 300
MIN_TRUE_EVENT = 60
HIT_LEAD = 60
DET_QUANTILES = (0.90, 0.99, 0.995, 0.999)
MAIN_QUANTILE = 0.995
GROUPS = ("valve1", "valve2", "other")
LABEL_COLUMNS = {"datetime", "anomaly", "changepoint"}
STAT_NAMES = ("last", "mean", "std", "min", "max", "slope")


@dataclass(frozen=True)
class AlarmEvent:
    start: int
    end: int


@dataclass
class FileScores:
    file: str
    n: int
    cal_start: int
    cal_end: int
    cal_n: int
    flagged: int
    cal_anomaly_samples: int
    anomaly: np.ndarray
    scores: dict[str, np.ndarray]
    pca_components: int | None


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-root",
        type=Path,
        default=repo_root / "data" / "SKAB-master" / "data",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repo_root / "results" / "2026-09-15" / "codex",
    )
    return parser.parse_args()


def linear_quantile(values: np.ndarray, q: float) -> float:
    finite = np.asarray(values, dtype=np.float64)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        raise ValueError("Cannot calculate a threshold from zero finite scores")
    return float(np.quantile(finite, q, method="linear"))


def causal_robust_z(x: np.ndarray) -> np.ndarray:
    """Section 2: strictly causal rolling median/IQR standardization."""
    n, d = x.shape
    z = np.zeros((n, d), dtype=np.float64)
    for t in range(1, n):
        lo = max(0, t - SCALER_WINDOW)
        win = x[lo:t]
        med = np.median(win, axis=0)
        q25, q75 = np.quantile(win, (0.25, 0.75), axis=0, method="linear")
        scale = np.maximum.reduce(
            (
                (q75 - q25) / 1.349,
                0.02 * np.abs(med),
                np.full(d, 1e-9, dtype=np.float64),
            )
        )
        z[t] = (x[t] - med) / scale
    return z


def ols_slope(window: np.ndarray) -> np.ndarray:
    """Per-column OLS slope with intercept against integer seconds 0..m-1."""
    m = window.shape[0]
    if m <= 1:
        return np.zeros(window.shape[1], dtype=np.float64)
    time = np.arange(m, dtype=np.float64)
    centered_time = time - time.mean()
    denominator = float(np.dot(centered_time, centered_time))
    return centered_time @ window / denominator


def make_features(z: np.ndarray) -> np.ndarray:
    """Section 3: 8 signals x six statistics, signal-major order."""
    n, d = z.shape
    features = np.empty((n, d * len(STAT_NAMES)), dtype=np.float64)
    for t in range(n):
        lo = max(0, t - (FEATURE_WINDOW - 1))
        win = z[lo : t + 1]
        stats = np.column_stack(
            (
                win[-1],
                win.mean(axis=0),
                win.std(axis=0, ddof=0),
                win.min(axis=0),
                win.max(axis=0),
                ols_slope(win),
            )
        )
        features[t] = stats.reshape(-1)
    return features


def score_f0(z: np.ndarray) -> np.ndarray:
    return np.max(np.abs(z), axis=1)


def score_f2(features: np.ndarray, cal_start: int, cal_end: int) -> tuple[np.ndarray, int]:
    pca = PCA(n_components=0.90, svd_solver="full")
    pca.fit(features[cal_start:cal_end])
    reconstructed = pca.inverse_transform(pca.transform(features))
    scores = np.linalg.norm(features - reconstructed, axis=1)
    return scores, int(pca.n_components_)


def score_f3(z: np.ndarray) -> np.ndarray:
    n, _ = z.shape
    scores = np.full(n, np.nan, dtype=np.float64)
    for t in range(CAL_START, n):
        a = z[max(0, t - 360) : t - 60]
        b = z[t - 60 : t]
        if len(a) < 1 or len(b) < 1:
            raise AssertionError(f"F3 received an empty window at t={t}")
        numerator = np.abs(a.mean(axis=0) - b.mean(axis=0))
        denominator = a.std(axis=0, ddof=0) + b.std(axis=0, ddof=0) + 1e-3
        scores[t] = np.max(numerator / denominator)
    return scores


def run_state_machine(scores: np.ndarray, eval_start: int, threshold: float) -> list[AlarmEvent]:
    """Section 6, with half-open alarm intervals."""
    n = len(scores)
    events: list[AlarmEvent] = []
    in_alarm = False
    above_run = 0
    below_run = 0
    cooldown_until = eval_start
    event_start: int | None = None

    for t in range(eval_start, n):
        score = scores[t]
        if not np.isfinite(score):
            raise ValueError(f"Non-finite evaluation score at t={t}")

        if in_alarm:
            if score < EXIT_RATIO * threshold:
                below_run += 1
            else:
                below_run = 0
            if below_run >= CONSEC_OUT:
                event_end = t + 1
                assert event_start is not None
                events.append(AlarmEvent(event_start, event_end))
                in_alarm = False
                event_start = None
                above_run = 0
                below_run = 0
                cooldown_until = event_end + COOLDOWN
            continue

        if t < cooldown_until:
            above_run = 0
            continue

        if score > threshold:
            above_run += 1
        else:
            above_run = 0

        if above_run >= CONSEC_IN:
            in_alarm = True
            event_start = t
            above_run = 0
            below_run = 0

    if in_alarm:
        assert event_start is not None
        events.append(AlarmEvent(event_start, n))

    for event in events:
        if not (eval_start <= event.start < event.end <= n):
            raise AssertionError(f"Invalid event interval: {event}")
    return events


def contiguous_true_events(anomaly: np.ndarray, eval_start: int) -> list[tuple[int, int]]:
    """Clip truth to eval first, then retain runs of length >=60."""
    y = np.asarray(anomaly, dtype=np.int8)
    mask = y[eval_start:] == 1
    padded = np.r_[False, mask, False]
    changes = np.flatnonzero(padded[1:] != padded[:-1])
    events: list[tuple[int, int]] = []
    for start_rel, end_rel in changes.reshape(-1, 2):
        start = eval_start + int(start_rel)
        end = eval_start + int(end_rel)
        if end - start >= MIN_TRUE_EVENT:
            events.append((start, end))
    return events


def evaluate_events(
    events: list[AlarmEvent], anomaly: np.ndarray, eval_start: int
) -> tuple[dict[str, object], list[dict[str, object]]]:
    n = len(anomaly)
    truth = contiguous_true_events(anomaly, eval_start)
    alarm_mask = np.zeros(n, dtype=bool)
    for event in events:
        alarm_mask[event.start : event.end] = True

    hit_alarm_indices: set[int] = set()
    delays: list[int] = []
    truth_hits = 0
    for g0, g1 in truth:
        lower = max(eval_start, g0 - HIT_LEAD)
        candidates = [i for i, event in enumerate(events) if lower <= event.start < g1]
        if candidates:
            truth_hits += 1
            hit_alarm_indices.update(candidates)
            earliest_start = min(events[i].start for i in candidates)
            delays.append(earliest_start - g0)

    false_indices = [
        i
        for i, event in enumerate(events)
        if i not in hit_alarm_indices and anomaly[event.start] == 0
    ]

    too_early_indices: set[int] = set()
    for i, event in enumerate(events):
        for g0, g1 in truth:
            if event.start < g0 - HIT_LEAD and event.start < g1 and event.end > g0:
                too_early_indices.add(i)
                break

    eval_healthy = anomaly[eval_start:] == 0
    healthy_samples = int(eval_healthy.sum())
    alarm_healthy_samples = int((alarm_mask[eval_start:] & eval_healthy).sum())

    metrics: dict[str, object] = {
        "true_event_count": len(truth),
        "hit_event_count": truth_hits,
        "alarm_event_count": len(events),
        "false_alarm_event_count": len(false_indices),
        "healthy_samples": healthy_samples,
        "alarm_healthy_samples": alarm_healthy_samples,
        "event_recall": truth_hits / len(truth) if truth else np.nan,
        "false_alarm_events_per_healthy_hour": (
            len(false_indices) / (healthy_samples / 3600.0) if healthy_samples else np.nan
        ),
        "tia_h": alarm_healthy_samples / healthy_samples if healthy_samples else np.nan,
        "median_delay_s": float(np.median(delays)) if delays else np.nan,
        "too_early_overlap_count": len(too_early_indices),
        "delays": delays,
    }

    event_rows: list[dict[str, object]] = []
    for i, event in enumerate(events):
        event_rows.append(
            {
                "alarm_event_id": i,
                "t_start": event.start,
                "t_end": event.end,
                "duration_samples": event.end - event.start,
                "start_label": int(anomaly[event.start]),
                "belongs_to_any_hit": int(i in hit_alarm_indices),
                "is_false_alarm_event": int(i in false_indices),
                "too_early_overlap": int(i in too_early_indices),
            }
        )
    return metrics, event_rows


def discover_files(data_root: Path) -> list[Path]:
    files = sorted(path for group in GROUPS for path in (data_root / group).glob("*.csv"))
    if len(files) != 34:
        raise RuntimeError(f"Expected 34 labeled SKAB files, found {len(files)}")
    return files


def prepare_file(path: Path, data_root: Path) -> FileScores:
    frame = pd.read_csv(path, sep=";")
    sensor_columns = [column for column in frame.columns if column not in LABEL_COLUMNS]
    if len(sensor_columns) != 8:
        raise RuntimeError(f"Expected 8 sensor columns in {path}, got {sensor_columns}")

    x = frame[sensor_columns].to_numpy(dtype=np.float64)
    anomaly = frame["anomaly"].to_numpy(dtype=np.int8)
    if not np.isfinite(x).all():
        raise ValueError(f"Non-finite sensor value in {path}")
    if not np.isin(anomaly, (0, 1)).all():
        raise ValueError(f"Non-binary anomaly label in {path}")

    n = len(frame)
    cal_end = min(CAL_END_FIXED, n)
    cal_n = cal_end - CAL_START
    if cal_n < MIN_CAL:
        return FileScores(
            file=path.relative_to(data_root).as_posix(),
            n=n,
            cal_start=CAL_START,
            cal_end=cal_end,
            cal_n=cal_n,
            flagged=int(anomaly[CAL_START:cal_end].sum() > 0),
            cal_anomaly_samples=int(anomaly[CAL_START:cal_end].sum()),
            anomaly=anomaly,
            scores={},
            pca_components=None,
        )

    z = causal_robust_z(x)
    features = make_features(z)
    f2_scores, pca_components = score_f2(features, CAL_START, cal_end)
    scores = {
        "F0": score_f0(z),
        "F2": f2_scores,
        "F3": score_f3(z),
    }
    for method, method_scores in scores.items():
        if not np.isfinite(method_scores[CAL_START:]).all():
            raise ValueError(f"Non-finite {method} score from calibration onward in {path}")

    cal_anomaly_samples = int(anomaly[CAL_START:cal_end].sum())
    return FileScores(
        file=path.relative_to(data_root).as_posix(),
        n=n,
        cal_start=CAL_START,
        cal_end=cal_end,
        cal_n=cal_n,
        flagged=int(cal_anomaly_samples > 0),
        cal_anomaly_samples=cal_anomaly_samples,
        anomaly=anomaly,
        scores=scores,
        pca_components=pca_components,
    )


def aggregate_rows(rows: Iterable[dict[str, object]]) -> dict[str, object]:
    rows = list(rows)
    total_truth = int(sum(int(row["true_event_count"]) for row in rows))
    total_hits = int(sum(int(row["hit_event_count"]) for row in rows))
    total_false = int(sum(int(row["false_alarm_event_count"]) for row in rows))
    total_healthy = int(sum(int(row["healthy_samples"]) for row in rows))
    total_alarm_healthy = int(sum(int(row["alarm_healthy_samples"]) for row in rows))
    all_delays = [delay for row in rows for delay in row["_delays"]]  # type: ignore[index]
    return {
        "file_count": len(rows),
        "true_event_count": total_truth,
        "hit_event_count": total_hits,
        "false_alarm_event_count": total_false,
        "healthy_samples": total_healthy,
        "alarm_healthy_samples": total_alarm_healthy,
        "event_recall": total_hits / total_truth if total_truth else np.nan,
        "false_alarm_events_per_healthy_hour": (
            total_false / (total_healthy / 3600.0) if total_healthy else np.nan
        ),
        "tia_h": total_alarm_healthy / total_healthy if total_healthy else np.nan,
        "median_delay_s": float(np.median(all_delays)) if all_delays else np.nan,
    }


def run_internal_checks() -> None:
    """Deterministic synthetic checks for frozen state-machine/metric boundaries."""
    scores = np.zeros(80, dtype=np.float64)
    scores[10:20] = 2.0
    events = run_state_machine(scores, eval_start=10, threshold=1.0)
    assert [(event.start, event.end) for event in events] == [(19, 50)]

    scores = np.zeros(380, dtype=np.float64)
    scores[10:20] = 2.0
    scores[50:360] = 2.0
    events = run_state_machine(scores, eval_start=10, threshold=1.0)
    assert [(event.start, event.end) for event in events] == [(19, 50), (359, 380)]

    anomaly = np.zeros(400, dtype=np.int8)
    anomaly[200:300] = 1
    metrics, _ = evaluate_events([AlarmEvent(100, 250)], anomaly, eval_start=0)
    assert metrics["hit_event_count"] == 0
    assert metrics["false_alarm_event_count"] == 1
    assert metrics["too_early_overlap_count"] == 1

    metrics, _ = evaluate_events([AlarmEvent(140, 180)], anomaly, eval_start=0)
    assert metrics["hit_event_count"] == 1
    assert metrics["false_alarm_event_count"] == 0
    assert metrics["median_delay_s"] == -60.0


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fmt_rate(value: object, percent: bool = False) -> str:
    if value is None or pd.isna(value):
        return "NA"
    number = float(value)
    return f"{100 * number:.2f}%" if percent else f"{number:.4f}"


def run() -> None:
    run_internal_checks()
    args = parse_args()
    data_root = args.data_root.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    repo_root = Path(__file__).resolve().parents[2]
    protocol_path = repo_root / "docs" / "PROTOCOL_v1.1.md"

    prepared = [prepare_file(path, data_root) for path in discover_files(data_root)]
    eligible = [item for item in prepared if item.cal_n >= MIN_CAL]
    insufficient = [item for item in prepared if item.cal_n < MIN_CAL]

    per_method_rows: dict[str, list[dict[str, object]]] = {method: [] for method in ("F0", "F2", "F3")}
    det_rows: list[dict[str, object]] = []
    all_event_rows: list[dict[str, object]] = []

    for method in ("F0", "F2", "F3"):
        rows_by_q: dict[float, list[dict[str, object]]] = {q: [] for q in DET_QUANTILES}
        for item in eligible:
            scores = item.scores[method]
            for q in DET_QUANTILES:
                threshold = linear_quantile(scores[item.cal_start : item.cal_end], q)
                events = run_state_machine(scores, item.cal_end, threshold)
                metrics, event_rows = evaluate_events(events, item.anomaly, item.cal_end)
                row: dict[str, object] = {
                    "method": method,
                    "q": q,
                    "file": item.file,
                    "status": "ok",
                    "N": item.n,
                    "cal_start": item.cal_start,
                    "cal_end": item.cal_end,
                    "cal_n": item.cal_n,
                    "eval_start": item.cal_end,
                    "eval_n": item.n - item.cal_end,
                    "flagged": item.flagged,
                    "cal_anomaly_samples": item.cal_anomaly_samples,
                    "threshold": threshold,
                    "pca_components": item.pca_components if method == "F2" else np.nan,
                    **{key: value for key, value in metrics.items() if key != "delays"},
                    "_delays": metrics["delays"],
                }
                rows_by_q[q].append(row)

                for event_row in event_rows:
                    all_event_rows.append(
                        {
                            "method": method,
                            "q": q,
                            "file": item.file,
                            "threshold": threshold,
                            **event_row,
                        }
                    )

        for q in DET_QUANTILES:
            aggregate = aggregate_rows(rows_by_q[q])
            det_rows.append({"method": method, "q": q, **aggregate})

        main_rows = rows_by_q[MAIN_QUANTILE]
        for row in main_rows:
            clean = {key: value for key, value in row.items() if key != "_delays"}
            per_method_rows[method].append(clean)

        for item in insufficient:
            per_method_rows[method].append(
                {
                    "method": method,
                    "q": MAIN_QUANTILE,
                    "file": item.file,
                    "status": "insufficient-cal",
                    "N": item.n,
                    "cal_start": item.cal_start,
                    "cal_end": item.cal_end,
                    "cal_n": item.cal_n,
                    "eval_start": item.cal_end,
                    "eval_n": item.n - item.cal_end,
                    "flagged": item.flagged,
                    "cal_anomaly_samples": item.cal_anomaly_samples,
                }
            )

    for method, rows in per_method_rows.items():
        pd.DataFrame(rows).sort_values("file").to_csv(
            output_dir / f"protocol_v11_{method}.csv", index=False, encoding="utf-8-sig"
        )

    det_frame = pd.DataFrame(det_rows).sort_values(["method", "q"])
    det_frame.to_csv(output_dir / "protocol_v11_det.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(all_event_rows).sort_values(["method", "q", "file", "alarm_event_id"]).to_csv(
        output_dir / "protocol_v11_events.csv", index=False, encoding="utf-8-sig"
    )

    main_aggregate = det_frame[np.isclose(det_frame["q"], MAIN_QUANTILE)].copy()
    if main_aggregate["true_event_count"].nunique() != 1:
        raise AssertionError("Methods disagree on the frozen truth-event denominator")
    if main_aggregate["healthy_samples"].nunique() != 1:
        raise AssertionError("Methods disagree on the frozen healthy-sample denominator")
    no_truth_files = [
        str(row["file"])
        for row in per_method_rows["F0"]
        if row.get("status") == "ok" and int(row["true_event_count"]) == 0
    ]
    summary_lines = [
        "# PROTOCOL_v1.1 Codex 独立盲跑结果",
        "",
        "> 盲跑纪律：本实现及本报告生成前未读取 DSH 的实现或 `protocol_v11_*` 结果。",
        "",
        "## 复现信息",
        "",
        f"- 协议：`docs/PROTOCOL_v1.1.md`",
        f"- 协议 SHA-256：`{sha256(protocol_path)}`",
        f"- 脚本：`src/codex/2026-09-15_05_protocol_v11.py`",
        f"- 脚本 SHA-256：`{sha256(Path(__file__).resolve())}`",
        "- 命令：`python src/codex/2026-09-15_05_protocol_v11.py`",
        f"- 数据：SKAB 带标签文件 {len(prepared)} 个；主表纳入 {len(eligible)} 个；insufficient-cal {len(insufficient)} 个",
        f"- flagged 文件数：{sum(item.flagged for item in eligible)}",
        "- 内置状态机与命中窗边界自检：PASS",
        f"- eval 裁剪后无长度≥60真值事件的文件：{', '.join(no_truth_files) if no_truth_files else '无'}",
        "- `other/2.csv` 原真值为 `[104,488)`；eval 从 480 开始后仅余 8 点，按第 7 节被过滤，因此主汇总真值分母为 33。",
        "",
        "## 主阈值 q=0.995 汇总",
        "",
        "| 方法 | 文件 | 命中/真值 | 事件召回 | 误报事件 | 健康样本 | 误报事件/健康小时 | 报警健康样本 | TIA-H | 延迟中位(s) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, row in main_aggregate.iterrows():
        summary_lines.append(
            f"| {row['method']} | {int(row['file_count'])} | "
            f"{int(row['hit_event_count'])}/{int(row['true_event_count'])} | "
            f"{fmt_rate(row['event_recall'], percent=True)} | "
            f"{int(row['false_alarm_event_count'])} | {int(row['healthy_samples'])} | "
            f"{fmt_rate(row['false_alarm_events_per_healthy_hour'])} | "
            f"{int(row['alarm_healthy_samples'])} | {fmt_rate(row['tia_h'], percent=True)} | "
            f"{fmt_rate(row['median_delay_s'])} |"
        )

    summary_lines.extend(
        [
            "",
            "## DET 扫描",
            "",
            "| 方法 | q | 命中/真值 | 事件召回 | 误报事件 | 健康样本 | 误报事件/健康小时 | 报警健康样本 | TIA-H | 延迟中位(s) |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for _, row in det_frame.iterrows():
        summary_lines.append(
            f"| {row['method']} | {row['q']:.3f} | "
            f"{int(row['hit_event_count'])}/{int(row['true_event_count'])} | "
            f"{fmt_rate(row['event_recall'], percent=True)} | "
            f"{int(row['false_alarm_event_count'])} | {int(row['healthy_samples'])} | "
            f"{fmt_rate(row['false_alarm_events_per_healthy_hour'])} | "
            f"{int(row['alarm_healthy_samples'])} | {fmt_rate(row['tia_h'], percent=True)} | "
            f"{fmt_rate(row['median_delay_s'])} |"
        )

    summary_lines.extend(
        [
            "",
            "## 实现口径",
            "",
            "- F0 直接使用逐时刻八路因果稳健 z 的最大绝对值。",
            "- F2 使用 48 维原特征、PCA 自带中心化，不做二次缩放；SPE 是原坐标重构残差 L2。",
            "- F3 使用冻结的 A/B 历史窗，当前样本不进入 B；从 t=120 起打分。",
            "- 状态机仅从 eval_start 开始；事件起点是第 10 个越限点，事件终点包含第 30 个退出确认点。",
            "- 真值先裁到 eval，再过滤不足 60 秒的片段；汇总率由跨文件总分子/总分母计算。",
            "",
            "## 输出文件",
            "",
            "- `protocol_v11_F0.csv`、`protocol_v11_F2.csv`、`protocol_v11_F3.csv`：q=0.995 逐文件结果。",
            "- `protocol_v11_det.csv`：三个方法、四个阈值的跨文件 DET 汇总。",
            "- `protocol_v11_events.csv`：所有方法和阈值的告警事件明细及归因。",
            "",
            "## 盲比状态",
            "",
            "本报告只给 Codex 侧结果；尚未读取 DSH 侧数字。双方亮数后先比逐文件整数计数和样本分母，再执行第 8 节 10% 判据。",
            "",
        ]
    )
    (output_dir / "protocol_v11_summary.md").write_text("\n".join(summary_lines), encoding="utf-8")

    print(main_aggregate.to_string(index=False))
    print(f"\nWrote outputs to: {output_dir}")


if __name__ == "__main__":
    run()

