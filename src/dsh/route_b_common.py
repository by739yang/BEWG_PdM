# -*- coding: utf-8 -*-
"""路线 B 公共层（DSH，2026-09-22）：通道定义、参考域阈值、真值失效、机理 RUL。
被 2026-09-22_03（单轨迹分析）与 04（幅值/速率扫描）共用，保证两条脚本口径完全一致。
"""
import os, sys, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dual_baseline import frozen_z, adaptive_z, topk_score, make_events, _scale_floor

DIR = 'results/2026-09-22/dsh'
MON = ['泥饼流量', '滤液量', '滤液TSS', '干固体产率', '浓缩池底TSS']
FAILLINE = 20.0
EVENTKW = dict(enter=4, exit_=8, ratio=0.8, cooldown=8)


def load(tag):
    return pd.read_csv(os.path.join(DIR, 'bsm2_route_b_%s.csv.gz' % tag))


def prep(df, cols=None):
    c = list(cols if cols is not None else MON)
    if RATIO in c and RATIO not in df.columns:
        df = with_ratio(df)
    Y = df[c].copy()
    Y.index = pd.to_datetime((df.t_day * 86400).round().astype('int64'), unit='s')
    return Y


def hod(X):
    return np.asarray(X.index.hour).astype(int)


def ref_window(Bh, d0=30.0, d1=45.0):
    return Bh[(Bh.index >= Bh.index[0] + pd.Timedelta(days=d0)) & (Bh.index < Bh.index[0] + pd.Timedelta(days=d1))]


def frozen_score(X, REF, FL, cols=None):
    c = cols if cols is not None else MON
    return np.asarray(topk_score(frozen_z(X, c, REF, state=hod(X), state_ref=hod(REF), floor=FL), 3), dtype=float).ravel()


def adaptive_score(X, cols=None):
    c = cols if cols is not None else MON
    return np.asarray(topk_score(adaptive_z(X, c, win_days=2.0, state=hod(X)), 3), dtype=float).ravel()


def thresholds(H, d0=30.0, d1=45.0):
    Bh = prep(H)
    REF = ref_window(Bh, d0, d1)
    FL = _scale_floor(Bh, MON)
    thr = float(np.quantile(frozen_score(REF, REF, FL), 0.999))
    msk = (np.asarray(H.t_day) >= d0) & (np.asarray(H.t_day) < d1)
    thra = float(np.quantile(adaptive_score(Bh)[msk], 0.999))
    return Bh, REF, FL, thr, thra


def truth_failure(G, deg_start, run_days=1.0):
    dD = np.asarray(G['t_day'])
    v = (G['泥饼含固率'] < FAILLINE).rolling(int(round(96 * run_days)), min_periods=24).mean()
    idx = [i for i in range(len(v)) if v.iloc[i] >= 1.0 and dD[i] > deg_start]
    return (float(dD[idx[0]]) if idx else None)


def first_alarm(G, score, thr, deg_start):
    dD = np.asarray(G['t_day'])
    ev = make_events(pd.Series(score), thr, **EVENTKW)
    pre = [(float(dD[s]), float(dD[e])) for s, e in ev if dD[s] <= deg_start]
    post = [(float(dD[s]), int(s)) for s, e in ev if dD[s] > deg_start]
    return ev, pre, post


def rul_estimate(G, i0, target=FAILLINE, windows=(5, 2, 1), pts_per_day=96):
    y_all = np.asarray(G['泥饼含固率'].values, dtype=float)
    out = {}
    for wd in windows:
        lo = max(0, i0 - wd * pts_per_day)
        y = y_all[lo:i0 + 1]
        b_, a_ = np.polyfit(np.arange(len(y), dtype=float), y, 1)
        out[wd] = (None if b_ >= -1e-9 else float(max((target - a_) / b_ - (len(y) - 1), 0.0) / pts_per_day))
    return out


# ---------------------------------------------------------------- 整厂仿真
import time, io, json
import bsm2_python as _b
from bsm2_python.bsm2_base import BSM2Base
import bsm2_python.bsm2.init.reginit_bsm2 as _reginit

PKG = os.path.dirname(_b.__file__)
DT = 1.0 / 96.0
TS0, TS1, RAMP = 28.0, 18.0, 60.0
SI, SS, XI, XS, XBH, XBA, XP, SO, SNO, SNH, SND, XND, SALK, TSS, Q, TEMP = range(16)
COLS = ['t_day', '目标含固率', '泥饼含固率', '泥饼流量', '干固体产率', '滤液量', '滤液TSS',
        '消化罐进泥TSS', '消化罐进泥流量', '沼气CH4', '沼气流', '出水氨氮', '出水TSS',
        '回流污泥TSS', '浓缩池底TSS', '曝气能耗', '泵能耗', '搅拌能耗']


def _influent(n):
    d = np.genfromtxt(os.path.join(PKG, 'data', 'dyninfluent_bsm2.csv'), delimiter=',', skip_header=1)
    while len(d) < n:
        d = np.vstack([d, d])
    return d[:n]


