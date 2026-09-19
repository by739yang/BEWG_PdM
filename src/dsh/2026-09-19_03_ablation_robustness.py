# -*- coding: utf-8 -*-
"""检测模块消融 + 鲁棒性（DSH，2026-09-19）
口径：与冻结结论一致（冻结分母 96,270 分钟、事件机 5/10/0.8x/30、三态命中），只变打分链路。
V0 基线；V1 聚合改 max|z|；V2 静态标准化；V3 不分工况；V4 去派生特征；
V5/V6 随机缺失 10%/30% 分钟；V7 关键传感器卡死。"""
import numpy as np, pandas as pd, json, os, time
t0=time.time(); OUT='results/2026-09-19/dsh'; os.makedirs(OUT,exist_ok=True)
FW=json.load(open('docs/metropt3_fault_windows.json',encoding='utf-8'))
fw=[(pd.Timestamp(x['start']),pd.Timestamp(x['end'])) for x in FW['windows']]
RAW=['TP2','TP3','H1','Reservoirs','Oil_temperature','Motor_current']
DER=['TP3_minus_Reservoirs','TP3_minus_H1']
d=pd.read_csv('data/metropt3/metropt3.csv',usecols=['timestamp']+RAW+['DV_eletric'],parse_dates=['timestamp']).set_index('timestamp')
m=d.resample('1min').agg({**{c:'mean' for c in RAW}, 'DV_eletric':'max'})
F=pd.DataFrame({c:m[c] for c in RAW}); F['TP3_minus_Reservoirs']=m['TP3']-m['Reservoirs']; F['TP3_minus_H1']=m['TP3']-m['H1']
allc=list(F.columns)
state=pd.Series(np.where(m['Motor_current'].fillna(0)<1.0,'stopped',np.where(m['DV_eletric'].fillna(0)>=0.5,'loaded','unloaded')),index=m.index)
switch=(state.ne(state.shift(1))&state.shift(1).notna()).values
J=pd.read_csv('results/2026-09-18/dsh/minute_mask_intersection.csv.gz',parse_dates=['ts'])
fault=np.zeros(len(J),bool)
for a,b in fw: fault|=np.asarray((J.ts>=a)&(J.ts<=b))
base=(J.B_ds&J.B_cx&J.fin_ds&J.fin_cx&(~fault)&J.stable_ds&J.stable_cx)
run_=(base&J.run_ds&J.run_cx)
def ev_metrics(score,thr=2.395):
    sv=np.nan_to_num(score,nan=0.0); over=sv>thr; n=len(sv); ev=[]; st=0; r=0; s0=0; last=-10**9
    for t in range(n):
        if st==0:
            if t<last+30: r=0
            elif over[t]:
                r+=1
                if r>=5: s0=t; st=1; r=0
            else: r=0
        else:
            if sv[t]<0.8*thr:
                r+=1
                if r>=10: ev.append((s0,t+1)); last=t+1; st=0; r=0
            else: r=0
    if st==1: ev.append((s0,n))
    timely=late=0
    for g0,g1 in fw:
        tt=[s for s,e in ev if g0-pd.Timedelta(minutes=60)<=J.ts.iloc[s]<=g0+pd.Timedelta(minutes=60)]
        lt=[s for s,e in ev if g0+pd.Timedelta(minutes=60)<J.ts.iloc[s]<=g1]
        timely+=1 if tt else 0; late+=1 if (lt and not tt) else 0
    fp=sum(1 for s,e in ev if not any(g0-pd.Timedelta(minutes=60)<=J.ts.iloc[s]<=g1 for g0,g1 in fw))
    alarm=np.zeros(n,bool)
    for s_,e_ in ev: alarm[s_:min(e_,n)]=True
    return dict(告警数=len(ev),timely=timely,late=late,miss=4-timely-late,误报=fp,
                误报率=round(fp/max(base.sum()/60,1e-9),4),TIA_H=round(float((alarm&base).sum())/max(base.sum(),1),4))
# ---- 估计器 ----
def daily_est(df, use_state=True, days=None):
    out={}
    for day in days:
        lo=day-pd.Timedelta(days=14); sub=df.loc[lo:day-pd.Timedelta(seconds=1)]
        stt=state.reindex(sub.index); sw=(stt.ne(stt.shift(1))&stt.shift(1).notna()).values
        key=lambda s: s if use_state else 'ALL'
        groups=[('ALL',sub[~sw])] if not use_state else [(s,sub[(stt==s).values & (~sw)]) for s in ['stopped','unloaded','loaded']]
        e={}
        for k,X in groups:
            if len(X)<120: X=sub[~sw]
            if len(X)<60: e[k]=None; continue
            med=X.median(); sc=(((X.quantile(.75)-X.quantile(.25))/1.349).where(lambda v:v>1e-9,X.std())).fillna(1.0)
            GS=((df.quantile(.75)-df.quantile(.25))/1.349); GSD=df.std()
            G=pd.concat([GS.where(GS>1e-9,GSD).fillna(1.0)*0.2, GSD.fillna(1.0)*0.1],axis=1).max(axis=1)
            e[k]=(med, pd.concat([sc,G],axis=1).max(axis=1))
        out[day]=e
    return out
