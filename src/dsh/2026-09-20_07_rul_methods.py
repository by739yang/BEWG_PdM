# -*- coding: utf-8 -*-
"""BSM1 RUL 方法对照（DSH，2026-09-20）：通用健康指数外推 vs 机理指标（溶解氧）外推 / 指数拟合
用已落盘的 120 天数据，不重跑仿真。真值失效：SO3 持续 1 天低于 0.5 mg/L。"""
import pandas as pd, numpy as np, json, os
OUT='results/2026-09-20/dsh'
b=pd.read_csv(os.path.join(OUT,'bsm1_120d_baseline.csv')); d=pd.read_csv(os.path.join(OUT,'bsm1_120d_degraded.csv'))
DEG=20.0; ALARM=40.07; SO_LIM=0.5
v=(d.SO3<SO_LIM).rolling(96).mean()
idx=[i for i in range(len(v)) if v.iloc[i]>=1.0 and i/96>DEG]
truth=idx[0]/96 if idx else None
true_rul=(truth-ALARM) if truth else None
print('真值失效 %.2f 天，报警 %.2f 天 → 真值剩余 %.2f 天' % (truth,ALARM,true_rul))
i0=int(ALARM*96)
def fit(seg,kind='lin'):
    x=np.arange(len(seg),dtype=float)/96.0; y=seg.values
    if kind=='lin': k=np.polyfit(x,y,1); return ('lin',k)
    else:
        y2=np.log(np.maximum(y,1e-6)); k=np.polyfit(x,y2,1); return ('exp',k)
rows=[]
for WIND in [3,5,10]:
    for kind in ['lin','exp']:
        seg=d.SO3.iloc[max(0,i0-int(WIND*96)):i0+1]
        km,k=fit(seg,kind)
        cur=float(seg.iloc[-1])
        if km=='lin':
            rul=(cur-SO_LIM)/(-k[0]) if k[0]<-1e-9 else None
        else:
            a=float(np.exp(k[1])); kk=k[0]
            rul=(np.log(max(cur,1e-6))-np.log(SO_LIM))/(-kk) if kk<-1e-9 else None
        rows.append(dict(方法='机理-溶解氧外推(%s, %d 天窗口)'%('线性' if kind=='lin' else '指数',WIND),
            RUL估计=None if rul is None else round(float(rul),2),
            RUL真值=round(true_rul,2),
            绝对误差=None if rul is None else round(abs(rul-true_rul),2)))
# 通用健康指数（此前结果）
rows.append(dict(方法='通用-健康指数线性外推（5 天窗口）',RUL估计=27.82,RUL真值=round(true_rul,2),绝对误差=round(abs(27.82-true_rul),2)))
R=pd.DataFrame(rows)
R.to_csv(os.path.join(OUT,'bsm1_rul_methods.csv'),index=False,encoding='utf-8-sig')
print(R.to_string(index=False))
json.dump(dict(真值失效天=round(truth,2),报警天=ALARM,真值剩余天=round(true_rul,2),结果=R.to_dict('records')),
    open(os.path.join(OUT,'bsm1_rul_methods.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
