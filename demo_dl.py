# -*- coding: utf-8 -*-
"""SKAB 深度学习版：1D 卷积自编码器（仅在正常数据上训练）
协议与 v5 完全一致：逐文件因果自适应标准化 -> 滑窗特征 -> 1分钟判决 -> 同样的指标
两种训练范式：(i) 全局迁移(仅用 anomaly-free)  (ii) 逐设备自校准(用本机前40%历史)
"""
import numpy as np, pandas as pd, glob, os, time, torch, torch.nn as nn
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest

BASE=r'C:\Users\boyi\Desktop\BEWG_PdM\data\SKAB-master\data'
OUT=r'C:\Users\boyi\Desktop\BEWG_PdM\results'
FEATS=['Accelerometer1RMS','Accelerometer2RMS','Current','Pressure','Temperature','Thermocouple','Voltage','Volume Flow RateRMS']
REF=0.40; BURN=120; AW=120; TARGET_FPR=0.005; BLOCK=60; GAP=300; L=60; DEV='cuda' if torch.cuda.is_available() else 'cpu'
torch.manual_seed(0); np.random.seed(0)

def load(fp):
    df=pd.read_csv(fp,sep=';'); df.columns=[c.strip() for c in df.columns]
    for c in df.columns:
        if c not in ('datetime','anomaly','changepoint'): df[c]=pd.to_numeric(df[c],errors='coerce')
    return df
def adaptive_z(X,W=AW,minp=45):
    n=X.shape[0]; Z=np.zeros_like(X)
    for t in range(n):
        win=X[max(0,t-W):t]
        if len(win)<minp: win=X[:min(minp,n)]
        med=np.median(win,0); iqr=np.percentile(win,75,0)-np.percentile(win,25,0); sd=win.std(0)
        sc=np.where(iqr>1e-9,iqr,np.where(sd>1e-9,sd,1.0)); sc=np.maximum(sc,0.02*np.maximum(np.abs(med),1e-3))
        Z[t]=(X[t]-med)/sc
    return Z
def winfeat(Z,w=15):
    Zd=pd.DataFrame(Z); r=Zd.rolling(w,min_periods=1); return np.nan_to_num(np.hstack([Z,r.mean().values,r.std().fillna(0).values]))

class ConvAE(nn.Module):
    def __init__(self, d, ch=32, lat=16):
        super().__init__()
        self.enc=nn.Sequential(nn.Conv1d(d,ch,5,2,2), nn.GELU(), nn.Conv1d(ch,ch,5,2,2), nn.GELU(),
                               nn.Conv1d(ch,lat,3,1,1), nn.GELU())
        self.dec=nn.Sequential(nn.ConvTranspose1d(lat,ch,3,1,1), nn.GELU(),
                               nn.ConvTranspose1d(ch,ch,5,2,2,1), nn.GELU(),
                               nn.ConvTranspose1d(ch,d,5,2,2,1))
    def forward(self,x):
        z=self.enc(x); y=self.dec(z)
        return y[:, :, :x.shape[2]]

def make_seq(F, L=L):
    if len(F)<=L: return np.zeros((0,L,F.shape[1]),dtype=np.float32)
    idx=np.arange(L, len(F)+1)
    S=np.stack([F[i-L:i] for i in idx]).astype(np.float32)
    return S

def score_seq(model, S, bs=256):
    model.eval(); out=[]
    with torch.no_grad():
        for i in range(0,len(S),bs):
            b=torch.from_numpy(S[i:i+bs]).to(DEV).transpose(1,2)
            r=model(b)
            e=((r-b)**2).mean(1)          # (B, T)
            out.append(e[:,-1].cpu().numpy())   # 最后一个时刻的误差（因果）
    return np.concatenate(out) if out else np.zeros(0)

def train_ae(S, epochs=80, lr=1e-3, ch=32, lat=16):
    m=ConvAE(S.shape[2],ch,lat).to(DEV)
    opt=torch.optim.Adam(m.parameters(),lr=lr); lossf=nn.MSELoss()
    X=torch.from_numpy(S).to(DEV)
    n=len(X); bs=min(128,n)
    for ep in range(epochs):
        perm=torch.randperm(n,device=DEV)
        for i in range(0,n,bs):
            b=X[perm[i:i+bs]].transpose(1,2)
            opt.zero_grad(); r=m(b); l=lossf(r,b); l.backward(); opt.step()
    return m

