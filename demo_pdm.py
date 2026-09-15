# -*- coding: utf-8 -*-
"""SKAB 实测对比：工业常规报警值 vs 标准过程监控 vs 我们的自适应方案
协议/诚实性声明：所有方法均不使用故障标签训练或调参；阈值按"参考期误报率<=0.5%"标定。
评估：留出参考期之后的时间段（模拟上线后持续监测）。
"""
import numpy as np, pandas as pd, glob, os
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif']=['Microsoft YaHei']; plt.rcParams['axes.unicode_minus']=False

BASE=r'C:\Users\boyi\Desktop\BEWG_PdM\data\SKAB-master\data'
OUT=r'C:\Users\boyi\Desktop\BEWG_PdM\results'; os.makedirs(OUT,exist_ok=True)
FEATS=['Accelerometer1RMS','Accelerometer2RMS','Current','Pressure','Temperature','Thermocouple','Voltage','Volume Flow RateRMS']
REF=0.20; TARGET_FPR=0.005; PERSIST=3; AW=300

def load(fp):
    df=pd.read_csv(fp,sep=';'); df.columns=[c.strip() for c in df.columns]
    for c in df.columns:
        if c not in ('datetime','anomaly','changepoint'): df[c]=pd.to_numeric(df[c],errors='coerce')
    return df

def static_z(X, Xref):
    med=np.median(Xref,0); iqr=np.percentile(Xref,75,0)-np.percentile(Xref,25,0); sd=Xref.std(0)
    sc=np.where(iqr>1e-9,iqr,np.where(sd>1e-9,sd,1.0))
    return (X-med)/sc

def adaptive_z(X, W=AW, minp=60):
    n=X.shape[0]; Z=np.zeros_like(X)
    for t in range(n):
        lo=max(0,t-W); win=X[lo:t]
        if len(win)<minp: win=X[:min(minp,n)]
        med=np.median(win,0)
        iqr=np.percentile(win,75,0)-np.percentile(win,25,0); sd=win.std(0)
        sc=np.where(iqr>1e-9,iqr,np.where(sd>1e-9,sd,1.0))
        sc=np.maximum(sc, 0.02*np.maximum(np.abs(med),1e-3))   # 相对离散度下限，防退化传感器
        Z[t]=(X[t]-med)/sc
    return Z

def winfeat(Z, w=15):
    Zd=pd.DataFrame(Z); r=Zd.rolling(w,min_periods=1)
    return np.nan_to_num(np.hstack([Z, r.mean().values, r.std().fillna(0).values]))

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

def persist(a, k=PERSIST):
    if k<=1: return a
    return (pd.Series(a).rolling(k,min_periods=1).sum().values>=k).astype(int)

def metrics(y,a):
    tp=((a==1)&(y==1)).sum(); fp=((a==1)&(y==0)).sum(); fn=((a==0)&(y==1)).sum()
    p=tp/(tp+fp+1e-9); r=tp/(tp+fn+1e-9)
    yb=np.diff(np.r_[0,y,0]); st=np.where(yb==1)[0]; en=np.where(yb==-1)[0]
    ev=[(s0,e0) for s0,e0 in zip(st,en) if e0-s0>=5]; det=0; dl=[]
    for s0,e0 in ev:
        w=a[s0:min(e0+60,len(a))]
        if len(w) and w.sum()>0: det+=1; dl.append(int(np.argmax(w)))
    return dict(f1=2*p*r/(p+r+1e-9),prec=p,rec=r,fp_h=fp/max((y==0).sum()/60,1e-9)*60,
                ev=det/max(len(ev),1),delay=np.median(dl) if dl else np.nan)

files=sorted(glob.glob(os.path.join(BASE,'valve1','*.csv'))+glob.glob(os.path.join(BASE,'valve2','*.csv'))+glob.glob(os.path.join(BASE,'other','*.csv')))
rows=[]; example=None

