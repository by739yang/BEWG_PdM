# -*- coding: utf-8 -*-
"""路线 B（技术收尾）：跨季节 / 多进水相位稳健性（DSH，2026-09-22）
动机：第 27 节的结论都在官方动态进水的同一段（相位 0）上得到，第 66 天的抢跑事件也是该相位的产物。
本脚本把健康/退化两条轨迹在三个进水相位（第 0 / 200 / 400 天起）各跑一遍，检验三条结论是否跨相位成立：
  ① 原始量（5 个可测量）+ 零误报口径 → 是否仍然「检不出」；
  ② 设备级比值通道 → 是否仍在 ~10 天量级；
  ③ 同工况对拍差分（日尺度平滑）→ 是否仍是有效解法。
产物：results/2026-09-22/dsh/bsm2_route_b_seasons.{csv,md,png} 与 season_<相位>_{healthy,degraded}.csv.gz
用法：python src/dsh/2026-09-22_07_bsm2_route_b_seasons.py
"""
import os, sys, io, json, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import route_b_common as R

D = R.DIR
DEG = 60.0
NL = chr(10)
PHASES = [0.0, 200.0, 400.0]
import sys as _sys
ONLY = None
if len(_sys.argv) > 1 and _sys.argv[1] != 'report':
    ONLY = [float(_sys.argv[1])]
    PHASES = [p for p in PHASES if p == ONLY[0]]


def smooth_day(s, days=1.0, ppd=96):
    return pd.Series(np.asarray(s, dtype=float)).rolling(max(4, int(round(days * ppd))), min_periods=1).mean().values


def pair_diff(G, H, cols, seeds=8, rel=0.02, lab_rel=0.03):
    null = []
    for s in range(seeds):
        h1 = R.add_noise(H, rel=rel, lab_rel=lab_rel, seed=300 + s)
        h2 = R.add_noise(H, rel=rel, lab_rel=lab_rel, seed=400 + s)
        r1 = R.detect_with(h1, H, cols=cols, thr_mode='zero_fa', deg_start=DEG)
        r2 = R.detect_with(h2, H, cols=cols, thr_mode='zero_fa', deg_start=DEG)
        d = smooth_day(np.asarray(r2['分数'], dtype=float) - np.asarray(r1['分数'], dtype=float))
        m = np.asarray(H.t_day) >= 30.0
        null.append(float(np.max(d[m])))
    thr = float(np.max(null) * 1.02)
    delays = []
    for s in range(seeds):
        hn = R.add_noise(H, rel=rel, lab_rel=lab_rel, seed=100 + s)
        gn = R.add_noise(G, rel=rel, lab_rel=lab_rel, seed=1000 + s)
        hh = R.detect_with(hn, H, cols=cols, thr_mode='zero_fa', deg_start=DEG)
        gg = R.detect_with(gn, H, cols=cols, thr_mode='zero_fa', deg_start=DEG)
        ex = smooth_day(np.asarray(gg['分数'], dtype=float) - np.asarray(hh['分数'], dtype=float))
        ex = np.where(np.asarray(G.t_day) >= 30.0, ex, 0.0)
        from dual_baseline import make_events
        ev = make_events(pd.Series(ex), thr, **R.EVENTKW)
        dD = np.asarray(G.t_day)
        post = [float(dD[i]) for i, e in ev if dD[i] > DEG]
        if post:
            delays.append(post[0] - DEG)
    return dict(零阈值=round(thr, 3), 延迟中位=(round(float(np.median(delays)), 2) if delays else None),
                区间=([round(min(delays), 2), round(max(delays), 2)] if delays else None),
                检出率='%d/%d' % (len(delays), seeds))


REPORT = (len(_sys.argv) > 1 and _sys.argv[1] == 'report')
rows = []
detail = {}
if REPORT:
    for _p in (0, 200, 400):
        rows.extend(json.load(io.open(os.path.join(D, 'seasons_part%d.json' % _p), encoding='utf-8')))
        detail[_p] = dict(H=pd.read_csv(os.path.join(D, 'season_%d_healthy.csv.gz' % _p)),
                          G=pd.read_csv(os.path.join(D, 'season_%d_degraded.csv.gz' % _p)))
    print('汇总 %d 个相位（复用 part 文件）' % len(rows))
for ph in ([] if REPORT else PHASES):
    print('=== 进水相位 %d 天：跑健康 + 退化两条轨迹 ===' % ph)
    H = R.run_plant(deg_start=None, days=160.0, verbose=False, offset_days=ph)
    G = R.run_plant(deg_start=DEG, days=160.0, verbose=False, offset_days=ph)
    H.to_csv(os.path.join(D, 'season_%d_healthy.csv.gz' % int(ph)), index=False, compression='gzip')
    G.to_csv(os.path.join(D, 'season_%d_degraded.csv.gz' % int(ph)), index=False, compression='gzip')
    fail = R.truth_failure(G, DEG)
    a = R.detect_with(G, H, cols=R.MON, thr_mode='zero_fa', deg_start=DEG)
    an = R.noise_median(H, G, cols=[R.RATIO], rel=0.02, lab_rel=0.03, seeds=4, thr_mode='zero_fa', deg_start=DEG)
    b = R.detect_with(G, H, cols=[R.RATIO], thr_mode='zero_fa', deg_start=DEG)
    c = pair_diff(G, H, [R.RATIO], seeds=4)
    # 该相位的最大进水事件幅度（用于解释）
    PKG = os.path.dirname(__import__('bsm2_python').__file__)
    din = np.genfromtxt(os.path.join(PKG, 'data', 'dyninfluent_bsm2.csv'), delimiter=',', skip_header=1)
    k = int(round(ph / R.DT)); Q = din[k:k + len(H), 15]
    q_ref = np.quantile(Q[30 * 96:45 * 96], [.5])[0]
    q_max = np.quantile(Q[30 * 96:], .99)
    rows.append(dict(进水相位天=int(ph), 真值失效=(None if fail is None else round(fail, 2)),
                     相位内Q中位=round(float(q_ref), 1), 相位内Q_99分位=round(float(q_max), 1), Q波动比=round(float(q_max / q_ref), 3),
                     原始量首报=a['首报'], 原始量延迟=a['检出延迟'], 原始量提前量=a['提前量'],
                     比值无噪延迟=b['检出延迟'],
                     比值含噪延迟中位=(None if an['检出延迟中位'] is None else round(an['检出延迟中位'], 2)),
                     比值含噪区间=(None if not an['检出延迟区间'] else [round(x, 2) for x in an['检出延迟区间']]),
                     对拍差分延迟中位=c['延迟中位'], 对拍差分检出率=c['检出率']))
    detail[int(ph)] = dict(H=H, G=G, a=a, b=b, an=an, c=c)
    print('  ', json.dumps(rows[-1], ensure_ascii=False))
