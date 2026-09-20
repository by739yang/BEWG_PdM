# -*- coding: utf-8 -*-
"""BSM1 退化幅值-斜率扫描分析（DSH，2026-09-20）
输入：results/2026-09-20/dsh/bsm1_amp_sweep.csv + 各场景仿真 CSV
输出：bsm1_amp_sweep_stats.csv/json、bsm1_sweep_3in1.png、bsm1_amp_sweep_report.md
结论要点：冻结通道首报时刻与幅值无关（共同外部成分主导）；"0 误报"是刀锋边缘；
         单调随严重度变化的是越限样本数/最长连续长度与分布位置（滚动中位数）。"""
import sys, os, json, io, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dual_baseline import frozen_z, topk_score, _scale_floor
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif']=['Microsoft YaHei']; plt.rcParams['axes.unicode_minus']=False
OUT='results/2026-09-20/dsh'
CH=['SO3','SO4','SO5','SNH_eff','Ntot_eff','TSS_eff','sludge_h']
ENTER=4
SCEN=[('健康',1.00,'bsm1_120d_baseline.csv'),('80%/100d',0.80,'bsm1_sweep_keep80_ramp100.csv'),
      ('60%/100d',0.60,'bsm1_sweep_keep60_ramp100.csv'),('40%/100d',0.40,'bsm1_120d_degraded.csv'),
      ('20%/100d',0.20,'bsm1_sweep_keep20_ramp100.csv'),('40%/40d',0.40,'bsm1_sweep_keep40_ramp040.csv'),
      ('20%/40d',0.20,'bsm1_sweep_keep20_ramp040.csv')]
S=pd.read_csv(f'{OUT}/bsm1_amp_sweep.csv')
rate={1.00:0.0,0.80:0.2,0.60:0.4,0.40:0.6,0.20:0.8}
def prep(df):
    x=df.copy(); x.index=pd.to_datetime(x.t_day*86400,unit='s'); return x
B=prep(pd.read_csv(f'{OUT}/bsm1_120d_baseline.csv')); REF=B[(B.t_day>=30)&(B.t_day<45)]
hod=lambda X: ((X.t_day*24)%24).astype(int).values
def runs(mask):
    out=[]; c=0
    for v in mask:
        if v: c+=1
        elif c: out.append(c); c=0
    if c: out.append(c)
    return out
rows=[]; series={}
for tag,keep,f in SCEN:
    X=prep(pd.read_csv(os.path.join(OUT,f)))
    FL=_scale_floor(X,CH)
    ZR=frozen_z(REF,CH,REF,state=hod(REF),state_ref=hod(REF),floor=FL)
    thr=float(pd.Series(np.asarray(topk_score(ZR,3),dtype=float).ravel()).quantile(0.999))
    s=np.asarray(topk_score(frozen_z(X,CH,REF,state=hod(X),state_ref=hod(REF),floor=FL),3),dtype=float).ravel()
    m=s>thr; r=runs(m); d=np.asarray(X.t_day)
    rm=pd.Series(s).rolling(5*1440,min_periods=288).median().values
    first=None; c=0
    for i,v in enumerate(m):
        c=c+1 if v else 0
        if c>=ENTER: first=float(d[i-ENTER+1]); break
    j110=int(np.searchsorted(d,110.0))
    late=float(np.nanmedian(rm[max(0,j110-720):j110+720]))
    rows.append(dict(场景=tag, 最终KLa比例=keep, 健康运行=bool(keep>=1.0), 冻结阈值=round(thr,3),
                     越限样本数=int(m.sum()), 最长连续越限=int(max(r) if r else 0),
                     满足持续性=bool(first is not None), 冻结首报天=(None if first is None else round(first,2)),
                     第110天滚动5天中位数=round(late,2),
                     SO3均值末期=round(float(X[X.t_day>100].SO3.mean()),3)))
    series[tag]=(d,rm)
ST=pd.DataFrame(rows); ST.to_csv(f'{OUT}/bsm1_amp_sweep_stats.csv',index=False,encoding='utf-8-sig')
print(ST.to_string(index=False))

fig,ax=plt.subplots(1,3,figsize=(16,4.6))
BL,RD,GO,GY='#1f4e79','#c00000','#d99b1f','#7f7f7f'
S['衰减速率每百天']=S['斜坡天'].apply(lambda r: 0) if False else S.apply(lambda x:(1-x['最终KLa比例'])/x['斜坡天']*100,axis=1)
x=S['衰减速率每百天'].values
ax[0].plot(x,S['检出延迟天'],'o-',color=BL,label='检出延迟（天）')
ax[0].plot(x,S['提前量SO3_0_5'],'s--',color=RD,label='失效前提前量（SO3<0.5）')
ax[0].plot(x,S['提前量SO3_1_0'],'^:',color=GO,label='出水劣化前提前量（SO3<1.0）')
ax[0].axhline(0,color=GY,lw=.8)
ax[0].set_xlabel('退化速率（%KLa/百天）'); ax[0].set_ylabel('天'); ax[0].set_title('① 检出延迟与预警提前量 vs 退化速率')
ax[0].legend(fontsize=8); ax[0].grid(alpha=.3)
ax[1].bar(range(len(ST)),ST.越限样本数,color=[GY]+[BL]*(len(ST)-1))
for i,(n,l) in enumerate(zip(ST.越限样本数,ST.最长连续越限)):
    ax[1].text(i,n+0.8,'%d 点\n最长 %d'%(n,l),ha='center',fontsize=8)
