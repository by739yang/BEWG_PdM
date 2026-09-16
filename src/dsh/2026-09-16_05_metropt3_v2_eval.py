# -*- coding: utf-8 -*-
"""MetroPT-3 独立基线 v2（DSH）：分钟桶 + 三态工况 + 多信号聚合(top3 RMS) + 每日 walk-forward 重估
评估所用的故障窗口从 data/metropt3/fault_windows.json 读取（待 Codex 提供官方来源后替换重跑）。"""
import pandas as pd, numpy as np, os, json
OUT='results/2026-09-16/dsh'; CSV='data/metropt3/metropt3.csv'
ANALOG=['TP2','TP3','H1','DV_pressure','Reservoirs','Oil_temperature','Motor_current','Caudal_impulses']
RAW=['TP2','TP3','H1','Reservoirs','Oil_temperature','Motor_current']
DIGITAL=['COMP','DV_eletric']
REF_DAYS=14; ENTER=5; EXIT=10; RATIO=0.8; COOL=30; TOPK=3; Q=0.995

d=pd.read_csv(CSV, usecols=['timestamp']+ANALOG+DIGITAL, parse_dates=['timestamp']).set_index('timestamp')
m=d.resample('1min').agg({**{c:'mean' for c in ANALOG}, **{c:'max' for c in DIGITAL}}).dropna(how='all')
F=pd.DataFrame({c:m[c] for c in RAW})
F['TP3_minus_Reservoirs']=m['TP3']-m['Reservoirs']; F['TP3_minus_H1']=m['TP3']-m['H1']
FEATS=list(F.columns)
cur=m['Motor_current'].fillna(0); comp=m['COMP'].fillna(0); dve=m['DV_eletric'].fillna(0)
state=pd.Series(np.where(cur<1.0,'stopped',np.where(dve>=0.5,'loaded','unloaded')),index=m.index)
switch=state.ne(state.shift(1)) & state.shift(1).notna()
print('分钟桶 %d 工况 %s 切换分钟 %d' % (len(F), state.value_counts().to_dict(), int(switch.sum())))

GS=((F.quantile(.75)-F.quantile(.25))/1.349)
GSD=F.std()
GSC=pd.concat([GS.where(GS>1e-9,GSD).fillna(1.0)*0.2, GSD.fillna(1.0)*0.1],axis=1).max(axis=1)
days=sorted(set(F.index.normalize()))
def est(hi):
    lo=hi-pd.Timedelta(days=REF_DAYS); out={}
    sub=F.loc[lo:hi]; st=state.loc[lo:hi]; sw=switch.loc[lo:hi]
    for s in ['stopped','unloaded','loaded']:
        X=sub[(st==s)&(~sw)]
        if len(X)<120: X=sub[~sw]
        if len(X)<60: out[s]=None; continue
        med=X.median(); sc=(((X.quantile(.75)-X.quantile(.25))/1.349).where(lambda v: v>1e-9, X.std())).fillna(1.0)
        out[s]=(med, pd.concat([sc,GSC],axis=1).max(axis=1))
    return out
parts=[]; EST={}
for i,day in enumerate(days):
    EST[day]=est(day-pd.Timedelta(seconds=1))
    hi=days[i+1] if i+1<len(days) else F.index[-1]+pd.Timedelta(seconds=1)
    sl=(F.index>=day)&(F.index<hi)
    if not sl.any(): continue
    X=F[sl]; st=state[sl]; Z=pd.DataFrame(0.0,index=X.index,columns=FEATS)
    for s in ['stopped','unloaded','loaded']:
        e=EST[day].get(s)
        if e is None: continue
        mk=(st==s)
        if mk.sum()==0: continue
        Z.loc[mk]=(X.loc[mk]-e[0])/e[1]
    parts.append(Z)
