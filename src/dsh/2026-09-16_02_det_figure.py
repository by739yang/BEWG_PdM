# -*- coding: utf-8 -*-
"""P1：SKAB DET 曲线定稿（池化 + 与 Codex 对照 + 出图）"""
import pandas as pd, numpy as np, io, os
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif']=['Microsoft YaHei']; plt.rcParams['axes.unicode_minus']=False
R='.'; OUT='results/2026-09-16/dsh'
d=pd.read_csv('results/2026-09-15/dsh/protocol_v14_det_counts.csv')
pool=d.groupby(['method','quantile']).agg(events=('events','sum'),hits=('hits','sum'),
      fp_events=('fp_events','sum'),healthy_hours=('healthy_hours','sum'),
      alarm_healthy=('alarm_healthy','sum'),delay=('delay','median')).reset_index()
pool['recall']=pool.hits/pool.events
pool['fp_per_hour']=pool.fp_events/pool.healthy_hours
pool['tia']=pool.alarm_healthy/(pool.healthy_hours*3600)
pool.to_csv(os.path.join(OUT,'det_curve_skab.csv'),index=False,encoding='utf-8-sig')

c=pd.read_csv('results/2026-09-15/codex/protocol_v11_det.csv')
m=pool.merge(c,left_on=['method','quantile'],right_on=['method','q'],suffixes=('_ds','_cx'))
m['d_recall']=(m.recall-m.event_recall).abs()
m['d_fp']=(m.fp_per_hour-m.false_alarm_events_per_healthy_hour).abs()
m['d_tia']=(m.tia-m.tia_h).abs()
print('与 Codex DET 最大偏差：召回 %.4f  误报率 %.4f  TIA %.4f' % (m.d_recall.max(), m.d_fp.max(), m.d_tia.max()))

fig,ax=plt.subplots(1,2,figsize=(13,5))
colors={'F0':'#7f7f7f','F2':'#1f4e79','F3':'#c00000'}
for meth,g in pool.groupby('method'):
    g=g.sort_values('fp_per_hour')
    ax[0].plot(g.fp_per_hour,g.recall,'o-',color=colors[meth],label=meth,linewidth=1.6,markersize=5)
    for _,r in g.iterrows():
        ax[0].annotate(f"{r['quantile']:g}",(r.fp_per_hour,r.recall),textcoords='offset points',xytext=(4,4),fontsize=7)
ax[0].set_xscale('log'); ax[0].set_xlabel('独立误报事件 / 健康小时（对数轴）'); ax[0].set_ylabel('事件召回率')
ax[0].set_title('SKAB DET 曲线（每条线四个阈值点 0.90/0.99/0.995/0.999）'); ax[0].grid(alpha=.3); ax[0].legend()
for meth,g in pool.groupby('method'):
    g=g.sort_values('fp_per_hour')
    ax[1].plot(g.fp_per_hour,g.tia,'o-',color=colors[meth],label=meth,linewidth=1.6,markersize=5)
ax[1].set_xscale('log'); ax[1].set_xlabel('独立误报事件 / 健康小时（对数轴）'); ax[1].set_ylabel('TIA-H（健康时间处于报警的比例）')
ax[1].set_title('代价面：误报率 vs 健康时间被报警占用'); ax[1].grid(alpha=.3); ax[1].legend()
plt.tight_layout(); plt.savefig(os.path.join(OUT,'det_curve_skab.png'),dpi=140)

lines=['# P1：SKAB DET 曲线（定稿）','','命令：python src/dsh/2026-09-16_02_det_figure.py',
 '数据：results/2026-09-15/dsh/protocol_v14_det_counts.csv（PROTOCOL_v1.4 的四个阈值点扫描）',
 '与 Codex 对照：最大偏差 召回 %.4f、误报率 %.4f、TIA %.4f' % (m.d_recall.max(),m.d_fp.max(),m.d_tia.max()),'',
 '## 池化结果','',pool[['method','quantile','hits','events','recall','fp_events','fp_per_hour','tia','delay']].round(3).to_markdown(index=False),'',
 '## 业务口径读数（重要）','',
 '把误报换算成运维能理解的频次（健康小时 = 每台设备运行 1 小时）：','',
 '| 方法 | 最保守的工作点 | 误报频次 | 事件召回 | 判断 |','|---|---|---|---|---|']
for meth,g in pool.groupby('method'):
    r=g.loc[g.fp_per_hour.idxmin()]
    lines.append('| %s | 阈值 %.3g | 每 %.1f 小时 1 次 | %.1f%% | %s |' % (
        meth, r['quantile'], 1/max(r.fp_per_hour,1e-9), r.recall*100,
        '可用' if r.fp_per_hour<=0.125 and r.recall>=0.5 else '不达运维可接受水平'))
lines+=['','结论：**目前没有任何方法能在"每 8 小时不超过 1 次误报"的预算下保住有意义的召回**。',
 '最保守的工作点是 F0 的 0.999 阈值：每 2.3 小时误报 1 次，召回只有 9.1%；F2 在 0.999 阈值下召回 42.4%，代价是每 0.2 小时就误报 1 次。',
 '这条结论不是坏消息，它正好是我们接下来要攻的靶子，也是商业计划书里最该讲清楚的技术门槛。']
io.open(os.path.join(OUT,'det_curve_skab.md'),'w',encoding='utf-8').write('\n'.join(lines))
print('DET 定稿完成')