ax[1].axhline(ENTER,color=RD,ls='--',lw=1.2); ax[1].text(len(ST)-0.6,ENTER+1.2,'事件机要求连续 %d 点'%ENTER,fontsize=8,color=RD,ha='right')
ax[1].set_xticks(range(len(ST))); ax[1].set_xticklabels(ST.场景,fontsize=8,rotation=20)
ax[1].set_ylabel('越限样本数'); ax[1].set_ylim(0,62); ax[1].set_title('② 刀锋边缘：健康 6 点/最长 3 点 vs 最轻退化 8 点/最长 4 点')
ax[1].grid(alpha=.3,axis='y')
ax[2].bar(range(len(ST)),ST['第110天滚动5天中位数'],color=[GY]+[RD if v>3.3 else BL for v in ST['第110天滚动5天中位数']])
for i,v in enumerate(ST['第110天滚动5天中位数']): ax[2].text(i,v+0.06,'%.2f'%v,ha='center',fontsize=8)
ax[2].set_xticks(range(len(ST))); ax[2].set_xticklabels(ST.场景,fontsize=8,rotation=20)
ax[2].set_ylabel('冻结分数（滚动 5 天中位数）'); ax[2].set_ylim(0,5.0)
ax[2].set_title('③ 随严重度单调变化的是分布位置（对数已对齐同一参考域）')
ax[2].grid(alpha=.3,axis='y')
plt.tight_layout(); plt.savefig(f'{OUT}/bsm1_sweep_3in1.png',dpi=130)
print('saved', f'{OUT}/bsm1_sweep_3in1.png')

NL=chr(10)+chr(10); f=io.open(f'{OUT}/bsm1_amp_sweep_report.md','w',encoding='utf-8'); W=f.write
W('# BSM1 退化幅值-斜率扫描报告（DSH，2026-09-20）'+NL)
W('数据：自建 BSM1 仿真（IWA 标准模型，15 分钟步长，120 天，第 20 天起 KLa 线性衰减到设定比例）。'+NL)
W('检测配置：双基线模块 src/dsh/dual_baseline.py；冻结参考域取健康运行的稳态段（第 30-45 天）；事件机要求连续 4 点越限。'+NL)
W('## 1. 场景与检出（自适应 / 冻结 两条通道）'+NL+S.to_markdown(index=False)+NL)
W('**冻结通道首报时刻在所有退化场景下都是第 40.3 天**（模块事件机 40.28 / 本文长度扫描 40.25，差 3 个采样；次报 94.4 天），与退化幅值、斜率无关 -> 冻结通道能判"有异常"，不携带严重度信息。'+NL)
W('## 2. 刀锋边缘（必须写进材料的事实）'+NL+ST.to_markdown(index=False)+NL)
W('健康运行 120 天里越限样本 6 个、最长连续 3 个，恰好小于事件机要求的 4 个 -> 0 误报；最轻微退化（-20%/100 天）越限 8 个、最长 4 个 -> 恰好 1 次告警。'+NL)
W('**"0 误报"与"误报"之间只差一个采样点。**该配置不能作为稳健性结论对外宣称。'+NL)
W('## 3. 随严重度单调变化的是什么'+NL)
W('① 越限样本数 / 最长连续越限长度（健康 6/3；-20%/慢 8/4；-40%/慢 9/8；-60%/慢 16/9；-40%/快 23/15；-80%/快 52/16）；'+NL)
W('② 分布位置：冻结分数滚动 5 天中位数（健康 %.2f；-20%%/慢 %.2f；-40%%/慢 %.2f；-80%%/慢 %.2f；-40%%/快 %.2f；-80%%/快 %.2f）。'+NL)
W('## 4. 预警提前量（对运维真正有意义的量）'+NL)
W('失效（SO3 持续 1 天 < 0.5 mg/L）前提前量：'+'、'.join('%s %s 天'%(a,b) for a,b in zip(S['最终KLa比例']*100, S['提前量SO3_0_5']))+'。'+NL)
W('出水劣化（SO3 持续 1 天 < 1.0 mg/L）前提前量：'+'、'.join('%s %s 天'%(a,b) for a,b in zip(S['最终KLa比例']*100, S['提前量SO3_1_0']))+'。'+NL)
W('**对 -40%/100 天及更快的退化，报警不早于出水指标劣化**（提前量为负），只有失效前数天的提前量；退化越慢，失效前提前量越大，但检出延迟基本固定在 20 天左右（0.2-0.6%/天）或 7-14 天（0.8-2.0%/天）。'+NL)
W('## 5. 第四条设计原则'+NL)
W('**慢漂移的严重度必须用分布位置统计量（滚动中位数/分位数偏移）或机理指标表达；单点越限的时刻不含严重度信息。**'+NL)
W('## 6. 局限'+NL)
W('- 冻结通道阈值受被监测数据全局尺度（scale floor）影响，跨场景不完全可比：越严重的场景 floor 越大、阈值越低，这会放大越限样本数差异。'+NL)
W('- 每个场景只跑了一条 120 天轨迹，未做多随机种子/多工况重复。'+NL)
f.close(); print('report written')
