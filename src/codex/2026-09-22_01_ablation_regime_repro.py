#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Q13: independently recalculate threshold-regime and calibration-window sensitivity."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/2026-09-22/codex"
DSH_SCORE = ROOT / "results/2026-09-16/dsh/metropt3_score_minutes_dsh.csv.gz"
BASE_SCRIPT = ROOT / "src/codex/2026-09-20_03_ablation_repro.py"
FAULTS = [
    ("F1", pd.Timestamp("2020-04-18 00:00"), pd.Timestamp("2020-04-18 23:59")),
    ("F2", pd.Timestamp("2020-05-29 23:30"), pd.Timestamp("2020-05-30 06:00")),
    ("F3", pd.Timestamp("2020-06-05 10:00"), pd.Timestamp("2020-06-07 14:30")),
    ("F4", pd.Timestamp("2020-07-15 14:30"), pd.Timestamp("2020-07-15 19:00")),
]
WINDOWS = [
    ("W1", pd.Timestamp("2020-02-01 00:00"), pd.Timestamp("2020-04-17 12:00")),
    ("W2", pd.Timestamp("2020-04-19 11:59"), pd.Timestamp("2020-05-29 11:30")),
    ("W3", pd.Timestamp("2020-05-30 18:00"), pd.Timestamp("2020-06-04 22:00")),
    ("W4", pd.Timestamp("2020-06-08 02:30"), pd.Timestamp("2020-07-15 02:30")),
    ("W5", pd.Timestamp("2020-07-16 07:00"), pd.Timestamp("2020-09-01 03:59")),
]


def load_base():
    spec = importlib.util.spec_from_file_location("codex_q6", BASE_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


def classify(events):
    timely = late = 0
    used = set()
    status = []
    for name, fs, fe in FAULTS:
        a = [(i, s, e) for i, (s, e) in enumerate(events)
             if fs - pd.Timedelta(minutes=60) <= s <= fs + pd.Timedelta(minutes=60)]
        b = [(i, s, e) for i, (s, e) in enumerate(events)
             if fs + pd.Timedelta(minutes=60) < s <= fe]
        if a:
            i, s, e = min(a, key=lambda x: x[1]); timely += 1; used.add(i); st = "timely"
        elif b:
            i, s, e = min(b, key=lambda x: x[1]); late += 1; used.add(i); st = "late"
        else:
            st = "miss"
        status.append(f"{name}:{st}")
    return dict(events=len(events), timely=timely, late=late, miss=4-timely-late,
                false_events=len(events)-len(used), status=";".join(status))


def eventize(df: pd.DataFrame, threshold: float):
    events=[]; active=False; enter=exitc=0; cooldown=0; start=None; last=None; prev_epoch=None
    for row in df.itertuples():
        t=row.Index; epoch=row.epoch
        contiguous = last is None or (t-last <= pd.Timedelta(minutes=1))
        if prev_epoch is not None and (epoch != prev_epoch or not contiguous):
            if active: events.append((start,last+pd.Timedelta(minutes=1)))
            active=False; enter=exitc=cooldown=0; start=None
        v=row.score; ok=bool(row.stable) and np.isfinite(v)
        high=ok and v>threshold; low=ok and v<0.8*threshold
        if active:
            if low:
                exitc += 1
                if exitc >= 10:
                    events.append((start,t+pd.Timedelta(minutes=1)))
                    active=False; start=None; enter=exitc=0; cooldown=30
            else: exitc=0
        else:
            if cooldown > 0: cooldown-=1; enter=0
            elif high:
                enter += 1
                if enter >= 5: active=True; start=t; enter=exitc=0
            else: enter=0
        prev_epoch=epoch; last=t
    if active: events.append((start,last+pd.Timedelta(minutes=1)))
    return events


def eval_rows(name, scored, thresholds):
    rows=[]
    for label, thr in thresholds:
        r=classify(eventize(scored, float(thr)))
        rows.append(dict(chain=name, calibration=label, threshold=float(thr), **r))
    return rows


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    # Layer A: independent event-machine recalculation over the deposited DSH minute score stream.
    dsh=pd.read_csv(DSH_SCORE, parse_dates=["timestamp"]).set_index("timestamp").sort_index()
    dsh["stable"]=True; dsh["epoch"]=0
    dsh_thresholds=[("label-assisted DET", 2.3954)]
    initial=dsh.loc[(dsh.index>=pd.Timestamp("2020-02-01 12:00")) &
                    (dsh.index<pd.Timestamp("2020-04-17 12:00")), "score"]
    dsh_thresholds.append(("unlabeled initial q0.995", float(initial.quantile(.995))))
    rows=eval_rows("DSH deposited score", dsh, dsh_thresholds)
    for wn,a,b in WINDOWS:
        vals=dsh.loc[(dsh.index>=a)&(dsh.index<b),"score"].dropna()
        thr=float(vals.quantile(.995))
        r=classify(eventize(dsh,thr))
        rows.append(dict(chain="DSH deposited score",calibration=f"{wn} q0.995",threshold=thr,
                         calibration_minutes=len(vals),**r))

    # Layer B: Codex's independent minute features + conditioned walk-forward score.
    base=load_base()
    minutes=base.minute_features()
    features=base.ANALOG+base.DERIVED+base.DUTY
    cod=base.walk_forward(minutes,features,True,"top3_rms").copy()
    cod=cod.sort_index()
    # old module already marks stable and epoch; use the same event machine, with gap resets.
    init=cod.loc[(cod.index>=pd.Timestamp("2020-02-08 00:00")) &
                 (cod.index<pd.Timestamp("2020-04-17 12:00")) & cod.stable,"score"].dropna()
    rows += eval_rows("Codex independent score", cod,
                      [("label-assisted DET (scale control only)",2.3954),
                       ("unlabeled initial q0.995",float(init.quantile(.995)))])
    for wn,a,b in WINDOWS:
        vals=cod.loc[(cod.index>=a)&(cod.index<b)&cod.stable,"score"].dropna()
        if vals.empty: continue
        thr=float(vals.quantile(.995)); r=classify(eventize(cod,thr))
        rows.append(dict(chain="Codex independent score",calibration=f"{wn} q0.995",threshold=thr,
                         calibration_minutes=len(vals),**r))

    out=pd.DataFrame(rows)
    out.to_csv(OUT/"q13_ablation_regime_repro.csv",index=False,encoding="utf-8-sig",float_format="%.6f")

    d5=out[(out.chain=="DSH deposited score")&out.calibration.str.match(r"W[1-5]")]
    c5=out[(out.chain=="Codex independent score")&out.calibration.str.match(r"W[1-5]")]
    def summary(x):
        return dict(thr_min=x.threshold.min(),thr_median=x.threshold.median(),thr_max=x.threshold.max(),
                    thr_ratio=x.threshold.max()/x.threshold.min(),fp_min=x.false_events.min(),
                    fp_max=x.false_events.max(),timely_values=sorted(x.timely.unique().tolist()))
    print(out.to_string(index=False))
    print("DSH5",summary(d5)); print("CODEX5",summary(c5))

if __name__ == "__main__":
    main()