def evaluate(pipeline, name, group, need_ref_fit=True):
    R=[]
    for f in files:
        df=load(f); y=df['anomaly'].values.astype(int)
        if y.sum()==0: continue
        X=df[FEATS].values.astype(float); n=len(X); k0=max(int(n*REF),60)
        a=pipeline(X,k0,y)
        R.append(metrics(y[k0:],a[k0:]))
    A=pd.DataFrame(R)
    rows.append(dict(方案=group,方法=name,平均F1=A.f1.mean(),精确率=A.prec.mean(),召回率=A.rec.mean(),
                     误报次每时=A.fp_h.mean(),事件检出率=A.ev.mean(),检测延迟中位=A.delay.median()))

# ---- 1. 工业常规：固定报警值（逐信号稳健 z 分数，取最大） ----
def pipe_thresh(X,k0,y):
    Z=static_z(X,X[:k0])
    thr=np.quantile(np.abs(Z[:k0]).max(1),1-TARGET_FPR)
    return (np.abs(Z).max(1)>thr).astype(int)
evaluate(pipe_thresh,'固定报警值（逐信号稳健 z-score）','① 传统做法')

# ---- 2. 标准过程监控：静态基线 + 马氏距离 ----
def pipe_maha_static(X,k0,y):
    F=winfeat(static_z(X,X[:k0])); m=Maha(); m.fit(F[:k0])
    thr=np.quantile(m.score(F[:k0]),1-TARGET_FPR)
    return persist((m.score(F)>thr).astype(int))
evaluate(pipe_maha_static,'马氏距离（静态基线 + 滑窗统计）','② 标准过程监控')

# ---- 3. 我们的方案：自适应基线 + 滑窗统计 + 多模型 + 持续性判据 ----
for nm, cls in [('马氏距离',Maha),('PCA 重构误差',PCAsp),('孤立森林',IF)]:
    def pipe(X,k0,y,cls=cls):
        F=winfeat(adaptive_z(X)); m=cls(); m.fit(F[:k0])
        thr=np.quantile(m.score(F[:k0]),1-TARGET_FPR)
        return persist((m.score(F)>thr).astype(int))
    evaluate(pipe,nm,'③ 本方案（自适应基线）')

df=pd.DataFrame(rows)
df.to_csv(os.path.join(OUT,'demo_results.csv'),index=False,encoding='utf-8-sig')
open(os.path.join(OUT,'demo_table.md'),'w',encoding='utf-8').write(df.to_markdown(index=False,floatfmt='.3f'))

# ---- 示意图：一台泵的全过程 ----
f=os.path.join(BASE,'valve1','0.csv'); df0=load(f); y=df0['anomaly'].values; X=df0[FEATS].values.astype(float); n=len(X); k0=int(n*REF)
F=winfeat(adaptive_z(X)); m=Maha(); m.fit(F[:k0]); s=m.score(F)
thr=np.quantile(s[:k0],1-TARGET_FPR); a=persist((s>thr).astype(int))
fig,ax=plt.subplots(3,1,figsize=(12,8),sharex=True)
for i,name in enumerate(['Accelerometer1RMS','Temperature','Volume Flow RateRMS']):
    j=FEATS.index(name); ax[i].plot(X[:,j],lw=.8,color='#1f4e79'); ax[i].set_ylabel(name,fontsize=8)
    ax[i].axvspan(np.argmax(y==1),n,color='red',alpha=.12); ax[i].grid(alpha=.3)
ax[2].set_xlabel('时间（秒，1Hz 采样）')
plt.suptitle('SKAB 实测（泵）: 红色区间=真实故障  下方为自适应方案判决',fontsize=11)
plt.tight_layout(); plt.savefig(os.path.join(OUT,'demo_case.png'),dpi=140)
print(df.to_markdown(index=False,floatfmt='.3f'))
print('\n判决对比（该文件前 1200 秒）: 本方案报警点数=%d, 其中落在故障期=%d' % (a.sum(), ((a==1)&(y==1)).sum()))
