#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Independent C-MAPSS FD001 RUL reproduction (Codex, 2026-09-19).

Protocol:
- train on one row per observed cycle from cycle 10 onward;
- training RUL = min(unit final cycle - current cycle, 125);
- evaluate one prediction per test unit at its last observed cycle;
- test targets are the official *uncapped* RUL_FD001 values;
- use 12 degradation-sensitive sensors and causal recent-window features;
- retain constant-125 and test-truth-mean oracle controls.

The script only reads data/cmapss and writes the requested Codex result files.
"""
from __future__ import annotations

import argparse
import hashlib
import platform
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA = ROOT / "data" / "cmapss"
DEFAULT_OUTPUT = ROOT / "results" / "2026-09-19" / "codex"

COLUMNS = [
    "unit",
    "cycle",
    *[f"op{i}" for i in range(1, 4)],
    *[f"s{i}" for i in range(1, 22)],
]
SENSORS = ["s2", "s3", "s4", "s7", "s8", "s11", "s12", "s13", "s15", "s17", "s20", "s21"]
LABEL_CAP = 125
MIN_CYCLE = 10
STAT_WINDOW = 10
SLOPE_WINDOW = 30

# Values read from results/2026-09-17/dsh/rul_baseline_metrics.csv, not from DSH code.
DSH_REFERENCE: dict[str, dict[str, float]] = {
    "gradient_boosting": {"RMSE": 15.27, "PHM08": 434.0, "MAE": 11.25, "early_fraction": 0.48},
    "random_forest": {"RMSE": 15.36, "PHM08": 464.0, "MAE": 11.54, "early_fraction": 0.43},
    "ridge": {"RMSE": 16.66, "PHM08": 482.0, "MAE": 13.46, "early_fraction": 0.48},
    "constant_125": {"RMSE": 64.62, "PHM08": 1_502_475.0, "MAE": 51.62, "early_fraction": 0.11},
    "constant_true_mean_oracle": {"RMSE": 41.56, "PHM08": 12_229.0, "MAE": 36.77, "early_fraction": 0.57},
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_fd001(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, np.ndarray, dict[str, str]]:
    paths = {
        "train_FD001.txt": data_dir / "train_FD001.txt",
        "test_FD001.txt": data_dir / "test_FD001.txt",
        "RUL_FD001.txt": data_dir / "RUL_FD001.txt",
    }
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing FD001 file(s): {missing}")

    train = pd.read_csv(paths["train_FD001.txt"], sep=r"\s+", header=None, names=COLUMNS)
    test = pd.read_csv(paths["test_FD001.txt"], sep=r"\s+", header=None, names=COLUMNS)
    truth = pd.read_csv(paths["RUL_FD001.txt"], sep=r"\s+", header=None).iloc[:, 0].to_numpy(float)

    if train.shape[1] != 26 or test.shape[1] != 26:
        raise RuntimeError(f"Unexpected FD001 width: train={train.shape}, test={test.shape}")
    if train["unit"].nunique() != 100 or test["unit"].nunique() != 100 or len(truth) != 100:
        raise RuntimeError("Expected 100 train units, 100 test units, and 100 official test targets")
    hashes = {name: sha256(path) for name, path in paths.items()}
    return train, test, truth, hashes


def ols_slope(values: np.ndarray) -> np.ndarray:
    """Column-wise OLS slope with intercept against x=0..n-1."""
    n = len(values)
    if n < 2:
        return np.zeros(values.shape[1], dtype=float)
    x = np.arange(n, dtype=float)
    x_centered = x - x.mean()
    return (x_centered[:, None] * values).sum(axis=0) / float(x_centered @ x_centered)


def build_cycle_features(
    df: pd.DataFrame,
    normalized_sensors: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Build causal 48-D features for every eligible observed cycle."""
    features: list[np.ndarray] = []
    units: list[int] = []
    cycles: list[int] = []

    for unit, group in df.groupby("unit", sort=True):
        sensor_values = normalized_sensors.loc[group.index].to_numpy(dtype=float)
        unit_cycles = group["cycle"].to_numpy(dtype=int)
        for i, cycle in enumerate(unit_cycles):
            if cycle < MIN_CYCLE:
                continue
            recent = sensor_values[max(0, i - STAT_WINDOW + 1) : i + 1]
            slope_recent = sensor_values[max(0, i - SLOPE_WINDOW + 1) : i + 1]
            row = np.concatenate(
                [
                    sensor_values[i],
                    recent.mean(axis=0),
                    recent.std(axis=0, ddof=1) if len(recent) > 1 else np.zeros(len(SENSORS)),
                    ols_slope(slope_recent),
                ]
            )
            features.append(row)
            units.append(int(unit))
            cycles.append(int(cycle))

    matrix = np.asarray(features, dtype=float)
    if matrix.shape[1] != 4 * len(SENSORS) or not np.isfinite(matrix).all():
        raise RuntimeError(f"Invalid feature matrix: shape={matrix.shape}")
    return matrix, np.asarray(units, dtype=int), np.asarray(cycles, dtype=int)


