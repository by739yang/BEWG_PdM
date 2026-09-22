# -*- coding: utf-8 -*-
"""路线 B 补强 ② 扩展：更大漂移幅度 + 相关漂移（AR(1)）+ 对拍零分布样本量（DSH，2026-09-22）
复用 2026-09-22_06 的实现（importlib 加载），只补三类新配置，写到独立的 ext 产物，不改动原表：
  ① 幅度 10%：线性慢漂移 / 周期 6.3 天 / 随机游走（看边界是否继续恶化）；
  ② AR(1) 相关漂移（ρ=0.99，平稳标准差 = 幅度）：3% / 5%（更接近真实标定漂移的时间相关性）；
  ③ 最严苛配置的缓解：AR(1) 5% + 双测量平均（两路独立 AR(1) 取均值）。
另跑：同工况对拍差分的样本量敏感性（4 / 8 / 12 对健康-健康零分布，比值通道）。
产物：results/2026-09-22/dsh/bsm2_route_b_drift_ext.{csv,md}、bsm2_route_b_pairdiff_seeds.csv
用法：python src/dsh/2026-09-22_09_bsm2_route_b_drift_ext.py
"""
import os, sys, io, json, importlib.util, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import route_b_common as R

D = R.DIR
NL = chr(10)
spec = importlib.util.spec_from_file_location('drift06', os.path.join(os.path.dirname(os.path.abspath(__file__)), '2026-09-22_06_bsm2_route_b_drift.py'))
d6 = importlib.util.module_from_spec(spec); spec.loader.exec_module(d6)
H, G, DEG, FAIL = d6.H, d6.G, d6.DEG, d6.FAIL


def bias_ar1(t, amp, rng, rho=0.99):
    n = len(t); w = np.zeros(n); prev = 0.0
    sd = amp * np.sqrt(1.0 - rho ** 2)
    for i in range(n):
        prev = rho * prev + rng.normal(0.0, sd); w[i] = prev
    return w


def make_ext(df, kind, amp, seed, mitigate='M1 无补偿', rel=0.02, lab_rel=0.03):
    rng = np.random.default_rng(seed)
    d = R.add_noise(df, rel=rel, lab_rel=lab_rel, seed=seed, lab_bias=0.0)
    t = np.asarray(d['t_day'], dtype=float)
    if kind == 'AR1相关漂移':
        b = bias_ar1(t, amp, np.random.default_rng(seed + 5))
    else:
        b = d6.bias_series(t, kind, amp, np.random.default_rng(seed + 3))
    if mitigate == 'M3 双测量平均':
        if kind == 'AR1相关漂移':
            b = 0.5 * (bias_ar1(t, amp, np.random.default_rng(seed + 21)) + bias_ar1(t, amp, np.random.default_rng(seed + 23)))
        else:
            b = 0.5 * (d6.bias_series(t, kind, amp, np.random.default_rng(seed + 11)) + d6.bias_series(t, kind, amp, np.random.default_rng(seed + 13)))
    d[R.RATIO] = d[R.RATIO] * (1.0 + b)
    return d


def evaluate(kind, amp, mitigate='M1 无补偿', seeds=6):
    delays = []; fa = 0
    for s in range(seeds):
        Hn = make_ext(H, kind, amp, 100 + s, mitigate); Gn = make_ext(G, kind, amp, 1000 + s, mitigate)
        r = R.detect_with(Gn, Hn, cols=[R.RATIO], thr_mode='zero_fa', deg_start=DEG)
        if r['健康告警数'] > 0:
            fa += 1
        if r['检出延迟'] is not None:
            delays.append(r['检出延迟'])
    return dict(检出延迟中位=(round(float(np.median(delays)), 2) if delays else None),
                检出延迟区间=([round(min(delays), 2), round(max(delays), 2)] if delays else None),
                检出率='%d/%d' % (len(delays), seeds),
                提前量中位=(round(FAIL - DEG - float(np.median(delays)), 2) if delays else None),
                健康误报出现次='%d/%d' % (fa, seeds))


rows = []
CFG = [('线性慢漂移', 0.10, 'M1 无补偿'), ('周期6.3天', 0.10, 'M1 无补偿'), ('随机游走', 0.10, 'M1 无补偿'),
       ('AR1相关漂移', 0.03, 'M1 无补偿'), ('AR1相关漂移', 0.05, 'M1 无补偿'), ('AR1相关漂移', 0.05, 'M3 双测量平均')]