days=sorted(set(F.index.normalize()))
EST_WF=daily_est(F,True,days); print('walk-forward 估计完成 %.0fs'%(time.time()-t0))
STAT=(F.median(), pd.concat([(((F.quantile(.75)-F.quantile(.25))/1.349).where(lambda v:v>1e-9,F.std()).fillna(1.0)),(((F.quantile(.75)-F.quantile(.25))/1.349).where(lambda v:v>1e-9,F.std()).fillna(1.0))*0.2],axis=1).max(axis=1))
def z_table(mode, feats, use_state):
    Z=pd.DataFrame(0.0,index=F.index,columns=feats)
    if mode=='static':
        Z=(F[feats]-STAT[0][feats])/STAT[1][feats]; return Z.clip(-30,30)
    for i,day in enumerate(days):
        hi=days[i+1] if i+1<len(days) else F.index[-1]+pd.Timedelta(seconds=1)
        sl=(F.index>=day)&(F.index<hi)
        X=F.loc[sl,feats]; stt=state.loc[sl]
        keys=['ALL'] if not use_state else ['stopped','unloaded','loaded']
        for k in keys:
            e=EST_WF[day].get(k)
            if e is None: continue
            mk=np.ones(len(X),bool) if not use_state else (stt==k).values
            if mk.sum()==0: continue
            Z.loc[X.index[mk],feats]=(X[mk]-e[0][feats])/e[1][feats]
    return Z.clip(-30,30)
def score_top3(Z,k=3):
    A=np.abs(Z.values); return pd.Series(np.sqrt((np.sort(A,axis=1)[:,-k:]**2).mean(1)),index=Z.index)
def score_max(Z): return pd.Series(np.abs(Z.values).max(1),index=Z.index)
# ---- 变体 ----
rows=[]; base_score=None
Z0=z_table('wf',allc,True); base_score=score_top3(Z0).reindex(J.ts).values
frozen_score=pd.read_csv('results/2026-09-16/dsh/metropt3_score_minutes_dsh.csv.gz',index_col=0,parse_dates=True)['score'].reindex(J.ts).values
d_=np.abs(np.nan_to_num(base_score,nan=0)-np.nan_to_num(frozen_score,nan=0))
print('V0 与冻结分数：中位差 %.4f，95分位差 %.4f，最大差 %.2f' % (np.median(d_),np.quantile(d_,0.95),d_.max()))
r=ev_metrics(base_score); r.update(变体='V0 基线（walk-forward + 工况条件化 + top3-RMS）'); rows.append(r)
r=ev_metrics(score_max(Z0).reindex(J.ts).values); r.update(变体='V1 聚合改 max|z|（单信号）'); rows.append(r)
Zs=z_table('static',allc,False); r=ev_metrics(score_top3(Zs).reindex(J.ts).values); r.update(变体='V2 静态标准化（全期一次估计）'); rows.append(r)
Zn=z_table('wf',allc,False); r=ev_metrics(score_top3(Zn).reindex(J.ts).values); r.update(变体='V3 不做工况条件化'); rows.append(r)
Zr=z_table('wf',RAW,True); r=ev_metrics(score_top3(Zr).reindex(J.ts).values); r.update(变体='V4 去掉派生特征'); rows.append(r)
rng=np.random.default_rng(0)
for frac,tag in [(0.10,'V5 随机缺失 10% 分钟'),(0.30,'V6 随机缺失 30% 分钟')]:
    s_=base_score.copy(); idx=rng.choice(len(s_),int(len(s_)*frac),replace=False); s_[idx]=0.0
    r=ev_metrics(s_); r.update(变体=tag); rows.append(r)
Cs=base_score.copy()
# V7 传感器卡死：Oil_temperature 固定为其全局中位数后重算（用静态估计近似，只影响该列）
Zs2=z_table('static',allc,False).copy(); Zs2['Oil_temperature']=0.0
r=ev_metrics(score_top3(Zs2).reindex(J.ts).values); r.update(变体='V7 温度通道卡死（该列置零）'); rows.append(r)
R=pd.DataFrame(rows)[['变体','告警数','timely','late','miss','误报','误报率','TIA_H']]
R.to_csv(os.path.join(OUT,'ablation_robustness.csv'),index=False,encoding='utf-8-sig')
print(R.to_markdown(index=False))
print('耗时 %.0fs'%(time.time()-t0))
json.dump(dict(口径='冻结分母 + 冻结事件机 + 三态命中，只变打分链路',结果=R.to_dict('records')),
    open(os.path.join(OUT,'ablation_robustness.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
