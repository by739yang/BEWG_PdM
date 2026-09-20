#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Simplified independent MetroPT-3 ablation for Q6."""
from __future__ import annotations
from pathlib import Path
import argparse
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data/metropt3/metropt3.csv"
OUT = ROOT / "results/2026-09-20/codex"
ANALOG = ["TP2","TP3","H1","DV_pressure","Reservoirs","Oil_temperature","Motor_current"]
DERIVED = ["TP3_minus_Reservoirs","TP3_minus_H1"]
DUTY = ["loaded_fraction_60m","unloaded_fraction_60m","stopped_fraction_60m","switches_60m"]
FAULTS = [
    ("F1", pd.Timestamp("2020-04-18 00:00"), pd.Timestamp("2020-04-18 23:59")),
    ("F2", pd.Timestamp("2020-05-29 23:30"), pd.Timestamp("2020-05-30 06:00")),
    ("F3", pd.Timestamp("2020-06-05 10:00"), pd.Timestamp("2020-06-07 14:30")),
    ("F4", pd.Timestamp("2020-07-15 14:30"), pd.Timestamp("2020-07-15 19:00")),
]
EPOCHS = [
    ("initial", "2020-02-01 00:00", "2020-02-08 00:00", "2020-04-30 12:00"),
    ("post_maint_0430", "2020-05-01 00:00", "2020-05-08 00:00", "2020-06-08 16:00"),
    ("post_maint_0608", "2020-06-09 04:00", "2020-06-16 04:00", "2020-07-16 00:00"),
    ("post_maint_0716", "2020-07-16 12:00", "2020-07-23 12:00", "2020-09-02 00:00"),
]
THRESHOLD = 6.0


def minute_features() -> pd.DataFrame:
    use = ["timestamp", *ANALOG, "DV_eletric"]
    d = pd.read_csv(RAW, usecols=use, parse_dates=["timestamp"])
    state = np.where(d.Motor_current.to_numpy() < 1.0, 0,
                     np.where((d.DV_eletric.to_numpy() >= .5) | (d.Motor_current.to_numpy() >= 5.5), 2, 1))
    d["minute"] = d.timestamp.dt.floor("min"); d["raw_state"] = state
    med = d.groupby("minute", sort=True)[ANALOG].median()
    counts = pd.crosstab(d.minute, d.raw_state).reindex(columns=[0,1,2], fill_value=0)
    med["state"] = counts.to_numpy().argmax(1)
    med["state_purity"] = counts.max(axis=1).to_numpy() / counts.sum(axis=1).to_numpy()
    med["transition"] = counts.gt(0).sum(axis=1).to_numpy() > 1
    med["TP3_minus_Reservoirs"] = med.TP3 - med.Reservoirs
    med["TP3_minus_H1"] = med.TP3 - med.H1
    names = {0:"stopped",1:"unloaded",2:"loaded"}
    for code,name in names.items():
        frac = counts[code] / counts.sum(axis=1)
        med[f"{name}_fraction_60m"] = frac.rolling("60min",min_periods=12).mean()
    gap = med.index.to_series().diff()
    switch = ((med.state != med.state.shift()) & gap.le(pd.Timedelta(minutes=2))).astype(float)
    med["switches_60m"] = switch.rolling("60min",min_periods=12).sum()
    med["stable"] = (~med.transition) & med.state_purity.ge(.999) & med[ANALOG+DERIVED+DUTY].notna().all(axis=1)
    return med


def robust_params(rows: pd.DataFrame, features: list[str], conditioned: bool):
    groups = [0,1,2] if conditioned else ["ALL"]
    params = {}
    for g in groups:
        mask = rows.stable & ((rows.state == g) if conditioned else True)
        x = rows.loc[mask, features].to_numpy(float)
        if len(x) < 100: raise RuntimeError(f"insufficient group {g}: {len(x)}")
        center = np.nanmedian(x, axis=0)
        q25, q75 = np.nanpercentile(x, [25,75], axis=0)
        sigma = (q75-q25)/1.349
        sx=np.sort(x,axis=0); dif=np.diff(sx,axis=0); dif[dif<=0]=np.nan
        with np.errstate(all="ignore"): resolution=np.nanmedian(dif,axis=0)
        resolution=np.where(np.isfinite(resolution),resolution,0.0)
        floor=np.maximum.reduce([np.full_like(center,1e-4),np.abs(center)*1e-4,resolution*2])
        params[g]=(center,np.maximum(sigma,floor))
    return params