def blocks(a,b=BLOCK):
    m=(len(a)//b)*b; return (a[:m].reshape(-1,b).mean(1)>0.5).astype(int)
def metrics(y,a):
    yb=blocks(y); ab=blocks(a)
    tp=((ab==1)&(yb==1)).sum(); fp=((ab==1)&(yb==0)).sum(); fn=((ab==0)&(yb==1)).sum()
    p=tp/(tp+fp+1e-9); r=tp/(tp+fn+1e-9)
    yb2=np.diff(np.r_[0,yb,0]); st=np.where(yb2==1)[0]; en=np.where(yb2==-1)[0]
    det=0; dl=[]
    for s0,e0 in zip(st,en):
        w=ab[s0:min(e0+2,len(ab))]
        if len(w) and w.sum()>0: det+=1; dl.append(int(np.argmax(w))*BLOCK)
    return dict(f1=2*p*r/(p+r+1e-9),prec=p,rec=r,fp_min=(ab[yb==0]==1).mean() if (yb==0).sum() else 0,
                ev=det/max(len(st),1),delay=np.median(dl) if dl else np.nan)

files=sorted(glob.glob(os.path.join(BASE,'valve1','*.csv'))+glob.glob(os.path.join(BASE,'valve2','*.csv'))+glob.glob(os.path.join(BASE,'other','*.csv')))
print('device',DEV)
# 预取：全局训练集（仅 anomaly-free）
tr=load(os.path.join(BASE,'anomaly-free','anomaly-free.csv'))
Ftr=winfeat(adaptive_z(tr[FEATS].values.astype(float)))
Str=make_seq(Ftr)
print('global train windows', Str.shape)
t0=time.time(); gmodel=train_ae(Str, epochs=60); print('global train %.1fs, params %d'%(time.time()-t0, sum(p.numel() for p in gmodel.parameters())))

res=[]
# (i) 全局迁移
R=[]
for f in files:
    d=load(f); y=d['anomaly'].values.astype(int)
    if y.sum()==0: continue
    X=d[FEATS].values.astype(float); n=len(X); k0=max(int(n*REF),BURN+30)
    F=winfeat(adaptive_z(X)); S=make_seq(F)
    sc=score_seq(gmodel,S); off=L-1            # sc[i] 对应 F[i+L-1]
    full=np.full(n,np.nan); full[off:off+len(sc)]=sc
    cal=full[BURN:k0]; thr=np.nanquantile(cal,1-TARGET_FPR)
    a=(np.nan_to_num(full,nan=0)>thr).astype(int)[k0:]; yt=y[k0:]
    R.append(metrics(yt,a))
A=pd.DataFrame(R); res.append(dict(方案='全局迁移(仅正常机训练)',方法='1D 卷积自编码器',F1=A.f1.mean(),精确率=A.prec.mean(),召回率=A.rec.mean(),误报分钟比例=f"{A.fp_min.mean()*100:.1f}%",事件检出率=A.ev.mean(),延迟中位=A.delay.median()))
print('global done', flush=True)

# (ii) 逐设备自校准
R=[]; t0=time.time()
for f in files:
    d=load(f); y=d['anomaly'].values.astype(int)
    if y.sum()==0: continue
    X=d[FEATS].values.astype(float); n=len(X); k0=max(int(n*REF),BURN+30)
    F=winfeat(adaptive_z(X)); S=make_seq(F); off=L-1
    m=train_ae(S[:max(0,k0-off)], epochs=120, lr=2e-3)
    sc=score_seq(m,S); full=np.full(n,np.nan); full[off:off+len(sc)]=sc
    cal=full[BURN:k0]; thr=np.nanquantile(cal,1-TARGET_FPR)
    a=(np.nan_to_num(full,nan=0)>thr).astype(int)[k0:]; yt=y[k0:]
    R.append(metrics(yt,a))
A2=pd.DataFrame(R); res.append(dict(方案='逐设备自校准(本机历史)',方法='1D 卷积自编码器',F1=A2.f1.mean(),精确率=A2.prec.mean(),召回率=A2.rec.mean(),误报分钟比例=f"{A2.fp_min.mean()*100:.1f}%",事件检出率=A2.ev.mean(),延迟中位=A2.delay.median()))
print('per-file done in %.1fs'%(time.time()-t0), flush=True)

df=pd.DataFrame(res)
df.to_csv(os.path.join(OUT,'dl_results.csv'),index=False,encoding='utf-8-sig')
open(os.path.join(OUT,'dl_table.md'),'w',encoding='utf-8').write(df.to_markdown(index=False,floatfmt='.3f'))
print(df.to_markdown(index=False,floatfmt='.3f'))
