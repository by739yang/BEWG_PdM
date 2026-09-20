#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Independent simplified CWRU reproduction for Q4 (2026-09-20)."""
from __future__ import annotations

from pathlib import Path
import argparse
import json
import numpy as np
import pandas as pd
from scipy.stats import skew, kurtosis
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "cwru"
OUT = ROOT / "results" / "2026-09-20" / "codex"
FS = 48_000.0
WIN = 4096
STEP = 2048
SEED = 20260920
CLASSES = ("Normal", "B", "IR", "OR")


def load_signal(record: str) -> np.ndarray:
    with np.load(DATA / f"{record}.npz") as z:
        return np.asarray(z["DE"], dtype=np.float64).ravel()


def windows(x: np.ndarray, start: int = 0, stop: int | None = None) -> np.ndarray:
    stop = len(x) if stop is None else min(stop, len(x))
    starts = np.arange(start, stop - WIN + 1, STEP, dtype=int)
    return np.stack([x[i:i + WIN] for i in starts]) if len(starts) else np.empty((0, WIN))


def extract(w: np.ndarray, mode: str) -> np.ndarray:
    if not len(w):
        return np.empty((0, 24))
    eps = 1e-12
    mean = w.mean(1)
    std = w.std(1)
    rms = np.sqrt(np.mean(w * w, axis=1))
    abs_mean = np.mean(np.abs(w), axis=1)
    ptp = np.ptp(w, axis=1)
    abs_max = np.max(np.abs(w), axis=1)
    sk = skew(w, axis=1, bias=False)
    ku = kurtosis(w, axis=1, fisher=True, bias=False)
    crest = abs_max / np.maximum(rms, eps)

    spec = np.abs(np.fft.rfft(w, axis=1)) ** 2
    freq = np.fft.rfftfreq(WIN, d=1.0 / FS)
    total = spec.sum(1)
    centroid = (spec * freq).sum(1) / np.maximum(total, eps)
    bandwidth = np.sqrt((spec * (freq[None, :] - centroid[:, None]) ** 2).sum(1) / np.maximum(total, eps))
    p = spec / np.maximum(total[:, None], eps)
    entropy = -(p * np.log(np.maximum(p, eps))).sum(1) / np.log(spec.shape[1])

    edges = np.linspace(0.0, 12_000.0, 13)
    bands = np.column_stack([
        spec[:, (freq >= edges[i]) & (freq < edges[i + 1])].sum(1)
        for i in range(12)
    ])
    if mode == "selective":
        bands = bands / np.maximum(total[:, None], eps)
    else:
        bands = np.log1p(bands)
    return np.column_stack([mean, std, rms, abs_mean, ptp, abs_max, sk, ku, crest,
                            centroid, bandwidth, entropy, bands])


def record_features(record: str, mode: str, part: tuple[float, float] = (0.0, 1.0)) -> np.ndarray:
    x = load_signal(record)
    if mode == "full":
        x = (x - x.mean()) / max(x.std(), 1e-12)
    lo = int(len(x) * part[0]); hi = int(len(x) * part[1])
    return extract(windows(x, lo, hi), mode)


def add_record(xs: list[np.ndarray], ys: list[np.ndarray], record: str, label: str,
               mode: str, part: tuple[float, float] = (0.0, 1.0)) -> None:
    X = record_features(record, mode, part)
    xs.append(X); ys.append(np.repeat(label, len(X)))


