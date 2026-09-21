# -*- coding: utf-8 -*-
"""记录 BSM1 的剩余污泥流（污泥线闭环 A 的输入）（DSH，2026-09-21）
BSM1 的二沉池底层组成 = 回流污泥 = 剩余污泥（只差流量：QW=385 m3/d）。
本脚本跑健康与退化（第 20 天起 KLa 衰减至 40%/100 天）两条轨迹，逐步记录底层 21 维向量与关键量。
用法：python src/dsh/2026-09-21_09_record_waste_sludge.py"""
import os, sys, time, json, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bsm2_python as b
D21='results/2026-09-21/dsh'; os.makedirs(D21, exist_ok=True)
DAYS=120.0; DT=1/96; DEG_START=20.0; KEEP=0.40; RAMP=100.0
N=int(round(DAYS/DT))+1+96*3
NAMES=['S_I','S_S','X_I','X_S','X_BH','X_BA','X_P','S_O','S_NO','S_NH','S_ND','X_ND','S_ALK','TSS','Q','T','d1','d2','d3','d4','d5']
def run(keep, tag):
    from bsm2_python.bsm2.init import asm1init_bsm2 as AS
    o=b.BSM1OL(endtime=DAYS, timestep=DT, evaltime=1); o.stabilize()
    k0=np.asarray(o.klas).copy(); rec=[]; t0=time.time()
    for i in range(int(round(DAYS/DT))):
        t=i*DT; k=k0.copy()
        if keep<1.0: k=k*(1.0-(1.0-keep)*min(1.0, max(0.0,(t-DEG_START)/RAMP)))
        o.step(i,k)
        ye=np.asarray(o.ys_eff).ravel(); yo=np.asarray(o.ys_out).ravel()   # o.ys_out = 二沉池底层（=回流污泥组成）
        rec.append(dict(t_day=t, DO3=float(np.asarray(o.y_out3).ravel()[7]), NH_eff=float(ye[9]), TSS_eff=float(ye[13]),
                        sludge_h=float(np.asarray(o.sludge_height)), Q_eff=float(ye[14]),
                        **{'w_'+n: float(yo[j]) for j,n in enumerate(NAMES)}))
    print('  %-8s %d 步 / %.0fs' % (tag, len(rec), time.time()-t0), flush=True)
    return pd.DataFrame(rec)
if __name__=='__main__':
    for keep, tag, fn in [(1.0,'健康','sludge_flow_healthy.csv.gz'), (KEEP,'退化','sludge_flow_degraded.csv.gz')]:
        d=run(keep, tag); d.to_csv(os.path.join(D21,fn), index=False)
        print('   %s：剩余污泥 TSS 均值 %.0f mg/L ｜ QW=385 m3/d ｜ 干固体 %.1f kg/d' % (
            tag, d.w_TSS.mean(), d.w_TSS.mean()*385/1000))
    print('完成')
