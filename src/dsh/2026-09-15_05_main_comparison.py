# -*- coding: utf-8 -*-
"""SKAB 实测 v5：修正标定期 + 1分钟决策粒度（贴近现场运维判据）
所有方法均不使用故障标签；标定期取参考段的后半部分（等自适应窗口进入稳态之后）。
"""
import numpy as np, pandas as pd, glob, os
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif']=['Microsoft YaHei']; plt.rcParams['axes.unicode_minus']=False

BASE=r'C:\Users\boyi\Desktop\BEWG_PdM\data\SKAB-master\data'
OUT=r'C:\Users\boyi\Desktop\BEWG_PdM\results\2026-09-15\dsh'; os.makedirs(OUT,exist_ok=True)
FEATS=['Accelerometer1RMS','Accelerometer2RMS','Current','Pressure','Temperature','Thermocouple','Voltage','Volume Flow RateRMS']
REF=0.40; BURN=120; AW=120; TARGET_FPR=0.005; BLOCK=60; GAP=300

def load(fp):
    df=pd.read_csv(fp,sep=';'); df.columns=[c.strip() for c in df.columns]
    for c in df.columns:
        if c not in ('datetime','anomaly','changepoint'): df[c]=pd.to_numeric(df[c],errors='coerce')
    return df
def adaptive_z(X,W=AW,minp=45):
    n=X.shape[0]; Z=np.zeros_like(X)
    for t in range(n):
        win=X[max(0,t-W):t]
        if len(win)<minp: win=X[:min(minp,n)]
        med=np.median(win,0); iqr=np.percentile(win,75,0)-np.percentile(win,25,0); sd=win.std(0)
        sc=np.where(iqr>1e-9,iqr,np.where(sd>1e-9,sd,1.0))
        sc=np.maximum(sc,0.02*np.maximum(np.abs(med),1e-3))
        Z[t]=(X[t]-med)/sc
    return Z
def winfeat(Z,w=15):
    Zd=pd.DataFrame(Z); r=Zd.rolling(w,min_periods=1); return np.nan_to_num(np.hstack([Z,r.mean().values,r.std().fillna(0).values]))
class Maha:
    def fit(self,X):
        self.mu=X.mean(0); C=np.cov((X-self.mu).T)+np.eye(X.shape[1])*1e-3; self.P=np.linalg.inv(C)
    def score(self,X):
        D=X-self.mu; return np.sqrt(np.maximum(np.einsum('ij,jk,ik->i',D,self.P,D),0))
class PCAsp:
    def fit(self,X): self.pca=PCA(n_components=0.9,random_state=0).fit(X)
    def score(self,X):
        R=X-self.pca.inverse_transform(self.pca.transform(X)); return np.sqrt((R**2).sum(1))
class IF:
    def fit(self,X): self.m=IsolationForest(n_estimators=300,random_state=0,n_jobs=-1).fit(X)
    def score(self,X): return -self.m.score_samples(X)
