# -*- coding: utf-8 -*-
"""材料图表定稿（DSH，2026-09-18）：四合一figure
① SKAB DET 曲线 ② 维护策略成本对比 ③ 成本敏感性网格 ④ RUL 预测散点"""
import pandas as pd, numpy as np, os
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif']=['Microsoft YaHei']; plt.rcParams['axes.unicode_minus']=False
D='results'; OUT=f'{D}/2026-09-18/dsh'
fig,ax=plt.subplots(2,2,figsize=(13,9))
# ① DET 曲线
det=pd.read_csv(f'{D}/2026-09-16/dsh/det_curve_skab.csv')
colors={'F0':'#7f7f7f','F2':'#1f4e79','F3':'#c00000'}
for m,g in det.groupby('method'):
    g=g.sort_values('fp_per_hour')
    ax[0,0].plot(g.fp_per_hour,g.recall,'o-',color=colors.get(m),label=m,linewidth=1.6,markersize=5)
ax[0,0].set_xscale('log'); ax[0,0].set_xlabel('独立误报事件 / 健康小时'); ax[0,0].set_ylabel('事件召回率')
ax[0,0].set_title('① SKAB：误报预算 vs 召回（双实现零偏差）'); ax[0,0].grid(alpha=.3); ax[0,0].legend()
# ② 策略成本
pol=pd.read_csv(f'{OUT}/decision_policy_v6.csv')
sel=pol[pol.参数.isin(['—']) | pol.参数.str.contains('100 周期|提前期 60|P\(RUL<40\)>=0.2|P\(RUL<60\)>=0.5')]
names=sel.策略.str.replace('② ','').str.replace('③ ','').str.replace('④ ','')+'\n'+sel.参数
ax[0,1].bar(range(len(sel)),sel.单台成本,color=['#999999']+['#1f4e79']*(len(sel)-1))
ax[0,1].set_xticks(range(len(sel))); ax[0,1].set_xticklabels(names,fontsize=7,rotation=15)
ax[0,1].set_ylabel('单台成本（占位参数，元）'); ax[0,1].set_title('② 维护策略成本对比（越低越好）'); ax[0,1].grid(alpha=.3,axis='y')
# ③ 敏感性网格
G=pd.read_csv(f'{OUT}/decision_sensitivity_v6.csv')
piv=G.pivot_table(index='失效代价',columns='更换代价',values='AI相对固定节省')
im=ax[1,0].imshow(piv.values,cmap='RdYlGn',vmin=-0.25,vmax=0.3)
ax[1,0].set_xticks(range(len(piv.columns))); ax[1,0].set_xticklabels(piv.columns)
ax[1,0].set_yticks(range(len(piv.index))); ax[1,0].set_yticklabels(piv.index)
for i in range(piv.shape[0]):
    for j in range(piv.shape[1]):
        v=piv.values[i,j]
        ax[1,0].text(j,i,('%.0f%%'%(v*100)) if not np.isnan(v) else '—',ha='center',va='center',fontsize=8,
                     color='black' if v>-0.15 else 'white')
ax[1,0].set_xlabel('计划更换代价（元/次）'); ax[1,0].set_ylabel('非计划失效代价（元/次）')
ax[1,0].set_title('③ AI 相对固定周期的节省（绿=AI 占优）')
plt.colorbar(im,ax=ax[1,0],fraction=0.046)
# ④ RUL 散点
P=pd.read_csv(f'{D}/2026-09-17/dsh/rul_baseline_per_unit.csv')
pc=[c for c in P.columns if c.startswith('pred_') and 'trend' not in c][0]
ax[1,1].scatter(P.true_RUL,P[pc],s=18,alpha=.7,color='#1f4e79')
lim=[0,max(P.true_RUL.max(),P[pc].max())*1.05]
ax[1,1].plot(lim,lim,'k--',linewidth=1)
ax[1,1].set_xlabel('真值 RUL（周期）'); ax[1,1].set_ylabel('预测 RUL（周期）')
ax[1,1].set_title('④ C-MAPSS RUL 预测（RMSE 15.27 / PHM08 434，待独立复核）'); ax[1,1].grid(alpha=.3)
plt.suptitle('澜脉 · 关键结果四图（2026-09-18）',fontsize=13)
plt.tight_layout(); plt.savefig(f'{OUT}/figures_4in1.png',dpi=150)
print('已生成', f'{OUT}/figures_4in1.png')
for nm,df in [('DET',det),('策略',sel),('敏感性',G),('RUL',P)]: print(nm,'行数',len(df))
