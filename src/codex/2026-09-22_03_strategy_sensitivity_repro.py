#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Q15: independent 45-cell combination-strategy sensitivity scan using time windows."""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src/dsh'))
from dual_baseline import frozen_z, topk_score, make_events, _scale_floor
OUT=ROOT/'results/2026-09-22/codex'
DIRS=[ROOT/'results/2026-09-20/dsh',ROOT/'results/2026-09-21/dsh']
CH=['SO3','SO4','SO5','SNH_eff','Ntot_eff','TSS_eff','sludge_h']
PAIRS=[
 ('A','bsm1_120d_baseline.csv','bsm1_120d_degraded.csv'),
 ('B','bsm1_winB_120_240_baseline.csv','bsm1_winB_120_240_degraded.csv'),
 ('C','bsm1_winC_240_360_baseline.csv','bsm1_winC_240_360_degraded.csv'),
 ('slow20','bsm1_120d_baseline.csv','bsm1_sweep_keep80_ramp100.csv'),
 ('slow40','bsm1_120d_baseline.csv','bsm1_sweep_keep60_ramp100.csv'),
 ('slow60','bsm1_120d_baseline.csv','bsm1_120d_degraded.csv'),
 ('slow80','bsm1_120d_baseline.csv','bsm1_sweep_keep20_ramp100.csv'),
 ('fast60','bsm1_120d_baseline.csv','bsm1_sweep_keep40_ramp040.csv'),
 ('fast80','bsm1_120d_baseline.csv','bsm1_sweep_keep20_ramp040.csv'),
 ('storm40','bsm1_R3_add_storm_baseline.csv','bsm1_R3_add_storm_degraded.csv'),
 ('standard40','bsm1std_baseline.csv','bsm1std_degraded.csv'),
 ('R1dry','bsm1_R1_dry_baseline.csv','bsm1_R1_dry_degraded.csv')]


def path(name):
    for d in DIRS:
        p=d/name
        if p.exists(): return p
    raise FileNotFoundError(name)


def prep(p):
    x=pd.read_csv(p); x.index=pd.to_datetime(x.t_day*86400,unit='s'); return x


def starts(mask,day,lo,hi):
    m=np.asarray(mask,bool)&(day>=lo)&(day<=hi); out=[]; active=False
    for i,v in enumerate(m):
        if v and not active: out.append(float(day[i])); active=True
        elif not v: active=False
    return out


def main():
    OUT.mkdir(parents=True,exist_ok=True); cache=[]
    for tag,bf,df in PAIRS:
        B,D=prep(path(bf)),prep(path(df)); ref=B[(B.t_day>=30)&(B.t_day<45)]
        floor=_scale_floor(B,CH)
        def score(X):
            state=((X.t_day*24)%24).astype(int).to_numpy()
            rs=((ref.t_day*24)%24).astype(int).to_numpy()
            return np.asarray(topk_score(frozen_z(X,CH,ref,state=state,state_ref=rs,floor=floor),3),float).ravel()
        sh,sd=score(B),score(D)
        rs=((ref.t_day*24)%24).astype(int).to_numpy()
        thr=float(np.quantile(np.asarray(topk_score(frozen_z(ref,CH,ref,state=rs,state_ref=rs,floor=floor),3),float).ravel(),.999))
        cache.append(dict(tag=tag,B=B,D=D,sh=sh,sd=sd,thr=thr,
                          eh=make_events(pd.Series(sh),thr),ed=make_events(pd.Series(sd),thr)))
    rows=[]
    for win in (1,3,5):
        for c in cache:
            # Hard requirement: actual datetime windows, never point-count windows.
            c[f'rh{win}']=pd.Series(c['sh'],index=c['B'].index).rolling(f'{win}D',min_periods=96).median().to_numpy()
            c[f'rd{win}']=pd.Series(c['sd'],index=c['D'].index).rolling(f'{win}D',min_periods=96).median().to_numpy()
            db=c['B'].t_day.to_numpy(); rh=c[f'rh{win}']
            c[f'base{win}']=float(np.nanmedian(rh[(db>=30)&(db<45)]))
        for kr in (1.15,1.25,1.40):
            for ka in (1.05,1.10,1.15,1.25,1.40):
                health_single=health_ratio=health_and=0; dsingle=[]; dratio=[]; dand=[]; dunion=[]
                for c in cache:
                    B,D=c['B'],c['D']; db=B.t_day.to_numpy(); dd=D.t_day.to_numpy()
                    rh,rd=c[f'rh{win}'],c[f'rd{win}']; base=c[f'base{win}']
                    hs=[float(db[i]) for i,e in c['eh'] if float(db[i])>=45]
                    ds=[float(dd[i]) for i,e in c['ed'] if float(dd[i])>20]
                    health_single += len(hs)
                    def elevated(r,d,x):
                        m=(d>=x-1)&(d<=x+1)&np.isfinite(r)
                        return bool(m.any() and np.nanmax(r[m])>ka*base)
                    ha=[x for x in hs if elevated(rh,db,x)]
                    da=[x for x in ds if elevated(rd,dd,x)]
                    health_and += len(ha)
                    hr=starts(rh>kr*base,db,45,120); dr=starts(rd>kr*base,dd,45,120)
                    health_ratio += len(hr)
                    if ds: dsingle.append(min(ds)-20)
                    if dr: dratio.append(min(dr)-20)
                    if da: dand.append(min(da)-20)
                    un=ds+dr
                    if un: dunion.append(min(un)-20)
                med=lambda x: None if not x else round(float(np.median(x)),1)
                rows.append(dict(window_days=win,k_and=ka,k_ratio=kr,
                                 health_single=health_single,health_ratio=health_ratio,
                                 health_union=health_single+health_ratio,health_and=health_and,
                                 detected_single=len(dsingle),detected_ratio=len(dratio),
                                 detected_union=len(dunion),detected_and=len(dand),
                                 delay_single=med(dsingle),delay_union=med(dunion),delay_and=med(dand)))
    out=pd.DataFrame(rows)
    out.to_csv(OUT/'q15_strategy_sensitivity.csv',index=False,encoding='utf-8-sig')
    print(out.to_string(index=False))

if __name__=='__main__': main()

