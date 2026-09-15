# -*- coding: utf-8 -*-
"""SKAB 基准：工业界常用方法 vs 无监督学习方法的异常检测对比
协议：仅用 anomaly-free 文件训练/定阈值（冷启动，无故障样本），在含故障的文件上评估。
"""
import numpy as np, pandas as pd, glob, os, time, json
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest

BASE = r'C:\Users\boyi\Desktop\BEWG_PdM\data\SKAB-master\data'
OUT  = r'C:\Users\boyi\Desktop\BEWG_PdM\results'
os.makedirs(OUT, exist_ok=True)

FEATS = ['Accelerometer1RMS','Accelerometer2RMS','Current','Pressure','Temperature',
         'Thermocouple','Voltage','Volume Flow RateRMS']
WIN, TARGET_FPR = 15, 0.005

def load(fp):
    df = pd.read_csv(fp, sep=';')
    df.columns = [c.strip() for c in df.columns]
    for c in df.columns:
        if c not in ('datetime','anomaly','changepoint'):
            df[c] = pd.to_numeric(df[c], errors='coerce')
    return df

def feats(df):
    X = df[FEATS].astype(float)
    r = X.rolling(WIN, min_periods=1)
    out = pd.concat([X, r.mean().add_suffix('_m'), r.std().fillna(0).add_suffix('_s'),
                     X.diff().fillna(0).add_suffix('_d')], axis=1)
    return out.bfill().fillna(0).values

# ---------- 数据 ----------
tr = load(os.path.join(BASE,'anomaly-free','anomaly-free.csv'))
test_files = sorted(glob.glob(os.path.join(BASE,'valve1','*.csv')) +
                    glob.glob(os.path.join(BASE,'valve2','*.csv')) +
                    glob.glob(os.path.join(BASE,'other','*.csv')))
trF = feats(tr)
print('train rows', len(tr), 'features', trF.shape[1], '| test files', len(test_files))

# ---------- 方法 ----------
def robust_z_score(Xtr_raw, Xte_raw):
    med = np.median(Xtr_raw, 0); mad = np.median(np.abs(Xtr_raw - med), 0)*1.4826
    mad[mad == 0] = 1e-9
    f = lambda A: np.abs((A - med)/mad).max(1)
    return f(Xtr_raw), f(Xte_raw)

class PCARecon:
    def __init__(self, k=0.9):
        self.sc = None; self.pca = None; self.k = k
    def fit(self, X):
        self.sc = StandardScaler().fit(X)
        Z = self.sc.transform(X)
        self.pca = PCA(n_components=self.k, random_state=0).fit(Z)
    def score(self, X):
        Z = self.sc.transform(X)
        R = Z - self.pca.inverse_transform(self.pca.transform(Z))
        return np.sqrt((R**2).sum(1))

class Mahalanobis:
    def fit(self, X):
        self.mu = X.mean(0)
        C = np.cov((X - self.mu).T) + np.eye(X.shape[1])*1e-6
        self.P = np.linalg.inv(C)
    def score(self, X):
        D = X - self.mu
        return np.sqrt(np.einsum('ij,jk,ik->i', D, self.P, D))

def run():
    rows = []; per_file = {}
    # ---- 阈值法（工业界通用做法：固定报警值 / 稳健z分数）----
    t0 = time.time()
    str_, ste_ = robust_z_score(tr[FEATS].values.astype(float),
                                np.vstack([feats(load(f))[:, :len(FEATS)] for f in test_files]))
    rows.append(dict(method='固定阈值法 (稳健 z-score, 工业常规)', fit_s=time.time()-t0,
                     score_train=str_, score_test=ste_, mode='concat'))
    # ---- 其余方法（仅在正常数据上训练）----
    trX = trF
    methods = {}
    t0 = time.time(); m = Mahalanobis(); m.fit(trX)
    methods['马氏距离 (Mahalanobis)'] = (m, time.time()-t0)
    t0 = time.time(); p = PCARecon(); p.fit(trX)
    methods['PCA 重构误差 (SPE, 过程工业标准)'] = (p, time.time()-t0)
    t0 = time.time(); iso = IsolationForest(n_estimators=200, random_state=0, n_jobs=-1).fit(trX)
    class IF: 
        def score(self, X): return -iso.score_samples(X)
    methods['孤立森林 (IsolationForest)'] = (IF(), time.time()-t0)
    for name, (mdl, fs) in methods.items():
        rows.append(dict(method=name, fit_s=fs, score_train=mdl.score(trX),
                         score_test=None, mode='per_file', model=mdl))
    # ---- 评估 ----
    out = []
    for r in rows:
        if r['mode'] == 'concat':
            # 逐文件切分
            lens = [len(load(f)) for f in test_files]
            scores = np.split(r['score_test'], np.cumsum(lens)[:-1])
        else:
            scores = [r['model'].score(feats(load(f))) for f in test_files]
        thr = np.quantile(r['score_train'], 1-TARGET_FPR)
        f1s=[]; prs=[]; rcs=[]; det=0; tot=0; delays=[]; fp_alarms=0; normal_min=0; fpr_train=(r['score_train']>thr).mean()
        for f, s in zip(test_files, scores):
            df = load(f); y = df['anomaly'].values.astype(int)
            if y.sum() == 0: continue
            a = (s > thr).astype(int)
            tp = ((a==1)&(y==1)).sum(); fp = ((a==1)&(y==0)).sum(); fn = ((a==0)&(y==1)).sum()
            prec = tp/(tp+fp+1e-9); rec = tp/(tp+fn+1e-9); f1 = 2*prec*rec/(prec+rec+1e-9)
            f1s.append(f1); prs.append(prec); rcs.append(rec)
            fp_alarms += fp; normal_min += (y==0).sum()/60.0
            # 事件级
            yb = np.diff(np.r_[0, y, 0]); starts = np.where(yb==1)[0]; ends = np.where(yb==-1)[0]
            for st, en in zip(starts, ends):
                if en-st < 5: continue
                tot += 1
                w = a[st:min(en+60, len(a))]
                if w.sum() > 0:
                    det += 1; delays.append(int(np.argmax(w)))
        out.append(dict(method=r['method'], F1=np.mean(f1s), P=np.mean(prs), R=np.mean(rcs),
                        事件检出=f'{det}/{tot}',
                        det=f'{det/max(tot,1)*100:.0f}%',
                        延迟中位=f'{np.median(delays):.0f}s' if delays else '-',
                        误报次每时=f'{fp_alarms/max(normal_min,1)*60:.1f}',
                        训练报错率=f'{fpr_train*100:.1f}%', 训练秒=f"{r['fit_s']:.1f}"))
    df = pd.DataFrame(out).sort_values('F1', ascending=False)
    df.to_csv(os.path.join(OUT,'baseline_results.csv'), index=False, encoding='utf-8-sig')
    with open(os.path.join(OUT,'baseline_table.md'),'w',encoding='utf-8') as fh:
        fh.write(df.to_markdown(index=False, floatfmt='.3f'))
    print(df.to_markdown(index=False, floatfmt='.3f'))

run()
