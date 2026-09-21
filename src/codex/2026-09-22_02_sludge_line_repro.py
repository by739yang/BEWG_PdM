#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Q16 independent sludge-line, detector, RUL, and placeholder-cost decision reproduction."""
from __future__ import annotations
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
DSH_SRC=ROOT/'src/dsh'
sys.path.insert(0,str(DSH_SRC))
from bsm2_python.bsm2 import thickener_bsm2 as T, dewatering_bsm2 as D
from bsm2_python.bsm2.init import thickenerinit_bsm2 as TI, dewateringinit_bsm2 as DI
from dual_baseline import frozen_z, topk_score, adaptive_z, make_events, _scale_floor

INP=ROOT/'results/2026-09-21/dsh/sludge_flow_healthy.csv.gz'
OUT=ROOT/'results/2026-09-22/codex'
QW=385.0
OBS=['wet_cake_m3d','filtrate_m3d','filtrate_tss','dry_solids_kgd','overflow_tss']


def build(deg_start=None,ramp_days=60.0):
    d=pd.read_csv(INP); cols=[c for c in d.columns if c.startswith('w_')]
    rows=[]
    for r in d.itertuples(index=False):
        t=float(r.t_day)
        f=0.0 if deg_start is None else min(1.0,max(0.0,(t-deg_start)/ramp_days))
        target=28.0+(18.0-28.0)*f; thick=7.0+(6.0-7.0)*f
        y=np.array([float(getattr(r,c)) for c in cols]); y[14]=QW
        tp=TI.THICKENERPAR.copy(); tp[0]=thick
        dp=DI.DEWATERINGPAR.copy(); dp[0]=target
        yt_u,yt_o=T.Thickener(tp).output(y); yc,yr=D.Dewatering(dp).output(yt_u)
        rows.append(dict(t_day=t,cake_solids_pct=float(yc[13])/10000.0,target_pct=target,
                         wet_cake_m3d=float(yc[14]),filtrate_m3d=float(yr[14]),
                         filtrate_tss=float(yr[13]),dry_solids_kgd=float(yc[13])*float(yc[14])/1000.0,
                         overflow_tss=float(yt_o[13]),thickened_pct=float(yt_u[13])/10000.0))
    x=pd.DataFrame(rows)
    x.index=pd.to_datetime((x.t_day*86400).round().astype('int64'),unit='s')
    return x


def detect(H,G,deg_start=60.0):
    ref=H.loc[(H.t_day>=30)&(H.t_day<45),OBS]
    floor=_scale_floor(H[OBS],OBS)
    state_h=H.index.hour.to_numpy(); state_g=G.index.hour.to_numpy(); state_ref=ref.index.hour.to_numpy()
    zref=frozen_z(ref,OBS,ref,state=state_ref,state_ref=state_ref,floor=floor)
    thr=float(np.quantile(np.asarray(topk_score(zref,3),float).ravel(),.999))
    zf=frozen_z(G[OBS],OBS,ref,state=state_g,state_ref=state_ref,floor=floor)
    sf=np.asarray(topk_score(zf,3),float).ravel()
    za_h=adaptive_z(H[OBS],OBS,win_days=2.0,state=state_h)
    za_g=adaptive_z(G[OBS],OBS,win_days=2.0,state=state_g)
    sa_h=np.asarray(topk_score(za_h,3),float).ravel(); sa_g=np.asarray(topk_score(za_g,3),float).ravel()
    mref=(H.t_day.to_numpy()>=30)&(H.t_day.to_numpy()<45)
    athr=float(np.quantile(sa_h[mref],.999))
    ans={}
    for name,score,t in [('frozen',sf,thr),('adaptive',sa_g,athr)]:
        ev=make_events(pd.Series(score),t)
        pre=sum(1 for s,e in ev if G.t_day.iloc[s]<=deg_start)
        post=[float(G.t_day.iloc[s]) for s,e in ev if G.t_day.iloc[s]>deg_start]
        ans[name]=dict(threshold=t,events=len(ev),pre_events=pre,first_post=(post[0] if post else None))
    return ans


def failure_day(G):
    bad=(G.cake_solids_pct<20.0).astype(float)
    one_day=bad.rolling('1D',min_periods=96).mean()
    hit=G.loc[(one_day>=1.0)&(G.t_day>60)]
    return None if hit.empty else float(hit.t_day.iloc[0])


def rul_at(G,alarm_day,window_days):
    x=G.loc[(G.t_day>=alarm_day-window_days)&(G.t_day<=alarm_day),['t_day','cake_solids_pct']]
    b,a=np.polyfit(x.t_day.to_numpy(float),x.cake_solids_pct.to_numpy(float),1)
    return None if b>=-1e-12 else max((20.0-(a+b*alarm_day))/b,0.0)


