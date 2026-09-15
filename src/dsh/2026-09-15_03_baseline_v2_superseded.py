# -*- coding: utf-8 -*-
"""SKAB 基准 v2：所有方法在同一特征/同一判决协议下对比（更公平）
- 特征：逐文件稳健标准化(中位数/IQR，不使用标签) + 15s 滑窗均值/标准差
- 判决：分数做 15s 中值滤波后与阈值比较；阈值由"仅正常样本"的训练文件按目标误报率标定
- 指标：逐点 F1、误报次数/小时、事件检出率、检测延迟
"""
import numpy as np, pandas as pd, glob, os, time
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest

BASE = r'C:\Users\boyi\Desktop\BEWG_PdM\data\SKAB-master\data'
OUT  = r'C:\Users\boyi\Desktop\BEWG_PdM\results\2026-09-15\dsh'
os.makedirs(OUT, exist_ok=True)
FEATS = ['Accelerometer1RMS','Accelerometer2RMS','Current','Pressure','Temperature',
         'Thermocouple','Voltage','Volume Flow RateRMS']
WIN, SMOOTH, TARGET_FPR = 15, 15, 0.005

def load(fp):
    df = pd.read_csv(fp, sep=';'); df.columns = [c.strip() for c in df.columns]
    for c in df.columns:
        if c not in ('datetime','anomaly','changepoint'):
            df[c] = pd.to_numeric(df[c], errors='coerce')
    return df

def prep(df, ref=None):
    X = df[FEATS].values.astype(float)
    if ref is None:
        med = np.median(X,0); iqr = np.percentile(X,75,0)-np.percentile(X,25,0); ref = (med,iqr)
    med, iqr = ref
    Z = (X-med)/np.where(iqr==0, 1e-9, iqr)
    Zd = pd.DataFrame(Z, columns=FEATS); r = Zd.rolling(WIN, min_periods=1)
    F = np.hstack([Z, r.mean().values, r.std().fillna(0).values])
    return np.nan_to_num(F), ref

def smooth(s, w=SMOOTH):
    return pd.Series(s).rolling(w, min_periods=1, center=True).median().values

class Mahalanobis:
    def fit(self, X):
        self.mu = X.mean(0); C = np.cov((X-self.mu).T)+np.eye(X.shape[1])*1e-6; self.P = np.linalg.inv(C)
    def score(self, X):
        D = X-self.mu; return np.sqrt(np.einsum('ij,jk,ik->i', D, self.P, D))

class PCARecon:
    def fit(self, X):
        self.sc = StandardScaler().fit(X); Z = self.sc.transform(X)
        self.pca = PCA(n_components=0.9, random_state=0).fit(Z)
    def score(self, X):
        Z = self.sc.transform(X); R = Z-self.pca.inverse_transform(self.pca.transform(Z))
        return np.sqrt((R**2).sum(1))

class IForest:
    def fit(self, X):
        self.m = IsolationForest(n_estimators=200, random_state=0, n_jobs=-1).fit(X)
    def score(self, X): return -self.m.score_samples(X)

class ZThresh:   # 工业界常规：稳健 z 分数报警值
    def fit(self, X): self.k = X.shape[1]
    def score(self, X): return np.abs(X[:, :8]).max(1)*3.0   # 用标准化原信号

tr = load(os.path.join(BASE,'anomaly-free','anomaly-free.csv'))
trF, trref = prep(tr)
test_files = sorted(glob.glob(os.path.join(BASE,'valve1','*.csv')) +
                    glob.glob(os.path.join(BASE,'valve2','*.csv')) +
                    glob.glob(os.path.join(BASE,'other','*.csv')))
print('train', trF.shape, '| test files', len(test_files))

models = {'固定阈值法 (稳健 z-score, 工业常规)': ZThresh(),
          '马氏距离 (Mahalanobis)': Mahalanobis(),
          'PCA 重构误差 SPE (过程工业标准)': PCARecon(),
          '孤立森林 (IsolationForest)': IForest()}

rows = []
for name, mdl in models.items():
    t0 = time.time(); mdl.fit(trF); fit_s = time.time()-t0
    thr = np.quantile(smooth(mdl.score(trF)), 1-TARGET_FPR)
    f1s=[];prs=[];rcs=[];det=0;tot=0;delays=[];fp=0;nmin=0
    for f in test_files:
        df = load(f); y = df['anomaly'].values.astype(int)
        if y.sum() == 0: continue
        F,_ = prep(df, None)           # 逐文件稳健归一化（不使用标签）
        s = smooth(mdl.score(F)); a = (s > thr).astype(int)
        tp=((a==1)&(y==1)).sum(); fp_=((a==1)&(y==0)).sum(); fn=((a==0)&(y==1)).sum()
        p=tp/(tp+fp_+1e-9); r=tp/(tp+fn+1e-9)
        f1s.append(2*p*r/(p+r+1e-9)); prs.append(p); rcs.append(r)
        fp += fp_; nmin += (y==0).sum()/60
        yb=np.diff(np.r_[0,y,0]); st=np.where(yb==1)[0]; en=np.where(yb==-1)[0]
        for s0,e0 in zip(st,en):
            if e0-s0 < 5: continue
            tot += 1; w=a[s0:min(e0+60,len(a))]
            if w.sum()>0: det+=1; delays.append(int(np.argmax(w)))
    rows.append(dict(方法=name, 平均F1=np.mean(f1s), 平均精确率=np.mean(prs), 平均召回率=np.mean(rcs),
                     事件检出率=f'{det/max(tot,1)*100:.0f}% ({det}/{tot})',
                     检测延迟中位=f'{np.median(delays):.0f}s' if delays else '-',
                     误报次每时=f'{fp/max(nmin,1)*60:.1f}', 训练耗时=f'{fit_s:.1f}s'))
    print('done', name, flush=True)

df = pd.DataFrame(rows).sort_values('平均F1', ascending=False)
df.to_csv(os.path.join(OUT,'baseline_results_v2.csv'), index=False, encoding='utf-8-sig')
open(os.path.join(OUT,'baseline_table_v2.md'),'w',encoding='utf-8').write(df.to_markdown(index=False, floatfmt='.3f'))
print(df.to_markdown(index=False, floatfmt='.3f'))
