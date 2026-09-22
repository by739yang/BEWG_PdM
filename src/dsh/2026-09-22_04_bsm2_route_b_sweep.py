# -*- coding: utf-8 -*-
"""路线 B：幅值 / 速率扫描（DSH，2026-09-22）
退化均起始第 60 天：速率轴 = 终值固定 18%、斜坡 30/60/120 天；幅值轴 = 斜坡固定 60 天、终值 22/20/18%。
每个场景跑一遍官方整厂并**落盘轨迹**（便于后续不重跑就换判据），然后按两种通道集评价：
  A 5 个原始可测量（零误报口径）
  B 设备级比值通道「干固体/湿泥饼量」（零误报口径，2% 仪表 + 3% 日粒度实验室噪声，8 个噪声实现取中位）
产物：results/2026-09-22/dsh/bsm2_route_b_sweep.{csv,md,png} 与 bsm2_route_b_sweep_<i>_<场景>.csv.gz
用法：python src/dsh/2026-09-22_04_bsm2_route_b_sweep.py
"""
import os, sys, io, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import route_b_common as R

D = R.DIR
DEG = 60.0
DAYS = 160.0
SC = [('速率 30 天', 30.0, 18.0), ('速率 60 天', 60.0, 18.0), ('速率 120 天', 120.0, 18.0),
      ('幅值 22%', 60.0, 22.0), ('幅值 20%', 60.0, 20.0), ('幅值 18%', 60.0, 18.0)]
SLUG = {'速率 30 天': 'rate30d', '速率 60 天': 'rate60d', '速率 120 天': 'rate120d',
        '幅值 22%': 'amp22', '幅值 20%': 'amp20', '幅值 18%': 'amp18'}   # ASCII 文件名（Codex 批次 5：中文名有跨平台/归档风险）

H = R.load('healthy')
base_flow = float(H[H.t_day >= 150]['泥饼流量'].mean())
rows = []
for k, (tag, ramp, ts1) in enumerate(SC):
    fp = os.path.join(D, 'bsm2_route_b_sweep_%d_%s.csv.gz' % (k, SLUG[tag]))
    if os.path.exists(fp):
        print('[%s] 复用已落盘轨迹 %s' % (tag, os.path.basename(fp)))
        G = pd.read_csv(fp)
    else:
        print('[%s] 斜坡 %s 天、终值 %s%% ...' % (tag, ramp, ts1))
        G = R.run_plant(deg_start=DEG, ramp=ramp, ts1=ts1, days=DAYS, verbose=False)
        G.to_csv(fp, index=False, compression='gzip')
    fail = R.truth_failure(G, DEG)
    a = R.detect_with(G, H, cols=R.MON, thr_mode='zero_fa', deg_start=DEG)
    n = R.noise_median(H, G, cols=[R.RATIO], rel=0.02, lab_rel=0.03, seeds=8, thr_mode='zero_fa', deg_start=DEG)
    b = R.detect_with(G, H, cols=[R.RATIO], thr_mode='zero_fa', deg_start=DEG)
    rows.append(dict(场景=tag, 斜坡天=ramp, 终值含固率=round(float(G['泥饼含固率'].iloc[-1]), 2),
                     降解速率pp每天=round((28.0 - ts1) / ramp, 4),
                     真值失效=(None if fail is None else round(fail, 2)),
                     原始量首报=a['首报'], 原始量检出延迟=a['检出延迟'], 原始量提前量=a['提前量'],
                     比值无噪首报=b['首报'], 比值无噪延迟=b['检出延迟'],
                     比值含噪延迟中位=(None if n['检出延迟中位'] is None else round(n['检出延迟中位'], 2)),
                     比值含噪延迟区间=(None if not n['检出延迟区间'] else [round(x, 2) for x in n['检出延迟区间']]),
                     比值含噪提前量中位=(None if n['提前量中位'] is None else round(n['提前量中位'], 2)),
                     健康误报出现次_比值=n['健康误报出现次数'],
                     RUL误差中位_10天窗=(None if n['RUL误差_1天窗中位'] is None else None),
                     末期泥饼流量=round(float(G[G.t_day >= 150]['泥饼流量'].mean()), 3),
                     泥饼流量相对健康=round(float(G[G.t_day >= 150]['泥饼流量'].mean()) / base_flow - 1.0, 4)))