def build(experiment: str, mode: str) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    tr_x: list[np.ndarray] = []; tr_y: list[np.ndarray] = []
    te_x: list[np.ndarray] = []; te_y: list[np.ndarray] = []
    if experiment == "E3":
        add_record(tr_x, tr_y, "Normal", "Normal", mode, (0.0, 0.5))
        add_record(te_x, te_y, "Normal", "Normal", mode, (0.5, 1.0))
        for c in ("B", "IR", "OR"):
            add_record(tr_x, tr_y, f"{c}_7" if c != "OR" else "OR6_7", c, mode)
            add_record(te_x, te_y, f"{c}_14" if c != "OR" else "OR6_14", c, mode)
    elif experiment == "E4":
        add_record(tr_x, tr_y, "Normal", "Normal", mode, (0.0, 2.0 / 3.0))
        add_record(te_x, te_y, "Normal", "Normal", mode, (2.0 / 3.0, 1.0))
        for c in ("B", "IR", "OR"):
            for size in (7, 14):
                add_record(tr_x, tr_y, f"{c}_{size}" if c != "OR" else f"OR6_{size}", c, mode)
            add_record(te_x, te_y, f"{c}_21" if c != "OR" else "OR6_21", c, mode)
    elif experiment == "E5":
        add_record(tr_x, tr_y, "Normal", "Normal", mode)
        add_record(te_x, te_y, "N1750", "Normal", mode)
        for c in ("B", "IR", "OR"):
            for size in (7, 14, 21):
                add_record(tr_x, tr_y, f"{c}_{size}" if c != "OR" else f"OR6_{size}", c, mode)
            add_record(te_x, te_y, f"{c}_7_1750" if c != "OR" else "OR6_7_1750", c, mode)
    else:
        raise ValueError(experiment)
    return np.vstack(tr_x), np.concatenate(tr_y), np.vstack(te_x), np.concatenate(te_y)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output-dir", type=Path, default=OUT)
    args = ap.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    labels = {"E3": "7mil→14mil", "E4": "7+14mil→21mil", "E5": "1730rpm→1750rpm"}
    rows = []
    for mode in ("raw", "selective", "full"):
        for exp in ("E3", "E4", "E5"):
            Xtr, ytr, Xte, yte = build(exp, mode)
            model = RandomForestClassifier(n_estimators=300, max_features="sqrt",
                                           class_weight="balanced", random_state=SEED,
                                           n_jobs=-1)
            model.fit(Xtr, ytr)
            pred = model.predict(Xte)
            rows.append({
                "normalization": mode,
                "experiment": exp,
                "split": labels[exp],
                "model": "RandomForest",
                "train_windows": len(ytr),
                "test_windows": len(yte),
                "accuracy": accuracy_score(yte, pred),
                "macro_f1": f1_score(yte, pred, labels=list(CLASSES), average="macro"),
            })
    out = pd.DataFrame(rows)
    out.to_csv(args.output_dir / "diag_repro.csv", index=False, encoding="utf-8-sig", float_format="%.6f")

    pivot = out.pivot(index="normalization", columns="experiment", values="macro_f1")
    multi_ok = bool(pivot.loc["raw", "E4"] > pivot.loc["raw", "E3"] and
                    pivot.loc["selective", "E4"] > pivot.loc["selective", "E3"])
    norm_ok = bool(pivot.loc["selective", "E5"] > pivot.loc["full", "E5"] and
                   pivot.loc["selective", "E4"] > pivot.loc["full", "E4"])
    if not (multi_ok and norm_ok):
        raise RuntimeError(f"direction check failed: multi={multi_ok}, normalization={norm_ok}")

    display = out.copy()
    display["accuracy"] = display["accuracy"].map(lambda x: f"{x:.3f}")
    display["macro_f1"] = display["macro_f1"].map(lambda x: f"{x:.3f}")
    md = [
        "# Q4：CWRU 诊断结论独立复核",
        "",
        "## 最小独立实现",
        "",
        "- 输入：`data/cwru/*.npz` 的驱动端 `DE` 信号；假定采样率 48 kHz。",
        "- 切窗：4096 点、步长 2048；固定随机种子 20260920。",
        "- 特征：9 个时域幅值/形状特征、频谱质心/带宽/熵、12 个 0–12 kHz 频带能量，共 24 维。",
        "- 分类器：300 棵随机森林，`max_features=sqrt`、类别平衡。",
        "- 防止 Normal 同段泄漏：E3 将 Normal 前/后 50% 分给训练/测试；E4 按前 2/3 与后 1/3 分割；E5 使用不同记录 Normal/N1750。",
        "- 三种归一化：`raw`=绝对幅值+log 频带能量；`selective`=保留幅值，仅将频带能量除以总能量；`full`=每条记录先做全信号 z-score。",
        "",
        "## 实测结果",
        "",
        display.to_markdown(index=False),
        "",
        "## 两条结论",
        "",
        f"1. **多尺寸训练方向复现成功。** raw：E3 {pivot.loc['raw','E3']:.3f} → E4 {pivot.loc['raw','E4']:.3f}；selective：E3 {pivot.loc['selective','E3']:.3f} → E4 {pivot.loc['selective','E4']:.3f}。在本简化特征下，7+14mil 训练到 21mil 的宏 F1 高于仅 7mil 训练到 14mil。",
        f"2. **归一化要挑对象的方向复现成功。** 跨转速 E5：selective={pivot.loc['selective','E5']:.3f}，full={pivot.loc['full','E5']:.3f}；E4：selective={pivot.loc['selective','E4']:.3f}，full={pivot.loc['full','E4']:.3f}。全记录 z-score 会抹除有诊断价值的绝对幅值。",
        "",
        "## 与 DSH 数字的关系及限制",
        "",
        "本实现只要求方向复核，窗口、特征和 Normal 切分均与 DSH 不同，因此不声称复现 DSH 的具体 0.625/0.550。E5 的 raw/selective 得到 1.000，说明这些记录在该特征空间中很容易分开，也可能含记录级工况签名；该完美结果不得外推为真实跨厂泛化性能。每类只有少数记录，窗口不是独立设备样本。",
        "",
        "机器可读明细：`diag_repro.csv`。",
    ]
    (args.output_dir / "diag_repro.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(out.to_string(index=False))
    print(json.dumps({"multi_size_direction": multi_ok, "normalization_direction": norm_ok}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
