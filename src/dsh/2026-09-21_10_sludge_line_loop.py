# -*- coding: utf-8 -*-
"""污泥线轻量闭环（路线 A）（DSH，2026-09-21）
链路：BSM1 剩余污泥（QW=385 m3/d，底层组成）→ 浓缩池 Thickener → 脱水机 Dewatering → 泥饼 + 滤液（回流）。
退化注入：**脱水机性能退化** —— 泥饼含固率目标 dewater_perc 从 28% 线性降到 18%（第 20 天起 60 天）；
         同时浓缩池目标含固率 thickener_perc 从 7% 降到 6%（污泥泵/浓缩池性能下降）。
被监测（真实厂可测的间接量）：滤液 TSS、滤液流量、泥饼干固体产率、浓缩池上清液 TSS、脱水机固体通量。
真值失效：泥饼含固率 DS < 20%（不满足外运/处置要求）持续 1 天。
检测/诊断/RUL：复用双基线模块 + 机理量（泥饼含固率）因果外推。
产物：results/2026-09-21/dsh/sludge_line.{csv,md,png}
用法：python src/dsh/2026-09-21_10_sludge_line_loop.py"""
import os, sys, io, json, time, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bsm2_python.bsm2 import thickener_bsm2 as T, dewatering_bsm2 as D
from bsm2_python.bsm2.init import thickenerinit_bsm2 as TI, dewateringinit_bsm2 as DI
from dual_baseline import frozen_z, topk_score, make_events, _scale_floor
D21='results/2026-09-21/dsh'
QW=385.0; DEG_START=20.0; RAMP=60.0; DS_START=28.0; DS_END=18.0; TH_START=7.0; TH_END=6.0; DS_FAIL=20.0
th=T.Thickener(TI.THICKENERPAR.copy()); dw=D.Dewatering(DI.DEWATERINGPAR.copy())
def line_step(y_waste, ds_perc, th_perc):
    th.dw_par if False else None
    th.par if False else None
    # 注入目标含固率（参数数组第 0 位：浓缩池/脱水机目标 TSS 百分比）
    tp=TI.THICKENERPAR.copy(); tp[0]=th_perc; th_=T.Thickener(tp)
    dp=DI.DEWATERINGPAR.copy(); dp[0]=ds_perc; dw_=D.Dewatering(dp)
    yt_u, yt_o = th_.output(y_waste)          # 浓缩污泥（底流）/ 上清液
    yc, yr = dw_.output(yt_u)                 # 泥饼 / 滤液
    return dict(浓缩污泥TSS=float(yt_u[13]), 浓缩污泥Q=float(yt_u[14]), 上清液TSS=float(yt_o[13]), 泥饼TSS=float(yc[13]), 泥饼Q=float(yc[14]), 滤液TSS=float(yr[13]), 滤液Q=float(yr[14]), 干固体产率=float(yc[13])*float(yc[14])/1000.0, 泥饼含固率=float(yc[13])/10000.0, 浓缩含固率=float(yt_u[13])/10000.0, 湿泥饼产量=float(yc[14]), 滤液量=float(yr[14]))

def build(tag, f):
    d=pd.read_csv(os.path.join(D21,f))
    cols=[c for c in d.columns if c.startswith('w_')]
    rows=[]
    for i,r in d.iterrows():
        t=float(r.t_day)
        ds=DS_START+(DS_END-DS_START)*min(1.0, max(0.0,(t-DEG_START)/RAMP)) if tag=='退化' else DS_START
        thp=TH_START+(TH_END-TH_START)*min(1.0, max(0.0,(t-DEG_START)/RAMP)) if tag=='退化' else TH_START
        y=np.array([float(r[c]) for c in cols]); y[14]=QW     # 剩余污泥流量 QW
        o=line_step(y, ds, thp); o.update(t_day=t, 目标泥饼含固率=ds, 目标浓缩含固率=thp)
        rows.append(o)
    return pd.DataFrame(rows)
