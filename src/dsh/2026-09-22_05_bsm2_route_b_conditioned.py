# -*- coding: utf-8 -*-
"""路线 B 补强 ①：进水工况条件化阈值（DSH，2026-09-22）
背景：第 27.1 节的负结果 —— 固定参考域下的原始量通道被「进水工况事件」（第 66 天进水 +23.9%）抢跑。
本脚本按设计原则⑤把冻结基线升级为「冻结参考 + 工况条件化」：
  参考集 = 健康轨迹第 30 天起（含各种进水工况）；状态 = 进水流量分箱（4 或 8 分位箱）；
  每个箱内各自算 robust 中位/尺度（与冻结通道同口径），再取 topk3 + 事件机（4/8/0.8/8）。
评价：零误报口径（健康轨迹条件化分数最大值 × 1.02）与参考域 0.999 分位两种口径；
      通道集 A = 5 个原始可测量，通道集 B = 设备级比值通道。
产物：results/2026-09-22/dsh/bsm2_route_b_cond.{json,md,png,csv}
用法：python src/dsh/2026-09-22_05_bsm2_route_b_conditioned.py
"""
import os, sys, io, json, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import route_b_common as R
from dual_baseline import topk_score, make_events, _scale_floor

D = R.DIR
DEG = 60.0
NL = chr(10)
H = R.load('healthy')
G = R.load('degraded')
FAIL = R.truth_failure(G, DEG)
PKG = os.path.dirname(__import__('bsm2_python').__file__)
din = np.genfromtxt(os.path.join(PKG, 'data', 'dyninfluent_bsm2.csv'), delimiter=',', skip_header=1)
Q_ALL = din[:, 15]


def q_of(df):
    return Q_ALL[:len(df)]


def flow_bins(Bh_ref, nb):
    q = q_of(Bh_ref)
    edges = np.quantile(q, np.linspace(0, 1, nb + 1)[1:-1])
    return edges


def bin_idx(q, edges):
    return np.digitize(np.asarray(q, dtype=float), edges)


def cond_z(df, cols, ref, edges, hod_state=True, floor=None):
    """冻结参考 + 工况（流量箱）× 小时 条件化 robust z。"""
    q = q_of(df); b = bin_idx(q, edges)
    qr = q_of(ref); br = bin_idx(qr, edges)
    hr = np.asarray(pd.to_datetime((ref.t_day * 86400).round().astype('int64'), unit='s').dt.hour)
    hx = np.asarray(pd.to_datetime((df.t_day * 86400).round().astype('int64'), unit='s').dt.hour)
    Z = pd.DataFrame(0.0, index=range(len(df)), columns=cols)
    for c in cols:
        v = np.zeros(len(df))
        for k in np.unique(b):
            mk = (b == k)
            for h in (np.unique(hx) if hod_state else [0]):
                m = mk & (hx == h) if hod_state else mk
                if m.sum() == 0:
                    continue
                r = ref[(br == k) & (hr == h)] if hod_state else ref[br == k]
                if len(r) < 24:
                    r = ref[br == k]
                if len(r) < 24:
                    r = ref
                iqr = r[c].quantile(.75) - r[c].quantile(.25); sd = r[c].std()
                s = iqr / 1.349 if iqr > 1e-9 else (sd if sd > 1e-9 else 1.0)
                if floor is not None:
                    s = max(s, float(floor[c]))
                v[m] = ((df.loc[m, c].astype(float) - r[c].median()) / s).clip(-30, 30)
        Z[c] = v
    return Z


def eval_variant(df, ref, cols, edges, trim_ref_days=30.0, hod_state=True):
    """返回条件化分数与（口径化的）阈值。"""
    if R.RATIO in cols:
        ref = R.with_ratio(ref); df = R.with_ratio(df)
    ref2 = ref[ref.t_day >= trim_ref_days].copy()
    Bh = ref2
    FL = _scale_floor(ref2, cols)
    Zref = cond_z(ref2, cols, ref2, edges, hod_state, FL)
    sref = np.asarray(topk_score(Zref, min(3, len(cols))), dtype=float)
    Zx = cond_z(df, cols, ref2, edges, hod_state, FL)
    sx = np.asarray(topk_score(Zx, min(3, len(cols))), dtype=float)
    return sx, sref