def blocks(a,b=BLOCK):
    m=(len(a)//b)*b
    return (a[:m].reshape(-1,b).mean(1)>0.5).astype(int), b
def episodes(a,gap=GAP):
    idx=np.where(a==1)[0]
    if len(idx)==0: return []
    eps=[[idx[0],idx[0]]]
    for i in idx[1:]:
        if i-eps[-1][1]<=gap: eps[-1][1]=i
        else: eps.append([i,i])
    return eps

files=sorted(glob.glob(os.path.join(BASE,'valve1','*.csv'))+glob.glob(os.path.join(BASE,'valve2','*.csv'))+glob.glob(os.path.join(BASE,'other','*.csv')))
def run(name, cls, group):
    R=[]
    for f in files:
        df=load(f); y=df['anomaly'].values.astype(int)
        if y.sum()==0: continue
        X=df[FEATS].values.astype(float); n=len(X); k0=max(int(n*REF),BURN+30)
        F=winfeat(adaptive_z(X)); m=cls(); m.fit(F[BURN:k0])
        thr=np.quantile(m.score(F[BURN:k0]),1-TARGET_FPR)
        a=(m.score(F)>thr).astype(int)[k0:]
        yt=y[k0:]
        yb,bl=blocks(yt); ab,_=blocks(a)
        tp=((ab==1)&(yb==1)).sum(); fp=((ab==1)&(yb==0)).sum(); fn=((ab==0)&(yb==1)).sum()
        p=tp/(tp+fp+1e-9); r=tp/(tp+fn+1e-9)
        yb2=np.diff(np.r_[0,yb,0]); st=np.where(yb2==1)[0]; en=np.where(yb2==-1)[0]
        ev=[(s0,e0) for s0,e0 in zip(st,en)]; det=0; dl=[]
        for s0,e0 in ev:
            w=ab[s0:min(e0+2,len(ab))]
            if len(w) and w.sum()>0: det+=1; dl.append(int(np.argmax(w))*bl)
        fp_eps=[e for e in episodes(ab) if not any((e[0]<=e1 and e[1]>=s0) for s0,e1 in ev)]
        nmin=(yb==0).sum()*bl/60
        R.append(dict(f1=2*p*r/(p+r+1e-9),prec=p,rec=r,base=np.mean(yb),
                      fp_h=fp*bl/60/max(nmin/60,1e-9),fe_h=len(fp_eps)/max(nmin/60,1e-9),
                      ev=det/max(len(ev),1),delay=np.median(dl) if dl else np.nan))
    A=pd.DataFrame(R)
    return dict(方案=group,方法=name,平均F1=A.f1.mean(),精确率=A.prec.mean(),召回率=A.rec.mean(),
                误报分钟比例=f"{A.fp_h.mean()/60*100:.1f}%",误报事件次每时=A.fe_h.mean(),
                事件检出率=A.ev.mean(),检测延迟中位=A.delay.median(),平凡基线F1=(2*A.base.mean()/(1+A.base.mean())))

rows=[]
def thresh_method(X,k0,y):
    pass
# 1) 工业常规：固定报警值
def run_thr():
    R=[]
    for f in files:
        df=load(f); y=df['anomaly'].values.astype(int)
        if y.sum()==0: continue
        X=df[FEATS].values.astype(float); n=len(X); k0=max(int(n*REF),BURN+30)
        med=np.median(X[BURN:k0],0); iqr=np.percentile(X[BURN:k0],75,0)-np.percentile(X[BURN:k0],25,0); sd=X[BURN:k0].std(0)
        sc=np.where(iqr>1e-9,iqr,np.where(sd>1e-9,sd,1.0))
        Z=np.abs((X-med)/sc); thr=np.quantile(Z[BURN:k0].max(1),1-TARGET_FPR)
        a=(Z.max(1)>thr).astype(int)[k0:]; yt=y[k0:]
        yb,_=blocks(yt); ab,_=blocks(a)
        tp=((ab==1)&(yb==1)).sum(); fp=((ab==1)&(yb==0)).sum(); fn=((ab==0)&(yb==1)).sum()
        p=tp/(tp+fp+1e-9); r=tp/(tp+fn+1e-9)
        yb2=np.diff(np.r_[0,yb,0]); st=np.where(yb2==1)[0]; en=np.where(yb2==-1)[0]
        ev=list(zip(st,en)); det=0; dl=[]
        for s0,e0 in ev:
            w=ab[s0:min(e0+2,len(ab))]
            if len(w) and w.sum()>0: det+=1; dl.append(int(np.argmax(w))*60)
        fp_eps=[e for e in episodes(ab) if not any((e[0]<=e1 and e[1]>=s0) for s0,e1 in ev)]
        nmin=(yb==0).sum()
        R.append(dict(f1=2*p*r/(p+r+1e-9),prec=p,rec=r,base=np.mean(yb),fp_h=fp/max(nmin,1),
                      fe_h=len(fp_eps)/max(nmin/60,1e-9),ev=det/max(len(ev),1),delay=np.median(dl) if dl else np.nan))
    A=pd.DataFrame(R)
    return dict(方案='① 传统做法',方法='固定报警值（逐信号稳健 z）',平均F1=A.f1.mean(),精确率=A.prec.mean(),
                召回率=A.rec.mean(),误报分钟比例=f"{A.fp_h.mean()*100:.1f}%",误报事件次每时=A.fe_h.mean(),
                事件检出率=A.ev.mean(),检测延迟中位=A.delay.median(),平凡基线F1=(2*A.base.mean()/(1+A.base.mean())))
rows.append(run_thr())
for nm,cls in [('马氏距离',Maha),('PCA 重构误差',PCAsp),('孤立森林',IF)]:
    rows.append(run(nm,cls,'② 本方案（自适应基线+滑窗特征+1分钟判决）'))
df=pd.DataFrame(rows)
df.to_csv(os.path.join(OUT,'demo_results_v5.csv'),index=False,encoding='utf-8-sig')
open(os.path.join(OUT,'demo_table_v5.md'),'w',encoding='utf-8').write(df.to_markdown(index=False,floatfmt='.3f'))
print(df.to_markdown(index=False,floatfmt='.3f'))
print('\n注：平均故障时间占比=%.2f，平凡"一直报警"策略的F1=%.3f（作为参考线）' % (df['平凡基线F1'].iloc[0]/(2-df['平凡基线F1'].iloc[0]), df['平凡基线F1'].iloc[0]))
