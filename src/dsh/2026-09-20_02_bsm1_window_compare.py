# -*- coding: utf-8 -*-
"""BSM1 闭环诊断：自适应窗口长度 vs 慢退化检出（DSH，2026-09-20）
结论假设：2 天自适应窗会吸收 7 天的慢漂移；更长窗或静态基线能检出但误报更多。"""
import pandas as pd, numpy as np, json, os
OUT='results/2026-09-20/dsh'
b=pd.read_csv(os.path.join(OUT,'bsm1_baseline.csv')); d=pd.read_csv(os.path.join(OUT,'bsm1_degraded.csv'))
CH=['SO3','SO4','SO5','SNH_eff','Ntot_eff','TSS_eff','sludge_h']
DEG_START=14.0
def score(df,ref,WIN_days,static=False):
    Z=pd.DataFrame(0.0,index=df.index,columns=CH)
    for c in CH:
        x=df[c].astype(float)
        if static:
            med=ref[c].median(); iqr=ref[c].quantile(.75)-ref[c].quantile(.25); sd=ref[c].std()
            sc=iqr/1.349 if iqr>1e-9 else (sd if sd>1e-9 else 1.0)
            Z[c]=(x-med)/sc
        else:
            W=int(WIN_days*96)
            med=x.rolling(W,min_periods=24).median()
            iqr=x.rolling(W,min_periods=24).quantile(.75)-x.rolling(W,min_periods=24).quantile(.25)
            sd=x.rolling(W,min_periods=24).std()
            sc=iqr.where(iqr>1e-9,sd).fillna(1.0)
            Z[c]=((x-med)/sc).replace([np.inf,-np.inf],np.nan).fillna(0.0)
    A=np.abs(Z.values)
    return pd.Series(np.sqrt((np.sort(A,axis=1)[:,-3:]**2).mean(1)),index=df.index)
def events(sv,thr,ENTER=4,EXIT=8,RATIO=0.8,COOL=8):
    over=(sv>thr).values; n=len(sv); ev=[]; st=0; r=0; s0=0; last=-10**9
    for t in range(n):
        if st==0:
            if t<last+COOL: r=0
            elif over[t]:
                r+=1
                if r>=ENTER: s0=t; st=1; r=0
            else: r=0
        else:
            if sv.values[t]<RATIO*thr:
                r+=1
                if r>=EXIT: ev.append((s0,t+1)); last=t+1; st=0; r=0
            else: r=0
    if st==1: ev.append((s0,n))
    return ev
rows=[]
for tag,WIN,static in [('2 天自适应',2,False),('7 天自适应',7,False),('14 天自适应',14,False),('静态基线（全期）',None,True)]:
    cal=b[b.t_day<10]
    sb=score(b,cal,WIN,static); sd=score(d,cal,WIN,static)
    thr=float(sb.iloc[:int(10*96)].quantile(0.995))
    eb=events(sb,thr); ed=events(sd,thr)
    fb=[float(b.t_day.iloc[s]) for s,e in eb]; fd=[float(d.t_day.iloc[s]) for s,e in ed]
    det=[x for x in fd if x>=DEG_START]
    rows.append(dict(设置=tag,阈值=round(thr,2),
        基准误报=len(fb),退化前误报=len([x for x in fd if x<DEG_START]),
        退化后首报=round(min(det),2) if det else None,
        检出延迟天=round(min(det)-DEG_START,2) if det else None,
        退化后告警数=len(det)))
R=pd.DataFrame(rows)
R.to_csv(os.path.join(OUT,'bsm1_window_compare.csv'),index=False,encoding='utf-8-sig')
print(R.to_string(index=False))
json.dump(dict(假设='自适应窗口越长，越能检出慢漂移，但误报越多（或反之）',结果=R.to_dict('records')),
    open(os.path.join(OUT,'bsm1_window_compare.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
# 补充：退化场景各通道相对基准的变化幅度（第 14 天前后）
chg={}
for c in CH:
    pre=b[b.t_day<14][c].mean(); post=d[d.t_day>=14][c].mean()
    chg[c]=round((post-pre)/abs(pre)*100,1) if pre else None
print()
print('退化后各通道相对基准变化(%)：', chg)
json.dump(chg,open(os.path.join(OUT,'bsm1_channel_change.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
