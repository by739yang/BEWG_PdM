# -*- coding: utf-8 -*-
"""BSM1 闭环 v2：60 天、更慢退化（40% KLa / 40 天），用平滑健康指数做报警与 RUL，使其可验证"""
import bsm2_python as b, numpy as np, pandas as pd, json, os, time
OUT='results/2026-09-20/dsh'
DAYS=60; DT=1/96; DEG_START=20.0; DEG_DROP=0.40; WIN_D=14
def run(scale_fn,tag):
    t0=time.time(); o=b.BSM1OL(endtime=DAYS, timestep=DT, evaltime=1); o.stabilize()
    n=int(round(DAYS/DT)); k0=np.asarray(o.klas).copy(); rows=[]
    for i in range(n):
        t=i*DT; k=k0.copy()
        if scale_fn is not None: k=k*scale_fn(t)
        o.step(i,k); rr=np.asarray(o.ys_eff).ravel()
        rows.append(dict(t_day=t, SO3=float(np.asarray(o.y_out3).ravel()[7]), SO4=float(np.asarray(o.y_out4).ravel()[7]),
            SO5=float(np.asarray(o.y_out5).ravel()[7]), SNH_eff=float(rr[9]), Ntot_eff=float(rr[10]),
            TSS_eff=float(rr[13]), sludge_h=float(np.asarray(o.sludge_height)), kla_sum=float(k.sum())))
    print('  %s：%d 步 / %.0fs' % (tag,n,time.time()-t0)); return pd.DataFrame(rows)
print('运行 60 天场景……')
base=run(None,'基准'); deg=run(lambda t:(1.0 if t<DEG_START else 1.0-DEG_DROP*min(1.0,(t-DEG_START)/(DAYS-DEG_START))),'退化')
base.to_csv(os.path.join(OUT,'bsm1_60d_baseline.csv'),index=False); deg.to_csv(os.path.join(OUT,'bsm1_60d_degraded.csv'),index=False)
CH=['SO3','SO4','SO5','SNH_eff','Ntot_eff','TSS_eff','sludge_h']
def score(df,ref):
    Z=pd.DataFrame(0.0,index=df.index,columns=CH); W=int(WIN_D*96)
    for c in CH:
        x=df[c].astype(float); med=x.rolling(W,min_periods=96).median()
        iqr=x.rolling(W,min_periods=96).quantile(.75)-x.rolling(W,min_periods=96).quantile(.25)
        sd=x.rolling(W,min_periods=96).std(); sc=iqr.where(iqr>1e-9,sd).fillna(1.0)
        Z[c]=((x-med)/sc).replace([np.inf,-np.inf],np.nan).fillna(0.0)
    A=np.abs(Z.values); return pd.Series(np.sqrt((np.sort(A,axis=1)[:,-3:]**2).mean(1)),index=df.index)
def smooth(s,days=1.0): return s.rolling(int(days*96),min_periods=24).median()
sb=smooth(score(base,base[base.t_day<DEG_START])); sd=smooth(score(deg,base[base.t_day<DEG_START]))
thr=float(sb.iloc[:int(DEG_START*96)].quantile(0.995)); fail=3*thr
def first_cross(s,t0,x): 
    v=[float(s.index[i]) for i in range(len(s)) if float(s.iloc[i])>x and float((s.index[i])/96)>t0]
    return v[0]/96 if v else None
alarm=first_cross(sd,DEG_START,thr); danger=first_cross(sd,DEG_START,fail)
rul=None; slope=None
if alarm:
    i0=int(alarm*96); seg=sd.iloc[max(0,i0-3*96):i0+1]
    k=np.polyfit(np.arange(len(seg),dtype=float),seg.values,1)[0]*96
    cur=float(sd.iloc[i0]); slope=float(k)
    rul=(fail-cur)/k if k>1e-6 else None
res=dict(天数=DAYS,退化='第 %g 天起 KLa 线性衰减 %.0f%%'%(DEG_START,DEG_DROP*100),
    报警阈值=round(thr,3),危险阈值=round(fail,3),
    报警时刻天=None if alarm is None else round(alarm,2),
    检出延迟天=None if alarm is None else round(alarm-DEG_START,2),
    真值越危险阈值天=None if danger is None else round(danger,2),
    RUL估计天=None if rul is None else round(float(rul),2),
    RUL真值天=None if (danger is None or alarm is None) else round(danger-alarm,2),
    RUL绝对误差天=None if (rul is None or danger is None or alarm is None) else round(abs((alarm+rul)-danger),2),
    健康指数日斜率=slope,
    基准误报数=int((sb.iloc[:int(DEG_START*96)]>thr).sum()))
print(json.dumps(res,ensure_ascii=False,indent=2))
json.dump(res,open(os.path.join(OUT,'bsm1_60d_summary.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
