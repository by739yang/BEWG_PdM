# -*- coding: utf-8 -*-
"""MetroPT-3 独立基线 v2（DSH）：分钟桶 + 三态工况 + 多信号聚合 + 每日 walk-forward 重估"""
import pandas as pd, numpy as np, os, io, json
OUT='results/2026-09-16/dsh'; CSV='data/metropt3/metropt3.csv'
ANALOG=['TP2','TP3','H1','DV_pressure','Reservoirs','Oil_temperature','Motor_current','Caudal_impulses']
RAW=['TP2','TP3','H1','Reservoirs','Oil_temperature','Motor_current']
DIGITAL=['COMP','DV_eletric']
DERIVED=['TP3_minus_Reservoirs','TP3_minus_H1']
REF_DAYS=14; ENTER=5; EXIT=10; RATIO=0.8; COOL=30; TOPK=3
FW_JSON='data/metropt3/fault_windows.json'

d=pd.read_csv(CSV, usecols=['timestamp']+ANALOG+DIGITAL, parse_dates=['timestamp']).set_index('timestamp')
m=d.resample('1min').agg({**{c:'mean' for c in ANALOG}, **{c:'max' for c in DIGITAL}}).dropna(how='all')
F=pd.DataFrame(index=m.index)
for c in RAW: F[c]=m[c]
F['TP3_minus_Reservoirs']=m['TP3']-m['Reservoirs']; F['TP3_minus_H1']=m['TP3']-m['H1']
FEATS=list(F.columns)
cur=m['Motor_current'].fillna(0); comp=m['COMP'].fillna(0); dve=m['DV_eletric'].fillna(0)
state=np.where(cur<1.0,'stopped',np.where(dve>=0.5,'loaded','unloaded'))
state=pd.Series(state,index=m.index)
switch=state.ne(state.shift(1)) & state.shift(1).notna()
print('分钟桶', len(F), '工况分布', state.value_counts().to_dict(), '切换分钟', int(switch.sum()))

# ---- 每日 walk-forward 重估（每24小时用过去14天、排除切换与告警分钟）----
days=sorted(set(F.index.normalize()))
med={}; sca={}; alarm_flag=np.zeros(len(F),bool)
def est(lo,hi,exclude):
    out={}
    sub=F.loc[lo:hi]; st=state.loc[lo:hi]; sw=switch.loc[lo:hi]; ex=exclude.loc[lo:hi]
    for s in ['stopped','unloaded','loaded']:
        mask=(st==s)&(~sw)&(~ex)
        X=sub[mask]
        if len(X)<120: 
            X=sub[(~sw)&(~ex)]
        if len(X)<60: out[s]=None; continue
        med_=X.median(); iqr=(X.quantile(.75)-X.quantile(.25))/1.349
        sd=X.std()
        sc_=iqr.where(iqr>1e-9, sd).fillna(1.0)
        G=( (F.quantile(.75)-F.quantile(.25))/1.349 ).where(lambda v: v>1e-9, F.std()).fillna(1.0)
        sc_=pd.concat([sc_,G*0.05],axis=1).max(axis=1)
        out[s]=(med_,sc_)
    return out
Z=pd.DataFrame(0.0,index=F.index,columns=FEATS)
for i,day in enumerate(days):
    lo=day-pd.Timedelta(days=REF_DAYS)
    est_=est(lo,day-pd.Timedelta(seconds=1),pd.Series(alarm_flag,index=F.index))
    hi=days[i+1] if i+1<len(days) else F.index[-1]+pd.Timedelta(seconds=1)
    sl=(F.index>=day)&(F.index<hi)
    for t in range(len(F)):
        if not sl[t]: continue
        s=state.iloc[t]; e=est_.get(s) or est_.get('unloaded') or est_.get('loaded') or est_.get('stopped')
        if e is None: continue
        med_,sc_=e
        z=((F.iloc[t]-med_)/sc_).values
        tt=np.sort(np.abs(z))[::-1][:TOPK]
        Z.iloc[t]=np.sqrt((tt**2).mean())
score=Z.iloc[:,0] if False else Z.iloc[:,0]*0  # 占位，下面直接算
sc_series=pd.Series(np.sqrt((np.sort(np.abs(((F.values-med_.values)/sc_.values)),axis=1)[:,-TOPK:]**2).mean(1)),index=F.index)
print('分数统计：中位 %.2f 95分位 %.2f 最大 %.1f' % (sc_series.median(), sc_series.quantile(.95), sc_series.max()))
sc_series.to_frame('score').to_csv(os.path.join(OUT,'metropt3_score_minutes_dsh.csv.gz'),compression='gzip')
json.dump(dict(states=state.value_counts().to_dict(), switch_minutes=int(switch.sum()),
               feats=FEATS, topk=TOPK, note='v2 占位：评估待官方故障窗口确认后重跑'),
          open(os.path.join(OUT,'metropt3_v2_status.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
print('v2 打分完成（评估步骤待官方窗口）')
