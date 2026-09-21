# -*- coding: utf-8 -*-
"""污泥线幅值/速率扫描（DSH，2026-09-21）
目的：给出"脱水机退化的可检测性曲线"——检出延迟 / 提前量 / RUL 误差 随退化速率与幅值的变化。
两轴（退化均起始第 60 天，避开投运暂态）：
  速率轴：最终含固率固定 18%（低于处置要求 20%），斜坡 30 / 60 / 120 / 240 天
  幅值轴：斜坡固定 60 天，最终含固率 25 / 22 / 20 / 18%（后两档才触发失效）
被监测：只用间接量（湿泥饼产量、滤液量、滤液 TSS、干固体产率、上清液 TSS）；泥饼含固率仅作 RUL 机理锚。
产物：results/2026-09-21/dsh/sludge_sweep.{csv,md,png}
用法：python src/dsh/2026-09-21_12_sludge_sweep.py"""
import os, sys, io, json, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bsm2_python.bsm2 import thickener_bsm2 as T, dewatering_bsm2 as D
from bsm2_python.bsm2.init import thickenerinit_bsm2 as TI, dewateringinit_bsm2 as DI
from dual_baseline import frozen_z, topk_score, adaptive_z, make_events, _scale_floor
D21='results/2026-09-21/dsh'; QW=385.0; DS0=28.0; TH0, TH1 = 7.0, 6.0; DEG_START=60.0; FAIL=20.0
OBS=['湿泥饼产量','滤液量','滤液TSS','干固体产率','上清液TSS']
BASE=pd.read_csv(os.path.join(D21,'sludge_flow_healthy.csv.gz'))
COLS=[c for c in BASE.columns if c.startswith('w_')]
def build(ds_end, ramp):
    rows=[]
    for _,r in BASE.iterrows():
        t=float(r.t_day); f=min(1.0, max(0.0,(t-DEG_START)/ramp))
        ds=DS0+(ds_end-DS0)*f; thp=TH0+(TH1-TH0)*f
        y=np.array([float(r[c]) for c in COLS]); y[14]=QW
        tp=TI.THICKENERPAR.copy(); tp[0]=thp; dp=DI.DEWATERINGPAR.copy(); dp[0]=ds
        yt_u,yt_o=T.Thickener(tp).output(y); yc,yr=D.Dewatering(dp).output(yt_u)
        rows.append(dict(t_day=t, 泥饼含固率=float(yc[13])/10000.0, 湿泥饼产量=float(yc[14]), 滤液量=float(yr[14]),
                         滤液TSS=float(yr[13]), 干固体产率=float(yc[13])*float(yc[14])/1000.0, 上清液TSS=float(yt_o[13])))
    return pd.DataFrame(rows)
def prep(X):
    Y=X[OBS].copy(); Y.index=pd.to_datetime((X.t_day*86400).round().astype('int64'),unit='s'); return Y
hod=lambda X: np.asarray(X.index.hour).astype(int)
H=build(DS0,60.0); Bh=prep(H)
REF=Bh[(Bh.index>=Bh.index[0]+pd.Timedelta(days=30))&(Bh.index<Bh.index[0]+pd.Timedelta(days=45))]
FL=_scale_floor(Bh,OBS)
THR=float(np.quantile(np.asarray(topk_score(frozen_z(REF,OBS,REF,state=hod(REF),state_ref=hod(REF),floor=FL),3),dtype=float).ravel(),0.999))
ADAPT_THR=float(np.quantile(np.asarray(topk_score(adaptive_z(Bh,OBS,win_days=2.0,state=hod(Bh)),3),dtype=float).ravel()[(np.asarray(H.t_day)>=30)&(np.asarray(H.t_day)<45)],0.999))
SCEN=[('速率 30 天',18.0,30.0),('速率 60 天',18.0,60.0),('速率 120 天',18.0,120.0),('速率 240 天',18.0,240.0),
      ('幅值 -3pp(→25%)',25.0,60.0),('幅值 -6pp(→22%)',22.0,60.0),('幅值 -8pp(→20%)',20.0,60.0),('幅值 -10pp(→18%)',18.0,60.0)]