def score(rows: pd.DataFrame, features: list[str], conditioned: bool, aggregate: str, params) -> np.ndarray:
    out=np.full(len(rows),np.nan); stable=rows.stable.to_numpy(bool)
    for g in ([0,1,2] if conditioned else ["ALL"]):
        mask=stable & ((rows.state.to_numpy()==g) if conditioned else True)
        x=rows.loc[mask,features].to_numpy(float); c,s=params[g]
        z=np.clip(np.abs((x-c)/s),0,50)
        if aggregate=="top3_rms":
            k=min(3,z.shape[1]); top=np.partition(z,-k,axis=1)[:,-k:]; out[mask]=np.sqrt(np.mean(top*top,axis=1))
        else: out[mask]=z.max(axis=1)
    return out


def walk_forward(minutes: pd.DataFrame, features: list[str], conditioned: bool, aggregate: str) -> pd.DataFrame:
    pieces=[]
    for epoch,cs,ce,ee in EPOCHS:
        cs,ce,ee=map(pd.Timestamp,(cs,ce,ee))
        fixed=minutes.loc[(minutes.index>=cs)&(minutes.index<ce)&minutes.stable].copy()
        evaluation=minutes.loc[(minutes.index>=ce)&(minutes.index<ee)].copy()
        accepted=fixed.iloc[0:0].copy(); day=ce; quarantine=pd.Timestamp.min
        while day<ee:
            day_end=min(day+pd.Timedelta(days=1),ee)
            cur=evaluation.loc[(evaluation.index>=day)&(evaluation.index<day_end)].copy()
            if len(cur):
                recent=accepted.loc[accepted.index>=day-pd.Timedelta(days=14)]
                train=pd.concat([fixed,recent]).loc[lambda x:~x.index.duplicated(keep="last")]
                params=robust_params(train,features,conditioned)
                cur["score"]=score(cur,features,conditioned,aggregate,params)
                acc=np.zeros(len(cur),bool)
                for i,(t,v,ok) in enumerate(zip(cur.index,cur.score,cur.stable)):
                    if not ok or not np.isfinite(v): continue
                    if v>=4.0:
                        quarantine=max(quarantine,t+pd.Timedelta(hours=2)); continue
                    if t>=quarantine: acc[i]=True
                cur["accepted"]=acc; cur["epoch"]=epoch; pieces.append(cur[["stable","score","epoch"]])
                accepted=pd.concat([accepted,cur.loc[acc]])
            day=day_end
    return pd.concat(pieces).sort_index()


def eventize(scored: pd.DataFrame, threshold: float):
    events=[]; active=False; enter=exitc=0; cooldown=0; start=None; prev_epoch=None; last=None
    for t,row in scored.iterrows():
        if prev_epoch is not None and row.epoch!=prev_epoch:
            if active: events.append((start,last+pd.Timedelta(minutes=1)))
            active=False; enter=exitc=cooldown=0; start=None
        v=row.score; ok=bool(row.stable) and np.isfinite(v); high=ok and v>threshold; low=ok and v<.8*threshold
        if active:
            if low:
                exitc+=1
                if exitc>=10: events.append((start,t+pd.Timedelta(minutes=1))); active=False; start=None; enter=exitc=0; cooldown=30
            else: exitc=0
        else:
            if cooldown>0: cooldown-=1; enter=0
            elif high:
                enter+=1
                if enter>=5: active=True; start=t; enter=exitc=0
            else: enter=0
        prev_epoch=row.epoch; last=t
    if active: events.append((start,last+pd.Timedelta(minutes=1)))
    return events


def classify(events):
    timely=late=0; used=set(); details=[]
    for name,fs,fe in FAULTS:
        a=[(i,s,e) for i,(s,e) in enumerate(events) if fs-pd.Timedelta(minutes=60)<=s<=fs+pd.Timedelta(minutes=60)]
        b=[(i,s,e) for i,(s,e) in enumerate(events) if fs+pd.Timedelta(minutes=60)<s<=fe]
        if a: i,s,e=min(a,key=lambda x:x[1]); timely+=1; used.add(i); status="timely"
        elif b: i,s,e=min(b,key=lambda x:x[1]); late+=1; used.add(i); status="late"
        else: status="miss"
        details.append(f"{name}:{status}")
    return timely,late,4-timely-late,len(events)-len(used),";".join(details)


