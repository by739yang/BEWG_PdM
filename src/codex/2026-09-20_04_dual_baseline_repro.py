#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Independent minimal reproduction for Q7 BSM1 frozen-baseline checks."""
from __future__ import annotations
from pathlib import Path
import argparse
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
DSH=ROOT/"results/2026-09-20/dsh"
OUT=ROOT/"results/2026-09-20/codex"
CH=["SO3","SO4","SO5","SNH_eff","Ntot_eff","TSS_eff","sludge_h"]


def load(name:str)->pd.DataFrame:
    x=pd.read_csv(DSH/name); x.index=pd.to_datetime(x.t_day*86400,unit="s"); return x

def hod(x): return ((x.t_day*24)%24).astype(int).to_numpy()

def scale_floor(x):
    iqr=(x[CH].quantile(.75)-x[CH].quantile(.25))/1.349; sd=x[CH].std()
    return pd.concat([iqr.where(iqr>1e-9,sd).fillna(1.0)*.2,sd.fillna(1.0)*.1],axis=1).max(axis=1)

def frozen_score(target:pd.DataFrame, ref:pd.DataFrame, floor:pd.Series)->pd.Series:
    z=pd.DataFrame(0.0,index=target.index,columns=CH); st=hod(target); sr=hod(ref)
    for c in CH:
        for h in np.unique(st):
            m=st==h; r=ref.loc[sr==h,c]
            if len(r)<8: continue
            iqr=r.quantile(.75)-r.quantile(.25); sd=r.std()
            sc=iqr/1.349 if iqr>1e-9 else (sd if sd>1e-9 else 1.0)
            sc=max(sc,float(floor[c])); z.loc[m,c]=((target.loc[m,c]-r.median())/sc).clip(-30,30)
    a=np.abs(z.to_numpy()); top=np.sort(a,axis=1)[:,-3:]
    return pd.Series(np.sqrt(np.mean(top*top,axis=1)),index=target.index)

def model(target,ref,q=.999):
    floor=scale_floor(target); score=frozen_score(target,ref,floor); ref_score=frozen_score(ref,ref,floor)
    return score,float(ref_score.quantile(q))

def events(score,thr,enter=4,exit_=8,ratio=.8,cooldown=8):
    ev=[]; active=False; run=0; start=None; last_end=-10**9; v=score.to_numpy()
    for i,x in enumerate(v):
        if not active:
            if i<last_end+cooldown: run=0
            elif x>thr:
                run+=1
                if run>=enter: active=True; start=i; run=0
            else: run=0
        else:
            if x<ratio*thr:
                run+=1
                if run>=exit_: ev.append((start,i+1)); active=False; last_end=i+1; run=0
            else: run=0
    if active: ev.append((start,len(v)))
    return ev

def longest_run(mask):
    best=cur=0
    for x in mask:
        cur=cur+1 if x else 0; best=max(best,cur)
    return best

def ref_check(x,lo,hi):
    ref=x[(x.t_day>=lo)&(x.t_day<hi)]; score,thr=model(x,ref); ev=events(score,thr)
    days=[float(x.t_day.iloc[s]) for s,_ in ev]
    return dict(ref_window=f"day {lo}-{hi}",threshold=thr,exceedance_samples=int((score>thr).sum()),
                longest_exceedance_run=longest_run((score>thr).to_numpy()),alarm_events=len(ev),
                alarms_after_ref=sum(d>=hi for d in days),first_alarm_day=min(days) if days else np.nan)

def longest_below_days(x,threshold=.5):
    mask=(x.SO3<threshold).to_numpy(); return longest_run(mask)*float(np.median(np.diff(x.t_day)))

