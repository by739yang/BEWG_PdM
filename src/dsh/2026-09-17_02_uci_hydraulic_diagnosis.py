# -*- coding: utf-8 -*-
"""诊断模块 v1：UCI Hydraulic Systems 部件状态分类（DSH，2026-09-17）
数据结构：每行=一个循环(cycle)，列=该循环内的时序采样；profile.txt 给出部件状态标签。"""
import os, io, glob, json, zipfile
import numpy as np, pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.metrics import f1_score, accuracy_score, confusion_matrix
RAW='data/uci_hydraulic/raw'; ZIP='data/uci_hydraulic/hydraulic.zip'
OUT='results/2026-09-17/dsh'; os.makedirs(OUT,exist_ok=True)
def ensure_raw():
    if not os.path.isdir(RAW) or not os.listdir(RAW):
        os.makedirs(RAW,exist_ok=True)
        zipfile.ZipFile(ZIP).extractall(RAW)
    return RAW
def load():
    root=ensure_raw()
    txt=glob.glob(os.path.join(root,'**','*.txt'),recursive=True)
    prof=[p for p in txt if os.path.basename(p).lower().startswith('profile')]
    prof=prof[0] if prof else None
    if prof is None: raise SystemExit('未找到 profile.txt，解压目录：%s' % root)
    y=pd.read_csv(prof,sep='\t',header=None)
    y.columns=['cooler','valve','pump_leak','accumulator','stable'][:y.shape[1]]
    feats={}
    for p in txt:
        n=os.path.basename(p).upper().replace('.TXT','')
        if n.startswith('PROFILE'): continue
        try: a=pd.read_csv(p,sep='\t',header=None).values.astype(float)
        except Exception: continue
        if a.ndim!=2: continue
        if a.shape[0]!=len(y) and a.shape[1]==len(y): a=a.T
        if a.shape[0]!=len(y): continue
        feats[n]=a
    return y, feats
def describe(a):
    m=a.mean(1); sd=a.std(1); mn=a.min(1); mx=a.max(1)
    z=(a-m[:,None])/(sd[:,None]+1e-9)
    skew=(z**3).mean(1); kurt=(z**4).mean(1)-3
    rms=np.sqrt((a**2).mean(1))
    f=np.abs(np.fft.rfft(a-a.mean(1,keepdims=True),axis=1))
    P=f**2+1e-12; Pn=P/P.sum(1,keepdims=True)
    sent=-(Pn*np.log(Pn)).sum(1)
    dom=P.argmax(1)/a.shape[1]
    e=a[:,-1]-a[:,0]     # 循环内首末差
    return np.column_stack([m,sd,mn,mx,skew,kurt,rms,sent,dom,e])
y,feats=load()
print('循环数 %d，传感器文件 %d，标签列 %s' % (len(y), len(feats), list(y.columns)))
X=np.hstack([describe(a) for a in feats.values()])
cols=[]
for n,a in feats.items(): cols += [f'{n}_{k}' for k in ['mean','std','min','max','skew','kurt','rms','spec_ent','dom_freq','drift']]
print('特征矩阵', X.shape)

def cv(model, yv, name):
    skf=StratifiedKFold(5,shuffle=True,random_state=0)
    pred=cross_val_predict(model,X,yv,cv=skf)
    maj=np.bincount(yv).max()/len(yv)
    return dict(任务=name, 类别数=int(len(np.unique(yv))), 样本数=int(len(yv)),
                宏F1=round(f1_score(yv,pred,average='macro'),3), 准确率=round(accuracy_score(yv,pred),3),
                多数类基线=round(maj,3), 宏F1提升=round(f1_score(yv,pred,average='macro')-maj,3))
rows=[]
for col,name in [('cooler','冷却器状态'),('valve','阀门状态'),('pump_leak','泵内泄漏'),('accumulator','蓄能器压力'),('stable','稳定标志')]:
    if col not in y.columns: continue
    v=y[col].values
    rows.append(cv(make_pipeline(StandardScaler(),LogisticRegression(max_iter=2000)),v,name+'（逻辑回归）'))
    rows.append(cv(RandomForestClassifier(n_estimators=300,random_state=0,n_jobs=-1),v,name+'（随机森林）'))
R=pd.DataFrame(rows)
R.to_csv(os.path.join(OUT,'uci_hydraulic_diagnosis.csv'),index=False,encoding='utf-8-sig')
np.save(os.path.join(OUT,'uci_hydraulic_features.npy'),X)
pd.DataFrame(X,columns=cols).to_csv(os.path.join(OUT,'uci_hydraulic_features.csv.gz'),compression='gzip',index=False)
print(R.to_markdown(index=False))
open(os.path.join(OUT,'uci_hydraulic_diagnosis.md'),'w',encoding='utf-8').write(
 '# 诊断模块 v1：UCI Hydraulic 部件状态分类（DSH）\n\n命令：python src/dsh/2026-09-17_02_uci_hydraulic_diagnosis.py\n\n'
 + R.to_markdown(index=False) + '\n\n说明：5 折分层交叉验证；"多数类基线"为恒报多数类的准确率，作为对照。\n')
