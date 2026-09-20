#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Independently reproduce decision-layer v6 accounting and sensitivity grid."""
from __future__ import annotations

from pathlib import Path
import argparse
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "results/2026-09-18/dsh/decision_v6_predictions.csv.gz"
DSH_POLICY = ROOT / "results/2026-09-18/dsh/decision_policy_v6.csv"
DSH_GRID = ROOT / "results/2026-09-18/dsh/decision_sensitivity_v6.csv"
OUT = ROOT / "results/2026-09-20/codex"
N_UNITS = 100
URGENT_HORIZON = 60
PLACEHOLDER = dict(failure=50_000, replacement=8_000, waste=60)


def first_trigger(g: pd.DataFrame, kind: str, a: float | int | None = None,
                  b: float | None = None) -> pd.Series | None:
    if kind == "none":
        return None
    if kind == "fixed":
        hit = g["cycle"] >= int(a)
    elif kind == "point":
        hit = g["pred"] <= float(a)
    elif kind == "class":
        hit = g[f"p{int(a)}"] >= float(b)
    else:
        raise ValueError(kind)
    return g.loc[hit].iloc[0] if hit.any() else None


def account(df: pd.DataFrame, kind: str, a=None, b=None,
            failure=50_000, replacement=8_000, waste=60) -> dict:
    caught = missed = moved_nonurgent = wasted_cycles = 0
    for _, g in df.groupby("unit", sort=True):
        g = g.sort_values("cycle")
        urgent = bool(g["trueRUL_end"].iloc[0] <= URGENT_HORIZON)
        trig = first_trigger(g, kind, a, b)
        moved = trig is not None
        if urgent and moved:
            caught += 1
        elif urgent:
            missed += 1
        elif moved:
            moved_nonurgent += 1
            wasted_cycles += int(trig["trueRUL"])
    total = missed * failure + (caught + moved_nonurgent) * replacement + wasted_cycles * waste
    return dict(caught_urgent=caught, missed_urgent=missed, moved_nonurgent=moved_nonurgent,
                wasted_cycles=wasted_cycles, urgent_recall=caught / (caught + missed),
                total_cost=int(total), per_unit_cost=int(total / N_UNITS))


def label(kind, a=None, b=None):
    if kind == "none": return "none"
    if kind == "fixed": return f"fixed_{int(a)}"
    if kind == "point": return f"point_{int(a)}"
    return f"P{int(a)}>={float(b):.1f}"


def policy_rows(df: pd.DataFrame) -> pd.DataFrame:
    specs = [("none", None, None)]
    specs += [("fixed", x, None) for x in (25, 50, 75, 100, 150)]
    specs += [("point", x, None) for x in (10, 20, 30, 40, 60)]
    specs += [("class", h, p) for h in (20, 40, 60) for p in (0.2, 0.5, 0.8)]
    rows = []
    for kind, a, b in specs:
        r = account(df, kind, a, b, **PLACEHOLDER)
        rows.append(dict(section="policy", policy_key=label(kind, a, b), kind=kind,
                         parameter_a=a, parameter_b=b, **r))
    return pd.DataFrame(rows)


def sensitivity_rows(df: pd.DataFrame) -> pd.DataFrame:
    fixed_specs = [("fixed", x, None) for x in (25, 50, 75, 100, 125, 150)]
    ai_specs = [("point", x, None) for x in (10, 20, 30, 40, 60)] + [
        ("class", h, p) for h in (20, 40, 60) for p in (0.2, 0.5, 0.8)
    ]
    rows = []
    for fc in (20_000, 35_000, 50_000, 80_000, 120_000):
        for rc in (4_000, 8_000, 16_000):
            kw = dict(failure=fc, replacement=rc, waste=60)
            fixed = [(account(df, *s, **kw)["total_cost"], s) for s in fixed_specs]
            ai = [(account(df, *s, **kw)["total_cost"], s) for s in ai_specs]
            fixed_cost, fixed_spec = min(fixed, key=lambda x: x[0])
            ai_cost, ai_spec = min(ai, key=lambda x: x[0])
            winner = "AI" if ai_cost < fixed_cost else "fixed"
            rows.append(dict(section="sensitivity", failure_cost=fc, replacement_cost=rc,
                             waste_cost=60, ratio=round(fc / rc, 1), do_nothing_cost=39 * fc,
                             best_ai_cost=ai_cost, best_ai_parameter=label(*ai_spec),
                             best_fixed_cost=fixed_cost, best_fixed_parameter=f"{int(fixed_spec[1])} cycles",
                             winner=winner, ai_saving_vs_fixed=(fixed_cost - ai_cost) / fixed_cost))
    return pd.DataFrame(rows)


