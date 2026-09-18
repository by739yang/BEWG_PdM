#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""C-MAPSS FD001 RUL baseline repair (Codex, 2026-09-18).

The repaired pipeline uses one training row per observed cycle (cycle >= 10),
cycle-wise capped labels, and the official uncapped test RUL values.  Data are
read from the user cache and never written into the repository data/ directory.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CACHE = Path(os.environ.get("BEWG_PDM_CACHE_DIR", Path.home() / ".cache" / "BEWG_PdM")) / "cmapss"
DEFAULT_OUTPUT = ROOT / "results" / "2026-09-18" / "codex"
COLS = ["unit", "cycle", *[f"op{i}" for i in range(1, 4)], *[f"s{i}" for i in range(1, 22)]]
SENSORS = ["s2", "s3", "s4", "s7", "s8", "s11", "s12", "s13", "s15", "s17", "s20", "s21"]
CAP = 125
WINDOW = 10
MIN_CYCLE = 10


def read_data(cache: Path) -> tuple[pd.DataFrame, pd.DataFrame, np.ndarray]:
    train = pd.read_csv(cache / "train_FD001.txt", sep=r"\s+", header=None, names=COLS)
    test = pd.read_csv(cache / "test_FD001.txt", sep=r"\s+", header=None, names=COLS)
    truth = pd.read_csv(cache / "RUL_FD001.txt", sep=r"\s+", header=None, names=["RUL"])["RUL"].to_numpy(float)
    if train.shape[1] != 26 or train.empty or test["unit"].nunique() != len(truth):
        raise RuntimeError("invalid C-MAPSS FD001 files")
    return train, test, truth


def make_z(df: pd.DataFrame, center: pd.Series, scale: pd.Series) -> pd.DataFrame:
    return (df[SENSORS] - center) / scale


def build_cycle_features(df: pd.DataFrame, zdf: pd.DataFrame, window: int = WINDOW, min_cycle: int = MIN_CYCLE) -> tuple[pd.DataFrame, list[tuple[int, int]]]:
    """Build recent-window statistics for every cycle after the warm-up."""
    rows: list[dict[str, float]] = []
    keys: list[tuple[int, int]] = []
    for unit, group in df.groupby("unit", sort=True):
        idx = group.index.to_numpy()
        zg = zdf.loc[idx].reset_index(drop=True)
        cycles = group["cycle"].to_numpy()
        for i in range(len(group)):
            if cycles[i] < min_cycle:
                continue
            recent = zg.iloc[max(0, i - window + 1) : i + 1]
            recent5 = zg.iloc[max(0, i - 4) : i + 1].mean()
            prior5 = zg.iloc[max(0, i - 9) : max(0, i - 4)].mean()
            f: dict[str, float] = {}
            for col in SENSORS:
                f[f"{col}_last"] = float(zg.iloc[i][col])
                f[f"{col}_mean"] = float(recent[col].mean())
                f[f"{col}_std"] = float(recent[col].std(ddof=1)) if len(recent) > 1 else 0.0
                f[f"{col}_trend5v10"] = float(recent5[col] - prior5[col])
            rows.append(f)
            keys.append((int(unit), int(i)))
    return pd.DataFrame(rows), keys


def labels_for_keys(df: pd.DataFrame, keys: list[tuple[int, int]]) -> np.ndarray:
    max_cycles = df.groupby("unit")["cycle"].max().to_dict()
    return np.asarray([min(float(max_cycles[unit] - df.loc[df["unit"].eq(unit)].iloc[i]["cycle"]), CAP) for unit, i in keys], dtype=float)


def phm08(y_true: np.ndarray, pred: np.ndarray) -> float:
    error = np.asarray(pred) - np.asarray(y_true)
    return float(np.where(error < 0, np.exp(-error / 13.0) - 1.0, np.exp(error / 10.0) - 1.0).sum())


def score(y_true: np.ndarray, pred: np.ndarray) -> dict[str, float]:
    err = np.asarray(pred) - np.asarray(y_true)
    return {
        "RMSE": float(np.sqrt(np.mean(err**2))),
        "PHM08": phm08(y_true, pred),
        "MAE": float(np.mean(np.abs(err))),
    }


