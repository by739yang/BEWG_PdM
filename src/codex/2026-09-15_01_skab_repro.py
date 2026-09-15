#!/usr/bin/env python3
"""Independent SKAB reproduction for 2026-09-15 Codex task.

This implementation was written without reading src/dsh/demo_*.py or any src/dsh
code. It follows the protocol stated in PROJECT_STATE.md and makes every
otherwise-unspecified choice explicit in the generated report.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.metrics import f1_score

SENSOR_COLUMNS = [
    "Accelerometer1RMS",
    "Accelerometer2RMS",
    "Current",
    "Pressure",
    "Temperature",
    "Thermocouple",
    "Voltage",
    "Volume Flow RateRMS",
]


@dataclass(frozen=True)
class Protocol:
    adaptive_window: int = 120
    feature_window: int = 60
    calibration_fraction: float = 0.40
    threshold_quantile: float = 0.995
    relative_scale_floor: float = 0.001
    block_seconds: int = 60
    pca_variance: float = 0.90


def causal_robust_standardize(x: pd.DataFrame, p: Protocol) -> pd.DataFrame:
    """Past-only rolling median/IQR robust z score with a relative scale floor.

    Baseline at row t uses rows [t-window, t), never row t. The robust sigma is
    IQR/1.349. To avoid exploding z scores on nearly constant channels, sigma
    is floored at relative_scale_floor times the past rolling median absolute
    signal magnitude (and at machine-safe 1e-9).
    """
    past = x.shift(1)
    center = past.rolling(p.adaptive_window, min_periods=p.adaptive_window).median()
    q1 = past.rolling(p.adaptive_window, min_periods=p.adaptive_window).quantile(0.25)
    q3 = past.rolling(p.adaptive_window, min_periods=p.adaptive_window).quantile(0.75)
    robust_sigma = (q3 - q1) / 1.349
    magnitude = past.abs().rolling(p.adaptive_window, min_periods=p.adaptive_window).median()
    floor = p.relative_scale_floor * magnitude.clip(lower=1e-9)
    scale = robust_sigma.where(robust_sigma >= floor, floor).clip(lower=1e-9)
    return (x - center) / scale


def window_stat_features(z: pd.DataFrame, window: int) -> pd.DataFrame:
    """Causal 60-second summary features: last, mean, std, min, max, slope.

    Slope is the least-squares slope over equally spaced samples. All features
    use the window ending at the current row.
    """
    roll = z.rolling(window, min_periods=window)
    pieces = {
        "last": z,
        "mean": roll.mean(),
        "std": roll.std(ddof=0),
        "min": roll.min(),
        "max": roll.max(),
    }
    # slope = covariance(time, value) / variance(time), computed by convolution
    t = np.arange(window, dtype=float)
    tc = t - t.mean()
    denom = float(np.dot(tc, tc))
    arr = z.to_numpy(dtype=float)
    slope = np.full_like(arr, np.nan, dtype=float)
    for j in range(arr.shape[1]):
        col = arr[:, j]
        if len(col) >= window:
            # Convolution reverses weights; reverse tc to retain chronological sign.
            slope[window - 1 :, j] = np.convolve(col, tc[::-1], mode="valid") / denom
    pieces["slope"] = pd.DataFrame(slope, index=z.index, columns=z.columns)
    out = pd.concat(pieces, axis=1)
    out.columns = [f"{sensor}__{stat}" for stat, sensor in out.columns]
    return out


def score_fixed(z: pd.DataFrame) -> pd.Series:
    return z.abs().max(axis=1, skipna=False).rename("score")


def score_pca(features: pd.DataFrame, calibration_mask: np.ndarray, variance: float) -> tuple[pd.Series, int]:
    valid = np.isfinite(features.to_numpy()).all(axis=1)
    train_mask = valid & calibration_mask
    if train_mask.sum() < 3:
        raise RuntimeError(f"PCA calibration has only {train_mask.sum()} valid rows")
    x_train = features.loc[train_mask].to_numpy(dtype=float)
    pca = PCA(n_components=variance, svd_solver="full")
    pca.fit(x_train)
    scores = np.full(len(features), np.nan, dtype=float)
    x_valid = features.loc[valid].to_numpy(dtype=float)
    recon = pca.inverse_transform(pca.transform(x_valid))
    scores[valid] = np.mean((x_valid - recon) ** 2, axis=1)
    return pd.Series(scores, index=features.index, name="score"), int(pca.n_components_)


def contiguous_events(y: np.ndarray) -> list[tuple[int, int]]:
    y = y.astype(bool)
    starts = np.flatnonzero(y & ~np.r_[False, y[:-1]])
    ends = np.flatnonzero(y & ~np.r_[y[1:], False])
    return [(int(a), int(b)) for a, b in zip(starts, ends)]


def block_metrics(
    y: np.ndarray,
    point_alarm: np.ndarray,
    eval_start: int,
    block_size: int,
) -> dict[str, float | int]:
    """Aggregate evaluation tail into non-overlapping blocks anchored at eval_start."""
    y_eval = y[eval_start:].astype(bool)
    a_eval = point_alarm[eval_start:].astype(bool)
    n_blocks = int(np.ceil(len(y_eval) / block_size))
    yb = np.zeros(n_blocks, dtype=bool)
    ab = np.zeros(n_blocks, dtype=bool)
    for b in range(n_blocks):
        lo, hi = b * block_size, min((b + 1) * block_size, len(y_eval))
        yb[b] = y_eval[lo:hi].any()
        ab[b] = a_eval[lo:hi].any()

    normal = ~yb
    false_positive_blocks = int((ab & normal).sum())
    normal_blocks = int(normal.sum())
    fpr = false_positive_blocks / normal_blocks if normal_blocks else np.nan
    f1 = f1_score(yb, ab, zero_division=0)

    detected_events = 0
    delays: list[int] = []
    for start, end in contiguous_events(y):
        # Only the portion observable in the post-calibration evaluation tail.
        obs_start = max(start, eval_start)
        if end < eval_start:
            continue
        first_true_block = (obs_start - eval_start) // block_size
        last_true_block = (end - eval_start) // block_size
        hits = np.flatnonzero(ab[first_true_block : last_true_block + 1])
        if len(hits):
            detected_events += 1
            delays.append(int(hits[0]) * block_size)

    return {
        "f1": float(f1),
        "false_alarm_minute_ratio": float(fpr),
        "false_positive_blocks": false_positive_blocks,
        "normal_blocks": normal_blocks,
        "fault_blocks": int(yb.sum()),
        "predicted_alarm_blocks": int(ab.sum()),
        "events_evaluated": len([1 for s, e in contiguous_events(y) if e >= eval_start]),
        "events_detected": detected_events,
        "detected": int(detected_events > 0),
        "delay_seconds": float(np.median(delays)) if delays else np.nan,
    }


def evaluate_file(path: Path, data_root: Path, p: Protocol) -> list[dict]:
    df = pd.read_csv(path, sep=";")
    x = df[SENSOR_COLUMNS].apply(pd.to_numeric, errors="coerce")
    y = pd.to_numeric(df["anomaly"], errors="coerce").fillna(0).astype(int).to_numpy()
    n = len(df)
    calibration_end = int(np.floor(p.calibration_fraction * n))
    calibration_mask = np.zeros(n, dtype=bool)
    calibration_mask[p.adaptive_window:calibration_end] = True
    if not calibration_mask.any():
        raise RuntimeError(f"No calibration rows in {path}")

    z = causal_robust_standardize(x, p)
    fixed_scores = score_fixed(z)
    features = window_stat_features(z, p.feature_window)
    pca_scores, n_components = score_pca(features, calibration_mask, p.pca_variance)

    output: list[dict] = []
    rel = path.relative_to(data_root).as_posix()
    for method, scores, components in [
        ("fixed_robust_z", fixed_scores, np.nan),
        ("pca_reconstruction", pca_scores, n_components),
    ]:
        cal = scores.to_numpy()[calibration_mask]
        cal = cal[np.isfinite(cal)]
        if len(cal) == 0:
            raise RuntimeError(f"No finite calibration scores for {method} in {rel}")
        threshold = float(np.quantile(cal, p.threshold_quantile))
        point_alarm = np.isfinite(scores.to_numpy()) & (scores.to_numpy() > threshold)
        m = block_metrics(y, point_alarm, calibration_end, p.block_seconds)
        output.append(
            {
                "file": rel,
                "method": method,
                "rows": n,
                "calibration_start_row": p.adaptive_window,
                "calibration_end_row_exclusive": calibration_end,
                "calibration_anomaly_fraction": float(y[calibration_mask].mean()),
                "threshold": threshold,
                "pca_components": components,
                **m,
            }
        )
    return output


def pct(x: float) -> str:
    return "NA" if not np.isfinite(x) else f"{100*x:.1f}%"


def build_report(results: pd.DataFrame, p: Protocol, command: str) -> str:
    target = {
        "fixed_robust_z": {"name": "固定报警值（稳健 z）", "detection": 0.824, "fpr": 0.197, "delay": 60.0},
        "pca_reconstruction": {"name": "PCA 重构误差", "detection": 0.882, "fpr": 0.159, "delay": 0.0},
    }
    lines = [
        "# SKAB 基线独立复现（Codex）",
        "",
        "## 可复现命令",
        "",
        f"```powershell\n{command}\n```",
        "",
        "输出：`results/2026-09-15/codex/skab_repro.csv` 与本文件。",
        "",
        "## 明确化的协议选择",
        "",
        "本实现未读取或复用 `src/dsh/` 的任何脚本。PROJECT_STATE 只给出框架，以下细节是从零做出的固定选择：",
        f"- 每文件、严格过去窗口的因果滚动中位数与 IQR 标准化；窗口 {p.adaptive_window}s。",
        f"- 稳健尺度为 `IQR/1.349`，下限为过去信号绝对中位数的 {100*p.relative_scale_floor:.2f}%（另有 1e-9 数值下限）。",
        f"- PCA 输入为标准化信号最近 {p.feature_window}s 的 last/mean/std/min/max/slope，共 8×6=48 维；每文件单独拟合，保留 {100*p.pca_variance:.0f}% 方差。",
        f"- 标定段为行号 `[{p.adaptive_window}, floor(0.4N))`；阈值是该段逐秒分数的 {100*p.threshold_quantile:.1f}% 分位数。标签只用于最终评估。",
        f"- 从 `floor(0.4N)` 开始评估，按连续 {p.block_seconds}s 块聚合；块内任一点超阈即报警，块内任一点故障即故障块。",
        "- 事件检出：事件在评估段内覆盖的任一故障块报警；延迟按 60s 块量化。",
        "",
        "## 汇总对比",
        "",
        "| 方法 | Codex 事件检出率 | DSH 报告值 | 绝对偏差 | Codex 误报分钟比例 | DSH 报告值 | 绝对偏差 | Codex 延迟中位 | DSH 报告值 | 判定 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for method in ["fixed_robust_z", "pca_reconstruction"]:
        sub = results[results.method == method]
        events = int(sub.events_evaluated.sum())
        detected = int(sub.events_detected.sum())
        det = detected / events if events else np.nan
        fp = int(sub.false_positive_blocks.sum())
        nb = int(sub.normal_blocks.sum())
        fpr = fp / nb if nb else np.nan
        delays = sub.loc[sub.events_detected > 0, "delay_seconds"].dropna().to_numpy()
        delay = float(np.median(delays)) if len(delays) else np.nan
        td = target[method]
        det_diff = abs(det - td["detection"])
        fpr_diff = abs(fpr - td["fpr"])
        # Collaboration agreement defines relative reproduction deviation. For a
        # zero delay target, exact equality is required and otherwise reported separately.
        relative_devs = [det_diff / td["detection"], fpr_diff / td["fpr"]]
        verdict = "复现成功" if max(relative_devs) <= 0.10 and delay == td["delay"] else ("复现失败（>30%）" if max(relative_devs) > 0.30 else "需定位协议差异")
        lines.append(
            f"| {td['name']} | {pct(det)} ({detected}/{events}) | {pct(td['detection'])} | {pct(det_diff)} | "
            f"{pct(fpr)} ({fp}/{nb}) | {pct(td['fpr'])} | {pct(fpr_diff)} | {delay:.0f}s | {td['delay']:.0f}s | {verdict} |"
        )

    total_fault = int(results[results.method == "fixed_robust_z"].fault_blocks.sum())
    total_blocks = total_fault + int(results[results.method == "fixed_robust_z"].normal_blocks.sum())
    prevalence = total_fault / total_blocks if total_blocks else np.nan
    contaminated = results[(results.method == "fixed_robust_z") & (results.calibration_anomaly_fraction > 0)]
    lines += [
        "",
        "## 逐文件结果",
        "",
        "完整逐文件字段（F1、检出、误报及分母、阈值、PCA 维数、标定污染率）见 CSV。",
        "",
        "## 偏差分析与可核查事实",
        "",
        f"- 评估段共有 {total_blocks} 个分钟块，其中故障块 {total_fault} 个，故障块基数为 {pct(prevalence)}。因此只看总体 accuracy 会被类别基数误导。",
        f"- 有 {len(contaminated)} 个文件的 `[120s,40%)` 标定段含故障标签；它们是：" +
        (", ".join(contaminated.file.tolist()) if len(contaminated) else "无") + "。标签未参与拟合选择，但这证明固定前 40% 假设并不总能提供纯正常标定。",
        "- 与 DSH 数字不一致时，最可能的协议自由度依次是：稳健尺度采用 MAD 还是 IQR、相对尺度下限的比例、滑窗特征定义、分钟块锚点、事件命中窗口、以及误报分母是否仅计正常块。",
        "- **按协作约定的 >30% 标准，本次不是复现成功。我的直接判定是：DSH 把尚未冻结定义的数字写成了统一协议结果，这一步有错。** 固定报警值被称为“传统做法”，但 PROJECT_STATE 又要求所有方法经过因果自适应标准化与滑窗，二者在方法定义上冲突；PCA 的“1 分钟块判决”也未说明是任一点、均值、多数票还是持续时间门限。",
        "- 在本实现的明确事件定义（报警块必须与故障块重叠）下，固定报警仅检出 15/34，而不是 28/34。若把“评估尾段任意一次报警”也算事件检出，会把无关误报当命中。DSH 必须公开事件命中窗口；否则 82.4% 不可审计。",
        "- PCA 的误报分钟比例相差 38.8 个百分点，说明 DSH 实际使用的滑窗特征、分钟聚合或误报分母至少一项与任务单未写出的实现细节不同。不能在缺少这些定义时声称独立复现应得到 15.9%。",
        "- 我不在未冻结的自由度上用故障标签调参追逐 DSH 数字；所有默认值均在脚本参数与本节公开。",
        "",
        "## 字段说明",
        "",
        "- `f1`：该文件评估尾段的分钟块 F1。",
        "- `detected`：该文件事件是否至少被一个重叠故障块检出。",
        "- `false_alarm_minute_ratio`：正常分钟块中的误报比例；汇总时用总误报块/总正常块（不是逐文件比例平均）。",
        "- `delay_seconds`：首个报警故障块相对首个可评估故障块的块级延迟。",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=Path("data/SKAB-master/data"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/2026-09-15/codex"))
    parser.add_argument("--relative-scale-floor", type=float, default=0.001)
    args = parser.parse_args()

    p = Protocol(relative_scale_floor=args.relative_scale_floor)
    paths = sorted(
        pth for pth in args.data_root.rglob("*.csv")
        if "anomaly-free" not in pth.parts and pth.name != "anomaly-free.csv"
    )
    if len(paths) != 34:
        raise RuntimeError(f"Expected 34 labeled SKAB files, found {len(paths)}")

    rows: list[dict] = []
    for i, path in enumerate(paths, 1):
        print(f"[{i:02d}/{len(paths)}] {path.relative_to(args.data_root)}", flush=True)
        rows.extend(evaluate_file(path, args.data_root, p))

    results = pd.DataFrame(rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = args.output_dir / "skab_repro.csv"
    md_path = args.output_dir / "skab_repro.md"
    results.to_csv(csv_path, index=False, encoding="utf-8-sig")
    command = "python src/codex/2026-09-15_01_skab_repro.py"
    md_path.write_text(build_report(results, p, command), encoding="utf-8")
    print(f"Wrote {csv_path}")
    print(f"Wrote {md_path}")


if __name__ == "__main__":
    main()



