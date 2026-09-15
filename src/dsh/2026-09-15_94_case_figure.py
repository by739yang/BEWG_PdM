# -*- coding: utf-8 -*-
import numpy as np, pandas as pd, os
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif']=['Microsoft YaHei']; plt.rcParams['axes.unicode_minus']=False
from sklearn.decomposition import PCA
BASE=r'C:\Users\boyi\Desktop\BEWG_PdM\data\SKAB-master\data'
OUT=r'C:\Users\boyi\Desktop\BEWG_PdM\results\2026-09-15\dsh'
FEATS=['Accelerometer1RMS','Accelerometer2RMS','Current','Pressure','Temperature','Thermocouple','Voltage','Volume Flow RateRMS']
def load(fp):
    df=pd.read_csv(fp,sep=';'); df.columns=[c.strip() for c in df.columns]
    for c in df.columns:
        if c not in ('datetime','anomaly','changepoint'): df[c]=pd.to_numeric(df[c],errors='coerce')
    return df
def az(X,W=120,minp=45):
    n=X.shape[0]; Z=np.zeros_like(X)
    for t in range(n):
        win=X[max(0,t-W):t]
        if len(win)<minp: win=X[:min(minp,n)]
        med=np.median(win,0); iqr=np.percentile(win,75,0)-np.percentile(win,25,0); sd=win.std(0)
        sc=np.where(iqr>1e-9,iqr,np.where(sd>1e-9,sd,1.0)); sc=np.maximum(sc,0.02*np.maximum(np.abs(med),1e-3))
        Z[t]=(X[t]-med)/sc
    return Z
def feat(Z,w=15):
    Zd=pd.DataFrame(Z); r=Zd.rolling(w,min_periods=1); return np.nan_to_num(np.hstack([Z,r.mean().values,r.std().fillna(0).values]))
d=load(os.path.join(BASE,'valve1','0.csv')); y=d['anomaly'].values.astype(int); X=d[FEATS].values.astype(float); n=len(X)
F=feat(az(X)); p=PCA(n_components=0.9,random_state=0).fit(F[120:456])
sc=np.sqrt(((F-p.inverse_transform(p.transform(F)))**2).sum(1))
thr=np.quantile(sc[120:456],0.995); a=(sc>thr).astype(int)
print('阈值=%.3f  标定期(120-456s)超限率=%.3f%%' % (thr,(sc[120:456]>thr).mean()*100))
for nm,sl in [('参考期0-456s',slice(0,456)),('故障前正常段456-570s',slice(456,570)),('故障段570s后',slice(570,None))]:
    print('  %-18s 平均异常分数=%6.2f 超限比例=%5.1f%%' % (nm, sc[sl].mean(), (sc[sl]>thr).mean()*100))
fig,ax=plt.subplots(4,1,figsize=(12,9),sharex=True)
for i,name in enumerate(['Accelerometer1RMS','Temperature','Volume Flow RateRMS']):
    j=FEATS.index(name); ax[i].plot(X[:,j],lw=.8,color='#1f4e79')
    ax[i].set_ylabel(name,fontsize=8); ax[i].axvspan(570,n,color='red',alpha=.12); ax[i].grid(alpha=.3)
ax[3].plot(sc,lw=.9,color='#c00000'); ax[3].axhline(thr,ls='--',c='k',lw=.8)
ax[3].axvspan(570,n,color='red',alpha=.12); ax[3].set_ylabel('异常分数(SPE)',fontsize=8); ax[3].grid(alpha=.3)
ax[3].set_xlabel('时间（秒，1Hz）')
plt.suptitle('SKAB 真实水泵数据：信号形态 / 热漂移 / 退化信号 / 异常分数（红=真实故障区间）',fontsize=11)
plt.tight_layout(); plt.savefig(os.path.join(OUT,'case_valve1_0.png'),dpi=140)
print('saved', os.path.join(OUT,'case_valve1_0.png'))