def trend_control(train: pd.DataFrame, test: pd.DataFrame, center: pd.Series, scale: pd.Series) -> np.ndarray:
    """Transparent health-index trend extrapolation control."""
    ztr = make_z(train, center, scale)
    zte = make_z(test, center, scale)
    train_hi = ztr.mean(axis=1)
    target_hi = train.assign(HI=train_hi).groupby("unit")["HI"].last().mean()
    result: list[float] = []
    for _, group in test.groupby("unit", sort=True):
        g = zte.loc[group.index].mean(axis=1).to_numpy()
        cycles = group["cycle"].to_numpy(dtype=float)
        tail = min(30, len(group))
        slope = np.polyfit(cycles[-tail:], g[-tail:], 1)[0] if tail >= 2 else 0.0
        estimate = (target_hi - g[-1]) / slope if abs(slope) > 1e-6 else CAP
        result.append(float(np.clip(estimate, 0.0, 300.0)))
    return np.asarray(result, dtype=float)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    train, test, truth = read_data(args.cache_dir)
    center = train[SENSORS].mean()
    scale = train[SENSORS].std().replace(0, 1.0)
    ztrain, ztest = make_z(train, center, scale), make_z(test, center, scale)

    xtrain, train_keys = build_cycle_features(train, ztrain)
    ytrain = labels_for_keys(train, train_keys)
    xtest_all, test_keys = build_cycle_features(test, ztest)
    last_keys = []
    for unit, group in test.groupby("unit", sort=True):
        last_i = len(group) - 1
        key = (int(unit), int(last_i))
        if key not in test_keys:
            raise RuntimeError(f"missing final test cycle for unit {unit}")
        last_keys.append(key)
    test_indices = [test_keys.index(k) for k in last_keys]
    xtest = xtest_all.iloc[test_indices].reset_index(drop=True)

    models = {
        "gradient_boosting": GradientBoostingRegressor(n_estimators=300, max_depth=3, learning_rate=0.05, random_state=0),
        "random_forest": RandomForestRegressor(n_estimators=200, random_state=0, n_jobs=-1),
        "ridge": make_pipeline(StandardScaler(), Ridge(alpha=10.0)),
    }
    rows: list[dict[str, object]] = []
    per_unit = pd.DataFrame({"unit": np.arange(1, len(truth) + 1), "true_RUL": truth})
    print(f"train_rows={len(xtrain):,}")
    print(f"train_label_mean={ytrain.mean():.6f}")
    print(f"test_units={len(xtest):,}")

    for name, model in models.items():
        model.fit(xtrain, ytrain)
        pred = np.clip(model.predict(xtest), 0.0, 300.0)
        print(f"{name}_test_prediction_mean={pred.mean():.6f}")
        row = {"model": name, "category": "learned_model", **score(truth, pred), "train_rows": len(xtrain), "train_label_mean": float(ytrain.mean()), "test_prediction_mean": float(pred.mean()), "test_units": len(truth), "label_cap": CAP}
        rows.append(row)
        per_unit[f"pred_{name}"] = pred

    controls = {
        "constant_125": np.full(len(truth), 125.0),
        "constant_true_mean_oracle": np.full(len(truth), float(truth.mean())),
        "constant_train_median_diagnostic": np.full(len(truth), float(np.median(ytrain))),
        "trend_extrapolation": trend_control(train, test, center, scale),
    }
    for name, pred in controls.items():
        print(f"{name}_test_prediction_mean={pred.mean():.6f}")
        rows.append({"model": name, "category": "trivial_control" if name != "constant_train_median_diagnostic" else "diagnostic_control", **score(truth, pred), "train_rows": len(xtrain), "train_label_mean": float(ytrain.mean()), "test_prediction_mean": float(pred.mean()), "test_units": len(truth), "label_cap": CAP})
        per_unit[f"pred_{name}"] = pred

    result = pd.DataFrame(rows)
    result.to_csv(args.output_dir / "rul_repro.csv", index=False, encoding="utf-8-sig")
    per_unit.to_csv(args.output_dir / "rul_repro_per_unit.csv", index=False, encoding="utf-8-sig")

    dsh_reference = {"gradient_boosting": 19.73, "random_forest": 21.03, "ridge": 21.49}
    lines = [
        "# C-MAPSS FD001 RUL 流程修复复现（Codex，2026-09-18）", "",
        "## 修复点", "",
        f"- 训练样本为逐周期样本，而不是每台单元最后一周期：跳过前 `{MIN_CYCLE - 1}` 个周期后共 `{len(xtrain):,}` 行。",
        f"- 训练标签为 `min(max_cycle - cycle, {CAP})`；测试评估使用官方 `RUL_FD001.txt` 未截断真值。",
        f"- 训练标签均值：`{ytrain.mean():.6f}`；测试单元数：`{len(truth)}`。",
        "- 特征为 12 个常用传感器在最近 10 周期的 last/mean/std 与 5-vs-10 周期趋势差；不把测试集可见的末周期位置特征混入模型。",
        "", "## 结果", "", result.to_markdown(index=False), "",
        "## 与 DSH 参考的偏差判定", "",
    ]
    for name, reference in dsh_reference.items():
        actual = float(result.loc[result["model"].eq(name), "RMSE"].iloc[0])
        delta = actual - reference
        verdict = "通过（差异 ≤ 0.5 RMSE）" if abs(delta) <= 0.5 else "需复核（差异 > 0.5 RMSE）"
        lines.append(f"- `{name}`：Codex RMSE={actual:.3f}，DSH 参考={reference:.2f}，差={delta:+.3f}；{verdict}。")
    lines += [
        "", "## 解释与限制", "",
        "- `constant_true_mean_oracle` 使用测试真值均值，只作难度参考，不能作为可部署预测器。",
        "- `constant_train_median_diagnostic` 专门用于检查训练标签/样本构造；它不代表正式模型。",
        "- FD001 是单工况公开基准，不能直接声称污水厂设备现场 RUL 精度。",
        "- 数据从用户缓存读取：`" + str(args.cache_dir.resolve()) + "`；本脚本未写入 `data/`。",
    ]
    (args.output_dir / "rul_repro.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(result.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


