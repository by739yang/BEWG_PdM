# -*- coding: utf-8 -*-
"""BSM1 闭环 v3：慢退化检测方案对照（DSH，2026-09-20）
四个方案：14 天自适应 / 30 天自适应 / 静态基线 / 静态基线+趋势特征；看谁能检出 40%/40 天的慢退化，代价多少误报。"""
import pandas as pd, numpy as np, json, os
OUT='results/2026-09-20/dsh'
b=pd.read_csv(os.path.join(OUT,'bsm1_60d_baseline.csv')); d=pd.read_csv(os.path.join(OUT,'bsm1_60d_degraded.csv'))
CH=['SO3','SO4','SO5','SNH_eff','Ntot_eff','TSS_eff','sludge_h']; DEG=20.0
cal=b[b.t_day<DEG]
def zscore(df,WIN_days=None,static=False):
    Z=pd.DataFrame(0.0,index=df.index,columns=CH)
    for c in CH:
        x=df[c].astype(float)
        if static:
            med=cal[c].median(); iqr=cal[c].quantile(.75)-cal[c].quantile(.25); sd=cal[c].std()
            sc=iqr/1.349 if iqr>1e-9 else (sd if sd>1e-9 else 1.0)
            Z[c]=(x-med)/sc
        else:
            W=int(WIN_days*96); med=x.rolling(W,min_periods=96).median()
            iqr=x.rolling(W,min_periods=96).quantile(.75)-x.rolling(W,min_periods=96).quantile(.25)
            sd=x.rolling(W,min_periods=96).std(); sc=iqr.where(iqr>1e-9,sd).fillna(1.0)
            Z[c]=((x-med)/sc).replace([np.inf,-np.inf],np.nan).fillna(0.0)
    return Z
def health(df,WIN_days=None,static=False,trend=False):
    Z=zscore(df,WIN_days,static); A=np.abs(Z.values)
    s=pd.Series(np.sqrt((np.sort(A,axis=1)[:,-3:]**2).mean(1)),index=df.index)
    s=s.rolling(96,min_periods=24).median()
    if trend:
        t=s.rolling(int(14*96),min_periods=96).apply(lambda v: np.polyfit(np.arange(len(v)),v,1)[0]*96,raw=True)
        s=s+np.maximum(t,0)     # 只把正向漂移计入
    return s
def evaluate(hb,hd,thr_q=0.995):
    thr=float(hb.iloc[:int(DEG*96)].quantile(thr_q)); fail=3*thr
    def fc(s,x):
        v=[i for i in range(len(s)) if float(s.iloc[i])>x and i/96>DEG]
        return v[0]/96 if v else None
    a=fc(hd,thr); dg=fc(hd,fail)
    fp=int((hb.iloc[:int(DEG*96)]>thr).sum())
    return dict(阈值=round(thr,3),危险阈值=round(fail,3),报警时刻=None if a is None else round(a,2),
        检出延迟=None if a is None else round(a-DEG,2),真值越危险=None if dg is None else round(dg,2),
        基准误报采样数=fp, 基准误报率每万采样=round(fp/max(int(DEG*96),1)*10000,2))
rows=[]
for tag,kw in [('① 14 天自适应',dict(WIN_days=14)),('② 30 天自适应',dict(WIN_days=30)),
               ('③ 静态基线',dict(static=True)),('④ 静态基线+趋势特征',dict(static=True,trend=True))]:
    hb=health(b,**kw); hd=health(d,**kw); r=evaluate(hb,hd); r['方案']=tag; rows.append(r)
R=pd.DataFrame(rows)[['方案','阈值','危险阈值','报警时刻','检出延迟','真值越危险','基准误报采样数','基准误报率每万采样']]
R.to_csv(os.path.join(OUT,'bsm1_slow_drift_detectors.csv'),index=False,encoding='utf-8-sig')
print(R.to_string(index=False))
json.dump(dict(场景='60 天，第 20 天起 KLa 线性衰减 40%',结果=R.to_dict('records')),
    open(os.path.join(OUT,'bsm1_slow_drift_detectors.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