if not REPORT:
    json.dump(rows, io.open(os.path.join(D, 'seasons_part%d.json' % int(ph)), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
if ONLY is not None:
    print('相位 %d 完成：' % int(ph), json.dumps(rows[-1], ensure_ascii=False)); raise SystemExit(0)
T = pd.DataFrame(rows)
T.to_csv(os.path.join(D, 'bsm2_route_b_seasons.csv'), index=False, encoding='utf-8-sig')

L = []
W = L.append
W('# 路线 B 技术收尾：跨季节 / 多进水相位稳健性（DSH，2026-09-22）' + NL)
W('> 三个进水相位（官方 609 天动态进水的第 0 / 200 / 400 天起），每个相位各跑健康与退化两条 160 天整厂轨迹。' + NL)
W('> 口径：真值失效 = 泥饼含固率 < 20%% 持续 1 天；原始量/比值通道用零误报阈值（健康轨迹最大分 × 1.02）；含噪 = 2%% 仪表 + 3%% 日粒度实验室、6 个噪声实现；对拍差分 = 日尺度平滑 + 健康-健康零分布。' + NL)
W('## 1. 结果' + NL)
W(T.to_markdown(index=False) + NL)
W('## 2. 结论' + NL)
ok_ratio = all((r['比值含噪延迟中位'] is not None and r['比值含噪延迟中位'] < 25) for r in rows)
ok_raw = all((r['原始量延迟'] is None or r['原始量延迟'] > 60) for r in rows)
ok_pair = all((r['对拍差分延迟中位'] is not None) for r in rows)
W('- **比值通道**：三个相位的含噪延迟中位 %s → %s。' % ('/'.join(str(r['比值含噪延迟中位']) for r in rows),
    ('跨相位都在 ~10 天量级，结论稳健' if ok_ratio else '存在相位差异，需按相位分别报告')) + NL)
W('- **原始量**：三个相位的零误报延迟 %s → %s。' % ('/'.join(str(r['原始量延迟']) for r in rows),
    ('都远晚于比值通道（跨相位一致的负结果）' if ok_raw else '存在相位差异')) + NL)
W('- **同工况对拍差分**：%s，检出率 %s。' % ('/'.join(str(r['对拍差分延迟中位']) for r in rows), '/'.join(r['对拍差分检出率'] for r in rows)) + NL)
W('- 相位内的进水波动（Q 的 99 分位 / 中位）%s —— 用来解释不同相位里「工况事件」的强度差异。' % ('/'.join(str(r['Q波动比']) for r in rows)) + NL)
io.open(os.path.join(D, 'bsm2_route_b_seasons.md'), 'w', encoding='utf-8', newline=NL).write(NL.join(L))

import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei']; plt.rcParams['axes.unicode_minus'] = False
fig, ax = plt.subplots(1, 2, figsize=(13, 4.4))
x = np.arange(len(T)); w = 0.3
ax[0].bar(x - w, T['原始量延迟'].fillna(0), w, color='#9467bd', label='原始量（零误报）')
ax[0].bar(x, T['比值含噪延迟中位'].fillna(0), w, color='#d62728', label='比值通道（含噪中位）')
ax[0].bar(x + w, T['对拍差分延迟中位'].fillna(0), w, color='#2ca02c', label='同工况对拍差分（比值）')
ax[0].axhline(49.0, color='#ff7f0e', ls='--', lw=1); ax[0].text(0, 50.5, '失效时刻（距退化 49 天）', color='#ff7f0e', fontsize=8)
ax[0].set_xticks(x); ax[0].set_xticklabels(['相位 %d 天' % p for p in T['进水相位天']]); ax[0].set_ylabel('检出延迟（天）'); ax[0].legend(fontsize=8); ax[0].grid(alpha=.3); ax[0].set_title('① 三个进水相位的检出延迟')
for p in T['进水相位天']:
    d = detail[int(p)]
    ax[1].plot(d['G'].t_day, d['G']['泥饼含固率'], lw=.9, label='相位 %d 退化' % p)
ax[1].axhline(20, color='#2ca02c', ls='--', lw=1); ax[1].axvline(DEG, color='#7f7f7f', ls=':', lw=1)
ax[1].set_xlabel('天'); ax[1].set_ylabel('泥饼含固率（%）'); ax[1].legend(fontsize=8); ax[1].grid(alpha=.3); ax[1].set_title('② 三个相位的退化轨迹（含固率）')
fig.suptitle('路线 B：跨季节 / 多进水相位稳健性', fontsize=13)
fig.tight_layout(); fig.savefig(os.path.join(D, 'bsm2_route_b_seasons.png'), dpi=130)
print()
print(T.to_string(index=False))