def legacy_point_rul(G,alarm_day,window_days):
    """Reproduce the DSH report's rounded-day -> 96-points/day indexing for comparison only."""
    f=round(float(alarm_day),2); i0=int(f*96); lo=max(0,i0-window_days*96)
    y=G.cake_solids_pct.to_numpy(float)[lo:i0+1]
    b,a=np.polyfit(np.arange(len(y),dtype=float),y,1)
    return None if b>=-1e-12 else max((20.0-a)/b-(len(y)-1),0.0)/96.0


def decision_table():
    # All amounts below are PLACEHOLDERS, not real monetary values.
    CP,CF,WASTE=8000.0,50000.0,60.0
    HORIZON,NUNIT,WINDOW,ALARM_DELAY,RUL_ERR=365.0,400,7.0,1.33,1.0
    rng=np.random.default_rng(7)
    def run(name,fixed_T=None,mode='fixed',min_gap=0.0):
        plan=fail=0; waste=0.0
        for _ in range(NUNIT):
            L=float(49.0*np.exp(rng.normal(0,.2))); t=0.0
            while t<HORIZON:
                if mode=='fixed':
                    act=t+fixed_T
                    if t+L<=act: fail+=1; t=t+L+.5
                    else: waste+=max(act-t-L,0); plan+=1; t=act
                elif mode=='alarm':
                    act=t+max(ALARM_DELAY,min_gap)
                    if act<t+L: plan+=1; waste+=max(L-(act-t),0); t=act
                    else: fail+=1; t=t+L+.5
                elif mode=='rul':
                    est=L-RUL_ERR; deadline=t+max(est-WINDOW,ALARM_DELAY); act=min(deadline,t+est)
                    if act<t+L: plan+=1; waste+=max(L-(act-t),0); t=act
                    else: fail+=1; t=t+L+.5
                else: fail+=1; t=t+L+.5
        cost=plan*CP+fail*CF+waste*WASTE
        return dict(policy=name,planned=plan,failures=fail,waste_days=waste,total_placeholder=cost,
                    per_unit_year_placeholder=cost/NUNIT)
    rows=[run('fixed30',30,'fixed'),run('fixed40',40,'fixed'),run('fixed49',49,'fixed'),run('fixed60',60,'fixed'),
          run('alarm30',mode='alarm',min_gap=30),run('alarm0',mode='alarm'),
          run('RUL',mode='rul'),run('failure',mode='fail')]
    return pd.DataFrame(rows)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    H=build(None); G=build(60.0,60.0)
    ref=(H.t_day>=30)&(H.t_day<45); end=G.t_day>=115
    wet0=float(H.loc[ref,'wet_cake_m3d'].median()); wet1=float(G.loc[end,'wet_cake_m3d'].median())
    dry0=float(H.loc[ref,'dry_solids_kgd'].median()); dry1=float(G.loc[end,'dry_solids_kgd'].median())
    wet_final_h=float(H.wet_cake_m3d.iloc[-1]); wet_final_g=float(G.wet_cake_m3d.iloc[-1])
    dry_final_h=float(H.dry_solids_kgd.iloc[-1]); dry_final_g=float(G.dry_solids_kgd.iloc[-1])
    fail=failure_day(G); det=detect(H,G); alarm=det['frozen']['first_post']
    ruls={f'rul_{w}d_time':rul_at(G,alarm,w) for w in (5,2,1)}
    ruls.update({f'rul_{w}d_legacy_points':legacy_point_rul(G,alarm,w) for w in (5,2,1)})
    dec=decision_table(); dec.to_csv(OUT/'q16_sludge_decision_repro.csv',index=False,encoding='utf-8-sig',float_format='%.6f')
    fixed=dec[dec.policy.str.startswith('fixed')].sort_values('total_placeholder').iloc[0]
    rul=dec[dec.policy=='RUL'].iloc[0]
    summary=dict(QW_m3d=QW,wet_healthy_ref_median=wet0,wet_degraded_late_median=wet1,
                 wet_cross_window_increase_pct=(wet1/wet0-1)*100,
                 wet_final_healthy=wet_final_h,wet_final_degraded=wet_final_g,
                 wet_same_time_increase_pct=(wet_final_g/wet_final_h-1)*100,
                 dry_healthy_ref_median=dry0,dry_degraded_late_median=dry1,
                 dry_cross_window_change_pct=(dry1/dry0-1)*100,
                 dry_final_healthy=dry_final_h,dry_final_degraded=dry_final_g,
                 dry_same_time_change_pct=(dry_final_g/dry_final_h-1)*100,
                 failure_day=fail,detector=det,true_rul=(fail-alarm),**ruls,
                 best_fixed=fixed.to_dict(),rul_policy=rul.to_dict(),
                 rul_saving_pct=(1-rul.total_placeholder/fixed.total_placeholder)*100)
    (OUT/'q16_sludge_repro.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,default=float),encoding='utf-8')
    pd.concat([H.assign(track='healthy'),G.assign(track='degraded')]).to_csv(OUT/'q16_sludge_line_repro.csv',index=False,encoding='utf-8-sig',float_format='%.8f')
    print(json.dumps(summary,ensure_ascii=False,indent=2,default=float))

if __name__=='__main__': main()