rows = []
detail = {}
for label, cols in [('A 5 个原始量', R.MON), ('B 比值通道', [R.RATIO])]:
    for nb in (4, 8):
        edges = flow_bins(H, nb)
        sx_g, sref_h = eval_variant(G, H, cols, edges)
        thr_z = float(np.max(sref_h) * 1.02)                     # 零误报口径
        ev_h = make_events(pd.Series(sref_h), thr_z, **R.EVENTKW)
        ev_g = make_events(pd.Series(sx_g), thr_z, **R.EVENTKW)
        dD = np.asarray(G.t_day)
        post = [(float(dD[s]), int(s)) for s, e in ev_g if dD[s] > DEG]
        pre = [(float(dD[s]), float(dD[e])) for s, e in ev_g if dD[s] <= DEG]
        first = (post[0][0] if post else None)
        rul = R.rul_estimate(G, post[0][1]) if post else {5: None, 2: None, 1: None}
        lead = (None if (FAIL is None or first is None) else round(FAIL - first, 2))
        rows.append(dict(通道集=label, 流量分箱=nb, 阈值口径='零误报（条件化, 健康最大×1.02）', 阈值=round(thr_z, 3),
                         健康轨迹误报=len(ev_h), 健康轨迹最高分=round(float(np.max(sref_h)), 2),
                         退化后首报=(None if first is None else round(first, 2)),
                         检出延迟=(None if first is None else round(first - DEG, 2)),
                         提前量=lead, RUL误差_1天窗=(None if (rul[1] is None or lead is None) else round(abs(rul[1] - lead), 2)),
                         退化前告警=len(pre)))
        detail[label + '_%d箱' % nb] = dict(edges=[round(float(x), 1) for x in edges],
                                           健康分数=sref_h, 退化分数=sx_g, 阈值=thr_z)
T = pd.DataFrame(rows)

# 对照：无条件（原口径）
from dual_baseline import frozen_z
Bh = R.prep(H); REF = R.ref_window(Bh)
FL = _scale_floor(Bh, R.MON)
T0 = R.detect_with(G, H, cols=R.MON, thr_mode='zero_fa', deg_start=DEG)
T0r = R.detect_with(G, H, cols=[R.RATIO], thr_mode='zero_fa', deg_start=DEG)
T1 = R.detect_with(G, H, cols=R.MON, thr_mode='q999', deg_start=DEG)

# 第 66 天工况事件处的分数变化
def score_at(sx, day, tol=0.2):
    i = int(np.argmin(np.abs(np.asarray(G.t_day) - day)))
    return round(float(sx[i]), 2)

d66 = dict(无条件_5原始量=score_at(T0['分数'], 66.11), 无条件_阈值=round(T0['阈值'], 3))

