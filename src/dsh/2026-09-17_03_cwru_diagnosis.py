# -*- coding: utf-8 -*-
"""诊断模块 v1：CWRU 轴承故障分类（DSH，2026-09-17）
数据：data/cwru/{Normal,IR_7,OR6_7,B_7}.npz，DE 通道 48kHz，每个文件 485,643 点。
切分：不重叠窗口 2048 点；按时间前后 6:4 划分训练/测试（避免相邻窗口泄漏）。"""
import numpy as np, pandas as pd, os, json
from scipy.stats import kurtosis, skew
from scipy.signal import hilbert
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.metrics import accuracy_score, f1_score, confusion_matrix
OUT='results/2026-09-17/dsh'; os.makedirs(OUT,exist_ok=True)
FILES=[('正常','data/cwru/Normal.npz'),('内圈故障','data/cwru/IR_7.npz'),
       ('外圈故障','data/cwru/OR6_7.npz'),('滚动体故障','data/cwru/B_7.npz')]
W=2048
def feats(x):
    x=x-x.mean()
    rms=np.sqrt((x**2).mean()); peak=np.abs(x).max()
    X=np.abs(np.fft.rfft(x)); X[0]=0
    P=X**2+1e-12; Pn=P/P.sum()
    idx=np.arange(len(P))
    cent=(Pn*idx).sum()/len(P); ent=-(Pn*np.log(Pn)).sum()
    dom=idx[P.argmax()]/len(P)
    n=len(P); bands=[Pn[int(a*n):int(b*n)].sum() for a,b in [(0,.05),(.05,.15),(.15,.35),(.35,.6),(.6,1)]]
    env=np.abs(hilbert(x)); E=np.abs(np.fft.rfft(env-env.mean())); E[0]=0
    Pe=E**2+1e-12; Pe/=Pe.sum()
    envk=float(((Pe-Pe.mean())**4).sum()/ (Pe.var()**2+1e-12)) if Pe.var()>0 else 0.0
    return [x.mean(), x.std(), rms, peak, np.ptp(x), float(skew(x)), float(kurtosis(x)),
            peak/(rms+1e-12), rms/(np.abs(x).mean()+1e-12), cent, ent, dom, *bands, envk]
rows=[]; labels=[]
for name,path in FILES:
    z=np.load(path, allow_pickle=True)['DE'].ravel()
    for i in range(0, len(z)-W+1, W):
        rows.append(feats(z[i:i+W])); labels.append(name)
X=np.array(rows); y=np.array(labels)
cols=['mean','std','rms','peak','p2p','skew','kurt','crest','shape','spec_cent','spec_ent','dom_freq',
      'band1','band2','band3','band4','band5','env_kurt']
print('窗口总数 %d，类别分布 %s，特征 %d' % (len(X), dict(pd.Series(y).value_counts()), X.shape[1]))
tr=np.zeros(len(y),bool)
for c in np.unique(y):
    idx=np.where(y==c)[0]; k=int(len(idx)*0.6); tr[idx[:k]]=True
res=[]; cms={}
for name,mdl in [('逻辑回归',make_pipeline(StandardScaler(),LogisticRegression(max_iter=3000))),
                 ('随机森林',RandomForestClassifier(n_estimators=400,random_state=0,n_jobs=-1))]:
    mdl.fit(X[tr],y[tr]); p=mdl.predict(X[~tr])
    maj=max(pd.Series(y[~tr]).value_counts())/ (~tr).sum()
    res.append(dict(模型=name,训练窗口=int(tr.sum()),测试窗口=int((~tr).sum()),
        准确率=round(accuracy_score(y[~tr],p),3), 宏F1=round(f1_score(y[~tr],p,average='macro'),3),
        多数类基线=round(float(maj),3)))
    cms[name]=pd.DataFrame(confusion_matrix(y[~tr],p,labels=[c for c,_ in FILES]),
                           index=[c for c,_ in FILES], columns=[c for c,_ in FILES])
R=pd.DataFrame(res)
R.to_csv(os.path.join(OUT,'cwru_diagnosis_metrics.csv'),index=False,encoding='utf-8-sig')
pd.DataFrame(X,columns=cols).assign(label=y).to_csv(os.path.join(OUT,'cwru_diagnosis_features.csv.gz'),compression='gzip',index=False)
with open(os.path.join(OUT,'cwru_diagnosis_report.md'),'w',encoding='utf-8') as f:
    f.write('# 诊断模块 v1：CWRU 轴承故障分类（DSH）\n\n命令：python src/dsh/2026-09-17_03_cwru_diagnosis.py\n\n')
    f.write('数据：CWRU 轴承数据（GitHub 镜像 srigas/CWRU_Bearing_NumPy），1730 RPM，DE 通道 48kHz，'
            '每类一个记录文件，共 %d 个不重叠窗口（2048 点）。\n\n' % len(X))
    f.write(R.to_markdown(index=False)+'\n\n## 混淆矩阵（随机森林）\n\n'+cms['随机森林'].to_markdown()+ '\n\n')
    f.write('## 局限（必读）\n1. 每类只有一个记录文件，只做了时间前后切分，结果偏乐观；\n'
            '2. 未做跨转速、跨故障尺寸的泛化测试；\n'
            '3. 数据来自轴承试验台，与污水厂水泵的工况与传感布置不同，不能直接外推；\n'
            '4. 下一版需补 14/21 mil 与不同转速的记录做跨记录验证。\n')
print(R.to_markdown(index=False))
print()
print(cms['随机森林'].to_string())
