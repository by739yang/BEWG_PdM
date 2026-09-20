# -*- coding: utf-8 -*-
"""BSM1 闭环 v4（DSH，2026-09-20）：120 天长窗慢退化，验证 RUL 误差
退化：第 20 天起 KLa 线性衰减至 40%（约 0.4%/天，共 60% 降幅）
失效判据（双定义，取先到者）：A) 健康指数越过 3 倍报警阈值；B) 溶解氧 SO3 持续 1 天低于 0.5 mg/L
RUL：报警时刻用健康指数趋势线性外推到失效阈值，与真值比较"""
import bsm2_python as b, numpy as np, pandas as pd, json, os, time
OUT='results/2026-09-20/dsh'
DAYS=120; DT=1/96; DEG_START=20.0; KEEP=0.40
def run(scale_fn,tag):
    t0=time.time(); o=b.BSM1OL(endtime=DAYS, timestep=DT, evaltime=1); o.stabilize()
    n=int(round(DAYS/DT)); k0=np.asarray(o.klas).copy(); rows=[]
    for i in range(n):
        t=i*DT; k=k0.copy()
        if scale_fn is not None: k=k*scale_fn(t)
        o.step(i,k); rr=np.asarray(o.ys_eff).ravel()
        rows.append((t,float(np.asarray(o.y_out3).ravel()[7]),float(np.asarray(o.y_out4).ravel()[7]),
            float(np.asarray(o.y_out5).ravel()[7]),float(rr[9]),float(rr[10]),float(rr[13]),
            float(np.asarray(o.sludge_height)),float(k.sum())))
    print('  %s：%d 步 / %.0fs' % (tag,n,time.time()-t0))
    return pd.DataFrame(rows,columns=['t_day','SO3','SO4','SO5','SNH_eff','Ntot_eff','TSS_eff','sludge_h','kla_sum'])
print('运行 120 天场景（两遍）……')
base=run(None,'基准'); deg=run(lambda t:(1.0 if t<DEG_START else 1.0-(1-KEEP)*min(1.0,(t-DEG_START)/(DAYS-DEG_START))),'退化')
base.to_csv(os.path.join(OUT,'bsm1_120d_baseline.csv'),index=False); deg.to_csv(os.path.join(OUT,'bsm1_120d_degraded.csv'),index=False)
print('基准统计：SO3 均值 %.2f ｜ SNH_eff 均值 %.2f ｜ TSS 均值 %.1f' % (base.SO3.mean(),base.SNH_eff.mean(),base.TSS_eff.mean()))
print('退化末期：SO3 均值 %.2f ｜ kla_sum %.0f（基准 %.0f）' % (deg[deg.t_day>100].SO3.mean(), deg[deg.t_day>100].kla_sum.mean(), base[base.t_day>100].kla_sum.mean()))
CH=['SO3','SO4','SO5','SNH_eff','Ntot_eff','TSS_eff','sludge_h']
cal=base[base.t_day<DEG_START]
Z={}
for tag,df in [('base',base),('deg',deg)]:
    Zz=pd.DataFrame(0.0,index=df.index,columns=CH)
    for c in CH:
        med=cal[c].median(); iqr=cal[c].quantile(.75)-cal[c].quantile(.25); sdv=cal[c].std()
        sc=iqr/1.349 if iqr>1e-9 else (sdv if sdv>1e-9 else 1.0)
        Zz[c]=(df[c]-med)/sc
    Z[tag]=Zz
def health(Zz):
    A=np.abs(Zz.values); s=pd.Series(np.sqrt((np.sort(A,axis=1)[:,-3:]**2).mean(1)))
    return s.rolling(96,min_periods=24).median()
hb=health(Z['base']); hd=health(Z['deg'])
thr=float(hb.iloc[:int(DEG_START*96)].quantile(0.995)); fail=3*thr
def first_cross(s,x,after=DEG_START):
    v=[i/96 for i in range(len(s)) if float(s.iloc[i])>x and i/96>after]
    return v[0] if v else None
alarm=first_cross(hd,thr); danger=first_cross(hd,fail)
so_fail=None
v=(deg.SO3<0.5).rolling(96).mean()
idx=[i for i in range(len(v)) if v.iloc[i]>=1.0 and i/96>DEG_START]
if idx: so_fail=idx[0]/96
truth=min([x for x in [danger,so_fail] if x is not None], default=None)
rul=None; slope=None
if alarm and truth:
    i0=int(alarm*96); seg=hd.iloc[max(0,i0-int(5*96)):i0+1]
    k=np.polyfit(np.arange(len(seg),dtype=float),seg.values,1)[0]*96; slope=float(k)
    cur=float(hd.iloc[i0]); rul=(fail-cur)/k if k>1e-6 else None
res=dict(天数=DAYS,退化='第 %g 天起 KLa 衰减至 %.0f%%'%(DEG_START,KEEP*100),
    报警阈值=round(thr,3),危险阈值=round(fail,3),
    报警时刻=None if alarm is None else round(alarm,2),
    检出延迟=None if alarm is None else round(alarm-DEG_START,2),
    真值失效时刻=None if truth is None else round(truth,2),
    失效来源='健康指数越危险阈值' if truth==danger else ('SO3 持续低于 0.5' if truth==so_fail else None),
    SO3失效时刻=None if so_fail is None else round(so_fail,2),
    RUL估计天=None if rul is None else round(float(rul),2),
    RUL真值天=None if (truth is None or alarm is None) else round(truth-alarm,2),
    RUL绝对误差天=None if (rul is None or truth is None or alarm is None) else round(abs((alarm+rul)-truth),2),
    基准误报采样数=int((hb.iloc[:int(DEG_START*96)]>thr).sum()))
print(json.dumps(res,ensure_ascii=False,indent=2))
json.dump(res,open(os.path.join(OUT,'bsm1_120d_summary.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