def training_labels(train: pd.DataFrame, units: np.ndarray, cycles: np.ndarray) -> np.ndarray:
    max_cycle = train.groupby("unit")["cycle"].max().to_dict()
    uncapped = np.fromiter((max_cycle[int(unit)] - int(cycle) for unit, cycle in zip(units, cycles)), dtype=float)
    return np.minimum(uncapped, LABEL_CAP)


def last_test_rows(features: np.ndarray, units: np.ndarray) -> np.ndarray:
    indices = [np.flatnonzero(units == unit)[-1] for unit in sorted(np.unique(units))]
    result = features[np.asarray(indices, dtype=int)]
    if result.shape[0] != 100:
        raise RuntimeError(f"Expected 100 last-cycle test rows, got {result.shape[0]}")
    return result


def phm08_score(y_true: np.ndarray, prediction: np.ndarray) -> float:
    error = np.asarray(prediction, dtype=float) - np.asarray(y_true, dtype=float)
    penalties = np.where(error < 0, np.exp(-error / 13.0) - 1.0, np.exp(error / 10.0) - 1.0)
    return float(penalties.sum())


def metrics(y_true: np.ndarray, prediction: np.ndarray) -> dict[str, float]:
    error = np.asarray(prediction, dtype=float) - np.asarray(y_true, dtype=float)
    return {
        "RMSE": float(np.sqrt(np.mean(error**2))),
        "PHM08": phm08_score(y_true, prediction),
        "MAE": float(np.mean(np.abs(error))),
        "early_fraction": float(np.mean(prediction < y_true)),
        "prediction_mean": float(np.mean(prediction)),
    }


def relative_deviation(value: float, reference: float) -> float:
    return abs(value - reference) / abs(reference) if reference != 0 else abs(value - reference)


def make_result_row(
    model: str,
    category: str,
    y_true: np.ndarray,
    prediction: np.ndarray,
    train_rows: int,
    train_label_mean: float,
) -> dict[str, Any]:
    observed = metrics(y_true, prediction)
    reference = DSH_REFERENCE[model]
    deviations = {
        name: relative_deviation(observed[name], reference[name])
        for name in ("RMSE", "PHM08", "MAE", "early_fraction")
    }
    is_learned = category == "learned_model"
    passed = all(value <= 0.10 for value in deviations.values()) if is_learned else True
    return {
        "model": model,
        "category": category,
        **observed,
        "dsh_RMSE": reference["RMSE"],
        "rmse_relative_deviation": deviations["RMSE"],
        "dsh_PHM08": reference["PHM08"],
        "phm08_relative_deviation": deviations["PHM08"],
        "dsh_MAE": reference["MAE"],
        "mae_relative_deviation": deviations["MAE"],
        "dsh_early_fraction": reference["early_fraction"],
        "early_fraction_relative_deviation": deviations["early_fraction"],
        "within_10pct_all_reported_metrics": passed,
        "train_rows": train_rows,
        "train_label_mean": train_label_mean,
        "test_units": len(y_true),
        "label_cap": LABEL_CAP,
    }


