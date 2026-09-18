# -*- coding: utf-8 -*-
"""诊断模块 v2：CWRU 跨记录验证（DSH，2026-09-18）
E1 同记录内切分（原口径，乐观）  E2 跨转速（1730 训练 → 1750 测试）  E3 跨故障尺寸（7mil 训练 → 14mil 测试）"""
import numpy as np, pandas as pd, os, json
from scipy.stats import kurtosis, skew
from scipy.signal import hilbert
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, confusion_matrix
OUT='results/2026-09-18/dsh'; os.makedirs(OUT,exist_ok=True)
W=2048
def feats(x):
    x=x-x.mean(); rms=np.sqrt((x**2).mean()); peak=np.abs(x).max()
    X=np.abs(np.fft.rfft(x)); X[0]=0; P=X**2+1e-12; Pn=P/P.sum(); idx=np.arange(len(P))
    n=len(P); bands=[Pn[int(a*n):int(b*n)].sum() for a,b in [(0,.05),(.05,.15),(.15,.35),(.35,.6),(.6,1)]]
    env=np.abs(hilbert(x)); E=np.abs(np.fft.rfft(env-env.mean())); E[0]=0
    Pe=E**2+1e-12; Pe/=Pe.sum()
    envk=float(((Pe-Pe.mean())**4).sum()/(Pe.var()**2+1e-12)) if Pe.var()>0 else 0.0
    return [x.mean(),x.std(),rms,peak,np.ptp(x),float(skew(x)),float(kurtosis(x)),peak/(rms+1e-12),
            rms/(np.abs(x).mean()+1e-12),(Pn*idx).sum()/n,-(Pn*np.log(Pn)).sum(),idx[P.argmax()]/n,
            *bands,envk]
def load(name):
    z=np.load('data/cwru/%s.npz'%name,allow_pickle=True)['DE'].ravel()
    X=np.array([feats(z[i:i+W]) for i in range(0,len(z)-W+1,W)])
    return X
CACHE={}
def get(name):
    if name not in CACHE: CACHE[name]=load(name)
    return CACHE[name]
CLS=['正常','内圈','外圈','滚动体']
def run(train, test, label):     # train/test: dict 类名 -> 文件名
    Xtr=np.vstack([get(f) for f in train.values()]); ytr=np.repeat(list(train.keys()),[len(get(f)) for f in train.values()])
    Xte=np.vstack([get(f) for f in test.values()]);  yte=np.repeat(list(test.keys()),[len(get(f)) for f in test.values()])
    out=[]
    for nm,mdl in [('逻辑回归',make_pipeline(StandardScaler(),LogisticRegression(max_iter=3000))),
                   ('随机森林',RandomForestClassifier(n_estimators=400,random_state=0,n_jobs=-1))]:
        mdl.fit(Xtr,ytr); p=mdl.predict(Xte)
        out.append(dict(实验=label,模型=nm,训练窗口=len(ytr),测试窗口=len(yte),
            准确率=round(accuracy_score(yte,p),3),宏F1=round(f1_score(yte,p,average='macro'),3),
            多数类基线=round(float(pd.Series(yte).value_counts().max())/len(yte),3)))
        if nm=='随机森林':
            cm=pd.DataFrame(confusion_matrix(yte,p,labels=CLS),index=CLS,columns=CLS)
    return out, cm
rows=[]; cms={}
# E1 同记录内（前 60% 训练 / 后 40% 测试）
tr={}; te={}
for cls,f in zip(CLS,['Normal','IR_7','OR6_7','B_7']):
    X=get(f); k=int(len(X)*0.6); tr[cls]=X[:k]; te[cls]=X[k:]
Xtr=np.vstack(list(tr.values())); ytr=np.repeat(CLS,[len(v) for v in tr.values()])
Xte=np.vstack(list(te.values())); yte=np.repeat(CLS,[len(v) for v in te.values()])
for nm,mdl in [('逻辑回归',make_pipeline(StandardScaler(),LogisticRegression(max_iter=3000))),('随机森林',RandomForestClassifier(n_estimators=400,random_state=0,n_jobs=-1))]:
    mdl.fit(Xtr,ytr); p=mdl.predict(Xte)
    rows.append(dict(实验='E1 同记录内切分（原口径）',模型=nm,训练窗口=len(ytr),测试窗口=len(yte),
        准确率=round(accuracy_score(yte,p),3),宏F1=round(f1_score(yte,p,average='macro'),3),
        多数类基线=round(float(pd.Series(yte).value_counts().max())/len(yte),3)))
    cms['E1']=pd.DataFrame(confusion_matrix(yte,p,labels=CLS),index=CLS,columns=CLS)
# E2 跨转速
r2,cm2=run({'正常':'Normal','内圈':'IR_7','外圈':'OR6_7','滚动体':'B_7'},
           {'正常':'N1750','内圈':'IR_7_1750','外圈':'OR6_7_1750','滚动体':'B_7_1750'},'E2 跨转速（1730→1750）')
rows+=r2; cms['E2']=cm2
# E3 跨故障尺寸（正常类用 1750 记录的窗口，避免与训练同源）
r3,cm3=run({'正常':'Normal','内圈':'IR_7','外圈':'OR6_7','滚动体':'B_7'},
           {'正常':'N1750','内圈':'IR_14','外圈':'OR6_14','滚动体':'B_14'},'E3 跨故障尺寸（7mil→14mil）')
rows+=r3; cms['E3']=cm3
R=pd.DataFrame(rows)
R.to_csv(os.path.join(OUT,'cwru_crossval_metrics.csv'),index=False,encoding='utf-8-sig')
with open(os.path.join(OUT,'cwru_crossval_report.md'),'w',encoding='utf-8') as f:
    f.write('# 诊断模块 v2：CWRU 跨记录验证（DSH，2026-09-18）\n\n命令：python src/dsh/2026-09-18_05_cwru_crossval.py\n\n')
    f.write('E1 同一记录内前 60% 训练 / 后 40% 测试；E2 用 1730 RPM 训练、1750 RPM 测试；E3 用 7mil 故障训练、14mil 故障测试（正常类用 1750 记录窗口）。\n\n')
    f.write(R.to_markdown(index=False)+'\n\n')
    for k in ['E1','E2','E3']:
        f.write('## %s 混淆矩阵（随机森林）\n\n' % k + cms[k].to_markdown() + '\n\n')
    f.write('## 结论要看什么\nE1 与 E2/E3 的落差，就是"同记录内刷分"与"真实泛化能力"的差距。\n')
print(R.to_markdown(index=False))
print()
for k in ['E2','E3']: print(k, '混淆矩阵：'); print(cms[k].to_string()); print()
