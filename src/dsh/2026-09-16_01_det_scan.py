# -*- coding: utf-8 -*-
"""DSH 侧 PROTOCOL_v1.1 盲跑实现（docs/PROTOCOL_v1.1.md）"""
import numpy as np, pandas as pd, glob, os, io
from sklearn.decomposition import PCA
from numpy.lib.stride_tricks import sliding_window_view

BASE=r'C:\Users\boyi\Desktop\BEWG_PdM\data\SKAB-master\data'
OUT =r'C:\Users\boyi\Desktop\BEWG_PdM\results\2026-09-15\dsh'
FEATS=['Accelerometer1RMS','Accelerometer2RMS','Current','Pressure','Temperature',
       'Thermocouple','Voltage','Volume Flow RateRMS']
CAL_A, CAL_B0, W, FW = 120, 480, 120, 60
CI, CO, RATIO, COOL = 10, 30, 0.8, 300
QUANTS=[0.90,0.99,0.995,0.999]
EV_MIN=60; DELTA=60

def load(fp):
    df=pd.read_csv(fp,sep=';'); df.columns=[c.strip() for c in df.columns]
    for c in df.columns:
        if c not in ('datetime','anomaly','changepoint'): df[c]=pd.to_numeric(df[c],errors='coerce')
    return df
def causal_z(X):
    n=X.shape[0]; Z=np.zeros_like(X)                      # t=0 -> 0
    for t in range(1,n):
        win=X[max(0,t-W):t]
        med=np.median(win,0); iqr=np.percentile(win,75,0)-np.percentile(win,25,0)
        Z[t]=(X[t]-med)/np.maximum(np.maximum(iqr/1.349,0.02*np.abs(med)),1e-9)
    return Z
def feats48(Z):
    Zd=pd.DataFrame(Z,columns=FEATS); r=Zd.rolling(FW,min_periods=1)
    n=Z.shape[0]; w=np.arange(FW)-(FW-1)/2.0; w=w/(w**2).sum()
    if n>=FW:
        sl=np.einsum('tfk,k->tf', sliding_window_view(Z,FW,axis=0), w)
        slope=np.vstack([np.repeat(sl[:1],FW-1,0), sl])
    else: slope=np.zeros_like(Z)
    return np.nan_to_num(np.hstack([Z, r.mean().values, r.std(ddof=0).fillna(0).values,
                                    r.min().values, r.max().values, slope]))
def score_F3(Z):
    n=Z.shape[0]; s=np.zeros(n)
    for t in range(CAL_A,n):
        A=Z[max(0,t-360):t-60]; B=Z[t-60:t]
        if len(A)<10 or len(B)<10: continue
        s[t]=(np.abs(A.mean(0)-B.mean(0))/(A.std(0)+B.std(0)+1e-3)).max()
    return s
def events_state(sc, thr):
    """状态机（在 sc 的局部索引上运行），返回 [(t_start,t_end_local)]"""
    n=len(sc); over=sc>thr; ev=[]; state=0; run=0; start=0; last_end=-10**9
    for t in range(n):
        if state==0:
            if t < last_end+COOL:
                run=0
            elif over[t]:
                run+=1
                if run>=CI:
                    start=t
                    state=1; run=0
            else: run=0
        else:
            if sc[t]<RATIO*thr:
                run+=1
                if run>=CO: ev.append((start,t+1)); last_end=t+1; state=0; run=0
            else: run=0
    if state==1: ev.append((start,n))
    return ev
def truth_events(y, ev_start):
    yb=np.diff(np.r_[0,y,0]); st=np.where(yb==1)[0]; en=np.where(yb==-1)[0]
    out=[]
    for s0,e0 in zip(st,en):
        s1,e1=max(s0,ev_start),e0
        if e1-s1>=EV_MIN: out.append((s1,e1))
    return out