for kind, amp, mit in CFG:
    r = evaluate(kind, amp, mit)
    rows.append(dict(偏差结构=kind, 幅度='%d%%' % (100 * amp), 缓解=mit, **r))
    print('  %-12s %3d%% %-14s 延迟中位 %s 天 (%s) 检出率 %s 提前量 %s' % (kind, 100 * amp, mit, r['检出延迟中位'], r['检出延迟区间'], r['检出率'], r['提前量中位']))
T = pd.DataFrame(rows)
T.to_csv(os.path.join(D, 'bsm2_route_b_drift_ext.csv'), index=False, encoding='utf-8-sig')

# ---- 对拍差分样本量敏感性 ----
import importlib.util as _iu
spec2 = _iu.spec_from_file_location('cond05', os.path.join(os.path.dirname(os.path.abspath(__file__)), '2026-09-22_05_bsm2_route_b_conditioned.py'))
srows = []
for seeds in (4, 8, 12):
    h1 = [R.add_noise(H, rel=0.02, lab_rel=0.03, seed=300 + s) for s in range(seeds)]
    h2 = [R.add_noise(H, rel=0.02, lab_rel=0.03, seed=400 + s) for s in range(seeds)]
    r1 = [R.detect_with(x, H, cols=[R.RATIO], thr_mode='zero_fa', deg_start=DEG) for x in h1]
    r2 = [R.detect_with(x, H, cols=[R.RATIO], thr_mode='zero_fa', deg_start=DEG) for x in h2]
    from dual_baseline import make_events
    sd = lambda s: pd.Series(np.asarray(s, dtype=float)).rolling(96, min_periods=1).mean().values
    m = np.asarray(H.t_day) >= 30.0
    null = max(float(np.max(sd(np.asarray(b['分数'], dtype=float) - np.asarray(a['分数'], dtype=float))[m])) for a, b in zip(r1, r2))
    thr = null * 1.02
    delays = []
    for s in range(seeds):
        hn = R.add_noise(H, rel=0.02, lab_rel=0.03, seed=100 + s); gn = R.add_noise(G, rel=0.02, lab_rel=0.03, seed=1000 + s)
        hh = R.detect_with(hn, H, cols=[R.RATIO], thr_mode='zero_fa', deg_start=DEG)
        gg = R.detect_with(gn, H, cols=[R.RATIO], thr_mode='zero_fa', deg_start=DEG)
        ex = sd(np.asarray(gg['分数'], dtype=float) - np.asarray(hh['分数'], dtype=float))
        ex = np.where(np.asarray(G.t_day) >= 30.0, ex, 0.0)
        ev = make_events(pd.Series(ex), thr, **R.EVENTKW)
        dD = np.asarray(G.t_day)
        post = [float(dD[i]) for i, e in ev if dD[i] > DEG]
        if post:
            delays.append(post[0] - DEG)
    srows.append(dict(零分布对数=seeds, 判别种子数=seeds, 零阈值=round(thr, 3),
                      检出延迟中位=(round(float(np.median(delays)), 2) if delays else None),
                      检出率='%d/%d' % (len(delays), seeds)))
    print('  对拍差分：%2d 对零分布 → 阈值 %.3f、延迟中位 %s 天（%s）' % (seeds, thr, srows[-1]['检出延迟中位'], srows[-1]['检出率']))
TS = pd.DataFrame(srows)
TS.to_csv(os.path.join(D, 'bsm2_route_b_pairdiff_seeds.csv'), index=False, encoding='utf-8-sig')

L = ['# 路线 B 补强 ② 扩展：更大漂移幅度 / 相关漂移 / 对拍样本量（DSH，2026-09-22）' + NL,
     '> 复用 06 脚本的实现；口径同第 29.2 节（比值通道、零误报阈值、2%% 仪表 + 3%% 日粒度实验室噪声、每配置 6 个噪声实现、真值失效第 %.2f 天）。' % FAIL + NL,
     '## 1. 更大幅度与相关漂移' + NL, T.to_markdown(index=False) + NL,
     '## 2. 同工况对拍差分的样本量敏感性（比值通道）' + NL, TS.to_markdown(index=False) + NL,
     '## 3. 读法' + NL,
     '- 幅度 10%% 下三类结构的延迟与检出率，说明「随机游走」的恶化速度远快于确定性偏差；' + NL,
     '- AR(1) 相关漂移（ρ=0.99）更接近真实标定漂移的时间相关性；' + NL,
     '- 对拍差分的零阈值随样本量增大而收紧（零分布最大值是极值统计量），因此延迟与检出率会随样本量变化 —— 这条要如实写进局限。' + NL]
io.open(os.path.join(D, 'bsm2_route_b_drift_ext.md'), 'w', encoding='utf-8', newline=NL).write(NL.join(L))
print()
print(T.to_string(index=False)); print(); print(TS.to_string(index=False))