Z=pd.concat(parts).reindex(F.index).fillna(0.0).clip(-30,30)
absZ=np.abs(Z.values); k=min(TOPK,absZ.shape[1])
score=pd.Series(np.sqrt((np.sort(absZ,axis=1)[:,-k:]**2).mean(1)),index=Z.index)
print('分数：中位 %.2f 95%% %.2f 99.5%% %.2f 最大 %.1f' % (score.median(),score.quantile(.95),score.quantile(.995),score.max()))
score.to_frame('score').to_csv(os.path.join(OUT,'metropt3_score_minutes_dsh.csv.gz'),compression='gzip')

# 标定：首个故障前 + 前 12 小时预热
FW=json.load(open('data/metropt3/fault_windows.json',encoding='utf-8'))
fw=[(pd.Timestamp(x['start']),pd.Timestamp(x['end'])) for x in FW['windows']]
cal=score.loc[:str(fw[0][0]-pd.Timedelta(hours=12))].iloc[12*60:]
thr=float(cal.quantile(Q)); print('标定分钟 %d 主阈值 %.3f' % (len(cal),thr))
def run(thr):
    sv=score.values; over=sv>thr; n=len(sv); ev=[]; st=0; r=0; st0=0; last=-10**9
    for t in range(n):
        if st==0:
            if t<last+COOL: r=0
            elif over[t]:
                r+=1
                if r>=ENTER: st0=t; st=1; r=0
            else: r=0
        else:
            if sv[t]<RATIO*thr:
                r+=1
                if r>=EXIT: ev.append((st0,t+1)); last=t+1; st=0; r=0
            else: r=0
    if st==1: ev.append((st0,n))
    return ev
idx=score.index
def hit(s):
    ts=idx[s]
    for a,b in fw:
        if a-pd.Timedelta(hours=1)<=ts<=b: return (a,b)
    return None
def metrics(ev):
    hits=[e for e in ev if hit(e[0])]; covered={hit(s) for s,e in hits}
    fault=np.zeros(len(idx),bool)
    for a,b in fw: fault|=(idx>=a)&(idx<=b)
    usable=(~fault)&(~switch.values)&(state.values!='stopped')
    alarm=np.zeros(len(idx),bool)
    for s,e in ev: alarm[s:min(e,len(idx))]=True
    hmin=usable.sum(); tia=(alarm&usable).sum()/max(hmin,1)
    dl=[(idx[s]-hit(s)[0]).total_seconds()/60 for s,e in hits]
    return dict(true_events=len(fw),detected=len(covered),event_recall=len(covered)/len(fw),
                alarm_events=len(ev),fp_events=len(ev)-len(hits),usable_hours=round(hmin/60,1),
                fp_per_healthy_hour=(len(ev)-len(hits))/max(hmin/60,1e-9),tia_h=tia,
                delay_min_median=float(np.median(dl)) if dl else None)
res=metrics(run(thr)); res.update(dataset='MetroPT-3',block='1min',threshold=round(thr,3),
    cal_minutes=int(len(cal)),fault_windows_source=FW.get('source','unknown'))
print(json.dumps(res,ensure_ascii=False,indent=2))
json.dump(res,open(os.path.join(OUT,'metropt3_v2_summary.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
pd.DataFrame([{'t_start':str(idx[s]),'t_end':str(idx[min(e,len(idx)-1)]),'hit':bool(hit(s))} for s,e in run(thr)]).to_csv(
    os.path.join(OUT,'metropt3_v2_alarm_events.csv'),index=False,encoding='utf-8-sig')
qs=[cal.quantile(q) for q in np.linspace(0.90,0.9999,30)]
rows=[]
for q in qs:
    r=metrics(run(float(q))); r['threshold']=round(float(q),4); rows.append(r)
pd.DataFrame(rows).to_csv(os.path.join(OUT,'metropt3_v2_det.csv'),index=False,encoding='utf-8-sig')
best=max(rows,key=lambda r:(r['event_recall'], -r['fp_per_healthy_hour']))
print('DET 最佳点：', {kk:best[kk] for kk in ['threshold','event_recall','fp_per_healthy_hour','tia_h']})