def verify(policy: pd.DataFrame, grid: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    d = pd.read_csv(DSH_POLICY)
    keys = ["none"] + [f"fixed_{x}" for x in (25, 50, 75, 100, 150)] + [f"point_{x}" for x in (10,20,30,40,60)] + [f"P{h}>={p:.1f}" for h in (20,40,60) for p in (0.2,0.5,0.8)]
    d = d.assign(policy_key=keys)
    m = policy.merge(d[["policy_key","抓住紧急","漏掉紧急","动用非紧急","浪费周期","总成本","单台成本"]], on="policy_key", how="left")
    m["exact_match"] = (
        (m.caught_urgent == m["抓住紧急"]) & (m.missed_urgent == m["漏掉紧急"]) &
        (m.moved_nonurgent == m["动用非紧急"]) & (m.wasted_cycles == m["浪费周期"]) &
        (m.total_cost == m["总成本"]) & (m.per_unit_cost == m["单台成本"])
    )

    dg = pd.read_csv(DSH_GRID)
    mg = grid.merge(dg, left_on=["failure_cost","replacement_cost"], right_on=["失效代价","更换代价"], how="left")
    winner_map = {"AI":"AI", "fixed":"固定周期"}
    mg["exact_match"] = (
        (mg.best_ai_cost == mg["最优AI成本"]) & (mg.best_fixed_cost == mg["最优固定周期成本"]) &
        (mg.best_ai_parameter == mg["最优AI参数"]) &
        (mg.best_fixed_parameter.str.extract(r"(\d+)")[0].astype(int) == mg["最优固定参数"].str.extract(r"(\d+)")[0].astype(int)) &
        (mg.winner.map(winner_map) == mg["获胜方"])
    )
    return m, mg


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--output-dir", type=Path, default=OUT); args = ap.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(INPUT, compression="gzip")
    required = {"unit","cycle","pred","p20","p40","p60","trueRUL","trueRUL_end"}
    if set(df.columns) != required:
        raise RuntimeError(f"unexpected columns: {df.columns.tolist()}")
    policy = policy_rows(df); grid = sensitivity_rows(df)
    pm, gm = verify(policy, grid)
    if not pm.exact_match.all() or not gm.exact_match.all():
        raise RuntimeError("DSH comparison failed")

    combined = pd.concat([policy.assign(exact_match=True), grid.assign(exact_match=True)], ignore_index=True, sort=False)
    combined.to_csv(args.output_dir / "decision_v6_repro.csv", index=False, encoding="utf-8-sig", float_format="%.6f")
    pshow = policy[["policy_key","caught_urgent","missed_urgent","moved_nonurgent","wasted_cycles","urgent_recall","total_cost","per_unit_cost"]].copy()
    pshow["urgent_recall"] = pshow.urgent_recall.map(lambda x: f"{x:.3f}")
    gshow = grid[["failure_cost","replacement_cost","best_ai_cost","best_ai_parameter","best_fixed_cost","best_fixed_parameter","winner","ai_saving_vs_fixed"]].copy()
    gshow["ai_saving_vs_fixed"] = gshow.ai_saving_vs_fixed.map(lambda x: f"{x:.3f}")
    ai_wins = int((grid.winner == "AI").sum())
    md = [
        "# Q2：决策层 v6 独立复核",
        "",
        "## 独立会计实现",
        "",
        "- 紧急单元：`trueRUL_end <= 60`，本数据共 39/100 台。",
        "- 策略首次触发：固定周期取首个 `cycle >= interval`；点估计取首个 `pred <= lead`；分类式取首个 `p20/p40/p60 >= threshold`。",
        "- 紧急且触发=抓住紧急；紧急且未触发=漏掉紧急；非紧急且触发=动用非紧急，浪费周期取首次触发处 `trueRUL`。",
        "- 总成本=`漏掉紧急×失效代价 + (抓住紧急+动用非紧急)×更换代价 + 浪费周期×浪费单价`。",
        "- **50,000 / 8,000 / 60 均为占位参数，只用于复核会计，不代表真实金额或经济收益。**",
        "",
        "## 主表复算",
        "",
        pshow.to_markdown(index=False),
        "",
        f"上述 {len(policy)} 行的整数会计、总成本和单台成本与 DSH v6 **逐行精确一致**；召回仅有显示舍入差异。",
        "",
        "## 15 格成本敏感性",
        "",
        gshow.to_markdown(index=False),
        "",
        f"15/15 网格的最优 AI 成本/参数、最优固定周期成本/参数及赢家均与 DSH 精确一致；AI 赢 {ai_wins}/15 格，固定周期赢 {15-ai_wins}/15 格。固定候选包含 125 周期（虽未在主展示表列出，但会成为若干网格的最优点）。",
        "",
        "## 判定",
        "",
        "复核通过。v6 的紧急单元会计口径和成本敏感性网格可由落盘逐周期预测独立还原。结果只说明在这些占位成本比值下的策略排序；部署前必须由企业提供失效、更换、停机、剩余寿命浪费等真实成本分布。",
        "",
        "机器可读明细：`decision_v6_repro.csv`。",
    ]
    (args.output_dir / "decision_v6_repro.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"policy exact: {pm.exact_match.sum()}/{len(pm)}; grid exact: {gm.exact_match.sum()}/{len(gm)}; AI wins={ai_wins}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