def run_plant(deg_start=None, ramp=RAMP, ts0=TS0, ts1=TS1, days=160.0, verbose=True):
    """官方整厂 BSM2Base + 脱水机 dw_par[0] 退化注入（deg_start=None 表示健康轨迹）。"""
    n = int(round(days / DT)) + 1
    arr = _influent(n)
    data = np.column_stack([np.arange(len(arr)) * DT, arr[:, 1:]])
    t0 = time.time()
    p = BSM2Base(data_in=data, timestep=DT, endtime=days)
    m = len(p.timesteps)   # 包的 simtime 比 timesteps 多一格，按后者循环
    rec = []
    for i in range(m):
        t = float(p.simtime[i])
        v = ts0 if deg_start is None else ts0 + (ts1 - ts0) * min(1.0, max(0.0, (t - deg_start) / ramp))
        p.dewatering.dw_par[0] = v
        p.step(i)
        cake = np.asarray(p.ydw_s_all[i]); feed = np.asarray(p.yi_out2_all[i])
        _, rej = p.dewatering.output(feed)
        ch4, h2, co2, qgas = p.performance.gas_production(np.asarray(p.yd_out_all[i]), _reginit.T_OP)
        eff = np.asarray(p.y_eff_all[i]); was = np.asarray(p.ys_was_all[i]); thi = np.asarray(p.yt_uf_all[i])
        rec.append((t, v, cake[TSS] / 10000.0, cake[Q], cake[TSS] * cake[Q] / 1000.0, rej[Q], rej[TSS],
                    feed[TSS], feed[Q], ch4, qgas, eff[SNH], eff[TSS], was[TSS], thi[TSS],
                    float(p.ae), float(p.pe), float(p.me)))
        if verbose and (i + 1) % max(1, m // 4) == 0:
            print('    步 %d/%d  %.0f s  含固率 %.2f%%  泥饼流量 %.2f' % (i + 1, m, time.time() - t0, rec[-1][2], rec[-1][3]))
    df = pd.DataFrame(rec, columns=COLS).replace([np.inf, -np.inf], np.nan)
    df.attrs['用时秒'] = round(time.time() - t0, 1)
    df.attrs['步数'] = m
    return df


# ------------------------------------------------- 机理性比值通道 与 仪表噪声
# 工程含义：脱水后泥饼的固体含量 = 干固体产率 / 湿泥饼量（两个都可测：皮带秤/流量计 + 实验室干固体）。
# 该比值天然抵消"污泥产量随进水季节漂移"，因此是整厂尺度上稳健的退化指示量。
MEAS = ['泥饼流量', '滤液量', '滤液TSS', '干固体产率', '浓缩池底TSS']
RATIO = '含固率代理'
MON_R = MEAS + [RATIO]


def with_ratio(df):
    d = df.copy()
    d[RATIO] = d['干固体产率'] / d['泥饼流量'] / 10.0   # kg/d / (m3/d) = kg/m3 -> % 需 /10
    return d


def add_noise(df, rel=0.02, seed=0, lab_rel=0.03, lab_per_day=True):
    """仪表噪声：流量类连续白噪声（相对 rel）；泥饼含固率为实验室日报（日粒度，相对 lab_rel）。
    干固体产率按 含固率 × 湿泥饼量 重算，因此比值通道只继承实验室噪声、免疫流量计噪声。"""
    rng = np.random.default_rng(seed)
    d = df.copy()
    n = len(d)
    d['泥饼流量'] = d['泥饼流量'] * (1.0 + rng.normal(0, rel, n))
    d['滤液量'] = d['滤液量'] * (1.0 + rng.normal(0, rel, n))
    d['滤液TSS'] = d['滤液TSS'] * (1.0 + rng.normal(0, rel, n))
    d['浓缩池底TSS'] = d['浓缩池底TSS'] * (1.0 + rng.normal(0, rel, n))
    if lab_per_day:
        day = np.floor(np.asarray(d['t_day']))        # 每天一个实验室样品
        ulab = rng.normal(0, lab_rel, int(day[-1]) + 2)
        e = ulab[day.astype(int)]
    else:
        e = rng.normal(0, lab_rel, n)
    d['泥饼含固率'] = d['泥饼含固率'] * (1.0 + e)
    d['干固体产率'] = d['泥饼含固率'] * d['泥饼流量'] * 10.0
    d[RATIO] = d['干固体产率'] / d['泥饼流量'] / 10.0
    return d


def detect(df, H_ref, cols=None, deg_start=60.0):
    """在给定通道集上做 冻结 + 自适应 双通道检测，返回首报与告警。"""
    c = cols if cols is not None else MON
    Bh, REF, FL, thr, thra = thresholds_on(H_ref, cols=c)
    X = prep(df, c)
    sc = frozen_score(X, REF, FL, c)
    ev, pre, post = first_alarm(df, sc, thr, deg_start)
    sca = adaptive_score(X, c)
    eva, _, posta = first_alarm(df, sca, thra, deg_start)
    return dict(阈值=float(thr), 阈值自适应=float(thra), 首报=(None if not post else float(post[0][0])),
                首报索引=(None if not post else int(post[0][1])), 告警数=len(ev), 退化前告警=len(pre),
                自适应告警数=len(eva), 自适应首报=(None if not posta else float(posta[0][0])), 分数=sc)


def thresholds_on(H, cols=None, d0=30.0, d1=45.0):
    c = cols if cols is not None else MON
    Bh = prep(H, c)
    REF = ref_window(Bh, d0, d1)
    FL = _scale_floor(Bh, c)
    thr = float(np.quantile(frozen_score(REF, REF, FL, c), 0.999))
    msk = (np.asarray(H.t_day) >= d0) & (np.asarray(H.t_day) < d1)
    thra = float(np.quantile(adaptive_score(Bh, c)[msk], 0.999))
    return Bh, REF, FL, thr, thra


# ------------------------------------------------- 误报预算口径的评价入口
def detect_with(df, H_ref, cols=None, thr_mode='q999', margin=1.02, deg_start=60.0, target=FAILLINE):
    """统一评价：在给定通道集与阈值口径下，同时报出健康轨迹误报与退化轨迹检出。
    thr_mode='q999'：阈值 = 健康参考域 score 的 0.999 分位（原口径）；
    thr_mode='zero_fa'：阈值 = 健康轨迹 score 最大值 × margin（零误报口径，可按误报预算解释）。
    """
    c = list(cols if cols is not None else MON)
    Bh, REF, FL, thr999, thra = thresholds_on(H_ref, c)
    scH = frozen_score(Bh, REF, FL, c)
    thr = (float(np.max(scH)) * margin) if thr_mode == 'zero_fa' else float(thr999)
    evH = make_events(pd.Series(scH), thr, **EVENTKW)
    evH_pre = [(float(np.asarray(H_ref.t_day)[s]), float(np.asarray(H_ref.t_day)[e])) for s, e in evH]
    scG = frozen_score(prep(df, c), REF, FL, c)
    ev, pre, post = first_alarm(df, scG, thr, deg_start)
    sca = adaptive_score(prep(df, c), c)
    eva = make_events(pd.Series(sca), thra, **EVENTKW)
    fail = truth_failure(df, deg_start)
    rul = rul_estimate(df, post[0][1], target=target) if post else {5: None, 2: None, 1: None}
    lead = (None if (fail is None or not post) else round(fail - post[0][0], 2))
    return dict(通道集='+'.join(c), 阈值口径=thr_mode, 阈值=float(thr), 自适应阈值=float(thra),
                健康告警数=len(evH), 健康首报=(round(evH_pre[0][0], 2) if evH_pre else None),
                健康告警区间=[(round(a, 2), round(b, 2)) for a, b in evH_pre],
                首报=(None if not post else round(post[0][0], 2)),
                首报索引=(None if not post else int(post[0][1])),
                检出延迟=(None if not post else round(post[0][0] - deg_start, 2)),
                真值失效=(None if fail is None else round(fail, 2)), 提前量=lead,
                告警数=len(ev), 退化前告警=len(pre), 自适应告警数=len(eva),
                RUL_5天窗=(None if rul[5] is None else round(rul[5], 2)),
                RUL_2天窗=(None if rul[2] is None else round(rul[2], 2)),
                RUL_1天窗=(None if rul[1] is None else round(rul[1], 2)),
                RUL误差_1天窗=(None if (rul[1] is None or lead is None) else round(abs(rul[1] - lead), 2)),
                分数=scG, 健康分数=scH)


def noise_median(H, G, cols, rel=0.02, lab_rel=0.03, seeds=10, thr_mode='zero_fa', deg_start=60.0):
    """多次加噪取中位（把"某一条噪声实现恰好触发误报"的影响压掉）。"""
    rows = []
    for s in range(seeds):
        Hn = add_noise(H, rel=rel, lab_rel=lab_rel, seed=100 + s)
        Gn = add_noise(G, rel=rel, lab_rel=lab_rel, seed=1000 + s)
        r = detect_with(Gn, Hn, cols=cols, thr_mode=thr_mode, deg_start=deg_start)
        rows.append(r)
    import numpy as _np
    g = lambda k: [x[k] for x in rows if x[k] is not None]
    med = lambda k: (float(_np.median(g(k))) if g(k) else None)
    return dict(种子数=seeds, 仪表噪声=rel, 实验室噪声=lab_rel,
                检出延迟中位=med('检出延迟'), 检出延迟区间=([min(g('检出延迟')), max(g('检出延迟'))] if g('检出延迟') else None),
                健康告警数中位=med('健康告警数'), 健康误报出现次数=sum(1 for x in rows if x['健康告警数'] > 0),
                阈值中位=med('阈值'), 提前量中位=med('提前量'),
                RUL误差_1天窗中位=med('RUL误差_1天窗'), 明细=rows)
