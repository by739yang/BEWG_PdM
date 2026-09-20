# -*- coding: utf-8 -*-
"""比值判据（滚动 N 天中位数 / 工况自身健康基线）跨工况检验（DSH，2026-09-20）
动机：雨/暴雨工况显示单点事件机的健康误报 18-26 次，而分布位置统计量在同一工况内可分离 3-5 倍。
做法：对 12 个已落盘的（健康, 退化）工况对，用健康运行第 30-45 天作冻结参考域，
      基线 base = 该健康运行参考窗内「滚动 5 天中位数」的中位数（模拟投运期标定，不使用任何标签），
      判据 = 滚动 5 天中位数 > k x base；评估窗 = 第 45-120 天（不含参考窗）。
输出：bsm1_ratio_rule.{csv,json,md,png}"""
import sys, os, io, json, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dual_baseline import frozen_z, topk_score, make_events, _scale_floor
OUT='results/2026-09-20/dsh'
CH=['SO3','SO4','SO5','SNH_eff','Ntot_eff','TSS_eff','sludge_h']
KS=[1.3,1.5,2.0,3.0]
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
def rollmed(v):
    return pd.Series(v).rolling(5*1440,min_periods=288).median().values
rows=[]
for tag,fb,fd in PAIRS:
    pb=os.path.join(OUT,fb); pd_=os.path.join(OUT,fd)
    if not (os.path.exists(pb) and os.path.exists(pd_)): print('跳过（缺文件）',tag); continue
    B=prep(pd.read_csv(pb)); D=prep(pd.read_csv(pd_))
    REF=B[(B.t_day>=30)&(B.t_day<45)]; FL=_scale_floor(B,CH)   # 刻度下限取健康运行（投运期常量），两轨共用
    def sc(X):
        return np.asarray(topk_score(frozen_z(X,CH,REF,state=hod(X),state_ref=hod(REF),floor=FL),3),dtype=float).ravel()
    sH=sc(B); sD=sc(D)
    ref_thr=float(np.quantile(np.asarray(topk_score(frozen_z(REF,CH,REF,state=hod(REF),state_ref=hod(REF),floor=FL),3),dtype=float).ravel(),0.999))
    evH=make_events(pd.Series(sH), ref_thr)      # 单点事件机（现行做法）在健康运行上的告警数
    rH=rollmed(sH); rD=rollmed(sD)
    dB=np.asarray(B.t_day); dD=np.asarray(D.t_day)
    mref=(dB>=30)&(dB<45)
    base=float(np.nanmedian(rH[mref]))
    ev=(dB>=45)&(dB<=120); evt=ev.sum()
    rec=dict(工况=tag, 基线base=round(base,3), 参考窗阈值=round(ref_thr,3), 单点事件机_健康误报=len(evH))
    for k in KS:
        thr=k*base
        rec['健康越限占比_k%.1f'%k]=round(float(np.mean(rH[ev]>thr)),3)
        sel=(dD>45.0)&(dD<=120.0)&np.isfinite(rD)&(rD>thr)   # 参考窗（第 30-45 天）结束后才开始评估，避免把投运暂态当检出
        rec['检出延迟_k%.1f'%k]=(round(float(dD[sel][0])-20.0,2) if sel.any() else None)
    rows.append(rec); print(json.dumps(rec,ensure_ascii=False), flush=True)
T=pd.DataFrame(rows)
T.to_csv(os.path.join(OUT,'bsm1_ratio_rule.csv'),index=False,encoding='utf-8-sig')
with open(os.path.join(OUT,'bsm1_ratio_rule.json'),'w',encoding='utf-8') as f:
    json.dump(rows,f,ensure_ascii=False,indent=2)
print(); print(T.to_string(index=False))

import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif']=['Microsoft YaHei']; plt.rcParams['axes.unicode_minus']=False
BL,RD,GY='#1f4e79','#c00000','#7f7f7f'
x=np.arange(len(T)); wd=0.2
fig,ax=plt.subplots(1,2,figsize=(15,5))
for i,k in enumerate(KS):
    ax[0].bar(x+(i-1.5)*wd, T['健康越限占比_k%.1f'%k], wd, label='k=%.1f'%k)
