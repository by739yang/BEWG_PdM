# -*- coding: utf-8 -*-
"""BSM1 退化幅值-斜率扫描（DSH，2026-09-20）
固定 120 天 / 第 20 天起退化，扫描最终 KLa 比例与衰减斜坡长度；
对每个场景用已验证的双基线配置（自适应 2 天 + 冻结参考取健康运行稳态段）检出，
并给出相对"性能劣化点(SO3<1.0)"与"失效点(SO3<0.5)"的预警提前量。"""
import bsm2_python as b, numpy as np, pandas as pd, json, os, time, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dual_baseline import dual_detect
OUT='results/2026-09-20/dsh'
DAYS=120.0; DT=1/96; DEG_START=20.0
CH=['SO3','SO4','SO5','SNH_eff','Ntot_eff','TSS_eff','sludge_h']
SCEN=[(0.80,100.0),(0.60,100.0),(0.40,100.0),(0.20,100.0),(0.40,40.0),(0.20,40.0)]

def sim(keep, ramp, tag):
    t0=time.time(); o=b.BSM1OL(endtime=DAYS, timestep=DT, evaltime=1); o.stabilize()
    n=int(round(DAYS/DT)); k0=np.asarray(o.klas).copy(); rows=[]
    for i in range(n):
        t=i*DT; k=k0.copy()
        if keep<1.0: k=k*(1.0-(1.0-keep)*min(1.0, max(0.0,(t-DEG_START)/ramp)))
        o.step(i,k); rr=np.asarray(o.ys_eff).ravel()
        rows.append((t,float(np.asarray(o.y_out3).ravel()[7]),float(np.asarray(o.y_out4).ravel()[7]),
            float(np.asarray(o.y_out5).ravel()[7]),float(rr[9]),float(rr[10]),float(rr[13]),
            float(np.asarray(o.sludge_height)),float(k.sum())))
    print('  %-22s %d 步 / %.0fs' % (tag,n,time.time()-t0), flush=True)
    return pd.DataFrame(rows,columns=['t_day','SO3','SO4','SO5','SNH_eff','Ntot_eff','TSS_eff','sludge_h','kla_sum'])

def prep(df):
    x=df.copy(); x.index=pd.to_datetime(x.t_day*86400, unit='s'); return x
def hod(X): return ((X.t_day*24)%24).astype(int).values
def cross(df, level):
    v=(df.SO3<level).rolling(96, min_periods=24).mean()
    idx=[i for i in range(len(v)) if v.iloc[i]>=1.0 and df.t_day.iloc[i]>DEG_START]
    return (idx[0]/96.0) if idx else None

path=os.path.join(OUT,'bsm1_120d_baseline.csv')
if os.path.exists(path):
    base=pd.read_csv(path); print('复用已有基准运行 %s' % path)
else:
    base=sim(1.0,0,'基准'); base.to_csv(path,index=False)
B=prep(base); REF=B[(B.t_day>=30)&(B.t_day<45)]; ref_mask=B.t_day<DEG_START
rows=[]
for keep,ramp in SCEN:
    tag='KLa->%.0f%% 斜坡%.0f天'%(keep*100,ramp)
    f120=os.path.join(OUT,'bsm1_120d_degraded.csv'); fs=os.path.join(OUT,'bsm1_sweep_keep%02d_ramp%03d.csv'%(keep*100,ramp))
    if keep==0.40 and ramp==100.0 and os.path.exists(f120):
        deg=pd.read_csv(f120); print('  复用已有退化运行', flush=True)
    elif os.path.exists(fs):
        deg=pd.read_csv(fs); print('  复用', os.path.basename(fs), flush=True)
    else:
        deg=sim(keep,ramp,tag); deg.to_csv(fs,index=False)
    D=prep(deg)
    res=dual_detect(D, CH, D.t_day<DEG_START, win_days=2.0, k=3, ref_mask_frozen=(B.index>=REF.index[0])&(B.index<=REF.index[-1]),
                    ref_data_frozen=REF, state_frozen=hod(D), state_ref_frozen=hod(REF))
    A=res['alarms']; da={}
    for chn in ['adaptive','frozen']:
        g=A[A.channel==chn] if len(A) else A
        v=[float(D.t_day.loc[t]) for t in g.t if float(D.t_day.loc[t])>DEG_START]
        da[chn]=round(min(v),2) if v else None
    fb=dual_detect(B, CH, B.t_day<DEG_START, win_days=2.0, k=3, ref_mask_frozen=(B.index>=REF.index[0])&(B.index<=REF.index[-1]),
                   ref_data_frozen=REF, state_frozen=hod(B), state_ref_frozen=hod(REF))
    AB=fb['alarms']
    fp={chn:int(((AB.channel==chn).sum()) if len(AB) else 0) for chn in ['adaptive','frozen']}
    t1,t5=cross(deg,1.0),cross(deg,0.5)
    al=min([v for v in da.values() if v is not None], default=None)
    rows.append(dict(最终KLa比例=keep, 斜坡天=ramp, 衰减速率每百天=(1-keep)/ramp*100,
                     自适应首报=da['adaptive'], 冻结首报=da['frozen'], 最早报警=al,
                     检出延迟天=(None if al is None else round(al-DEG_START,2)),
                     性能劣化点SO3_1_0=(None if t1 is None else round(t1,2)),
                     失效点SO3_0_5=(None if t5 is None else round(t5,2)),
                     提前量SO3_1_0=(None if (t1 is None or al is None) else round(t1-al,2)),
                     提前量SO3_0_5=(None if (t5 is None or al is None) else round(t5-al,2)),
                     健康运行误报_自适应=fp['adaptive'], 健康运行误报_冻结=fp['frozen'],
                     退化末期SO3均值=round(float(deg[deg.t_day>100].SO3.mean()),3)))
    print('  -> %s' % json.dumps(rows[-1],ensure_ascii=False), flush=True)
T=pd.DataFrame(rows); T.to_csv(os.path.join(OUT,'bsm1_amp_sweep.csv'),index=False,encoding='utf-8-sig')
json.dump(rows, io.open(os.path.join(OUT,'bsm1_amp_sweep.json'),'w',encoding='utf-8'), ensure_ascii=False, indent=2) if False else None
with open(os.path.join(OUT,'bsm1_amp_sweep.json'),'w',encoding='utf-8') as f: json.dump(rows,f,ensure_ascii=False,indent=2)
print(); print(T.to_string(index=False))
