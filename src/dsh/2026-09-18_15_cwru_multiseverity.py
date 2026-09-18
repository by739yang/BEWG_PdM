# -*- coding: utf-8 -*-
"""诊断模块 v3（DSH，2026-09-18）：加故障特征频率特征 + 多尺寸训练，检验泛化
特征：通用时频 18 维 + 故障特征频率包络带能量 9 维（BPFO/BPFI/BSF 前三阶谐波）
实验：E3 7->14mil；E4 7+14 -> 21mil（留出尺寸）；E5 1730 全尺寸 -> 1750 跨转速"""
import numpy as np, pandas as pd, os, json
from scipy.stats import kurtosis, skew
from scipy.signal import hilbert
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, confusion_matrix
OUT='results/2026-09-18/dsh'; W=2048; FS=48000
# CWRU 6205-2RS 轴承系数
COEF=dict(BPFO=4.7135,BPFI=4.9469,BSF=2.3570)
def base_feats(x):
    x=x-x.mean(); rms=np.sqrt((x**2).mean()); peak=np.abs(x).max()
    X=np.abs(np.fft.rfft(x)); X[0]=0; P=X**2+1e-12; Pn=P/P.sum(); idx=np.arange(len(P)); n=len(P)
    bands=[Pn[int(a*n):int(b*n)].sum() for a,b in [(0,.05),(.05,.15),(.15,.35),(.35,.6),(.6,1)]]
    env=np.abs(hilbert(x)); E=np.abs(np.fft.rfft(env-env.mean())); E[0]=0
    Pe=E**2+1e-12; Pe/=Pe.sum()
    envk=float(((Pe-Pe.mean())**4).sum()/(Pe.var()**2+1e-12)) if Pe.var()>0 else 0.0
    return [x.mean(),x.std(),rms,peak,np.ptp(x),float(skew(x)),float(kurtosis(x)),peak/(rms+1e-12),
            rms/(np.abs(x).mean()+1e-12),(Pn*idx).sum()/n,-(Pn*np.log(Pn)).sum(),idx[P.argmax()]/n,*bands,envk], Pe, len(E)
def fault_band_feats(x, rpm):
    """包络谱在故障特征频率前三阶谐波附近的能量占比"""
    env=np.abs(hilbert(x)); E=np.abs(np.fft.rfft(env-env.mean())); E[0]=0
    Pe=E**2+1e-12; Pe/=Pe.sum(); n=len(Pe); fr=rpm/60.0
    out=[]
    for k in ['BPFO','BPFI','BSF']:
        f0=COEF[k]*fr
        for h in [1,2,3]:
            c=int(round(f0*h/FS*n)); bw=max(1,int(round(0.06*f0*h/FS*n)))
            lo,hi=max(0,c-bw),min(n,c+bw+1)
            out.append(float(Pe[lo:hi].sum()))
    return out
def load(name, rpm):
    z=np.load(f'data/cwru/{name}.npz',allow_pickle=True)['DE'].ravel()
    F=[]
    for i in range(0,len(z)-W+1,W):
        b,_,_=base_feats(z[i:i+W]); F.append(b+fault_band_feats(z[i:i+W],rpm))
    return np.array(F)
CACHE={}
def get(name, rpm):
    if name not in CACHE: CACHE[name]=load(name,rpm)
    return CACHE[name]
CLS=['正常','内圈','外圈','滚动体']
def lab(f):
    if f.startswith('N') or 'Normal' in f: return '正常'
    if f.startswith('IR'): return '内圈'
    if f.startswith('OR'): return '外圈'
    return '滚动体'
def ev(train, test, label):
    Xtr=np.vstack([get(f,rpm) for f,rpm in train]); ytr=np.concatenate([[lab(f)]*len(get(f,rpm)) for f,rpm in train])
    Xte=np.vstack([get(f,rpm) for f,rpm in test]);  yte=np.concatenate([[lab(f)]*len(get(f,rpm)) for f,rpm in test])
    o=[]
    for nm,mdl in [('逻辑回归',make_pipeline(StandardScaler(),LogisticRegression(max_iter=3000))),
                   ('随机森林',RandomForestClassifier(n_estimators=400,random_state=0,n_jobs=-1))]:
        mdl.fit(Xtr,ytr); p=mdl.predict(Xte)
        o.append(dict(实验=label,模型=nm,训练窗口=len(ytr),测试窗口=len(yte),
            准确率=round(accuracy_score(yte,p),3),宏F1=round(f1_score(yte,p,average='macro'),3),
            多数类基线=round(float(pd.Series(yte).value_counts().max())/len(yte),3)))
    return o
S7=[('Normal',1730),('IR_7',1730),('OR6_7',1730),('B_7',1730)]
S14=[('IR_14',1730),('OR6_14',1730),('B_14',1730)]
S21=[('IR_21',1730),('OR6_21',1730),('B_21',1730)]
N1750=[('N1750',1750)]
S7_1750=[('IR_7_1750',1750),('OR6_7_1750',1750),('B_7_1750',1750)]
rows=[]
rows+=ev(S7, [('Normal',1730)]+S14 if False else [('N1750',1750)]+S14, 'E3 7mil→14mil（新特征）')
rows+=ev(S7+S14, [('N1750',1750)]+S21, 'E4 7+14→21mil（留出尺寸）')
rows+=ev(S7+S14+S21, N1750+S7_1750, 'E5 1730全尺寸→1750（跨转速）')
R=pd.DataFrame(rows)
R.to_csv(os.path.join(OUT,'cwru_multiseverity_metrics.csv'),index=False,encoding='utf-8-sig')
print(R.to_markdown(index=False))
json.dump(dict(特征='通用时频 18 维 + 故障特征频率包络带能量 9 维（BPFO/BPFI/BSF 前三阶）',
  轴承系数=COEF,结果=R.to_dict('records'),
  对照='旧特征下 E3=0.536（见 cwru_crossval_metrics.csv）'),
  open(os.path.join(OUT,'cwru_multiseverity_summary.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
with open(os.path.join(OUT,'cwru_multiseverity.md'),'w',encoding='utf-8') as f:
    f.write('# 诊断模块 v3：故障特征频率特征 + 多尺寸训练（DSH，2026-09-18）\n\n')
    f.write('命令：python src/dsh/2026-09-18_15_cwru_multiseverity.py\n\n'+R.to_markdown(index=False)+'\n\n')
    f.write('对照：旧特征下 E3（7→14mil）宏F1 仅 0.536。\n')
