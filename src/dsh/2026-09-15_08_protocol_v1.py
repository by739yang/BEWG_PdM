# -*- coding: utf-8 -*-
"""DSH 侧实现：docs/PROTOCOL_v1.md 冻结协议（F0/F2/F3 + 事件化判决 + DET）"""
import numpy as np, pandas as pd, glob, os, io, json
from sklearn.decomposition import PCA

BASE = r'C:\Users\boyi\Desktop\BEWG_PdM\data\SKAB-master\data'
OUT  = r'C:\Users\boyi\Desktop\BEWG_PdM\results\2026-09-15\dsh'
FEATS = ['Accelerometer1RMS','Accelerometer2RMS','Current','Pressure','Temperature',
         'Thermocouple','Voltage','Volume Flow RateRMS']
W, COLD, FW = 120, 45, 60
CONSEC_IN, CONSEC_OUT, RATIO_OUT, COOLDOWN = 10, 30, 0.8, 300
QUANTS = [0.90, 0.99, 0.995, 0.999]
TRUTH_MIN = 60

def load(fp):
    df = pd.read_csv(fp, sep=';'); df.columns=[c.strip() for c in df.columns]
    for c in df.columns:
        if c not in ('datetime','anomaly','changepoint'):
            df[c]=pd.to_numeric(df[c], errors='coerce')
    return df

def causal_z(X):
    n = X.shape[0]; Z = np.zeros_like(X)
    for t in range(n):
        win = X[max(0,t-W):t]
        if len(win) < COLD: win = X[:min(COLD,n)]
        med = np.median(win,0)
        iqr = np.percentile(win,75,0)-np.percentile(win,25,0)
        sc = np.maximum(np.maximum(iqr/1.349, 0.02*np.abs(med)), 1e-9)
        Z[t] = (X[t]-med)/sc
    return Z

def feats48(Z):
    Zd = pd.DataFrame(Z, columns=FEATS); r = Zd.rolling(FW, min_periods=1)
    n = Z.shape[0]; w = np.arange(FW)- (FW-1)/2.0; w = w/(w**2).sum()
    from numpy.lib.stride_tricks import sliding_window_view
    if n >= FW:
        sw = sliding_window_view(Z, FW, axis=0)          # (n-FW+1, FW, 8)
        sl = np.einsum('tfk,k->tf', sw, w)
        slope = np.vstack([np.repeat(sl[:1], FW-1, 0), sl])
    else:
        slope = np.zeros_like(Z)
    parts = [Z, r.mean().values, r.std().fillna(0).values, r.min().values, r.max().values, slope]
    return np.nan_to_num(np.hstack(parts))

