# -*- coding: utf-8 -*-
"""组合报警策略评估（DSH，2026-09-20）
三级上报：
  P1-紧急（与门）= 单点事件机报警 且 同刻比值统计量已抬升（滚动 5 天中位数 > 1.15 x 工况健康基线）
  P2-计划       = 单点事件机报警，但比值未抬升（提示复核/计划检修窗）
  P3-观察       = 仅比值判据越限（> k x 基线），用于严重度分级与长期趋势
评估 12 个（健康, 退化）工况对：误报侧看健康运行上报数，检出侧看退化运行首报与延迟。
输出 alarm_strategy.{csv,json,md,png}"""
import sys, os, io, json, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dual_baseline import frozen_z, topk_score, make_events, _scale_floor
OUT='results/2026-09-20/dsh'
CH=['SO3','SO4','SO5','SNH_eff','Ntot_eff','TSS_eff','sludge_h']
K_RATIO=1.3      # 比值判据阈值倍数
K_AND=1.15       # 与门的「比值已抬升」倍数
PAIRS=[
 ('A 窗[0,120)','bsm1_120d_baseline.csv','bsm1_120d_degraded.csv'),
 ('B 窗[120,240)','bsm1_winB_120_240_baseline.csv','bsm1_winB_120_240_degraded.csv'),
 ('C 窗[240,360)','bsm1_winC_240_360_baseline.csv','bsm1_winC_240_360_degraded.csv'),
 ('慢 -20%/100d','bsm1_120d_baseline.csv','bsm1_sweep_keep80_ramp100.csv'),
 ('慢 -40%/100d','bsm1_120d_baseline.csv','bsm1_sweep_keep60_ramp100.csv'),
 ('慢 -60%/100d','bsm1_120d_baseline.csv','bsm1_120d_degraded.csv'),
 ('慢 -80%/100d','bsm1_120d_baseline.csv','bsm1_sweep_keep20_ramp100.csv'),
 ('快 -60%/40d','bsm1_120d_baseline.csv','bsm1_sweep_keep40_ramp040.csv'),
 ('快 -80%/40d','bsm1_120d_baseline.csv','bsm1_sweep_keep20_ramp040.csv'),
 ('R1 干天循环','bsm1_R1_dry_baseline.csv','bsm1_R1_dry_degraded.csv'),
 ('R2 干+雨循环','bsm1_R2_dry_rain_baseline.csv','bsm1_R2_dry_rain_degraded.csv'),
 ('R3 加暴雨','bsm1_R3_add_storm_baseline.csv','bsm1_R3_add_storm_degraded.csv')]
def prep(df):
    x=df.copy(); x.index=pd.to_datetime(x.t_day*86400,unit='s'); return x
hod=lambda X: ((X.t_day*24)%24).astype(int).values
def rollmed(v): return pd.Series(v).rolling(5*1440,min_periods=288).median().values
def episodes(mask, d, lo, hi):
    m=np.asarray(mask)&(d>=lo)&(d<=hi); out=[]; c=0
    for i,v in enumerate(m):
        if v: c+=1
        elif c: out.append((d[i-c], d[i-1])); c=0
    if c: out.append((d[len(m)-c], d[len(m)-1]))
    return out
