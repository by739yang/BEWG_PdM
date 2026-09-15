# -*- coding: utf-8 -*-
"""SKAB 变点检测器 vs 重构型检测器 + 融合方案（同样的协议与指标）"""
import numpy as np, pandas as pd, glob, os
from sklearn.decomposition import PCA
BASE=r'C:\Users\boyi\Desktop\BEWG_PdM\data\SKAB-master\data'
OUT=r'C:\Users\boyi\Desktop\BEWG_PdM\results'
FEATS=['Accelerometer1RMS','Accelerometer2RMS','Current','Pressure','Temperature','Thermocouple','Voltage','Volume Flow RateRMS']
REF=0.40; BURN=120; AW=120; TARGET_FPR=0.005; BLOCK=60
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
        sc=np.where(iqr>1e-9,iqr,np.where(sd>1e-9,sd,1.0)); sc=np.maximum(sc,0.02*np.maximum(np.abs(med),1e-3))
        Z[t]=(X[t]-med)/sc
    return Z
def cusum_score(Z, A=300, B=60):
    n,d=Z.shape; s=np.zeros(n)
    for t in range(A+B, n):
        a=Z[t-A-B:t-B]; b=Z[t-B:t]
        stat=np.abs(a.mean(0)-b.mean(0))/(a.std(0)+b.std(0)+1e-3)
        s[t]=stat.max()
    return s
class PCAsp:
    def fit(self,X): self.pca=PCA(n_components=0.9,random_state=0).fit(X)
    def score(self,X):
        R=X-self.pca.inverse_transform(self.pca.transform(X)); return np.sqrt((R**2).sum(1))
def wf(Z,w=15):
    Zd=pd.DataFrame(Z); r=Zd.rolling(w,min_periods=1); return np.nan_to_num(np.hstack([Z,r.mean().values,r.std().fillna(0).values]))
def blocks(a,b=BLOCK):
    m=(len(a)//b)*b; return (a[:m].reshape(-1,b).mean(1)>0.5).astype(int)
def persist(a,k=3): return (pd.Series(a).rolling(k,min_periods=1).sum().values>=k).astype(int)
def metrics(y,a):
    yb=blocks(y); ab=blocks(a)
    tp=((ab==1)&(yb==1)).sum(); fp=((ab==1)&(yb==0)).sum(); fn=((ab==0)&(yb==1)).sum()
    p=tp/(tp+fp+1e-9); r=tp/(tp+fn+1e-9)
    yb2=np.diff(np.r_[0,yb,0]); st=np.where(yb2==1)[0]; en=np.where(yb2==-1)[0]
    det=0; dl=[]
    for s0,e0 in zip(st,en):
        w=ab[s0:min(e0+2,len(ab))]
        if len(w) and w.sum()>0: det+=1; dl.append(int(np.argmax(w))*BLOCK)
    return dict(f1=2*p*r/(p+r+1e-9),prec=p,rec=r,fp=(ab[yb==0]==1).mean() if (yb==0).sum() else 0,
                ev=det/max(len(st),1),delay=np.median(dl) if dl else np.nan)
files=sorted(glob.glob(os.path.join(BASE,'valve1','*.csv'))+glob.glob(os.path.join(BASE,'valve2','*.csv'))+glob.glob(os.path.join(BASE,'other','*.csv')))
R1=[];R2=[];R3=[]
for f in files:
    d=load(f); y=d['anomaly'].values.astype(int)
    if y.sum()==0: continue
    X=d[FEATS].values.astype(float); n=len(X); k0=max(int(n*REF),BURN+30)
    Z=adaptive_z(X); F=wf(Z)
    sc_c=cusum_score(Z); thr_c=np.quantile(sc_c[BURN:k0],1-TARGET_FPR); a_c=persist((sc_c>thr_c).astype(int))
    pca=PCAsp(); pca.fit(F[BURN:k0]); sc_p=pca.score(F); thr_p=np.quantile(sc_p[BURN:k0],1-TARGET_FPR); a_p=persist((sc_p>thr_p).astype(int))
    a_f=((a_c==1)|(a_p==1)).astype(int)
    R1.append(metrics(y[k0:],a_c[k0:])); R2.append(metrics(y[k0:],a_p[k0:])); R3.append(metrics(y[k0:],a_f[k0:]))
def row(name,R):
    A=pd.DataFrame(R); return dict(方案=name,平均F1=A.f1.mean(),精确率=A.prec.mean(),召回率=A.rec.mean(),
        误报分钟比例=f"{A.fp.mean()*100:.1f}%",事件检出率=A.ev.mean(),检测延迟中位=A.delay.median())
df=pd.DataFrame([row('变点检测器（阶跃/堵塞/阀门类）',R1),
                 row('PCA 重构误差（缓变/磨损类）',R2),
                 row('融合（取并集）',R3)])
df.to_csv(os.path.join(OUT,'cp_results.csv'),index=False,encoding='utf-8-sig')
open(os.path.join(OUT,'cp_table.md'),'w',encoding='utf-8').write(df.to_markdown(index=False,floatfmt='.3f'))
print(df.to_markdown(index=False,floatfmt='.3f'))