def cal_range(n): return 120, min(120+1800, n//2)

def score_F0(Z): return np.abs(Z).max(1)
def fit_F2(F, a, b):
    p = PCA(n_components=0.90, random_state=0).fit(F[a:b])
    return lambda X: np.sqrt(((X - p.inverse_transform(p.transform(X)))**2).sum(1))
def score_F3(Z):
    n = Z.shape[0]; s = np.zeros(n)
    for t in range(360+60, n):
        A = Z[t-420:t-60]; B = Z[t-60:t]
        s[t] = (np.abs(A.mean(0)-B.mean(0))/(A.std(0)+B.std(0)+1e-3)).max()
    return s

def make_events(sc, thr):
    over = sc > thr; n = len(sc); ev=[]; state=0; run=0; start=0; last_end=-10**9
    for t in range(n):
        if state==0:
            if over[t]:
                if run==0: start=t
                run+=1
                if run>=CONSEC_IN and t-COOLDOWN>last_end:
                    state=1; run=0
            else: run=0
        else:
            if (not over[t]) or (sc[t] < RATIO_OUT*thr):
                run+=1
                if run>=CONSEC_OUT:
                    ev.append((start,t)); last_end=t; state=0; run=0
            else: run=0
    if state==1: ev.append((start,n-1))
    return ev

def eval_one(y, sc, thr):
    n=len(y); a,b = cal_range(n); ev = make_events(sc, thr)
    yb = np.diff(np.r_[0,y,0]); st=np.where(yb==1)[0]; en=np.where(yb==-1)[0]
    truth=[(s0,e0) for s0,e0 in zip(st,en) if e0-s0>=TRUTH_MIN and s0>=b]
    hit=0; delays=[]
    for (s0,e0) in truth:
        m=[e for e in ev if e[0]<=e0 and e[1]>=s0]
        if m: hit+=1; delays.append(min(e[0] for e in m)-s0)
    fp=[e for e in ev if not any(e[0]<=e1 and e[1]>=s0 for (s0,e1) in truth)]
    health=(y[b:]==0).sum(); alarm_id=np.zeros(n,bool)
    for (s0,e0) in ev: alarm_id[s0:e0+1]=True
    tia=(alarm_id[b:] & (y[b:]==0)).sum()/max(health,1)
    return dict(events=len(truth), hit=hit, recall=hit/max(len(truth),1),
                fp_events=len(fp), healthy_hours=health/3600.0,
                fp_per_hour=len(fp)/max(health/3600.0,1e-9), time_in_alarm=tia,
                delay_median=float(np.median(delays)) if delays else np.nan,
                n_alarm_events=len(ev))

files = sorted(glob.glob(os.path.join(BASE,'valve1','*.csv'))+
               glob.glob(os.path.join(BASE,'valve2','*.csv'))+
               glob.glob(os.path.join(BASE,'other','*.csv')))
rows=[]; det=[]
for f in files:
    d = load(f); y = d['anomaly'].values.astype(int); X = d[FEATS].values.astype(float)
    if y.sum()==0: continue
    n=len(X); a,b = cal_range(n)
    if b-a < 300: rows.append(dict(file=os.path.relpath(f,BASE), note='insufficient-cal')); continue
    Z = causal_z(X); F = feats48(Z)
    scores = {'F0': score_F0(Z), 'F2': fit_F2(F,a,b)(F), 'F3': score_F3(Z)}
    flag = int(y[a:b].sum()>0)
    for name, sc in scores.items():
        thr = np.quantile(sc[a:b], 0.995)
        r = eval_one(y, sc, thr); r.update(file=os.path.relpath(f,BASE), method=name, flagged=flag)
        rows.append(r)
        for q in QUANTS:
            tq = np.quantile(sc[a:b], q)
            rr = eval_one(y, sc, tq)
            det.append(dict(file=os.path.relpath(f,BASE), method=name, quantile=q,
                            recall=rr['recall'], fp_per_hour=rr['fp_per_hour'],
                            delay=rr['delay_median'], time_in_alarm=rr['time_in_alarm']))
    print('done', os.path.basename(f), flush=True)

df = pd.DataFrame(rows)
df.to_csv(os.path.join(OUT,'protocol_v1_per_file.csv'), index=False, encoding='utf-8-sig')
dd = pd.DataFrame(det); dd.to_csv(os.path.join(OUT,'protocol_v1_det.csv'), index=False, encoding='utf-8-sig')

summ=[]
for m in ['F0','F2','F3']:
    s = df[df.method==m]
    summ.append(dict(方法=m,
        事件召回=f"{s.hit.sum()}/{s.events.sum()} ({s.hit.sum()/max(s.events.sum(),1)*100:.1f}%)",
        误报事件=s.fp_events.sum(),
        独立误报事件每健康小时=round(s.fp_events.sum()/max(s.healthy_hours.sum(),1e-9),2),
        健康时间报警占比=f"{s.time_in_alarm.mean()*100:.1f}%",
        延迟中位秒=round(float(s.delay_median.median()),1), 文件数=len(s)))
S = pd.DataFrame(summ)
S.to_csv(os.path.join(OUT,'protocol_v1_summary.csv'), index=False, encoding='utf-8-sig')

lines = ['# PROTOCOL_v1 盲跑结果（DSH 侧）','',
         '命令：python src/dsh/2026-09-15_08_protocol_v1.py','',
         S.to_markdown(index=False),'','## DET 曲线数据（阈值=cal 分位数）','',
         dd.groupby(['method','quantile']).agg(文件数=('file','count'),
            事件召回=('recall','mean'), 误报事件每健康小时=('fp_per_hour','mean'),
            健康报警占比=('time_in_alarm','mean'), 延迟中位=('delay','median')).round(3).to_markdown(),'']
io.open(os.path.join(OUT,'protocol_v1_summary.md'),'w',encoding='utf-8').write('\n'.join(lines))
print(S.to_markdown(index=False))
print('flagged files (标定期含故障):', sorted(set(df[df.flagged==1].file)))