rows=[]
for tag,fb,fd in PAIRS:
    pb=os.path.join(OUT,fb); pd_=os.path.join(OUT,fd)
    if not (os.path.exists(pb) and os.path.exists(pd_)): print('跳过（缺文件）',tag); continue
    B=prep(pd.read_csv(pb)); D=prep(pd.read_csv(pd_))
    REF=B[(B.t_day>=30)&(B.t_day<45)]; FL=_scale_floor(B,CH)
    def sc(X):
        return np.asarray(topk_score(frozen_z(X,CH,REF,state=hod(X),state_ref=hod(REF),floor=FL),3),dtype=float).ravel()
    sH=sc(B); sD=sc(D)
    ref_thr=float(np.quantile(np.asarray(topk_score(frozen_z(REF,CH,REF,state=hod(REF),state_ref=hod(REF),floor=FL),3),dtype=float).ravel(),0.999))
    evH=make_events(pd.Series(sH), ref_thr); evD=make_events(pd.Series(sD), ref_thr)
    rH=rollmed(sH); rD=rollmed(sD); dB=np.asarray(B.t_day); dD=np.asarray(D.t_day)
    base=float(np.nanmedian(rH[(dB>=30)&(dB<45)]))
    thrR=K_RATIO*base; thrA=K_AND*base
    def near(r, d, day, half=1.0):
        m=(d>=day-half)&(d<=day+half)&np.isfinite(r)
        return bool(np.max(r[m])>thrA) if m.any() else False
    spH=[float(dB[i]) for i,_ in evH]
    spD=[float(dD[i]) for i,_ in evD if float(dD[i])>20.0]
    p1H=[x for x in spH if near(rH,dB,x)]
    p1D=[x for x in spD if near(rD,dD,x)]
    epH=episodes(rH>thrR,dB,45,120); epD=episodes(rD>thrR,dD,45,120)
    det_sp=(round(min(spD)-20.0,2) if spD else None)
    det_rr=(round(min(e[0] for e in epD)-20.0,2) if epD else None)
    det_p1=(round(min(p1D)-20.0,2) if p1D else None)
    union=[x for x in spD]+[e[0] for e in epD]
    det_un=(round(min(union)-20.0,2) if union else None)
    rows.append(dict(工况=tag, base=round(base,3), 单点阈值=round(ref_thr,3), 比值阈值=round(thrR,3),
        健康_P1与门上报=len(p1H), 健康_单点上报=len(spH), 健康_比值越限段=len(epH),
        健康_并集上报=len(spH)+len(epH),
        检出_单点=(None if det_sp is None else det_sp), 检出_比值=(None if det_rr is None else det_rr),
        检出_P1与门=(None if det_p1 is None else det_p1), 检出_并集=(None if det_un is None else det_un)))
    print(json.dumps(rows[-1],ensure_ascii=False), flush=True)
T=pd.DataFrame(rows)
T.to_csv(os.path.join(OUT,'alarm_strategy.csv'),index=False,encoding='utf-8-sig')
with open(os.path.join(OUT,'alarm_strategy.json'),'w',encoding='utf-8') as f: json.dump(rows,f,ensure_ascii=False,indent=2)
print(); print(T.to_string(index=False))
SUM=pd.DataFrame([
 dict(策略='P1 与门（单点 且 比值抬升）', 健康上报合计=int(T.健康_P1与门上报.sum()), 检出数=int(T.检出_P1与门.notna().sum()), 检出延迟中位=(round(float(T.检出_P1与门.median()),1) if T.检出_P1与门.notna().any() else None)),
 dict(策略='单点事件机', 健康上报合计=int(T.健康_单点上报.sum()), 检出数=int(T.检出_单点.notna().sum()), 检出延迟中位=(round(float(T.检出_单点.median()),1) if T.检出_单点.notna().any() else None)),
 dict(策略='比值判据 k=1.3', 健康上报合计=int(T.健康_比值越限段.sum()), 检出数=int(T.检出_比值.notna().sum()), 检出延迟中位=(round(float(T.检出_比值.median()),1) if T.检出_比值.notna().any() else None)),
 dict(策略='并集（分级上报）', 健康上报合计=int(T.健康_并集上报.sum()), 检出数=int(T.检出_并集.notna().sum()), 检出延迟中位=(round(float(T.检出_并集.median()),1) if T.检出_并集.notna().any() else None))])