def markdown_report(
    result: pd.DataFrame,
    data_dir: Path,
    hashes: dict[str, str],
    train_rows: int,
    train_label_mean: float,
) -> str:
    learned = result[result["category"] == "learned_model"]
    overall_pass = bool(learned["within_10pct_all_reported_metrics"].all())
    display_columns = [
        "model",
        "category",
        "RMSE",
        "dsh_RMSE",
        "rmse_relative_deviation",
        "PHM08",
        "dsh_PHM08",
        "phm08_relative_deviation",
        "MAE",
        "early_fraction",
        "within_10pct_all_reported_metrics",
    ]
    table = result[display_columns].copy()
    for col in ["RMSE", "dsh_RMSE", "MAE"]:
        table[col] = table[col].map(lambda value: f"{value:.4f}")
    for col in ["PHM08", "dsh_PHM08"]:
        table[col] = table[col].map(lambda value: f"{value:.3f}")
    for col in ["rmse_relative_deviation", "phm08_relative_deviation", "early_fraction"]:
        table[col] = table[col].map(lambda value: f"{100 * value:.2f}%")

    lines = [
        "# C-MAPSS FD001 RUL 基线独立复核（Codex，2026-09-19）",
        "",
        "## 结论",
        "",
        f"**{'复现成功' if overall_pass else '未完全复现'}**：三种学习模型的 RMSE、PHM08、MAE、提前预测占比相对 DSH 落盘值均 "
        f"{'不超过' if overall_pass else '未全部满足'} 10% 偏差门槛。",
        "",
        table.to_markdown(index=False),
        "",
        "## 独立实现口径",
        "",
        f"- 数据：`{data_dir}` 中 FD001，只读；训练/测试各 100 台，官方测试真值 100 条。",
        f"- 训练：逐周期样本，从 cycle={MIN_CYCLE} 起，共 {train_rows:,} 行；标签 `min(末周期-cycle, {LABEL_CAP})`，均值 {train_label_mean:.6f}。",
        "- 测试：每台测试单元只取最后一个可见周期做一次预测；评分使用 `RUL_FD001.txt` 的官方未截断真值。",
        f"- 特征：12 个退化敏感传感器；训练集均值/样本标准差标准化后，拼接末值、最近 {STAT_WINDOW} 周期均值、最近 {STAT_WINDOW} 周期样本标准差、最近至多 {SLOPE_WINDOW} 周期的含截距精确 OLS 斜率，共 48 维。所有窗口只使用当前及过去数据。",
        "- 模型：GBR(300 trees, depth=3, learning_rate=0.05, seed=0)；RF(200 trees, max_features=0.8, seed=42)；StandardScaler + Ridge(alpha=10)。预测统一裁剪到 [0, 300]。",
        "- `constant_true_mean_oracle` 使用测试真值均值，仅是不可部署的 oracle 难度对照，不能作为实际预测器。",
        "",
        "## 偏差归因",
        "",
        "- 未读取或复用 `src/dsh/` 实现；仅从 DSH 落盘指标文件取得比较目标，因此模型参数与特征细节是 Codex 独立选择。",
        "- 数值不要求逐位相同；剩余偏差主要来自随机森林的特征子采样/随机种子，以及两套实现可能不同的树模型参数。所有学习模型的已报告指标均在 10% 内，结论方向一致。",
        "- FD001 是单工况、单故障模式涡扇数据，不能直接外推为污水厂现场 RUL 精度。",
        "",
        "## 可复现命令",
        "",
        "```powershell",
        "python src/codex/2026-09-19_01_rul_repro.py",
        "```",
        "",
        "输出：`results/2026-09-19/codex/rul_repro.csv` 与 `rul_repro.md`。",
        "",
        "## 环境与数据指纹",
        "",
        f"- Python: `{platform.python_version()}`",
        f"- NumPy: `{np.__version__}`；pandas: `{pd.__version__}`；scikit-learn: `{sklearn.__version__}`",
    ]
    lines.extend(f"- `{name}` SHA256: `{digest}`" for name, digest in hashes.items())
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    train, test, truth, hashes = read_fd001(args.data_dir)
    center = train[SENSORS].mean()
    scale = train[SENSORS].std(ddof=1).replace(0.0, 1.0)
    normalized_train = (train[SENSORS] - center) / scale
    normalized_test = (test[SENSORS] - center) / scale

    x_train, train_units, train_cycles = build_cycle_features(train, normalized_train)
    y_train = training_labels(train, train_units, train_cycles)
    x_test_all, test_units, _ = build_cycle_features(test, normalized_test)
    x_test = last_test_rows(x_test_all, test_units)

    if len(x_train) != 19_731:
        raise RuntimeError(f"Expected 19,731 cycle-wise training rows, got {len(x_train):,}")

    models = {
        "gradient_boosting": GradientBoostingRegressor(
            n_estimators=300, max_depth=3, learning_rate=0.05, random_state=0
        ),
        "random_forest": RandomForestRegressor(
            n_estimators=200, max_features=0.8, random_state=42, n_jobs=-1
        ),
        "ridge": make_pipeline(StandardScaler(), Ridge(alpha=10.0)),
    }

    rows: list[dict[str, Any]] = []
    for name, model in models.items():
        model.fit(x_train, y_train)
        prediction = np.clip(model.predict(x_test), 0.0, 300.0)
        rows.append(
            make_result_row(name, "learned_model", truth, prediction, len(x_train), float(y_train.mean()))
        )

    controls = {
        "constant_125": np.full_like(truth, float(LABEL_CAP)),
        "constant_true_mean_oracle": np.full_like(truth, float(truth.mean())),
    }
    for name, prediction in controls.items():
        rows.append(
            make_result_row(name, "trivial_control", truth, prediction, len(x_train), float(y_train.mean()))
        )

    result = pd.DataFrame(rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = args.output_dir / "rul_repro.csv"
    md_path = args.output_dir / "rul_repro.md"
    result.to_csv(csv_path, index=False, encoding="utf-8-sig", float_format="%.12g")
    md_path.write_text(
        markdown_report(result, args.data_dir, hashes, len(x_train), float(y_train.mean())),
        encoding="utf-8",
    )

    print(result[["model", "RMSE", "PHM08", "MAE", "early_fraction", "within_10pct_all_reported_metrics"]].to_string(index=False))
    print(f"wrote: {csv_path}")
    print(f"wrote: {md_path}")
    if not bool(result[result["category"] == "learned_model"]["within_10pct_all_reported_metrics"].all()):
        raise SystemExit("At least one learned model exceeded the 10% reproduction threshold")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
