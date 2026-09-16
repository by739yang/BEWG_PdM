# -*- coding: utf-8 -*-
"""MetroPT-3 v2 评估（口径对齐版）：官方故障窗口 + 两种分母同时报告 + 30 点 DET"""
import pandas as pd, numpy as np, os, json
OUT='results/2026-09-16/dsh'
FW=json.load(open('data/metropt3/fault_windows.json',encoding='utf-8'))
fw=[(pd.Timestamp(x['start']),pd.Timestamp(x['end'])) for x in FW['windows']]
sc=pd.read_csv(os.path.join(OUT,'metropt3_score_minutes_dsh.csv.gz'),index_col=0,parse_dates=True)['score']
idx=sc.index
d=pd.read_csv('data/metropt3/metropt3.csv',usecols=['timestamp','COMP','DV_eletric','Motor_current'],parse_dates=['timestamp']).set_index('timestamp')
m=d.resample('1min').agg({'Motor_current':'mean','COMP':'max','DV_eletric':'max'})
cur=m['Motor_current'].fillna(0); dve=m['DV_eletric'].fillna(0)
state=pd.Series(np.where(cur<1.0,'stopped',np.where(dve>=0.5,'loaded','unloaded')),index=m.index)
switch=(state.ne(state.shift(1))&state.shift(1).notna()).reindex(idx).fillna(False).values
st=state.reindex(idx).fillna('stopped').values
fault=np.zeros(len(idx),bool)
for a,b in fw: fault |= (idx>=a)&(idx<=b)
def run(thr):
    sv=sc.values; over=sv>thr; n=len(sv); ev=[]; s_=0; r=0; s0=0; last=-10**9
    for t in range(n):
        if s_==0:
            if t<last+30: r=0
            elif over[t]:
                r+=1
                if r>=5: s0=t; s_=1; r=0
            else: r=0
        else:
            if sv[t]<0.8*thr:
                r+=1
                if r>=10: ev.append((s0,t+1)); last=t+1; s_=0; r=0
            else: r=0
    if s_==1: ev.append((s0,n))
    return ev
def hit(s):
    ts=idx[s]
    for a,b in fw:
        if a-pd.Timedelta(hours=1)<=ts<=b: return (a,b)
    return None
def metrics(thr, denom):
    ev=run(thr); hits=[e for e in ev if hit(e[0])]
    covered={hit(s) for s,e in hits}
    usable=(~fault)&(~switch)&((st!='stopped') if denom=='running' else True)
    alarm=np.zeros(len(idx),bool)
    for s,e in ev: alarm[s:min(e,len(idx))]=True
    hm=usable.sum(); tia=(alarm&usable).sum()/max(hm,1)
    dl=[(idx[s]-hit(s)[0]).total_seconds()/60 for s,e in hits]
    return dict(denominator=denom, threshold=round(float(thr),4), true_events=len(fw), detected=len(covered),
        event_recall=round(len(covered)/len(fw),3), alarm_events=len(ev), fp_events=len(ev)-len(hits),
        usable_hours=round(hm/60,1), fp_per_healthy_hour=round((len(ev)-len(hits))/max(hm/60,1e-9),4),
        tia_h=round(float(tia),4), delay_min_median=round(float(np.median(dl)),1) if dl else None)
cal=sc.loc[:str(fw[0][0]-pd.Timedelta(hours=12))].iloc[12*60:]
thr_main=float(cal.quantile(0.995))
rows=[metrics(thr_main,'running'),metrics(thr_main,'all_stable')]
qs=np.linspace(0.90,0.9999,30); det=[]
for q in qs:
    for dn in ['running','all_stable']:
        det.append(metrics(float(cal.quantile(q)),dn))
D=pd.DataFrame(det)
D.to_csv(os.path.join(OUT,'metropt3_v2_det_aligned.csv'),index=False,encoding='utf-8-sig')
head=pd.DataFrame(rows)
head.insert(0,'note','主阈值=标定期0.995分位')
head.to_csv(os.path.join(OUT,'metropt3_v2_summary_aligned.csv'),index=False,encoding='utf-8-sig')
json.dump(dict(threshold_main=round(thr_main,3), official_windows_source=FW['source'],
   windows=[{'id':x['id'],'start':x['start'],'end':x['end']} for x in FW['windows']],
   main=head.to_dict('records')), open(os.path.join(OUT,'metropt3_v2_aligned.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
print('=== 主阈值（%.3f）下的两种分母 ===' % thr_main)
print(head.to_string(index=False))
for dn in ['running','all_stable']:
    sub=D[D.denominator==dn].sort_values('threshold')
    b=sub[(sub.event_recall==sub.event_recall.max())].sort_values('fp_per_healthy_hour').iloc[0]
    print('DET(%s)：最高召回 %.0f%% @阈值 %.2f，误报 %.4f/可用小时，TIA-H %.1f%%' % (
        dn, b.event_recall*100, b.threshold, b.fp_per_healthy_hour, b.tia_h*100))
