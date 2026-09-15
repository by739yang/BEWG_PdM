# -*- coding: utf-8 -*-
"""DSH 侧 PROTOCOL_v1 实现（修订版）
改动1：真值事件按评估窗截断后再判长度（否则故障起点略早于标定期末的文件会被整条丢掉）
改动2：增加标定期定义的敏感性对照（mid: N/2 上限；fixed: 固定 380 样本）
"""
import numpy as np, pandas as pd, glob, os, io
from sklearn.decomposition import PCA
from numpy.lib.stride_tricks import sliding_window_view

BASE = r'C:\Users\boyi\Desktop\BEWG_PdM\data\SKAB-master\data'
OUT  = r'C:\Users\boyi\Desktop\BEWG_PdM\results\2026-09-15\dsh'
FEATS = ['Accelerometer1RMS','Accelerometer2RMS','Current','Pressure','Temperature',
         'Thermocouple','Voltage','Volume Flow RateRMS']
W, COLD, FW = 120, 45, 60
CONSEC_IN, CONSEC_OUT, RATIO_OUT, COOLDOWN = 10, 30, 0.8, 300
QUANTS = [0.90, 0.99, 0.995, 0.999]
TRUTH_MIN = 60
CAL_MODES = {'mid': lambda n: (120, min(120+1800, n//2)),
             'fixed': lambda n: (120, min(120+1800, max(300, min(380, n//2))))}

def load(fp):
    df = pd.read_csv(fp, sep=';'); df.columns=[c.strip() for c in df.columns]
    for c in df.columns:
        if c not in ('datetime','anomaly','changepoint'):
            df[c]=pd.to_numeric(df[c], errors='coerce')
    return df
def causal_z(X):
    n=X.shape[0]; Z=np.zeros_like(X)
    for t in range(n):
        win=X[max(0,t-W):t]
        if len(win)<COLD: win=X[:min(COLD,n)]
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
    return np.nan_to_num(np.hstack([Z, r.mean().values, r.std().fillna(0).values,
                                    r.min().values, r.max().values, slope]))
def score_F3(Z):
    n=Z.shape[0]; s=np.zeros(n)
    for t in range(420, n):
        A=Z[t-420:t-60]; B=Z[t-60:t]
        s[t]=(np.abs(A.mean(0)-B.mean(0))/(A.std(0)+B.std(0)+1e-3)).max()
    return s
def make_events(sc, thr):
    over=sc>thr; n=len(sc); ev=[]; state=0; run=0; start=0; last_end=-10**9
    for t in range(n):
        if state==0:
            if over[t]:
                if run==0: start=t
                run+=1
                if run>=CONSEC_IN and t-COOLDOWN>last_end: state=1; run=0
            else: run=0
        else:
            if (not over[t]) or (sc[t]<RATIO_OUT*thr):
                run+=1
                if run>=CONSEC_OUT: ev.append((start,t)); last_end=t; state=0; run=0
            else: run=0
    if state==1: ev.append((start,n-1))
    return ev
def eval_one(y, sc, thr, b):
    n=len(y); ev=make_events(sc,thr)
    yb=np.diff(np.r_[0,y,0]); st=np.where(yb==1)[0]; en=np.where(yb==-1)[0]
    truth=[]
    for s0,e0 in zip(st,en):                      # 截断到评估窗后再判长度
        s1,e1=max(s0,b),e0
        if e1-s1>=TRUTH_MIN: truth.append((s1,e1))
    hit=0; delays=[]
    for s0,e0 in truth:
        m=[e for e in ev if e[0]<=e0 and e[1]>=s0]
        if m: hit+=1; delays.append(min(e[0] for e in m)-s0)
    fp=[e for e in ev if not any(e[0]<=e1 and e[1]>=s0 for (s0,e1) in truth)]
    health=(y[b:]==0).sum(); alarm=np.zeros(n,bool)
    for s0,e0 in ev: alarm[s0:e0+1]=True
    return dict(events=len(truth), hit=hit, recall=hit/max(len(truth),1),
                fp_events=len(fp), healthy_hours=health/3600.0,
                fp_per_hour=len(fp)/max(health/3600.0,1e-9),
                time_in_alarm=(alarm[b:]&(y[b:]==0)).sum()/max(health,1),
                delay_median=float(np.median(delays)) if delays else np.nan)

files=sorted(glob.glob(os.path.join(BASE,'valve1','*.csv'))+
             glob.glob(os.path.join(BASE,'valve2','*.csv'))+
             glob.glob(os.path.join(BASE,'other','*.csv')))
rows=[]; cache={}
for f in files:
    d=load(f); y=d['anomaly'].values.astype(int); X=d[FEATS].values.astype(float)
    if y.sum()==0: continue
    Z=causal_z(X); F=feats48(Z); cache[f]=(y,Z,F)
    print('prep', os.path.basename(f), flush=True)

det=[]
for mode, fn in CAL_MODES.items():
    for f,(y,Z,F) in cache.items():
        n=len(X) if False else len(y); a,b=fn(n)
        if b-a<200: continue
        scores={'F0':np.abs(Z).max(1),'F2':None,'F3':score_F3(Z)}
        p=PCA(n_components=0.90,random_state=0).fit(F[a:b])
        scores['F2']=np.sqrt(((F-p.inverse_transform(p.transform(F)))**2).sum(1))
        for name,sc in scores.items():
            r=eval_one(y,sc,np.quantile(sc[a:b],0.995),b)
            r.update(file=os.path.relpath(f,BASE), method=name, cal_mode=mode,
                     flagged=int(y[a:b].sum()>0), cal_len=b-a)
            rows.append(r)
            for q in QUANTS:
                rr=eval_one(y,sc,np.quantile(sc[a:b],q),b)
                det.append(dict(cal_mode=mode,file=os.path.relpath(f,BASE),method=name,quantile=q,
                                recall=rr['recall'],fp_per_hour=rr['fp_per_hour'],
                                delay=rr['delay_median'],time_in_alarm=rr['time_in_alarm']))
    print('mode done', mode, flush=True)

df=pd.DataFrame(rows); dd=pd.DataFrame(det)
df.to_csv(os.path.join(OUT,'protocol_v1_per_file.csv'),index=False,encoding='utf-8-sig')
dd.to_csv(os.path.join(OUT,'protocol_v1_det.csv'),index=False,encoding='utf-8-sig')
S=df.groupby(['cal_mode','method']).apply(lambda s: pd.Series({
    '文件数':len(s), '事件数':int(s.events.sum()), '检出':int(s.hit.sum()),
    '事件召回':round(s.hit.sum()/max(s.events.sum(),1),3),
    '误报事件':int(s.fp_events.sum()),
    '误报事件每健康小时':round(s.fp_events.sum()/max(s.healthy_hours.sum(),1e-9),2),
    '健康时间报警占比':round(s.time_in_alarm.mean(),3),
    '延迟中位秒':round(float(s.delay_median.median()),1),
    '标定期含故障文件数':int(s[s.flagged==1].file.nunique()), '标定期长度中位':int(s.cal_len.median())})).reset_index()
open(os.path.join(OUT,'protocol_v1_summary.md'),'w',encoding='utf-8').write(
 '# PROTOCOL_v1 盲跑结果（DSH 侧，修订版）\n\n命令：python src/dsh/2026-09-15_09_protocol_v1_rev.py\n\n'+
 S.to_markdown(index=False)+'\n\n## DET 曲线数据\n\n'+
 dd.groupby(['cal_mode','method','quantile']).agg(文件数=('file','count'),事件召回=('recall','mean'),
     误报事件每健康小时=('fp_per_hour','mean'),健康报警占比=('time_in_alarm','mean'),
     延迟中位=('delay','median')).round(3).to_markdown())
print(S.to_markdown(index=False))
