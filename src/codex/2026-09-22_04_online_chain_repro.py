#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Q17: independent online gate + causal RUL reproduction with timestamp windows."""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src/dsh'))
from dual_baseline import dual_detect, frozen_z, topk_score, _scale_floor
OUT=ROOT/'results/2026-09-22/codex'
DIRS=[ROOT/'results/2026-09-20/dsh',ROOT/'results/2026-09-21/dsh']
CH=['SO3','SO4','SO5','SNH_eff','Ntot_eff','TSS_eff','sludge_h']
TRAJ=[('baseline_start20','bsm1_120d_baseline.csv','bsm1_120d_degraded.csv',20.0),
      ('start40','bsm1_120d_baseline.csv','bsm1mt_start40.csv',40.0),
      ('start60','bsm1_120d_baseline.csv','bsm1mt_start60.csv',60.0),
      ('phase3','bsm1_120d_baseline.csv','bsm1mt_phase3.csv',20.0),
      ('phase7','bsm1_120d_baseline.csv','bsm1mt_phase7.csv',20.0),
      ('standard40','bsm1std_baseline.csv','bsm1std_degraded.csv',20.0),
      ('fast80_40d','bsm1_120d_baseline.csv','bsm1_sweep_keep20_ramp040.csv',20.0)]


def path(name):
    for d in DIRS:
        p=d/name
        if p.exists(): return p
    raise FileNotFoundError(name)


def prep(name):
    x=pd.read_csv(path(name)); x.index=pd.to_datetime(x.t_day*86400,unit='s'); return x


def gate(score,mech,t0):
    now=(score.index>t0-pd.Timedelta('3D'))&(score.index<=t0)
    ref=(score.index>=t0-pd.Timedelta('30D'))&(score.index<=t0-pd.Timedelta('3D'))
    sn=float(score[now].median()); sr=float(score[ref].median())
    mn=float(mech[now].median()); mr=float(mech[ref].median())
    sratio=sn/sr if np.isfinite(sr) and sr>0 else np.nan
    mratio=mn/mr if np.isfinite(mr) and mr>0 else np.nan
    S1=bool(np.isfinite(sratio) and sratio>1.25); M1=bool(np.isfinite(mratio) and mratio<.85)
    return S1,M1,S1 and M1,sratio,mratio


def exp_rul(mech,start,end,target=.5):
    y=mech.loc[(mech.index>=start)&(mech.index<=end)].dropna()
    y=y[y>0]
    if len(y)<20: return None
    x=(y.index-y.index[0]).total_seconds()/86400.0
    b,a=np.polyfit(np.asarray(x,float),np.log(y.to_numpy(float)),1)
    if b>=-1e-9: return None
    cross=(np.log(target)-a)/b
    return float(max(cross-float(x[-1]),0.0))


def main():
    rows=[]
    for tag,bf,df,deg_start in TRAJ:
        B,D=prep(bf),prep(df); ref=B[(B.t_day>=30)&(B.t_day<45)]; floor=_scale_floor(B,CH)
        state=((D.t_day*24)%24).astype(int).to_numpy(); rs=((ref.t_day*24)%24).astype(int).to_numpy()
        sf=pd.Series(np.asarray(topk_score(frozen_z(D,CH,ref,state=state,state_ref=rs,floor=floor),3),float).ravel(),index=D.index)
        res=dual_detect(D,CH,D.t_day<deg_start,win_days=2.0,k=3,
                        ref_mask_frozen=(B.t_day>=30)&(B.t_day<45),ref_data_frozen=ref,
                        state_frozen=state,state_ref_frozen=rs)
        A=res['alarms']; candidates=[]
        for channel in ('adaptive','frozen'):
            g=A[A.channel==channel] if len(A) else A
            for t in g.t:
                if float(D.loc[t,'t_day'])>deg_start:
                    candidates.append((t,channel)); break
        if not candidates:
            rows.append(dict(track=tag)); continue
        t0,channel=min(candidates,key=lambda z:z[0]); alarm=float(D.loc[t0,'t_day'])
        mech=pd.Series(D.SO3.to_numpy(float),index=D.index)
        S1,M1,attach,sratio,mratio=gate(sf,mech,t0)
        bad=(mech<.5).astype(float).rolling('1D',min_periods=24).mean()
        hits=D.loc[(bad>=1.0)&(D.t_day>deg_start)]
        fail=None if hits.empty else float(hits.t_day.iloc[0]); truth=None if fail is None else fail-alarm
        online=exp_rul(mech,t0-pd.Timedelta('5D'),t0) if attach else None
        retro=None
        if attach and fail is not None:
            tf=D.index[np.argmin(np.abs(D.t_day.to_numpy()-fail))]
            retro=exp_rul(mech,t0,tf)
        rows.append(dict(track=tag,first_channel=channel,alarm_day=alarm,S1=S1,M1=M1,attach_rul=attach,
                         score_ratio=sratio,mechanism_ratio=mratio,online_rul=online,true_rul=truth,
                         abs_error=(None if online is None or truth is None else abs(online-truth)),retro_rul=retro))
    out=pd.DataFrame(rows); out.to_csv(OUT/'q17_online_chain.csv',index=False,encoding='utf-8-sig',float_format='%.6f')
    print(out.to_string(index=False)); print('attach',int(out.attach_rul.fillna(False).sum()),'online',int(out.online_rul.notna().sum()))

if __name__=='__main__': main()

