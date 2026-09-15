"""Audit candidate fixed calibration windows for SKAB PROTOCOL_v1.1.

This script reads raw SKAB labels only for post-hoc protocol diagnostics. Labels are
not used to fit a model or select per-file calibration boundaries.
"""
from __future__ import annotations

from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = ROOT / "data" / "SKAB-master" / "data"
OUT_DIR = ROOT / "results" / "2026-09-15" / "codex"
GROUPS = ("valve1", "valve2", "other")
DURATIONS = (300, 330, 360, 374, 375, 380)
CAL_START = 120
MIN_CAL = 300


def main() -> None:
    files = sorted(p for group in GROUPS for p in (DATA_ROOT / group).glob("*.csv"))
    records: list[dict[str, object]] = []

    for path in files:
        frame = pd.read_csv(path, sep=";")
        anomaly = pd.to_numeric(frame["anomaly"], errors="raise").astype(int)
        anomaly_indices = anomaly[anomaly.eq(1)].index
        first_anomaly = int(anomaly_indices[0]) if len(anomaly_indices) else None
        n_rows = len(frame)

        candidate_rules = {
            "mid_v1": min(CAL_START + 1800, n_rows // 2),
            "fixed380_mid": min(CAL_START + 380, n_rows // 2),
            **{f"fixed{duration}": min(CAL_START + duration, n_rows) for duration in DURATIONS},
        }
        for rule, cal_end in candidate_rules.items():
            cal_n = max(0, cal_end - CAL_START)
            cal_labels = anomaly.iloc[CAL_START:cal_end]
            anomaly_count = int(cal_labels.sum())
            records.append(
                {
                    "file": path.relative_to(DATA_ROOT).as_posix(),
                    "N": n_rows,
                    "first_anomaly_index_0based": first_anomaly,
                    "rule": rule,
                    "cal_start_inclusive": CAL_START,
                    "cal_end_exclusive": cal_end,
                    "cal_n": cal_n,
                    "cal_anomaly_samples": anomaly_count,
                    "cal_anomaly_fraction": anomaly_count / cal_n if cal_n else float("nan"),
                    "flagged": int(anomaly_count > 0),
                    "insufficient": int(cal_n < MIN_CAL),
                }
            )

    detail = pd.DataFrame.from_records(records)
    detail_path = OUT_DIR / "protocol_v11_calibration_audit.csv"
    detail.to_csv(detail_path, index=False, encoding="utf-8-sig")

    summary = (
        detail.groupby("rule", sort=False)
        .agg(
            files=("file", "count"),
            insufficient_files=("insufficient", "sum"),
            contaminated_files=("flagged", "sum"),
            min_cal_n=("cal_n", "min"),
            max_cal_n=("cal_n", "max"),
        )
        .reset_index()
    )
    contaminated = detail.loc[
        detail["flagged"].eq(1),
        [
            "rule",
            "file",
            "N",
            "first_anomaly_index_0based",
            "cal_start_inclusive",
            "cal_end_exclusive",
            "cal_n",
            "cal_anomaly_samples",
            "cal_anomaly_fraction",
        ],
    ]

    lines = [
        "# PROTOCOL_v1.1 标定窗审计",
        "",
        "标签仅用于事后诊断，不参与逐文件边界选择或模型标定。索引均为 0-based，标定区间为左闭右开。",
        "",
        f"- 带标签文件数：{len(files)}",
        f"- 文件长度：min={detail.loc[detail['rule'].eq('mid_v1'), 'N'].min()}，max={detail.loc[detail['rule'].eq('mid_v1'), 'N'].max()}",
        "",
        "## 规则汇总",
        "",
        summary.to_markdown(index=False),
        "",
        "## 含故障标定窗",
        "",
        contaminated.to_markdown(index=False),
        "",
        "## 可复现命令",
        "",
        "```powershell",
        "python src/codex/2026-09-15_04_protocol_v11_audit.py",
        "```",
        "",
    ]
    report_path = OUT_DIR / "protocol_v11_calibration_audit.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")

    print(summary.to_string(index=False))
    print("\nContaminated windows:")
    print(contaminated.to_string(index=False))
    print(f"\nWrote: {detail_path.relative_to(ROOT)}")
    print(f"Wrote: {report_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
