# -*- coding: utf-8 -*-
"""决策层 v2（DSH）：修正 RUL 口径——失败阈值改为故障窗峰值分数的高分位，并要求分数持续上升"""
import numpy as np, pandas as pd, json, os
OUT='results/2026-09-18/dsh'
FW=json.load(open('docs/metropt3_fault_windows.json',encoding='utf-8'))
fw=[(pd.Timestamp(x['start']),pd.Timestamp(x['end'])) for x in FW['windows']]
sc=pd.read_csv('results/2026-09-16/dsh/metropt3_score_minutes_dsh.csv.gz',index_col=0,parse_dates=True)['score']
J=pd.read_csv(os.path.join(OUT,'minute_mask_intersection.csv.gz'),parse_dates=['ts'])
J=J.merge(sc.rename('score'),left_on='ts',right_index=True,how='left')
fault=np.zeros(len(J),bool)
for a,b in fw: fault |= np.asarray((J.ts>=a)&(J.ts<=b))
sv=np.nan_to_num(J.score.values,nan=0.0)
THR=2.395
# ---- 失败阈值：四个故障窗各自峰值 -> 取均值与最小值的折中（写清口径）----
peaks=[]
for a,b in fw:
    m=(np.asarray(J.ts>=a)&np.asarray(J.ts<=b))
    peaks.append(float(sv[m].max()) if m.any() else np.nan)
peaks=[p for p in peaks if not np.isnan(p)]
thr_fail=float(np.mean(peaks))
print('各故障窗峰值:', [round(p,2) for p in peaks])
print('失败阈值(峰值均值) = %.2f  ｜ 告警阈值 = %.2f' % (thr_fail, THR))
def events(thr,ENTER=5,EXIT=10,RATIO=0.8,COOL=30):
    over=sv>thr; n=len(sv); ev=[]; st=0; r=0; s0=0; last=-10**9
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
ev=events(THR)
rows=[]
for (s0,e0) in ev:
    t0,t1=J.ts.iloc[s0],J.ts.iloc[min(e0,len(J)-1)]
    i0=J.ts.searchsorted(t0-pd.Timedelta(hours=6))
    y=sv[i0:max(e0,s0+1)]
    if len(y)<10: slope=0.0
    else:
        x=np.arange(len(y),dtype=float); x=x-x.mean(); slope=float((x*(y-y.mean())).sum()/(x*x).sum())
    cur=float(sv[min(e0-1,len(J)-1)])
    rising=slope>1e-3 and cur>THR
    rul_h=((thr_fail-cur)/slope/60.0) if rising else np.nan
    rows.append(dict(告警起点=str(t0),告警结束=str(t1),持续分钟=int((t1-t0).total_seconds()//60),
        峰值分数=round(float(sv[s0:e0].max()) if e0>s0 else 0.0,2), 结束分数=round(cur,2),
        趋势斜率每分=round(slope,4), 上升=bool(rising),
        RUL估计小时=None if np.isnan(rul_h) else round(float(max(0,min(720,rul_h))),1)))
D=pd.DataFrame(rows)
got=D.RUL估计小时.notna().sum()
print('告警 %d 个；满足"上升"条件 %d 个；RUL 可得 %d 个' % (len(D), int(D.上升.sum()), int(got)))
print('RUL 分位（小时）:', {k: round(float(v),1) for k,v in D.RUL估计小时.dropna().quantile([.25,.5,.75]).items()} if got else '无')
D.to_csv(os.path.join(OUT,'decision_layer_v2_alarms.csv'),index=False,encoding='utf-8-sig')
json.dump(dict(告警阈值=THR,失败阈值=round(thr_fail,2),各窗峰值=[round(p,2) for p in peaks],
    告警数=int(len(D)),满足上升条件=int(D.上升.sum()),RUL可得=int(got),
    口径说明='失败阈值=四个官方故障窗内峰值分数的均值；RUL=(失败阈值-当前分数)/6小时趋势斜率，要求斜率>0且当前分数>告警阈值',
    局限='真值事件仅 4 个，峰值均值属粗估；RUL 为经验代理，非物理寿命模型'),
    open(os.path.join(OUT,'decision_layer_v2_summary.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
print(D.head(5).to_string(index=False))
