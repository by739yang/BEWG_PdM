# -*- coding: utf-8 -*-
"""诊断模块 v4（DSH，2026-09-19）：按记录自适应归一化，检验跨尺寸/跨转速泛化
假设：跨记录时各记录的工况与量纲不同，按记录自身统计量归一化应显著改善迁移。
对照：原始特征（v3，E3 宏F1 0.413）。"""
import numpy as np, pandas as pd, os, json
from scipy.stats import kurtosis, skew
from scipy.signal import hilbert
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
OUT='results/2026-09-19/dsh'; os.makedirs(OUT,exist_ok=True)
W=2048; FS=48000; COEF=dict(BPFO=4.7135,BPFI=4.9469,BSF=2.3570)
def feats(x,rpm):
    x=x-x.mean(); rms=np.sqrt((x**2).mean()); peak=np.abs(x).max()
    X=np.abs(np.fft.rfft(x)); X[0]=0; P=X**2+1e-12; Pn=P/P.sum(); idx=np.arange(len(P)); n=len(P)
    bands=[Pn[int(a*n):int(b*n)].sum() for a,b in [(0,.05),(.05,.15),(.15,.35),(.35,.6),(.6,1)]]
    env=np.abs(hilbert(x)); E=np.abs(np.fft.rfft(env-env.mean())); E[0]=0
    Pe=E**2+1e-12; Pe/=Pe.sum()
    envk=float(((Pe-Pe.mean())**4).sum()/(Pe.var()**2+1e-12)) if Pe.var()>0 else 0.0
    base=[x.mean(),x.std(),rms,peak,np.ptp(x),float(skew(x)),float(kurtosis(x)),peak/(rms+1e-12),
          rms/(np.abs(x).mean()+1e-12),(Pn*idx).sum()/n,-(Pn*np.log(Pn)).sum(),idx[P.argmax()]/n,*bands,envk]
    fr=rpm/60.0; fb=[]
    for k in ['BPFO','BPFI','BSF']:
        f0=COEF[k]*fr
        for h in [1,2,3]:
            c=int(round(f0*h/FS*n)); bw=max(1,int(round(0.06*f0*h/FS*n)))
            fb.append(float(Pe[max(0,c-bw):min(n,c+bw+1)].sum()))
    return base+fb
CACHE={}
def get(name,rpm):
    if name not in CACHE:
        z=np.load(f'data/cwru/{name}.npz',allow_pickle=True)['DE'].ravel()
        CACHE[name]=np.array([feats(z[i:i+W],rpm) for i in range(0,len(z)-W+1,W)])
    return CACHE[name]
def lab(f):
    if f.startswith('N') or 'Normal' in f: return '正常'
    if f.startswith('IR'): return '内圈'
    if f.startswith('OR'): return '外圈'
    return '滚动体'
def run(train,test,tag,per_record):
    def prep(f,rpm):
        X=get(f,rpm).copy()
        if per_record=='all':
            X=(X-X.mean(0))/(X.std(0)+1e-12)          # 全归一化
        elif per_record=='partial':
            X[:, -9:]=(X[:, -9:]-X[:, -9:].mean(0))/(X[:, -9:].std(0)+1e-12)  # 只归故障带能量（相对量）
        return X
    Xtr=np.vstack([prep(f,r) for f,r in train]); ytr=np.concatenate([[lab(f)]*len(get(f,r)) for f,r in train])
    Xte=np.vstack([prep(f,r) for f,r in test]);  yte=np.concatenate([[lab(f)]*len(get(f,r)) for f,r in test])
    out=[]
    for nm,mdl in [('逻辑回归',make_pipeline(StandardScaler(),LogisticRegression(max_iter=3000))),
                   ('随机森林',RandomForestClassifier(n_estimators=400,random_state=0,n_jobs=-1))]:
        mdl.fit(Xtr,ytr); p=mdl.predict(Xte)
        out.append(dict(归一化={'all':'按记录全归','partial':'只归相对量',False:'原始'}[per_record],实验=tag,模型=nm,训练窗口=len(ytr),测试窗口=len(yte),
            准确率=round(accuracy_score(yte,p),3),宏F1=round(f1_score(yte,p,average='macro'),3),
            多数类基线=round(float(pd.Series(yte).value_counts().max())/len(yte),3)))
    return out
S7=[('Normal',1730),('IR_7',1730),('OR6_7',1730),('B_7',1730)]
S14=[('IR_14',1730),('OR6_14',1730),('B_14',1730)]
S21=[('IR_21',1730),('OR6_21',1730),('B_21',1730)]
S7_1750=[('IR_7_1750',1750),('OR6_7_1750',1750),('B_7_1750',1750)]
rows=[]
for pr in [False,'all','partial']:
    rows+=run(S7,[('N1750',1750)]+S14,'E3 7mil→14mil',pr)
    rows+=run(S7+S14,[('N1750',1750)]+S21,'E4 7+14→21mil',pr)
    rows+=run(S7+S14+S21,[('N1750',1750)]+S7_1750,'E5 1730全→1750',pr)
R=pd.DataFrame(rows)
R.to_csv(os.path.join(OUT,'cwru_adapt_metrics.csv'),index=False,encoding='utf-8-sig')
piv=R[R.模型=='随机森林'].pivot_table(index='实验',columns='归一化',values='宏F1')[['原始','只归相对量','按记录全归']]
print(R[R.模型=='随机森林'].to_string(index=False))
print()
print('=== 宏F1 对照（随机森林）===')
print(piv.to_string())
print()
print('提升（只归相对量）：', {i: round(float(piv.loc[i,'只归相对量']-piv.loc[i,'原始']),3) for i in piv.index})
json.dump(dict(假设='按记录自适应归一化改善跨记录迁移',结果=R.to_dict('records'),
   宏F1对照=piv.to_dict()),open(os.path.join(OUT,'cwru_adapt_summary.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