def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument("--output-dir",type=Path,default=OUT); args=ap.parse_args(); args.output_dir.mkdir(parents=True,exist_ok=True)
    m=minute_features(); variants=[
        ("V0_conditioned_derived_top3",True,True,"top3_rms"),
        ("V1_no_conditioning",False,True,"top3_rms"),
        ("V2_no_derived",True,False,"top3_rms"),
        ("V3_max_aggregation",True,True,"max"),]
    rows=[]
    for name,cond,derived,agg in variants:
        feats=ANALOG+(DERIVED if derived else [])+DUTY
        scored=walk_forward(m,feats,cond,agg); ev=eventize(scored,THRESHOLD)
        timely,late,miss,false,status=classify(ev)
        rows.append(dict(variant=name,conditioned=cond,derived_features=derived,aggregation=agg,threshold=THRESHOLD,
                         scored_minutes=len(scored),alarm_events=len(ev),timely=timely,late=late,miss=miss,false_alarm_events=false,event_status=status,
                         score_p99=float(np.nanquantile(scored.score,.99)),score_max=float(np.nanmax(scored.score))))
    out=pd.DataFrame(rows); out.to_csv(args.output_dir/"ablation_repro.csv",index=False,encoding="utf-8-sig",float_format="%.6f")
    base=out.iloc[0]; noc=out.iloc[1]; nod=out.iloc[2]; mx=out.iloc[3]
    display=out[["variant","alarm_events","timely","late","miss","false_alarm_events","event_status"]]
    md=[
        "# Q6：检测消融独立复核", "", "## 简化链路", "",
        "- 从 `data/metropt3/metropt3.csv` 独立聚合分钟中位数；工况由 Motor current 与 DV electric 分为 stopped/unloaded/loaded。",
        "- 特征：7 个模拟量、`TP3-Reservoirs`、`TP3-H1`，以及 60 分钟三工况占比和切换次数；`V2` 仅去掉两个压力差派生特征。",
        "- 每个维护 epoch 用首 7 天固定校准，并每日 walk-forward；历史窗 14 天，分数≥4 后隔离 2 小时；鲁棒 median/IQR 标准化。",
        "- 聚合：默认最大三个 |z| 的 RMS；`V3` 改为单通道 max|z|。",
        "- 为隔离开关影响，四个变体共用阈值 6.0；事件机为连续 5 点进入、连续 10 点低于 0.8×阈值退出、冷却 30 分钟；命中窗为故障前后 60 分钟，之后至故障结束算 late。",
        "- 这是 Codex 简化/自有链路，不复用 DSH 的分数；因此只检验方向，不要求复现 DSH 数字。", "", "## 实测结果", "", display.to_markdown(index=False), "", "## 对两条指定结论的判定", "",
        f"1. **‘不做工况条件化会 0 告警’未复现，得到反例。** V1 仍有 {int(noc.alarm_events)} 个告警、timely={int(noc.timely)}；相对 V0 的 {int(base.alarm_events)} 个告警确实下降，但并非完全失效。说明‘0 告警’依赖 DSH 的具体尺度、特征和阈值，不能提升为跨实现定律。",
        f"2. **‘去掉 TP3-Reservoirs、TP3-H1 后 timely 归零’未复现，得到反例。** V2 timely={int(nod.timely)}，与 V0 的 {int(base.timely)} 相同，且事件状态均为 F2/F3 timely。两个派生特征在 DSH 链路中重要，但本实现的原始 TP3/H1/Reservoirs 已保留等价信息，多变量聚合并不必然依赖显式差值。",
        f"3. **聚合方式方向与 DSH 一致。** max|z| 将 timely 从 {int(base.timely)} 降至 {int(mx.timely)}，误报从 {int(base.false_alarm_events)} 升至 {int(mx.false_alarm_events)}。", "", "## 解释与边界", "",
        "本反例不是说工况条件化或派生特征无用，而是说明两条强表述对实现敏感：无工况模型仍可被跨工况尺度和其他通道触发；显式差值被删除后，原始三压力通道仍允许 top-3 聚合响应同一物理变化。四个官方故障窗使 timely 每次变化 25%，证据量很小。建议将冻结表述收窄为‘在 DSH 当前链路/阈值下观察到’，并在共同阈值与各自重新标定阈值两种公平口径下重复消融。", "", "机器可读明细：`ablation_repro.csv`。",
    ]
    (args.output_dir/"ablation_repro.md").write_text("\n".join(md)+"\n",encoding="utf-8")
    print(out.to_string(index=False)); return 0

if __name__=="__main__": raise SystemExit(main())
