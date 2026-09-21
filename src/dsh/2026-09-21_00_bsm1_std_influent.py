# -*- coding: utf-8 -*-
"""BSM1 标准进水（包内 dryinfluent，BSM1 自己的干天进水）对照实验（DSH，2026-09-21）
目的：检查"曝气退化 → 反应池溶解氧下降 → 功能性失效"这条链在标准进水（设计负荷）下是否同样成立，
     避免只用包默认的 BSM2 动态进水而被质疑进水选择不当。
场景：健康 + 退化（第 20 天起 KLa 线性衰减至 40%，100 天）
用法：python 2026-09-21_00_bsm1_std_influent.py sim | python 2026-09-21_00_bsm1_std_influent.py"""
import sys, os, io, json, time, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bsm2_python as b
OUT='results/2026-09-21/dsh'
PKG=os.path.dirname(b.__file__)
DAYS=120.0; DT=1/96; DEG_START=20.0; KEEP=0.40; RAMP=100.0
N=int(round(DAYS/DT))+1+96*3
CH=['SO3','SO4','SO5','SNH_eff','Ntot_eff','TSS_eff','sludge_h']

def influent():
    dry=np.genfromtxt(os.path.join(PKG,'data','dryinfluent.csv'),delimiter=',',skip_header=1)[:,1:]
    seq=[]
    while sum(len(x) for x in seq)<N: seq.append(dry)
    return np.vstack(seq)[:N].copy()

def sim(keep, tag):
    arr=influent(); d=np.column_stack([np.arange(N)*DT, arr])
    t0=time.time(); o=b.BSM1OL(data_in=d, timestep=DT, endtime=DAYS, evaltime=1); o.stabilize()
    k0=np.asarray(o.klas).copy(); rec=[]
    for i in range(int(round(DAYS/DT))):
        t=i*DT; k=k0.copy()
        if keep<1.0: k=k*(1.0-(1.0-keep)*min(1.0, max(0.0,(t-DEG_START)/RAMP)))
        o.step(i,k); rr=np.asarray(o.ys_eff).ravel()
        rec.append((t,float(np.asarray(o.y_out3).ravel()[7]),float(np.asarray(o.y_out4).ravel()[7]),
            float(np.asarray(o.y_out5).ravel()[7]),float(rr[9]),float(rr[10]),float(rr[13]),
            float(np.asarray(o.sludge_height)),float(k.sum())))
    print('  %-14s %d 步 / %.0fs' % (tag,len(rec),time.time()-t0), flush=True)
    return pd.DataFrame(rec,columns=['t_day','SO3','SO4','SO5','SNH_eff','Ntot_eff','TSS_eff','sludge_h','kla_sum'])

if len(sys.argv)>1 and sys.argv[1]=='sim':
    os.makedirs(OUT,exist_ok=True)
    sim(1.0,'健康').to_csv(os.path.join(OUT,'bsm1std_baseline.csv'),index=False)
    sim(KEEP,'退化 -40%/100d').to_csv(os.path.join(OUT,'bsm1std_degraded.csv'),index=False)
    print('仿真完成'); sys.exit(0)

from dual_baseline import dual_detect
def prep(df):
    x=df.copy(); x.index=pd.to_datetime(x.t_day*86400,unit='s'); return x
hod=lambda X: ((X.t_day*24)%24).astype(int).values
B=prep(pd.read_csv(os.path.join(OUT,'bsm1std_baseline.csv')))
D=prep(pd.read_csv(os.path.join(OUT,'bsm1std_degraded.csv')))
def first_sustained(X, col, op, level, after=DEG_START):
    v=(X[col]>level) if op=='>' else (X[col]<level)
    r=v.rolling(96,min_periods=24).mean()
    idx=[i for i in range(len(r)) if r.iloc[i]>=1.0 and X.t_day.iloc[i]>after]
    return (float(X.t_day.iloc[idx[0]]) if idx else None)
REF=B[(B.t_day>=30)&(B.t_day<45)]
res=dual_detect(D, CH, D.t_day<DEG_START, win_days=2.0, k=3, ref_mask_frozen=(B.t_day>=30)&(B.t_day<45),
                ref_data_frozen=REF, state_frozen=hod(D), state_ref_frozen=hod(REF))
A=res['alarms']
rows=[]
for tag,X in [('健康运行',B),('退化 -40%/100d',D)]:
    do_min=float(X.SO3.min()); nh_max=float(X.SNH_eff.max())
    rows.append(dict(运行=tag, DO3均值=round(float(X.SO3.mean()),2), DO3末期=round(float(X[X.t_day>100].SO3.mean()),2),
                     DO5均值=round(float(X.SO5.mean()),2), 出水氨氮均值=round(float(X.SNH_eff.mean()),2),
                     出水氨氮最大=round(nh_max,2), 出水TSS均值=round(float(X.TSS_eff.mean()),1),
                     DO持续低于0_5=(None if not (X.SO3<0.5).rolling(96,min_periods=24).mean().ge(1.0).any() else round(first_sustained(X,'SO3','<',0.5,0.0),2))))
fp={}
AB=dual_detect(B, CH, B.t_day<DEG_START, win_days=2.0, k=3, ref_mask_frozen=(B.t_day>=30)&(B.t_day<45),
               ref_data_frozen=REF, state_frozen=hod(B), state_ref_frozen=hod(REF))['alarms']
for chn in ['adaptive','frozen']:
    g=A[A.channel==chn] if len(A) else A
    v=[float(D.t_day.loc[t]) for t in g.t] if len(g) else []
    fp[chn]=dict(首报=(round(min(v),2) if v else None), 退化后首报=(round(min([x for x in v if x>DEG_START]),2) if [x for x in v if x>DEG_START] else None))
T=pd.DataFrame(rows); T.to_csv(os.path.join(OUT,'bsm1std_channels.csv'),index=False,encoding='utf-8-sig')
print(); print(T.to_string(index=False)); print()
print('退化运行告警：自适应 首报 %s ｜ 冻结 首报 %s' % (fp['adaptive']['退化后首报'], fp['frozen']['退化后首报']))
fail_do=first_sustained(D,'SO3','<',0.5); fail_nh=first_sustained(D,'SNH_eff','>',10.0,0.0)
al=min([fp['adaptive']['退化后首报'] or 9e9, fp['frozen']['退化后首报'] or 9e9], default=None)
out=dict(标准进水=True, DO失效时刻=(None if fail_do is None else round(fail_do,2)),
         出水氨氮首次持续超10mgL=(None if fail_nh is None else round(fail_nh,2)),
         最早报警=(None if al is None or al>8e9 else round(al,2)),
         相对DO失效的提前量=(None if (fail_do is None or al is None or al>8e9) else round(fail_do-al,2)))
with open(os.path.join(OUT,'bsm1std_summary.json'),'w',encoding='utf-8') as f: json.dump(out,f,ensure_ascii=False,indent=2)
print(json.dumps(out,ensure_ascii=False))