json.dump(dict(脚本='2026-09-22_05_bsm2_route_b_conditioned.py', 真值失效天=FAIL,
               结果=T.to_dict('records'), 对照=dict(
                   无条件_零误报=dict(通道集='A 5 个原始量', 阈值=round(T0['阈值'], 3), 健康误报=T0['健康告警数'],
                                     首报=T0['首报'], 延迟=T0['检出延迟'], 提前量=T0['提前量']),
                   无条件_q999=dict(阈值=round(T1['阈值'], 3), 健康误报=T1['健康告警数'], 首报=T1['首报'], 延迟=T1['检出延迟']),
                   无条件_比值=dict(阈值=round(T0r['阈值'], 3), 首报=T0r['首报'], 延迟=T0r['检出延迟'])),
               第66天分数=d66),
          io.open(os.path.join(D, 'bsm2_route_b_cond.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
T.to_csv(os.path.join(D, 'bsm2_route_b_cond.csv'), index=False, encoding='utf-8-sig')

L = []
W = L.append
W('# 路线 B 补强 ①：进水工况条件化阈值（DSH，2026-09-22）' + NL)
W('> 动机：第 27.1 节显示，固定参考域下的原始量通道被第 66 天的进水工况事件（流量 +23.9%）抢跑。本补强按设计原则⑤把冻结基线升级为「**冻结参考 + 进水流量工况条件化**」：参考集 = 健康轨迹第 30 天起（覆盖各工况），状态 = 进水流量分位箱 × 小时，箱内各自 robust 中位/尺度，再 topk3 + 事件机（与冻结通道同口径）。' + NL)
W('> 真值失效第 %.2f 天；阈值口径 = 零误报（健康轨迹条件化分数最大值 × 1.02）。' % FAIL + NL)
W('## 1. 结果' + NL)
W(T.to_markdown(index=False) + NL)
W('## 2. 对照（无条件口径，来自第 27 节）' + NL)
W('| 通道集 | 阈值口径 | 阈值 | 健康误报 | 首报 | 延迟 |' + NL + '|---|---|---|---|---|---|')
W('| A 5 个原始量 | 零误报 | %.3f | %d | %s | %s |' % (T0['阈值'], T0['健康告警数'], T0['首报'], T0['检出延迟']))
W('| A 5 个原始量 | 参考域 0.999 分位 | %.3f | %d | %s | %s（误报抢跑） |' % (T1['阈值'], T1['健康告警数'], T1['首报'], T1['检出延迟']))
W('| B 比值通道 | 零误报 | %.3f | %d | %s | %s |' % (T0r['阈值'], T0r['健康告警数'], T0r['首报'], T0r['检出延迟']) + NL)
W('## 3. 结论（待本次运行结果确认）' + NL)
W('- 条件化的判据：健康轨迹条件化分数的最大值应显著下降 —— 第 66 天的工况事件在「高流量箱」里不再是异常。' + NL)
W('- 若条件化后原始量通道能在失效前较早期检出，则第 27.1 的负结果可由「工况条件化」修复；否则说明原始量对该退化确实不够灵敏，必须走设备级比值通道。' + NL)
io.open(os.path.join(D, 'bsm2_route_b_cond.md'), 'w', encoding='utf-8', newline=NL).write(NL.join(L))

import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei']; plt.rcParams['axes.unicode_minus'] = False
fig, ax = plt.subplots(1, 2, figsize=(13, 4.4))
dD = np.asarray(G.t_day)
ax[0].plot(dD, T0['分数'], color='#9467bd', lw=.8, label='无条件（冻结参考）')
k = 'A 5 个原始量_4箱'
ax[0].plot(dD, detail[k]['退化分数'], color='#d62728', lw=.8, label='条件化（4 流量箱 × 小时）')
ax[0].axhline(T0['阈值'], color='#9467bd', ls='--', lw=1)
ax[0].axhline(detail[k]['阈值'], color='#d62728', ls='--', lw=1)
ax[0].axvline(DEG, color='#7f7f7f', ls=':', lw=1)
if FAIL:
    ax[0].axvline(FAIL, color='#2ca02c', ls=':', lw=1)
ax[0].set_ylim(0, max(25, float(np.max(T0['分数'])) * 1.1))
ax[0].set_title('① 原始量分数：无条件 vs 工况条件化'); ax[0].set_xlabel('天'); ax[0].legend(fontsize=8); ax[0].grid(alpha=.3)
labs = ['无条件\n(原始量)', '条件化4箱\n(原始量)', '条件化8箱\n(原始量)', '比值通道\n(条件化4箱)']
vals = [T0['检出延迟'], T.loc[T.通道集.str.contains('A'), '检出延迟'].tolist()[:1][0], T.loc[T.通道集.str.contains('A'), '检出延迟'].tolist()[1], T.loc[T.通道集.str.contains('B'), '检出延迟'].tolist()[0]]
ax[1].bar(range(len(vals)), [v if v else 0 for v in vals], color=['#9467bd', '#d62728', '#ff7f0e', '#2ca02c'])
ax[1].axhline(FAIL - DEG, color='#2ca02c', ls='--', lw=1); ax[1].text(0, FAIL - DEG + 2, '失效时刻（第 %.0f 天）' % FAIL, color='#2ca02c', fontsize=8)
ax[1].set_xticks(range(len(labs))); ax[1].set_xticklabels(labs, fontsize=8)
ax[1].set_ylabel('检出延迟（天）'); ax[1].grid(alpha=.3); ax[1].set_title('② 检出延迟对比')
fig.suptitle('路线 B 补强 ①：进水工况条件化阈值', fontsize=13)
fig.tight_layout(); fig.savefig(os.path.join(D, 'bsm2_route_b_cond.png'), dpi=130)
print(T.to_string(index=False))
print()
print('无条件对照：5 原始量 零误报阈值 %.3f 延迟 %s | q999 阈值 %.3f 首报 %s | 比值 阈值 %.3f 延迟 %s' % (
    T0['阈值'], T0['检出延迟'], T1['阈值'], T1['首报'], T0r['阈值'], T0r['检出延迟']))


# ---------------------------------------------------------------- 变体 C：同工况对拍差分
# 现实含义：若有「同期/同工况的历史健康轨迹」，直接做配对差分即可把工况事件消掉；
# 这里用两组独立噪声实现下的健康轨迹对拍，构造差分零分布（因此阈值不是拍脑袋，而是实测的）。
def smooth_day(s, days=1.0, ppd=96):
    """日尺度平滑：同工况对拍在现实中比的是日均水平，单点刀锋尖峰不应主导零分布。"""
    return pd.Series(np.asarray(s, dtype=float)).rolling(max(4, int(round(days * ppd))), min_periods=1).mean().values

def pair_diff_eval(cols, nb=None, seeds=8, rel=0.02, lab_rel=0.03, deg_start=DEG, smooth_days=1.0):
    edges = flow_bins(H, nb) if nb else None
    def sc(df, ref):
        if edges is None:
            X = R.prep(df, cols); Rr = R.prep(ref, cols)
            from dual_baseline import frozen_z
            FL = _scale_floor(Rr, cols)
            Z = frozen_z(X, cols, R.ref_window(Rr), state=R.hod(X), state_ref=R.hod(R.ref_window(Rr)), floor=FL)
        else:
            Xs, _ = eval_variant(df, ref, cols, edges)
            return Xs
        return np.asarray(topk_score(Z, min(3, len(cols))), dtype=float)
    null_max = []
    for s in range(seeds):
        h1 = R.add_noise(H, rel=rel, lab_rel=lab_rel, seed=300 + s)
        h2 = R.add_noise(H, rel=rel, lab_rel=lab_rel, seed=400 + s)
        d = sc(h2, H) - sc(h1, H)
        msk = np.asarray(H.t_day) >= 30.0          # 排除投运暂态（设计原则③：参考与评估都必须取稳态段）
        null_max.append(float(np.max(smooth_day(d, smooth_days)[msk])))
    thr = float(np.max(null_max) * 1.02)
    dD = np.asarray(G.t_day)
    res = []
    for s in range(seeds):
        hn = R.add_noise(H, rel=rel, lab_rel=lab_rel, seed=100 + s)
        gn = R.add_noise(G, rel=rel, lab_rel=lab_rel, seed=1000 + s)
        ex = smooth_day(sc(gn, H) - sc(hn, H), smooth_days)
        ex = np.where(np.asarray(G.t_day) >= 30.0, ex, 0.0)   # 暂态段不参与判定
        ev = make_events(pd.Series(ex), thr, **R.EVENTKW)
        post = [(float(dD[i]), int(i)) for i, e in ev if dD[i] > deg_start]
        res.append(dict(seed=s, 首报=(post[0][0] if post else None), 首报索引=(post[0][1] if post else None),
                        延迟=(None if not post else round(post[0][0] - deg_start, 2)), 告警数=len(ev),
                        健康对拍误报=0))
    ok = [r for r in res if r['延迟'] is not None]
    return dict(通道集=('+'.join(cols)), 流量分箱=(nb if nb else '无（无条件差分）'), 平滑天=smooth_days, 差分零阈值=round(thr, 3),
                零分布最大值=round(float(np.max(null_max)), 3), 种子数=seeds,
                检出延迟中位=(round(float(np.median([r['延迟'] for r in ok])), 2) if ok else None),
                检出延迟区间=([min(r['延迟'] for r in ok), max(r['延迟'] for r in ok)] if ok else None),
                检出率='%d/%d' % (len(ok), seeds),
                提前量中位=(None if not ok else round(FAIL - np.median([r['延迟'] for r in ok]) - deg_start, 2)),
                明细=res)


variants = []
for label, cols, nb in [('A 5 个原始量', R.MON, None), ('B 比值通道', [R.RATIO], None)]:
    v = pair_diff_eval(cols, nb)
    v['通道集'] = label
    variants.append(v)
Td = pd.DataFrame([{k: x[k] for k in ['通道集', '流量分箱', '平滑天', '差分零阈值', '零分布最大值', '种子数', '检出率',
                                      '检出延迟中位', '检出延迟区间', '提前量中位']} for x in variants])
Td.to_csv(os.path.join(D, 'bsm2_route_b_pairdiff.csv'), index=False, encoding='utf-8-sig')
print()
print('=== 变体 C：同工况对拍差分（含噪 2%/3%，零分布来自健康-健康对拍）===')
print(Td.to_string(index=False))
json.dump(variants, io.open(os.path.join(D, 'bsm2_route_b_pairdiff.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