print('【第 1 步流股自检】')
chk=build('健康', 'sludge_flow_healthy.csv.gz').head(3)
print(chk[['t_day','浓缩TSS' if '浓缩TSS' in chk.columns else '浓缩污泥TSS','泥饼Q','滤液Q','滤液TSS','干固体产率','泥饼含固率','浓缩含固率']].round(2).to_string(index=False))
H=build('健康','sludge_flow_healthy.csv.gz'); G=build('退化','sludge_flow_degraded.csv.gz')
print(); print('健康：泥饼含固率 %.2f%% ｜ 滤液 TSS %.0f ｜ 干固体 %.0f kg/d' % (H.泥饼含固率.mean(), H.滤液TSS.mean(), H.干固体产率.mean()))
print('退化：泥饼含固率 %.2f%% -> %.2f%% ｜ 滤液 TSS %.0f -> %.0f' % (G.泥饼含固率.iloc[0], G.泥饼含固率.iloc[-1], G.滤液TSS.iloc[0], G.滤液TSS.iloc[-1]))
v=(G.泥饼含固率<DS_FAIL).rolling(96,min_periods=24).mean()
idx=[i for i in range(len(v)) if v.iloc[i]>=1.0 and G.t_day.iloc[i]>DEG_START]
fail=(float(G.t_day.iloc[idx[0]]) if idx else None)
print('真值失效（泥饼含固率 < %.0f%% 持续 1 天）：%s' % (DS_FAIL, ('第 %.2f 天'%fail) if fail else '未发生'))

# ---- 检测：只用间接可观测量（不含含固率本身） ----
OBS=['泥饼Q','滤液Q','滤液TSS','干固体产率','上清液TSS']   # 只用真实厂可测的间接量；泥饼含固率留给 RUL 作机理锚
def prep(X):
    Y=X[OBS].copy(); Y.index=pd.to_datetime((X.t_day*86400).round().astype('int64'), unit='s'); return Y
Bh, Bd = prep(H), prep(G)
REF=Bh[(Bh.index>=Bh.index[0]+pd.Timedelta(days=30))&(Bh.index<Bh.index[0]+pd.Timedelta(days=45))]
FL=_scale_floor(Bh,OBS)
hod=lambda X: ((np.asarray(X.index.hour)).astype(int))
def sc(X): return np.asarray(topk_score(frozen_z(X,OBS,REF,state=hod(X),state_ref=hod(REF),floor=FL),3),dtype=float).ravel()
sD=sc(Bd); thr=float(np.quantile(np.asarray(topk_score(frozen_z(REF,OBS,REF,state=hod(REF),state_ref=hod(REF),floor=FL),3),dtype=float).ravel(),0.999))
evD=make_events(pd.Series(sD), thr)
dB=np.asarray(Bd.index); dD=np.asarray(G.t_day)
first=[(float(dD[i]),i) for i,e in evD if float(dD[i])>DEG_START]
alarm=(first[0][0] if first else None)
print(); print('检测（双基线，只用间接量）：告警 %d 个；首个（退化后）%s；阈值 %.3f' % (len(evD), ('第 %.2f 天'%alarm) if alarm else '无', thr))
# ---- RUL：机理量（泥饼含固率）因果外推 ----
def rul_causal(series, t0, target, win=5*96):
    i0=int(t0*96); lo=max(0,i0-win+1); y=np.asarray(series[lo:i0+1],dtype=float)
    x=np.arange(len(y),dtype=float); b,a=np.polyfit(x,y,1)
    if b>=-1e-9: return None
    return float(max((target-a)/b-(len(y)-1),0.0)/96.0)
rul=(rul_causal(G.泥饼含固率.values, alarm, DS_FAIL) if alarm else None)
truth=(None if fail is None else round(fail-alarm,2))
print('RUL（机理：泥饼含固率线性外推到 %.0f%%）：%s ｜ 真值 %s 天 ｜ 误差 %s 天' % (
    DS_FAIL, ('%.2f 天'%rul) if rul is not None else '不可算', truth,
    ('%.2f'%abs(rul-truth)) if (rul is not None and truth is not None) else '-'))
out=pd.concat([H.assign(轨迹='健康'), G.assign(轨迹='退化')], ignore_index=True)
out.to_csv(os.path.join(D21,'sludge_line.csv'), index=False, encoding='utf-8-sig')
summ=dict(QW=QW, 健康泥饼含固率=round(float(H.泥饼含固率.mean()),2), 退化末期泥饼含固率=round(float(G.泥饼含固率.iloc[-1]),2),
          健康滤液TSS=round(float(H.滤液TSS.mean()),1), 退化末期滤液TSS=round(float(G.滤液TSS.iloc[-1]),1),
          真值失效天=(None if fail is None else round(fail,2)), 告警天=(None if alarm is None else round(alarm,2)),
          提前量=(None if (fail is None or alarm is None) else round(fail-alarm,2)),
          RUL估计=(None if rul is None else round(rul,2)), RUL误差=(None if (rul is None or truth is None) else round(abs(rul-truth),2)))
io.open(os.path.join(D21,'sludge_line_summary.json'),'w',encoding='utf-8').write(json.dumps(summ,ensure_ascii=False,indent=2))
print(); print(json.dumps(summ,ensure_ascii=False))