ax[0].set_xticks(x); ax[0].set_xticklabels(T.工况,fontsize=7.5,rotation=35,ha='right')
ax[0].set_ylabel('健康运行第 45-120 天越限时长占比'); ax[0].set_ylim(0,1.02)
ax[0].set_title('① 比值判据在健康运行上的误报（越低越好）'); ax[0].legend(fontsize=8,ncol=4); ax[0].grid(alpha=.3,axis='y')
wd2=0.25
for i,k in enumerate([1.3,1.5,2.0]):
    col='检出延迟_k%.1f'%k
    vals=[(0 if v is None else min(float(v),118)) for v in T[col]]
    ax[1].bar(x+(i-1)*wd2,vals,wd2,color=[BL,RD,'#7f7f7f'][i],label='k=%.1f'%k)
    for xi,v in enumerate(T[col]):
        if v is None: ax[1].text(xi+(i-1)*wd2,1.0,'未检出',ha='center',fontsize=6,color='white',rotation=90)
ax[1].set_xticks(x); ax[1].set_xticklabels(T.工况,fontsize=7.5,rotation=35,ha='right')
ax[1].set_ylabel('检出延迟（天，越大越晚）'); ax[1].set_ylim(0,122)
ax[1].set_title('② 检出延迟（自第 20 天起算；评估自第 45 天开始，故最小 25 天）'); ax[1].legend(fontsize=8); ax[1].grid(alpha=.3,axis='y')
plt.tight_layout(); plt.savefig(os.path.join(OUT,'bsm1_ratio_rule.png'),dpi=130)

NL=chr(10)+chr(10)
f=io.open(os.path.join(OUT,'bsm1_ratio_rule_report.md'),'w',encoding='utf-8'); W=f.write
W('# 比值判据跨工况检验（DSH，2026-09-20）'+NL)
W('判据：冻结分数（工况按一天中的时段分层）的**滚动 5 天中位数** 是否超过 **k 倍**「健康运行第 30-45 天标定出的基线」。'+NL)
W('标定只用健康运行、不使用任何故障标签；参考窗为第 30-45 天，**报警与误报的评估窗都取第 45-120 天**（避免把投运暂态当成检出——曾出现 k=1.3 时 8 个场景「检出延迟 0.01 天」的假象，已修正）。'+NL)
W('因此本文的「检出延迟」= 检出时刻 − 退化起始（第 20 天），最小可能值为 25 天（第 45 天才会开始评估）。'+NL)
W('## 1. 结果'+NL+T.to_markdown(index=False)+NL)
SUM=pd.DataFrame([dict(k=k, 健康越限合计=round(float(T['健康越限占比_k%.1f'%k].sum()),3),
    检出数=int(T['检出延迟_k%.1f'%k].notna().sum()),
    检出延迟中位=(round(float(T['检出延迟_k%.1f'%k].median()),1) if T['检出延迟_k%.1f'%k].notna().any() else None)) for k in KS])
W('## 2. 权衡汇总'+NL+SUM.to_markdown(index=False)+NL)
W('## 3. 结论'+NL)
W('**① 误报侧：比值判据在 12 个工况的健康运行上越限时长全部为 0.000**（k=1.3 起即成立），而同工况下现行单点事件机的健康误报为 0 / 4 / 3 / 0 / 0 / 0 / 0 / 0 / 0 / 26 / 18 / 26 次。误报侧是压倒性改善。'+NL)
W('**② 灵敏度侧：代价很大。** k=2.0 时 12 个退化场景只有 4 个在 120 天内检出，且延迟 68-98 天；k=1.3 时检出数上升但仍远晚于单点事件机（后者在相同场景为 0-37 天）。'+NL)
W('**③ 工程结论（诚实版）：比值判据不适合单独作为慢漂移的报警判据**，它更适合做「严重度分级 / 长期趋势监控」；即时报警仍要靠单点事件机，并接受其工况依赖的误报（第五条原则要求阈值按工况基线标定）。'+NL)
W('**④ 这也修正了 18.4 的乐观读法**：3-5 倍的「可分离」是同一工况内健康与退化的对比，但它不足以在 120 天内把慢漂移推到 k 倍基线的报警线之上。'+NL)
W('## 4. 局限'+NL)
W('- 基线取自各工况自己的健康运行参考窗（投运标定假设）；实际部署时该窗必须真的健康且已进稳态（第三条原则）。'+NL)
W('- 每个工况只有一条轨迹，未做随机重复。'+NL)
f.close(); print('report + figure written')