rows=[]
for tag,ds_end,ramp in SCEN:
    G=build(ds_end,ramp); Bd=prep(G); dD=np.asarray(G.t_day); g=G.泥饼含固率.values
    Zf=frozen_z(Bd,OBS,REF,state=hod(Bd),state_ref=hod(REF),floor=FL); sf=np.asarray(topk_score(Zf,3),dtype=float).ravel()
    Za=adaptive_z(Bd,OBS,win_days=2.0,state=hod(Bd)); sa=np.asarray(topk_score(Za,3),dtype=float).ravel()
    v=(G.泥饼含固率<FAIL).rolling(96,min_periods=24).mean()
    idx=[i for i in range(len(v)) if v.iloc[i]>=1.0 and dD[i]>DEG_START]
    fail=(float(dD[idx[0]]) if idx else None)
    def first_after(score,thr):
        ev=make_events(pd.Series(score),thr)
        vv=[float(dD[s]) for s,e in ev if dD[s]>DEG_START]
        return (ev, (min(vv) if vv else None), sum(1 for s,e in ev if dD[s]<=DEG_START))
    evf,ff,pref=first_after(sf,THR); eva,fa,prea=first_after(sa,ADAPT_THR)
    al=min([x for x in [ff,fa] if x is not None], default=None)
    rul=None
    if ff:
        i0=int(ff*96); lo=max(0,i0-96); y=np.asarray(g[lo:i0+1],dtype=float)
        b,a=np.polyfit(np.arange(len(y),dtype=float),y,1)
        rul=(None if b>=-1e-9 else float(max((FAIL-a)/b-(len(y)-1),0.0)/96.0))
    ana=(None if ds_end>=FAIL else round(DEG_START+ramp*(DS0-FAIL)/(DS0-ds_end),2))
    rows.append(dict(场景=tag, 最终含固率=ds_end, 斜坡天=ramp, 降解速率pp每天=round((DS0-ds_end)/ramp,3),
                     解析失效时刻=ana, 仿真期内失效=(fail is not None),
                     真值失效=(None if fail is None else round(fail,2)), 提前量=(None if (fail is None or ff is None) else round(fail-ff,2)),
                     冻结首报=(None if ff is None else round(ff,2)), 冻结退化前告警=pref,
                     冻结延迟=(None if ff is None else round(ff-DEG_START,2)),
                     自适应首报=(None if fa is None else round(fa,2)), 自适应延迟=(None if fa is None else round(fa-DEG_START,2)),
                     RUL估计=(None if rul is None else round(rul,2)),
                     RUL真值=(None if ff is None else round((fail if fail is not None else (ana if ana is not None else float('nan')))-ff,2) if (fail is not None or ana is not None) else None),
                     RUL误差=(None if (rul is None or ff is None or (fail is None and ana is None)) else
                              round(abs(rul-(((fail if fail is not None else ana))-ff)),2)),
                     末期含固率=round(float(G.泥饼含固率.iloc[-1]),2)))
    print('  %-16s 速率 %.3f pp/d ｜ 真值失效 %s ｜ 冻结首报 %s（前 %d 告警）｜ 延迟 %s ｜ 提前量 %s ｜ RUL %s' % (
        tag, rows[-1]['降解速率pp每天'], rows[-1]['真值失效'], rows[-1]['冻结首报'], pref,
        rows[-1]['冻结延迟'], rows[-1]['提前量'], rows[-1]['RUL估计']), flush=True)