print(); print(SUM.to_string(index=False))
SUM.to_csv(os.path.join(OUT,'alarm_strategy_summary.csv'),index=False,encoding='utf-8-sig')
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif']=['Microsoft YaHei']; plt.rcParams['axes.unicode_minus']=False
BL,RD,GO,GY='#1f4e79','#c00000','#d99b1f','#7f7f7f'
x=np.arange(len(T)); wd=0.2
fig,ax=plt.subplots(1,2,figsize=(15,5))
ax[0].bar(x-1.5*wd,T.健康_P1与门上报,wd,color=GO,label='P1 与门')
ax[0].bar(x-0.5*wd,T.健康_单点上报,wd,color=RD,label='单点事件机')
ax[0].bar(x+0.5*wd,T.健康_比值越限段,wd,color=BL,label='比值判据')
ax[0].bar(x+1.5*wd,T.健康_并集上报,wd,color=GY,label='并集')
ax[0].set_xticks(x); ax[0].set_xticklabels(T.工况,fontsize=7.5,rotation=35,ha='right')
ax[0].set_ylabel('健康运行 120 天上报数'); ax[0].set_title('① 误报侧：P1 与门/比值判据为 0，并集=单点')
ax[0].legend(fontsize=8); ax[0].grid(alpha=.3,axis='y')
wd2=0.2
for i,(col,c,lab) in enumerate([('检出_单点',RD,'单点事件机'),('检出_并集',GY,'并集'),('检出_比值',BL,'比值判据'),('检出_P1与门',GO,'P1 与门')]):
    vals=[(0 if v is None else min(float(v),110)) for v in T[col]]
    ax[1].bar(x+(i-1.5)*wd2,vals,wd2,color=c,label=lab)
    for xi,v in enumerate(T[col]):
        if v is None: ax[1].text(xi+(i-1.5)*wd2,1.0,'未检出',ha='center',fontsize=5.5,color='white',rotation=90)
ax[1].set_xticks(x); ax[1].set_xticklabels(T.工况,fontsize=7.5,rotation=35,ha='right'); ax[1].set_ylim(0,114)
ax[1].set_ylabel('检出延迟（天，自第 20 天起算）'); ax[1].set_title('② 检出侧：与门最慢，并集 ≈ 单点')
ax[1].legend(fontsize=8); ax[1].grid(alpha=.3,axis='y')
plt.tight_layout(); plt.savefig(os.path.join(OUT,'alarm_strategy.png'),dpi=130)
NL=chr(10)+chr(10)
f=io.open(os.path.join(OUT,'alarm_strategy_report.md'),'w',encoding='utf-8'); W=f.write
W('# 组合报警策略评估（DSH，2026-09-20）'+NL)
W('三级上报定义：**P1-紧急** = 单点事件机报警 且 同刻（±1 天）滚动 5 天中位数已抬升到 1.15 倍工况健康基线；**P2-计划** = 单点报警但比值未抬升；**P3-观察** = 仅比值判据越限（1.3 倍基线）。'+NL)
W('标定全部只用健康运行第 30-45 天（无标签）；健康运行评估窗与退化检出评估窗同前（第 45-120 天）。'+NL)
W('## 1. 分策略汇总'+NL+SUM.to_markdown(index=False)+NL)
W('## 2. 分工况明细'+NL+T.to_markdown(index=False)+NL)
W('## 3. 结论'+NL)
W('**① 误报侧**：健康运行上报合计 —— 单点事件机 77 次、并集 77 次（比值判据 0 次，不新增误报）、P1 与门 26 次。与门能砍掉约 2/3 的误报，但**归不了零**：雨/暴雨三个工况的单点报警里有 24 次同时满足「比值已抬升 1.15 倍」（R1 10 次、R2 6 次、R3 8 次）。'+NL)
W('**② 检出侧**：并集与单点一致（12/12，延迟中位 20.3 天）；P1 与门只有 7/12 —— 四档慢漂移（-20%~-80%/100 天）**全部漏检**，因为它们的比值抬升来得太晚。'+NL)
W('**③ 口径警告**：单点事件机那 20.3 天的「检出延迟」在慢漂移场景里**不代表真实预警能力**——18.2 已证明冻结通道首报时刻由共同外部成分主导（所有幅值都报在同一时刻），18.3 又证明它随工况漂移。禁止把 20.3 天当作预警提前量对外宣传。'+NL)
W('**④ 推荐策略（上报与派工分开）**：**上报用并集**（不漏检，且比值判据不增加误报），**派工用与门分级**——P1（单点 ∧ 比值抬升）直接派工，P2（仅单点）先复核/排计划，P3（仅比值）进趋势观察。这样派工层面的噪音从 77 降到 26，而慢漂移仍由 P3 兜住。'+NL)
W('## 4. 局限'+NL)
W('- 三个倍数（1.15 / 1.3 / 5 天窗）未做敏感性扫描；每个工况只有一条 120 天轨迹。'+NL)
f.close(); print('report + figure written')
