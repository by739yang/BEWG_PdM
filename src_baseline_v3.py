# -*- coding: utf-8 -*-
"""SKAB 基准 v3：A)全局模型直接迁移  B)逐设备自校准  协议不使用任何故障标签"""
import numpy as np, pandas as pd, glob, os
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest

BASE = r'C:\Users\boyi\Desktop\BEWG_PdM\data\SKAB-master\data'
OUT  = r'C:\Users\boyi\Desktop\BEWG_PdM\results'
FEATS = ['Accelerometer1RMS','Accelerometer2RMS','Current','Pressure','Temperature',
         'Thermocouple','Voltage','Volume Flow RateRMS']
WIN, SMOOTH, TARGET_FPR, REF_FRAC = 15, 15, 0.005, 0.20

def load(fp):
    df = pd.read_csv(fp, sep=';'); df.columns=[c.strip() for c in df.columns]
    for c in df.columns:
        if c not in ('datetime','anomaly','changepoint'):
            df[c]=pd.to_numeric(df[c], errors='coerce')
    return df

def rscale(X):
    med=np.median(X,0); iqr=np.percentile(X,75,0)-np.percentile(X,25,0); sd=X.std(0)
    sc=np.where(iqr>1e-9, iqr, np.where(sd>1e-9, sd, 1.0))
    return med, sc

def build(X, med, iqr):
    Z=(X-med)/iqr
    Zd=pd.DataFrame(Z,columns=FEATS); r=Zd.rolling(WIN,min_periods=1)
    return np.nan_to_num(np.hstack([Z, r.mean().values, r.std().fillna(0).values]))

def smooth(s,w=SMOOTH): return pd.Series(s).rolling(w,min_periods=1,center=True).median().values

class Mahalanobis:
    def fit(self,X):
        self.mu=X.mean(0); C=np.cov((X-self.mu).T)+np.eye(X.shape[1])*1e-6; self.P=np.linalg.inv(C)
    def score(self,X):
        D=X-self.mu; return np.sqrt(np.einsum('ij,jk,ik->i',D,self.P,D))
class PCARecon:
    def fit(self,X):
        self.sc=StandardScaler().fit(X); self.pca=PCA(n_components=0.9,random_state=0).fit(self.sc.transform(X))
    def score(self,X):
        Z=self.sc.transform(X); R=Z-self.pca.inverse_transform(self.pca.transform(Z)); return np.sqrt((R**2).sum(1))
class IForest:
    def fit(self,X): self.m=IsolationForest(n_estimators=200,random_state=0,n_jobs=-1).fit(X)
    def score(self,X): return -self.m.score_samples(X)
class ZThresh:
    def fit(self,X): pass
    def score(self,X): return np.abs(X[:,:8]).max(1)

MODELS = {'固定阈值法 (稳健 z-score)': ZThresh, '马氏距离 (Mahalanobis)': Mahalanobis,
          'PCA 重构误差 SPE': PCARecon, '孤立森林 (IsolationForest)': IForest}

def metrics(y,a):
    tp=((a==1)&(y==1)).sum(); fp=((a==1)&(y==0)).sum(); fn=((a==0)&(y==1)).sum()
    p=tp/(tp+fp+1e-9); r=tp/(tp+fn+1e-9)
    yb=np.diff(np.r_[0,y,0]); st=np.where(yb==1)[0]; en=np.where(yb==-1)[0]
    ev=[(s0,e0) for s0,e0 in zip(st,en) if e0-s0>=5]; det=0; dl=[]
    for s0,e0 in ev:
        w=a[s0:min(e0+60,len(a))]
        if len(w) and w.sum()>0: det+=1; dl.append(int(np.argmax(w)))
    return dict(f1=2*p*r/(p+r+1e-9), prec=p, rec=r,
                fp_h=fp/max((y==0).sum()/60,1e-9)*60,
                ev=det/max(len(ev),1), delay=np.median(dl) if dl else np.nan, n_ev=len(ev))

test_files = sorted(glob.glob(os.path.join(BASE,'valve1','*.csv')) +
                    glob.glob(os.path.join(BASE,'valve2','*.csv')) +
                    glob.glob(os.path.join(BASE,'other','*.csv')))

tr = load(os.path.join(BASE,'anomaly-free','anomaly-free.csv'))
Xtr = tr[FEATS].values.astype(float)
med_tr, sc_tr = rscale(Xtr); Ftr = build(Xtr, med_tr, sc_tr)

rows=[]
for name, cls in MODELS.items():
    m=cls(); m.fit(Ftr); thr=np.quantile(smooth(m.score(Ftr)),1-TARGET_FPR)
    R=[]
    for f in test_files:
        df=load(f); y=df['anomaly'].values.astype(int)
        if y.sum()==0: continue
        X=df[FEATS].values.astype(float)
        _m,_s = rscale(X); F=build(X, _m, _s)
        a=(smooth(m.score(F))>thr).astype(int)
        R.append(metrics(y,a))
    A=pd.DataFrame(R)
    rows.append(dict(方案='A 全局模型直接迁移', 方法=name, 平均F1=A.f1.mean(), 精确率=A.prec.mean(),
                     召回率=A.rec.mean(), 误报次每时=A.fp_h.mean(), 事件检出率=A.ev.mean(),
                     检测延迟中位=A.delay.median()))
    print('A', name, flush=True)

for name, cls in MODELS.items():
    R=[]
    for f in test_files:
        df=load(f); y=df['anomaly'].values.astype(int)
        if y.sum()==0: continue
        X=df[FEATS].values.astype(float); n=len(X); k0=max(int(n*REF_FRAC), 60)
        med,sc = rscale(X[:k0]); F=build(X, med, sc)
        mdl=cls(); mdl.fit(F[:k0]); thr=np.quantile(smooth(mdl.score(F[:k0])),1-TARGET_FPR)
        a=np.zeros(n, dtype=int)
        if name.startswith('固定阈值'):
            a[:]= (smooth(mdl.score(F))>thr).astype(int)   # 阈值法无训练，全时段可用
        else:
            a[k0:]= (smooth(mdl.score(F))[k0:]>thr).astype(int)
        R.append(metrics(y[k0:], a[k0:]))
    A=pd.DataFrame(R)
    rows.append(dict(方案='B 逐设备自校准(前20%历史)', 方法=name, 平均F1=A.f1.mean(), 精确率=A.prec.mean(),
                     召回率=A.rec.mean(), 误报次每时=A.fp_h.mean(), 事件检出率=A.ev.mean(),
                     检测延迟中位=A.delay.median()))
    print('B', name, flush=True)

df=pd.DataFrame(rows)
df.to_csv(os.path.join(OUT,'baseline_results_v3.csv'),index=False,encoding='utf-8-sig')
open(os.path.join(OUT,'baseline_table_v3.md'),'w',encoding='utf-8').write(df.to_markdown(index=False,floatfmt='.3f'))
print(df.to_markdown(index=False,floatfmt='.3f'))