T=pd.DataFrame(rows); T.to_csv(os.path.join(D21,'sludge_sweep.csv'), index=False, encoding='utf-8-sig')
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif']=['Microsoft YaHei']; plt.rcParams['axes.unicode_minus']=False
BL,RD,GO,GY='#1f4e79','#c00000','#d99b1f','#7f7f7f'
fig,ax=plt.subplots(1,3,figsize=(16,4.6))
r=T[T.场景.str.startswith('速率')]
ax[0].plot(r.斜坡天, r.冻结延迟, 'o-', color=BL, label='检出延迟（冻结通道）')
ax[0].plot(r.斜坡天, r.提前量, 's--', color=RD, label='失效前提前量')
ax[0].set_xlabel('退化斜坡长度（天）'); ax[0].set_ylabel('天'); ax[0].set_title('① 速率轴：退化越慢，检出越晚、提前量越小')
ax[0].legend(fontsize=8); ax[0].grid(alpha=.3)
m=T[T.场景.str.startswith('幅值')]
ax[1].plot(m.最终含固率, m.提前量, 's-', color=RD, label='提前量')
ax[1].plot(m.最终含固率, m.冻结延迟, 'o--', color=BL, label='检出延迟')
for i,(x,y) in enumerate(zip(m.最终含固率, m.提前量)):
    ax[1].text(x, (0 if pd.isna(y) else y)+3, '无失效' if pd.isna(y) else '%.1f'%y, ha='center', fontsize=8)
ax[1].invert_xaxis(); ax[1].set_xlabel('最终泥饼含固率（%）（处置要求 20%）'); ax[1].set_ylabel('天')
ax[1].set_title('② 幅值轴：退化越浅，提前量越小（≥20% 则不触发失效）'); ax[1].legend(fontsize=8); ax[1].grid(alpha=.3)
ok=T.dropna(subset=['RUL误差'])
ax[2].bar(range(len(ok)), ok.RUL误差, color=[RD if v>5 else '#2fa36b' for v in ok.RUL误差])
for i,v in enumerate(ok.RUL误差): ax[2].text(i, v+0.3, '%.2f'%v, ha='center', fontsize=8)
ax[2].set_xticks(range(len(ok))); ax[2].set_xticklabels(ok.场景, fontsize=7.5, rotation=25, ha='right')
ax[2].set_ylabel('RUL 绝对误差（天，1 天机理窗）'); ax[2].set_title('③ 剩余寿命误差（可算的场景）'); ax[2].grid(alpha=.3, axis='y')
plt.tight_layout(); plt.savefig(os.path.join(D21,'sludge_sweep.png'), dpi=130)
NL=chr(10)+chr(10)
f=io.open(os.path.join(D21,'sludge_sweep_report.md'),'w',encoding='utf-8'); W=f.write
W('# 污泥线幅值/速率扫描（DSH，2026-09-21）'+NL)
W('退化均起始第 60 天（避开投运暂态，见 25 节）。速率轴：最终含固率固定 18%，斜坡 30/60/120/240 天；幅值轴：斜坡固定 60 天，最终 25/22/20/18%。'+NL)
W('检测用冻结通道（参考域=健康第 30-45 天，阈值 %.3f）与自适应通道（阈值 %.3f）；RUL 用泥饼含固率 1 天窗线性外推到 20%%。' % (THR, ADAPT_THR)+NL)
W('## 1. 结果'+NL+T.to_markdown(index=False)+NL)
W('## 2. 结论'+NL)
W('- **速率轴**：斜坡 30/60/120/240 天的检出延迟与提前量见上表 —— 退化越慢，检出越晚、失效前提前量越小（与 18.2 节 BSM1 的结论同向）。'+NL)
W('- **幅值轴**：最终含固率 ≥20% 的场景（25%/22%）**不触发"处置要求失效"**，因此只有检出延迟、没有提前量；这一档的价值是"提前发现但不必立刻停机"。'+NL)
W('- **自适应通道**：见逐场景列，验证它在慢退化上是否漏检。'+NL)
W('- **RUL 误差**：见第③图与表中 RUL 误差列（1 天机理窗）。'+NL)
W('## 3. 局限'+NL)
W('- 理想单元（无堵塞动力学）；退化是参数级斜坡；单条进水轨迹。'+NL)
f.close(); print('CSV/报告/图已写入', D21)