T = pd.DataFrame(rows)
T.to_csv(os.path.join(D, 'bsm2_route_b_sweep.csv'), index=False, encoding='utf-8-sig')

NL = chr(10)
L = ['# 路线 B：幅值 / 速率扫描（DSH，2026-09-22）' + NL,
     '退化均起始第 60 天；每个场景跑一遍官方整厂（160 天、约 0.4 秒/模拟天、零 NaN），轨迹已落盘（ASCII 文件名 bsm2_route_b_sweep_<i>_<slug>.csv.gz）。' + NL,
     '注意：速率轴的 18% 是**目标终值**，120 天斜坡在 160 天仿真内只走到约 19.67%，未达到 18%。' + NL,
     '通道集 A = 5 个原始可测量（泥饼流量、滤液量、滤液 TSS、干固体产率、浓缩池底 TSS）；通道集 B = 设备级比值通道「干固体产率 / 湿泥饼量」。' + NL,
     '阈值口径均为**零误报**（阈值 = 健康轨迹分数最大值 × 1.02）；比值通道另加 2%% 仪表 + 3%% 日粒度实验室噪声、8 个噪声实现取中位。' + NL,
     '## 1. 结果' + NL, T.to_markdown(index=False) + NL, '## 2. 结论' + NL]
L.append('- **原始量通道（A）**：%s。' % ('；'.join('%s 延迟 %s 天（真值失效 %s 天）' % (r['场景'], r['原始量检出延迟'], r['真值失效']) for r in rows)) + NL)
L.append('- **比值通道（B）**：无噪延迟 %s 天（理想上界）；含噪延迟中位 %s 天。' % (
    '/'.join(str(r['比值无噪延迟']) for r in rows), '/'.join(str(r['比值含噪延迟中位']) for r in rows)) + NL)
L.append('- **湿泥饼产量**：末期相对健康 %s；理论值 +55.6%%（= 28/18−1，仅在终值 18%% 时成立）。' % (
    '；'.join('%s %+.2f%%' % (r['场景'], r['泥饼流量相对健康'] * 100) for r in rows)) + NL)
L.append('- **诚实标注**：模型里浓缩/脱水为**理想单元**（无堵塞与动力学），含噪延迟中位仍偏乐观；对外只引用含噪中位与区间。' + NL)
io.open(os.path.join(D, 'bsm2_route_b_sweep.md'), 'w', encoding='utf-8', newline=NL).write(NL.join(L))

import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei']; plt.rcParams['axes.unicode_minus'] = False
fig, ax = plt.subplots(1, 3, figsize=(14.5, 4.2))
x = np.arange(len(T))
ax[0].bar(x - .2, T['原始量检出延迟'].fillna(0), .4, color='#9467bd', label='A 原始量（零误报）')
ax[0].bar(x + .2, T['比值含噪延迟中位'].fillna(0), .4, color='#d62728', label='B 比值通道（含噪中位）')
ax[0].set_xticks(x); ax[0].set_xticklabels(T['场景'], rotation=25, ha='right', fontsize=8)
ax[0].set_ylabel('检出延迟（天）'); ax[0].legend(fontsize=8); ax[0].grid(alpha=.3); ax[0].set_title('① 检出延迟')
ax[1].bar(x, T['比值含噪提前量中位'].fillna(0), .5, color='#2ca02c')
ax[1].set_xticks(x); ax[1].set_xticklabels(T['场景'], rotation=25, ha='right', fontsize=8)
ax[1].set_ylabel('失效前提前量（天）'); ax[1].grid(alpha=.3); ax[1].set_title('② 提前量（比值通道，含噪）')
ax[2].bar(x, T['泥饼流量相对健康'] * 100, .5, color='#1f77b4')
ax[2].axhline(55.6, color='#7f7f7f', ls='--', lw=1); ax[2].text(0, 57, '理论 +55.6%（28/18−1）', fontsize=8, color='#7f7f7f')
ax[2].set_xticks(x); ax[2].set_xticklabels(T['场景'], rotation=25, ha='right', fontsize=8)
ax[2].set_ylabel('%'); ax[2].grid(alpha=.3); ax[2].set_title('③ 湿泥饼产量变化')
fig.suptitle('路线 B：BSM2 整厂脱水机退化的幅值/速率扫描', fontsize=13)
fig.tight_layout(); fig.savefig(os.path.join(D, 'bsm2_route_b_sweep.png'), dpi=130)
print(T.to_string(index=False))
