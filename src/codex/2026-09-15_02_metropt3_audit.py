#!/usr/bin/env python3
"""Download MetroPT-3 from UCI to a temporary cache and produce a read-only audit.

No file is written under data/. The official ZIP is cached under the operating
system temp directory so the 208 MiB source need not be committed to the repo.
"""
from __future__ import annotations

import hashlib
import shutil
import tempfile
import zipfile
from collections import Counter
from pathlib import Path
from urllib.request import urlopen

import numpy as np
import pandas as pd

URL = "https://archive.ics.uci.edu/static/public/791/metropt%2B3%2Bdataset.zip"
CSV_MEMBER = "MetroPT3(AirCompressor).csv"
PDF_MEMBER = "Data Description_Metro.pdf"
ANALOG = ["TP2", "TP3", "H1", "DV_pressure", "Reservoirs", "Oil_temperature", "Motor_current"]
DIGITAL = ["COMP", "DV_eletric", "Towers", "MPG", "LPS", "Pressure_switch", "Oil_level", "Caudal_impulses"]
FAILURES = [
    ("#1", "2020-04-18 00:00:00", "2020-04-18 23:59:00", "Air leak", "High stress", ""),
    ("#2*", "2020-05-29 23:30:00", "2020-05-30 06:00:00", "Air leak", "High stress", "Maintenance report: 30 Apr 12:00"),
    ("#3", "2020-06-05 10:00:00", "2020-06-07 14:30:00", "Air leak", "High stress", "Maintenance: 8 Jun 16:00"),
    ("#4", "2020-07-15 14:30:00", "2020-07-15 19:00:00", "Air leak", "High stress", "Maintenance: 16 Jul 00:00"),
]
MEANINGS = {
    "TP2": "压缩机侧压力（bar）",
    "TP3": "气动面板产生的压力（bar）",
    "H1": "旋风分离器过滤器排放时由压降产生的压力（bar）",
    "DV_pressure": "干燥塔排气时的压降（bar）；接近 0 表示压缩机带载运行",
    "Reservoirs": "储气罐下游压力（bar），理论上应接近 TP3",
    "Oil_temperature": "压缩机油温（°C）",
    "Motor_current": "三相电机一相电流（A）；约 0/4/7/9A 对应停机/卸载/带载/启动",
    "COMP": "进气阀电信号；激活表示无进气（停机或卸载）",
    "DV_eletric": "出口阀控制信号；激活表示带载，未激活表示停机或卸载",
    "Towers": "干燥塔选择信号；0 为塔 1，1 为塔 2",
    "MPG": "低于约 8.2 bar 时使压缩机带载的控制信号，与 COMP 行为相关",
    "LPS": "压力低于 7 bar 时激活的信号",
    "Pressure_switch": "检测干燥塔排放的压力开关信号",
    "Oil_level": "油位低于预期时激活的信号",
    "Caudal_impulses": "APU 至储气罐绝对空气流量的脉冲计数信号",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download(cache: Path) -> None:
    if cache.exists() and cache.stat().st_size > 200_000_000:
        return
    cache.parent.mkdir(parents=True, exist_ok=True)
    partial = cache.with_suffix(".partial")
    print(f"Downloading {URL} -> {cache}", flush=True)
    with urlopen(URL, timeout=180) as src, partial.open("wb") as dst:
        shutil.copyfileobj(src, dst, length=4 * 1024 * 1024)
    partial.replace(cache)


def fmt_pct(n: int, d: int) -> str:
    return f"{n/d:.6%}" if d else "NA"


def main() -> None:
    output = Path("results/2026-09-15/codex/metropt3_audit.md")
    cache = Path(tempfile.gettempdir()) / "BEWG_PdM_codex" / "metropt3_dataset.zip"
    download(cache)

    with zipfile.ZipFile(cache) as zf:
        info = zf.getinfo(CSV_MEMBER)
        names = zf.namelist()
        print(f"Reading {CSV_MEMBER} ({info.file_size} bytes)", flush=True)
        with zf.open(CSV_MEMBER) as stream:
            df = pd.read_csv(stream, low_memory=False)

    unnamed = [c for c in df.columns if c.startswith("Unnamed:")]
    index_col = unnamed[0] if unnamed else df.columns[0]
    ts = pd.to_datetime(df["timestamp"], errors="coerce")
    numeric_cols = [c for c in df.columns if c not in [index_col, "timestamp"]]
    total_cells = len(df) * len(df.columns)
    missing = df.isna().sum()
    missing_total = int(missing.sum())
    inf_counts = {c: int(np.isinf(pd.to_numeric(df[c], errors="coerce")).sum()) for c in numeric_cols}

    diffs = ts.diff().dt.total_seconds().dropna()
    cadence_counts = Counter(diffs.astype(int).tolist())
    top_cadence = cadence_counts.most_common(10)
    duplicate_ts = int(ts.duplicated().sum())
    nonpositive_steps = int((diffs <= 0).sum())
    gaps_gt_10 = int((diffs > 10).sum())
    gaps_gt_20 = int((diffs > 20).sum())

    profile_rows = []
    outlier_total = 0
    analog_cells = len(df) * len(ANALOG)
    for c in ANALOG:
        s = pd.to_numeric(df[c], errors="coerce")
        q1, q3 = float(s.quantile(0.25)), float(s.quantile(0.75))
        iqr = q3 - q1
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        outliers = int(((s < lo) | (s > hi)).sum()) if iqr > 0 else 0
        outlier_total += outliers
        profile_rows.append({
            "field": c, "min": float(s.min()), "q1": q1, "median": float(s.median()),
            "q3": q3, "max": float(s.max()), "iqr_outliers": outliers,
            "iqr_outlier_ratio": outliers / len(s),
        })
    profile = pd.DataFrame(profile_rows)

    digital_rows = []
    for c in DIGITAL:
        s = pd.to_numeric(df[c], errors="coerce")
        off_domain = int((~s.isin([0.0, 1.0]) & s.notna()).sum())
        digital_rows.append({
            "field": c, "unique": int(s.nunique(dropna=True)), "values": ", ".join(map(str, sorted(s.dropna().unique().tolist())[:20])),
            "off_binary_domain": off_domain,
        })
    digital_profile = pd.DataFrame(digital_rows)

    failures = pd.DataFrame(FAILURES, columns=["id", "start", "end", "failure", "severity", "report"])
    failures["start"] = pd.to_datetime(failures["start"])
    failures["end"] = pd.to_datetime(failures["end"])
    failures["rows_in_csv"] = [int(((ts >= r.start) & (ts <= r.end)).sum()) for r in failures.itertuples()]

    sample = df.head(200).to_csv(index=False, lineterminator="\n")
    first, last = ts.min(), ts.max()
    span = last - first
    median_dt = float(diffs.median())
    effective_hz = 1.0 / median_dt

    lines = [
        "# MetroPT-3 数据集获取与体检（不建模）",
        "",
        "## 可复现命令",
        "",
        "```powershell",
        "python src/codex/2026-09-15_02_metropt3_audit.py",
        "```",
        "",
        "> 脚本只把官方 ZIP 缓存到系统临时目录 `%TEMP%/BEWG_PdM_codex/`，没有写入或修改 `data/`。审计报告写入本文件。",
        "",
        "## 1. 来源、体积、采样、时间跨度",
        "",
        f"- 官方来源：UCI Machine Learning Repository，dataset id 791：`{URL}`",
        f"- ZIP 实际大小：{cache.stat().st_size:,} bytes（{cache.stat().st_size/2**20:.2f} MiB）；SHA-256：`{sha256(cache)}`。",
        f"- ZIP 内容：{', '.join(names)}；CSV 大小 {info.file_size:,} bytes（{info.file_size/2**20:.2f} MiB）。",
        f"- 实际行数：{len(df):,}；CSV 列数：{len(df.columns)}（其中 1 个导出索引列、1 个时间戳、15 个传感器字段）。",
        f"- 实际时间跨度：{first} 至 {last}，跨度 {span}。",
        f"- 实测采样间隔中位数：{median_dt:g}s，即约 {effective_hz:g} Hz。**因此该发布文件是约 0.1 Hz，不是 1 Hz。** UCI 页面/PDF 写 1 Hz，与 CSV 时间戳及索引步长不一致。",
        "",
        "时间戳相邻间隔（前 10 种最高频，秒）：",
        "",
        "| 间隔(s) | 次数 |",
        "|---:|---:|",
    ]
    lines += [f"| {k} | {v:,} |" for k, v in top_cadence]
    lines += [
        "",
        "## 2. 字段清单与含义",
        "",
        "| 字段 | 类型 | 含义 |",
        "|---|---|---|",
        f"| `{index_col}` | 导出索引 | 不是传感器；基本按 10 递增，不应作为模型特征 |",
        "| `timestamp` | 时间戳 | 采样时间 |",
    ]
    for c in ANALOG:
        lines.append(f"| `{c}` | 模拟量 | {MEANINGS[c]} |")
    for c in DIGITAL:
        lines.append(f"| `{c}` | 数字量 | {MEANINGS[c]} |")

    lines += [
        "",
        "## 3. 原始说明中的真实故障事件",
        "",
        "数据本身无逐点标签；以下来自官方 ZIP 内 `Data Description_Metro.pdf` 第 3 页的公司故障报告表。",
        "",
        "| 编号 | 开始 | 结束 | 故障 | 严重度 | 维护记录 | CSV 覆盖行数 |",
        "|---|---|---|---|---|---|---:|",
    ]
    for r in failures.itertuples():
        lines.append(f"| {r.id} | {r.start} | {r.end} | {r.failure} | {r.severity} | {r.report or '无'} | {r.rows_in_csv:,} |")
    lines += [
        "",
        "* 官方 PDF 第二行编号重复写成 `#1`；这里为便于引用标为 `#2*`，没有擅自更改原始事件时间。另：该行维护记录写“30 Apr 12:00”，早于 5 月 29 日故障窗口，疑似原始文档日期笔误，必须保留存疑。",
        "",
        "## 4. 数据质量",
        "",
        f"- 缺测：{missing_total:,}/{total_cells:,} 个单元格，比例 {fmt_pct(missing_total,total_cells)}。逐列缺测均为 0。",
        f"- `NaT` 时间戳：{int(ts.isna().sum()):,}；重复时间戳：{duplicate_ts:,}；非正向时间步：{nonpositive_steps:,}。",
        f"- 大于 10s 的相邻间隔：{gaps_gt_10:,}；大于 20s 的间隔：{gaps_gt_20:,}。时间轴并非严格等间隔。",
        f"- 数值正负无穷：{sum(inf_counts.values()):,}。",
        f"- 7 个模拟量按逐列 Tukey 1.5×IQR 规则共标出 {outlier_total:,}/{analog_cells:,}（{fmt_pct(outlier_total,analog_cells)}）个统计离群点。**这不是错误标签**：压缩机有停机/卸载/带载/启动等多工况，IQR 离群会混入合法状态切换，只能作为候选检查。",
        "",
        "### 模拟量范围与统计离群",
        "",
        "| 字段 | min | Q1 | median | Q3 | max | IQR 离群数 | 比例 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in profile.itertuples():
        lines.append(f"| {r.field} | {r.min:.6g} | {r.q1:.6g} | {r.median:.6g} | {r.q3:.6g} | {r.max:.6g} | {r.iqr_outliers:,} | {r.iqr_outlier_ratio:.4%} |")
    lines += [
        "",
        "### 数字量取值检查",
        "",
        "| 字段 | 唯一值数 | 已见取值 | 非 0/1 数 |",
        "|---|---:|---|---:|",
    ]
    for r in digital_profile.itertuples():
        lines.append(f"| {r.field} | {r.unique} | {r.values} | {r.off_binary_domain:,} |")

    lines += [
        "",
        "## 5. 是否需要重采样",
        "",
        "**需要先对齐规则时间网格，但不应伪装成 1 Hz。**建议：",
        "1. 以 10s 为目标频率重索引；保留 `is_gap` 掩码和原始时间差，不能无痕填补。",
        "2. 模拟量仅对短缺口做限长插值/前向保持，并做敏感性对照；数字量用前向保持，但跨长缺口不填。",
        "3. 所有窗口按真实时长换算：120s 基线约 12 个样本，1 分钟块约 6 个样本；更稳妥的是直接使用时间索引滚动窗口。",
        "",
        "## 6. 对统一协议的可用性判断",
        "",
        "**不能原样套用，但可做最小修改后使用。**",
        "- 可保留：逐设备因果自适应标准化、无标签标定、固定目标误报率、时间块判决。",
        "- 必须修改采样假设：从 SKAB 的 1Hz/120 点/60 点，改为时间型 `rolling('120s')` 与 `resample('60s')`，或在规则 10s 网格上用 12 点与 6 点。",
        "- 必须修改标定期：这是单台设备连续 6 个月的数据，不应按整个文件前 40% 做一次静态标定；应按维修记录切分时间、在每次维修后的确认健康段进行 walk-forward 标定，并禁止跨故障/维修边界泄漏。",
        "- 必须分工况：停机、卸载、带载、启动状态本身造成强多模态。先用数字控制量划分工况或把工况作为条件变量，再在同工况内标定异常分数。",
        "- 故障标签是粗粒度公司报告窗口，不是逐秒真值；事件检出、提前量和正常运行小时误报更适合，逐点 F1 只能作辅助。",
        "",
        "## 7. 前 200 行样例",
        "",
        "<details><summary>展开 CSV 样例（官方文件原列，前 200 行）</summary>",
        "",
        "```csv",
        sample.rstrip(),
        "```",
        "</details>",
        "",
        "## 8. 审计结论",
        "",
        "1. 官方文件可获取且可完整读取；但实际只有约 0.1 Hz，官方元数据的 1 Hz 说法不可直接采用。",
        "2. 数据无缺测/无无穷，但时间间隔不严格规则；统计离群点不能直接当坏值，因为多工况是真实结构。",
        "3. 该数据适合验证真实故障事件，但协议必须改为时间窗口 + 工况条件化 + 维修后 walk-forward 标定。",
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()