def evaluate(y, sc, thr, ev_start):
    n=len(y); sc_w=sc[ev_start:]; ev_local=events_state(sc_w, thr)
    ev=[(a+ev_start,b+ev_start) for a,b in ev_local]
    G=truth_events(y, ev_start)
    hits=[]; ok_starts={}
    for (g0,g1) in G:
        cand=[s for (s,_) in ev if max(ev_start,g0-DELTA)<=s<g1]
        if cand: hits.append((g0,g1,min(cand)))
    hit_starts={s for (_,_,s) in hits}
    too_early=[(s,e) for (s,e) in ev if s not in hit_starts and any(e>g0 and s<g0-DELTA for (g0,g1) in G)]
    fp=[s for (s,e) in ev if s not in hit_starts and y[s]==0]
    health=(y[ev_start:]==0).sum()
    alarm=np.zeros(n,bool)
    for (a,b) in ev: alarm[a:b]=True
    tia=(alarm[ev_start:]&(y[ev_start:]==0)).sum()/max(health,1)
    delays=[s-g0 for (g0,g1,s) in hits]
    return dict(events=len(G), hits=len(hits), recall=len(hits)/max(len(G),1),
                fp_events=len(fp), healthy_hours=health/3600.0,
                fp_per_hour=len(fp)/max(health/3600.0,1e-9),
                tia=tia, delay_median=float(np.median(delays)) if delays else np.nan,
                too_early=len(too_early), n_alarm_events=len(ev))
files=sorted(glob.glob(os.path.join(BASE,'valve1','*.csv'))+glob.glob(os.path.join(BASE,'valve2','*.csv'))+glob.glob(os.path.join(BASE,'other','*.csv')))
rows=[];det=[]
for f in files:
    d=load(f); y=d['anomaly'].values.astype(int); X=d[FEATS].values.astype(float)
    if y.sum()==0: continue
    n=len(X); a,b=CAL_A,min(CAL_B0,n)
    if b-a<300:
        rows.append(dict(file=os.path.relpath(f,BASE),method='SKIP',note='insufficient-cal')); continue
    Z=causal_z(X); F=feats48(Z)
    p=PCA(n_components=0.90,svd_solver='full',random_state=0).fit(F[a:b])
    scores={'F0':np.abs(Z).max(1),
            'F2':np.sqrt(((F-p.inverse_transform(p.transform(F)))**2).sum(1)),
            'F3':score_F3(Z)}
    for name,sc in scores.items():
        r=evaluate(y,sc,np.quantile(sc[a:b],0.995),b)
        r.update(file=os.path.relpath(f,BASE),method=name,flagged=int(y[a:b].sum()>0),cal_len=b-a)
        rows.append(r)
        for q in QUANTS:
            rr=evaluate(y,sc,np.quantile(sc[a:b],q),b)
            det.append(dict(file=os.path.relpath(f,BASE),method=name,quantile=q,
                            events=rr['events'],hits=rr['hits'],fp_events=rr['fp_events'],
                            healthy_hours=rr['healthy_hours'],
                            alarm_healthy=rr['tia']*rr['healthy_hours']*3600,
                            recall=rr['recall'],fp_per_hour=rr['fp_per_hour'],tia=rr['tia'],
                            delay=rr['delay_median']))
    print('done',os.path.basename(f),flush=True)
df=pd.DataFrame(rows); dd=pd.DataFrame(det)
df.to_csv(os.path.join(OUT,'protocol_v14b_per_file.csv'),index=False,encoding='utf-8-sig')
dd.to_csv(os.path.join(OUT,'protocol_v14_det_counts.csv'),index=False,encoding='utf-8-sig')
S=df[df.method!='SKIP'].groupby('method').apply(lambda s: pd.Series({
    '文件数':len(s),'标定期含故障文件数':int(s[s.flagged==1].file.nunique()),
    '真值事件数':int(s.events.sum()),'命中数':int(s.hits.sum()),
    '事件召回':round(s.hits.sum()/max(s.events.sum(),1),3),
    '误报事件数':int(s.fp_events.sum()),
    '误报事件每健康小时':round(s.fp_events.sum()/max(s.healthy_hours.sum(),1e-9),2),
    'TIA-H':round(s.tia.mean(),3),
    '延迟中位秒':round(float(s.delay_median.median()),1),
    '过早重叠诊断':int(s.too_early.sum()),'告警事件总数':int(s.n_alarm_events.sum())})).reset_index()
open(os.path.join(OUT,'protocol_v14b_summary.md'),'w',encoding='utf-8').write(
 '# PROTOCOL_v1.1 盲跑结果（DSH 侧）\n\n命令：python src/dsh/2026-09-15_10_protocol_v11.py\n\n'+
 S.to_markdown(index=False)+'\n\n## DET 扫描（阈值=cal 分位）\n\n'+
 dd.groupby(['method','quantile']).agg(文件数=('file','count'),事件召回均值=('recall','mean'),
   误报事件每健康小时均值=('fp_per_hour','mean'),TIA均值=('tia','mean'),
   延迟中位=('delay','median')).round(3).to_markdown())
print(S.to_markdown(index=False))
