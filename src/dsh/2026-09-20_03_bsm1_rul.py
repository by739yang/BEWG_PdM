# -*- coding: utf-8 -*-
"""汇总 BSM1 闭环结论 + 计算 RUL 外推（DSH，2026-09-20）"""
import pandas as pd, numpy as np, json, os
OUT='results/2026-09-20/dsh'
b=pd.read_csv(os.path.join(OUT,'bsm1_baseline.csv')); d=pd.read_csv(os.path.join(OUT,'bsm1_degraded.csv'))
CH=['SO3','SO4','SO5','SNH_eff','Ntot_eff','TSS_eff','sludge_h']
def score(df,ref,WIN):
    Z=pd.DataFrame(0.0,index=df.index,columns=CH)
    for c in CH:
        x=df[c].astype(float); W_=int(WIN*96)
        med=x.rolling(W_,min_periods=24).median()
        iqr=x.rolling(W_,min_periods=24).quantile(.75)-x.rolling(W_,min_periods=24).quantile(.25)
        sd=x.rolling(W_,min_periods=24).std()
        sc=iqr.where(iqr>1e-9,sd).fillna(1.0)
        Z[c]=((x-med)/sc).replace([np.inf,-np.inf],np.nan).fillna(0.0)
    A=np.abs(Z.values); return pd.Series(np.sqrt((np.sort(A,axis=1)[:,-3:]**2).mean(1)),index=df.index)
cal=b[b.t_day<10]; sb=score(b,cal,14); sd=score(d,cal,14)
thr=float(sb.iloc[:960].quantile(0.995)); fail=3*thr
alarm_t=15.78
i0=int(alarm_t*96)
seg=sd.iloc[max(0,i0-96):i0+1]; x=np.arange(len(seg),dtype=float)
k=np.polyfit(x,seg.values,1)[0]*96     # 每天斜率
cur=float(sd.iloc[i0])
rul=(fail-cur)/k if k>1e-6 else None
cross=[float(d.t_day.iloc[i]) for i in range(len(sd)) if sd.values[i]>fail]
res=dict(报警阈值=round(thr,2),危险阈值=round(fail,2),报警时刻=alarm_t,当前分数=round(cur,2),
    分数日斜率=round(float(k),3),RUL估计天=None if rul is None else round(float(rul),2),
    真值越危险阈值时刻=cross[0] if cross else None,
    说明='RUL 用报警时刻分数趋势线性外推到危险阈值；若真值窗口内未越过危险阈值，则 RUL 无法验证')
print(json.dumps(res,ensure_ascii=False,indent=2))
json.dump(res,open(os.path.join(OUT,'bsm1_rul_result.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
