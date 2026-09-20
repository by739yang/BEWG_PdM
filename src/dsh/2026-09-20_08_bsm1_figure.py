# -*- coding: utf-8 -*-
"""BSM1 数字孪生闭环 + 双基线参考域诊断：四合一图（DSH，2026-09-20）
① 退化过程与报警/失效时刻 ② 慢漂移方案对照 ③ RUL 方法对照 ④ 冻结参考域选择诊断"""
import pandas as pd, numpy as np, os, json, io
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif']=['Microsoft YaHei']; plt.rcParams['axes.unicode_minus']=False
OUT='results/2026-09-20/dsh'
fig,ax=plt.subplots(2,2,figsize=(13,9))
BL, RD, GO, GY = '#1f4e79', '#c00000', '#d99b1f', '#7f7f7f'

b=pd.read_csv(f'{OUT}/bsm1_120d_baseline.csv'); d=pd.read_csv(f'{OUT}/bsm1_120d_degraded.csv')
s=json.load(io.open(f'{OUT}/bsm1_120d_summary.json',encoding='utf-8'))
ax[0,0].plot(b.t_day,b.SO3,color=BL,lw=1.1,label='基准运行（无退化）')
ax[0,0].plot(d.t_day,d.SO3,color=RD,lw=1.1,label='退化运行（第 20 天起 KLa 衰减至 40%）')
ax[0,0].axhline(0.5,color=GY,ls='--',lw=1,label='危险阈值 SO3=0.5 mg/L')
ax[0,0].axvline(s['报警时刻'],color=GO,ls=':',lw=1.6)
ax[0,0].axvline(s['真值失效时刻'],color=RD,ls=':',lw=1.6)
ax[0,0].annotate('报警 %.2f 天'%s['报警时刻'],(s['报警时刻']+1,2.35),fontsize=8,color=GO)
ax[0,0].annotate('真值失效 %.2f 天'%s['真值失效时刻'],(s['真值失效时刻']+1,2.05),fontsize=8,color=RD)
ax[0,0].set_xlabel('时间（天）'); ax[0,0].set_ylabel('SO3（mg/L）'); ax[0,0].set_ylim(0,3.2)
ax[0,0].set_title('① BSM1 慢退化：检出（延迟 %.1f 天）与真值失效'%s['检出延迟'])
ax[0,0].legend(fontsize=8); ax[0,0].grid(alpha=.3)

sd=pd.read_csv(f'{OUT}/bsm1_slow_drift_detectors.csv')
lab=[x.replace('（','(').replace('）',')') for x in sd['方案']]
vals=[0 if pd.isna(v) else float(v) for v in sd['检出延迟']]
cols=[GY if pd.isna(v) else BL for v in sd['检出延迟']]
ax[0,1].bar(range(len(sd)),vals,color=cols)
for i,(v,raw) in enumerate(zip(vals,sd['检出延迟'])):
    if pd.isna(raw): ax[0,1].text(i,0.6,'完全漏检',ha='center',fontsize=9,color=RD,rotation=0)
    else: ax[0,1].text(i,v+0.4,'%.2f 天'%v,ha='center',fontsize=9)
ax[0,1].set_xticks(range(len(sd))); ax[0,1].set_xticklabels(lab,fontsize=8)
ax[0,1].set_ylabel('检出延迟（天，越低越好）'); ax[0,1].set_ylim(0,26)
ax[0,1].set_title('② 慢漂移检测方案对照（60 天场景，阈值=基线分位）')
ax[0,1].grid(alpha=.3,axis='y')
ax[0,1].text(0.02,0.93,'自适应基线：把漂移纳入新常态 → 永远不报警',transform=ax[0,1].transAxes,fontsize=8,color=RD)

rm=pd.read_csv(f'{OUT}/bsm1_rul_methods.csv').sort_values('绝对误差')
short=[x.replace('机理-溶解氧外推','机理-DO').replace('通用-健康指数线性外推','通用-健康指数') for x in rm['方法']]
cols=[RD if x.startswith('通用') else BL for x in rm['方法']]
ax[1,0].barh(range(len(rm)),rm['绝对误差'],color=cols)
ax[1,0].set_yticks(range(len(rm))); ax[1,0].set_yticklabels(short,fontsize=8)
for i,v in enumerate(rm['绝对误差']): ax[1,0].text(v+0.3,i,'%.2f 天'%v,va='center',fontsize=8)
ax[1,0].set_xlabel('RUL 绝对误差（天，越低越好）'); ax[1,0].set_xlim(0,24)
ax[1,0].set_title('③ RUL 方法对照（真值剩余 7.27 天）：机理指标 vs 通用健康指数')
ax[1,0].grid(alpha=.3,axis='x')

dr=pd.read_csv(f'{OUT}/dual_baseline_diag_reference.csv')
h=dr[dr.dataset.astype(str).str.contains('基准')]
ax[1,1].bar(range(len(h)),h.alarms,color=[RD if v>10 else BL for v in h.alarms])
for i,(v,tv) in enumerate(zip(h.alarms,h.thr)): ax[1,1].text(i,v+1.5,'%d 次\n(阈值 %.1f)'%(v,tv),ha='center',fontsize=8)
ax[1,1].set_xticks(range(len(h))); ax[1,1].set_xticklabels([x.replace('day ','第 ')+' 天' for x in h.ref_window],fontsize=8)
ax[1,1].set_ylabel('健康运行 120 天内的告警数'); ax[1,1].set_ylim(0,92)
ax[1,1].set_title('④ 冻结参考域必须取稳态段：参考窗选择 vs 误报')
ax[1,1].grid(alpha=.3,axis='y')
ax[1,1].text(0.02,0.92,'第 0-10 天是启动暂态 → 阈值被压到 4.4',transform=ax[1,1].transAxes,fontsize=8,color=RD)

plt.tight_layout(); plt.savefig(f'{OUT}/bsm1_4in1.png',dpi=130)
print('saved', f'{OUT}/bsm1_4in1.png', os.path.getsize(f'{OUT}/bsm1_4in1.png')//1024, 'KB')
