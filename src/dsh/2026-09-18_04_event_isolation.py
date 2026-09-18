# -*- coding: utf-8 -*-
"""切开实验：用 DSH 的事件机跑 Codex 的分数流，判断差异来自模型分数还是事件规则"""
import numpy as np, pandas as pd, json, os
OUT='results/2026-09-18/dsh'
FW=json.load(open('docs/metropt3_fault_windows.json',encoding='utf-8'))
fw=[(pd.Timestamp(x['start']),pd.Timestamp(x['end'])) for x in FW['windows']]
cx=pd.read_csv('results/2026-09-16/codex/metropt3_scored_minutes.csv.gz')
print('Codex 分数文件列：', list(cx.columns)[:8], '行数', len(cx))
tcol=[c for c in cx.columns if 'time' in c.lower()][0]; scol=[c for c in cx.columns if 'score' in c.lower()][0]
cx[tcol]=pd.to_datetime(cx[tcol]); cx=cx[[tcol,scol]].rename(columns={tcol:'ts',scol:'score'})
J=pd.read_csv(os.path.join(OUT,'minute_mask_intersection.csv.gz'),parse_dates=['ts'])
J=J.merge(cx,on='ts',how='left')
fault=np.zeros(len(J),bool)
for a,b in fw: fault |= np.asarray((J.ts>=a)&(J.ts<=b))
base=(J.B_ds&J.B_cx&J.fin_ds&J.fin_cx&(~fault)&J.stable_ds&J.stable_cx).values
print('合并后行数 %d，Codex 分数缺失 %d 分钟' % (len(J), int(J.score.isna().sum())))
def events(sv, thr, ENTER=5, EXIT=10, RATIO=0.8, COOL=30):
    sv=np.nan_to_num(sv,nan=0.0); over=sv>thr; n=len(sv); ev=[]; st=0; r=0; s0=0; last=-10**9
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
def report(sv, thr, label):
    ev=events(sv,thr)
    timely=late=0
    for g0,g1 in fw:
        t0=[s for s,e in ev if g0-pd.Timedelta(minutes=60)<=J.ts.iloc[s]<=g0+pd.Timedelta(minutes=60)]
        lt=[s for s,e in ev if g0+pd.Timedelta(minutes=60)<J.ts.iloc[s]<=g1]
        if t0: timely+=1
        elif lt: late+=1
    fp=sum(1 for s,e in ev if not any(g0-pd.Timedelta(minutes=60)<=J.ts.iloc[s]<=g1 for g0,g1 in fw))
    alarm=np.zeros(len(J),bool)
    for s,e in ev: alarm[s:min(e,len(J))]=True
    print('%s | 阈值 %.1f → 告警 %d 次，timely %d/4，late %d，误报 %d 次（%.4f/小时），TIA-H %.1f%%'
          % (label, thr, len(ev), timely, late, fp, fp/max(base.sum()/60,1e-9), 100*(alarm&base).sum()/max(base.sum(),1)))
    return dict(label=label,threshold=thr,alarm_events=len(ev),timely=timely,late=late,fp=fp,
                fp_per_hour=fp/max(base.sum()/60,1e-9),tia=float((alarm&base).sum())/max(base.sum(),1))
res=[]
print('=== 对照组：DSH 事件机 + DSH 分数 ===')
mysc=pd.read_csv('results/2026-09-16/dsh/metropt3_score_minutes_dsh.csv.gz',index_col=0,parse_dates=True)['score']
Jm=J.merge(mysc.rename('myscore'),left_on='ts',right_index=True,how='left')
res.append(report(Jm.myscore.values, 2.395, 'DSH机+DSH分'))
print()
print('=== 实验组：DSH 事件机 + Codex 分数 ===')
for thr in [2.0,4.0,6.0,10.0]:
    res.append(report(J.score.values, thr, 'DSH机+Codex分'))
print()
print('=== 参照：Codex 自报（其事件机 + 其分数）===')
print('Codex机+Codex分 | 阈值 6.0 → 告警 1006 次，timely 2/4，误报 1004 次（0.6257/小时），TIA-H 24.5%')
json.dump(res,open(os.path.join(OUT,'event_machine_isolation.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