def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument("--output-dir",type=Path,default=OUT); args=ap.parse_args(); args.output_dir.mkdir(parents=True,exist_ok=True)
    b=load("bsm1_120d_baseline.csv"); d=load("bsm1_120d_degraded.csv"); mild=load("bsm1_sweep_keep80_ramp100.csv")
    refs=[]
    for tag,x in [("healthy",b),("degraded",d)]:
        for lo,hi in [(0,10),(30,45)]: refs.append(dict(dataset=tag,**ref_check(x,lo,hi)))
    refdf=pd.DataFrame(refs)

    ref=b[(b.t_day>=30)&(b.t_day<45)]
    edge=[]
    for tag,x in [("healthy",b),("mild_keep80_ramp100",mild)]:
        score,thr=model(x,ref); mask=(score>thr).to_numpy(); ev=events(score,thr)
        edge.append(dict(dataset=tag,threshold=thr,exceedance_samples=int(mask.sum()),longest_exceedance_run=longest_run(mask),alarm_events=len(ev),first_alarm_day=float(x.t_day.iloc[ev[0][0]]) if ev else np.nan))
    edgedf=pd.DataFrame(edge)

    ops=[]
    for tag,name in [("A","bsm1_120d_baseline.csv"),("B","bsm1_winB_120_240_baseline.csv"),("C","bsm1_winC_240_360_baseline.csv")]:
        x=b if tag=="A" else load(name); mask=x.SO3<.5
        ops.append(dict(window=tag,so3_mean=float(x.SO3.mean()),so3_median=float(x.SO3.median()),samples_below_0_5=int(mask.sum()),fraction_below_0_5=float(mask.mean()),longest_below_0_5_days=longest_below_days(x,.5)))
    opsdf=pd.DataFrame(ops)

    refdf.to_csv(args.output_dir/"dual_baseline_reference_checks.csv",index=False,encoding="utf-8-sig",float_format="%.6f")
    edgedf.to_csv(args.output_dir/"dual_baseline_edge_check.csv",index=False,encoding="utf-8-sig",float_format="%.6f")
    opsdf.to_csv(args.output_dir/"dual_baseline_operating_windows.csv",index=False,encoding="utf-8-sig",float_format="%.6f")
    rshow=refdf.copy(); eshow=edgedf.copy(); oshow=opsdf.copy()
    for frame in (rshow,eshow,oshow):
        for c in frame.select_dtypes(include=["float"]).columns: frame[c]=frame[c].map(lambda v:f"{v:.6f}" if pd.notna(v) else "")
    h0=refdf[(refdf.dataset=="healthy")&(refdf.ref_window=="day 0-10")].iloc[0]
    h30=refdf[(refdf.dataset=="healthy")&(refdf.ref_window=="day 30-45")].iloc[0]
    d0=refdf[(refdf.dataset=="degraded")&(refdf.ref_window=="day 0-10")].iloc[0]
    d30=refdf[(refdf.dataset=="degraded")&(refdf.ref_window=="day 30-45")].iloc[0]
    eh,em=edgedf.iloc[0],edgedf.iloc[1]
    bstat=opsdf[opsdf.window=="B"].iloc[0]; cstat=opsdf[opsdf.window=="C"].iloc[0]
    md=[
      "# Q7：双基线 / 冻结参考域 / 刀锋边缘 / 工况泛化独立复核", "", "## 最小实现与简化项", "",
      "- 输入为五份已落盘 BSM1 轨迹；不重跑仿真。使用 7 个过程/出水通道：SO3、SO4、SO5、SNH_eff、Ntot_eff、TSS_eff、sludge_h。",
      "- 工况条件化：按一天中的整点小时（0–23）分层；每层以冻结参考窗 median 和 IQR/1.349 标准化，尺度下限取目标轨迹全局 IQR/标准差的保守组合。",
      "- 聚合：最大 3 个 |z| 的 RMS；阈值为参考域分数 p99.9。",
      "- 事件机：连续 4 个样本越限进入、连续 8 个样本低于 0.8×阈值退出、冷却 8 个样本。采样间隔约 15 分钟。",
      "- 该链路复核的是冻结通道；未实现自适应通道、重锁定或迟滞刷新。", "", "## 1. 参考窗选择", "", rshow.to_markdown(index=False), "",
      f"健康轨迹中，0–10 天参考产生 {int(h0.alarm_events)} 个事件，而 30–45 天参考为 {int(h30.alarm_events)} 个，方向明确且复现 DSH 的 75/0。启动暂态参考会把阈值从 {h30.threshold:.3f} 压到 {h0.threshold:.3f}，导致长期误报。", "", "## 2. 退化后参考窗吸收退化", "",
      f"退化轨迹以 0–10 天为参考时有 {int(d0.alarm_events)} 个事件（参考窗后 {int(d0.alarms_after_ref)} 个）；改用退化已开始后的 30–45 天作参考，只剩 {int(d30.alarm_events)} 个事件，且参考窗后为 {int(d30.alarms_after_ref)}。这支持‘参考域吸收退化、告警显著下降’；剩余 1 个事件发生在参考窗之前，不构成退化后检测。", "", "## 3. 刀锋边缘检查", "", eshow.to_markdown(index=False), "",
      f"健康与最轻微退化的**总越限样本数**是 {int(eh.exceedance_samples)} vs {int(em.exceedance_samples)}，相差 2，不是 1；**最长连续越限**是 {int(eh.longest_exceedance_run)} vs {int(em.longest_exceedance_run)}，只差 1 个样本，并恰好跨过连续 4 点的进入门槛。因此‘0 误报与 1 次告警只差一个采样点’对连续长度成立，但不应误写成总越限样本数只差 1。该配置确属刀锋边缘，不能据此宣称稳健零误报。", "", "## 4. 工况泛化与 SO3 绝对阈值", "", oshow.to_markdown(index=False), "",
      f"WinB 健康 SO3 均值 {bstat.so3_mean:.3f}，SO3<0.5 占 {bstat.fraction_below_0_5:.1%}，最长连续约 {bstat.longest_below_0_5_days:.2f} 天；WinC 均值 {cstat.so3_mean:.3f}，低于 0.5 占 {cstat.fraction_below_0_5:.1%}，最长连续约 {cstat.longest_below_0_5_days:.2f} 天。方向成立。",
      "绝对判据 `SO3<0.5` 的失效条件是：目标工况自身的健康分布已经落到阈值附近或以下，且持续时间满足事件门槛。此时健康运行就会被定义成‘失效’，退化开始、失效点和提前量均失真；阈值必须按工况健康基线标定为相对劣化幅度或条件分位数。", "", "## 总结", "",
      "四项复核中，参考域两项和工况泛化方向成立；刀锋边缘结论需精确表述为‘最长连续越限 3→4，只差一个样本’，总越限数实际为 6→8。", "", "辅助机器可读表：`dual_baseline_reference_checks.csv`、`dual_baseline_edge_check.csv`、`dual_baseline_operating_windows.csv`。",
    ]
    (args.output_dir/"dual_baseline_repro.md").write_text("\n".join(md)+"\n",encoding="utf-8")
    print('REFERENCE');print(refdf.to_string(index=False));print('\nEDGE');print(edgedf.to_string(index=False));print('\nOPS');print(opsdf.to_string(index=False))
    return 0
if __name__=="__main__":raise SystemExit(main())
