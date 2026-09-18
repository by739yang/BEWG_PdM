# -*- coding: utf-8 -*-
"""在冻结分母（双方掩码交集）上重算 DSH 侧 MetroPT-3 指标"""
import numpy as np, pandas as pd, json, os
OUT='results/2026-09-18/dsh'; os.makedirs(OUT,exist_ok=True)
FW=json.load(open('docs/metropt3_fault_windows.json',encoding='utf-8'))
fw=[(pd.Timestamp(x['start']),pd.Timestamp(x['end'])) for x in FW['windows']]
sc=pd.read_csv('results/2026-09-16/dsh/metropt3_score_minutes_dsh.csv.gz',index_col=0,parse_dates=True)['score']
J=pd.read_csv(os.path.join(OUT,'minute_mask_intersection.csv.gz'),parse_dates=['ts'])
J=J.merge(sc.rename('score'),left_on='ts',right_index=True,how='left')
fault=np.zeros(len(J),bool)
for a,b in fw: fault |= np.asarray((J.ts>=a)&(J.ts<=b))
base=(J.B_ds&J.B_cx&J.fin_ds&J.fin_cx&(~fault)&J.stable_ds&J.stable_cx).values
run =(base&J.run_ds&J.run_cx).values
print('冻结分母：all_stable %d 分钟（%.1f 小时）| running %d 分钟（%.1f 小时）| 交集总分钟 %d'
      % (base.sum(), base.sum()/60, run.sum(), run.sum()/60, len(J)))
def events(thr, ENTER=5, EXIT=10, RATIO=0.8, COOL=30):
    sv=np.nan_to_num(J.score.values,nan=0.0); over=sv>thr; n=len(sv)
    ev=[]; st=0; r=0; s0=0; last=-10**9
    for t in range(n):
        if st==0:
            if t<last+COOL: r=0
            elif over[t]:
                r+=1
                if r>=ENTER: s0=t; st=1; r=0
            else: r=0
        else:
            if sv[t]<RATIO*thr:
                r+=1
                if r>=EXIT: ev.append((s0,t+1)); last=t+1; st=0; r=0
            else: r=0
    if st==1: ev.append((s0,n))
    return ev
ts=J.ts.values
def cls(ev):
    out=[]
    for g0,g1 in fw:
        t0=[s for s,e in ev if g0-pd.Timedelta(minutes=60)<=J.ts.iloc[s]<=g0+pd.Timedelta(minutes=60)]
        lt=[s for s,e in ev if g0+pd.Timedelta(minutes=60)<J.ts.iloc[s]<=g1]
        out.append(dict(truth=str(g0),timely=bool(t0),late=bool(lt and not t0),
            delay=(J.ts.iloc[t0[0]]-g0).total_seconds()/60 if t0 else None))
    return out
def ev_metrics(thr):
    ev=events(thr); c=cls(ev)
    fp=sum(1 for s,e in ev if not any(g0-pd.Timedelta(minutes=60)<=J.ts.iloc[s]<=g1 for g0,g1 in fw))
    alarm=np.zeros(len(J),bool)
    for s,e in ev: alarm[s:min(e,len(J))]=True
    return dict(threshold=round(float(thr),4),alarm_events=len(ev),
        timely=sum(x['timely'] for x in c),late=sum(x['late'] for x in c),
        miss=sum((not x['timely']) and (not x['late']) for x in c),
        timely_recall=round(sum(x['timely'] for x in c)/len(fw),3),fp_events=fp,
        fp_per_hour_all_stable=round(fp/max(base.sum()/60,1e-9),4),
        fp_per_hour_running=round(fp/max(run.sum()/60,1e-9),4),
        tia_all_stable=round(float((alarm&base).sum())/max(base.sum(),1),4),
        tia_running=round(float((alarm&run).sum())/max(run.sum(),1),4),
        delay_timely_min=[x['delay'] for x in c if x['timely']])
cal=sc.loc[:str(fw[0][0]-pd.Timedelta(hours=12))].iloc[12*60:]
main=float(cal.quantile(0.995))
rows=[]
for q in np.linspace(0.90,0.9999,30):
    r=ev_metrics(float(cal.quantile(q))); r.pop('delay_timely_min'); rows.append(r)
D=pd.DataFrame(rows); D.to_csv(os.path.join(OUT,'metropt3_det_frozen_dsh.csv'),index=False,encoding='utf-8-sig')
R=ev_metrics(main)
json.dump(dict(frozen_denominator=dict(all_stable_minutes=int(base.sum()),running_minutes=int(run.sum())),
   main_threshold=R,det_best=dict(D.loc[D.timely_recall.idxmax(),['threshold','timely_recall','fp_per_hour_all_stable','tia_all_stable']])),
   open(os.path.join(OUT,'metropt3_metrics_frozen_dsh.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
print('主阈值 %.3f：timely %d / late %d / miss %d，误报 %d 次，%.4f 次/全稳定小时，TIA-H %.1f%%'
      % (main,R['timely'],R['late'],R['miss'],R['fp_events'],R['fp_per_hour_all_stable'],R['tia_all_stable']*100))
best=D.sort_values(['timely_recall','fp_per_hour_all_stable'],ascending=[False,True]).iloc[0]
print('DET 最佳：阈值 %.3f，timely %d/4，误报 %.4f 次/全稳定小时，TIA-H %.1f%%'
      % (best.threshold,best.timely,best.fp_per_hour_all_stable,best.tia_all_stable*100))
print('（对照：未冻结前我报的是 timely 2/4 @误报 0.0907）')
