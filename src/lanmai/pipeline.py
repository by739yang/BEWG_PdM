# -*- coding: utf-8 -*-
"""lanmai.pipeline —— 体检 / 标定 / 告警三段流程（澜脉，DSH，2026-09-21）"""
import numpy as np, pandas as pd, json, hashlib, io, os
from .core import (DEF_EVENT, DEF_ADAPT, DEF_THR_Q, window_of, load_table, state_series, scale_floor,
                   adaptive_z, frozen_stats, frozen_z, topk_score, make_events, trends)

def inspect(df):
    step = np.median(np.diff(df.index.values).astype('timedelta64[s]').astype(float)) if len(df) > 2 else np.nan
    stats = {}
    for c in df.columns:
        s = df[c]
        stats[c] = dict(缺失率=round(float(s.isna().mean()), 4), 均值=round(float(s.mean()), 4),
                        标准差=round(float(s.std()), 4), 最小值=round(float(s.min()), 4), 最大值=round(float(s.max()), 4),
                        零方差=bool(float(s.std()) < 1e-12))
    return dict(行数=int(len(df)), 起始=str(df.index[0]), 结束=str(df.index[-1]),
                采样间隔中位秒=(None if not np.isfinite(step) else float(step)),
                通道数=int(df.shape[1]), 零方差通道=[c for c in df.columns if stats[c]['零方差']],
                通道统计=stats)

def calibrate(df, channels, state_kind='none', state_col=None, nbin=4, quantile_channel=None,
              ref_frac=(0.0, 0.3), win_days=DEF_ADAPT['win_days'], q=DEF_THR_Q, event=None,
              trend_warn=0.5):
    event = dict(DEF_EVENT if event is None else event)
    n = len(df); i0 = int(n * ref_frac[0]); i1 = max(i0 + 20, int(n * ref_frac[1]))
    ref = df.iloc[i0:i1]
    st = state_series(df, state_kind, state_col, nbin, quantile_channel)
    st_ref = st.iloc[i0:i1]
    floor = {c: scale_floor(ref, c) for c in channels}
    frozen = {c: frozen_stats(ref, c, st_ref if state_kind != 'none' else None) for c in channels}
    warnings = []
    for c in channels:
        span_rel, _ = trends(ref, c)
        if abs(span_rel) > trend_warn:
            warnings.append('参考窗内通道 %s 有显著趋势（相对变化 %.2f）→ 该段可能不是稳态，按设计原则③应更换参考窗'
                            % (c, span_rel))
    Zref = pd.DataFrame({c: frozen_z(ref, c, frozen[c], st_ref, floor[c]) for c in channels})
    score_ref = topk_score(Zref, 3)
    thr = float(score_ref.quantile(q))
    base_ratio = float(score_ref.median()) if float(score_ref.median()) > 0 else 1.0
    return dict(meta=dict(时间起点=str(df.index[0]), 时间终点=str(df.index[-1]), 行数=int(n),
                          参考窗起点=str(ref.index[0]), 参考窗终点=str(ref.index[-1]), 参考窗行数=int(len(ref))),
                channels=list(channels), state=dict(kind=state_kind, col=state_col, nbin=nbin),
                floor=floor, frozen={c: {str(k): v for k, v in frozen[c].items()} for c in channels},
                adaptive=dict(win_days=float(win_days)),
                threshold=dict(q=float(q), value=float(thr)), event=event,
                ratio=dict(window_days=3.0, base_median=base_ratio, level1=1.15, level3=1.25),
                warnings=warnings)

def watch(df, base, warmup=None):
    channels = base['channels']
    st = state_series(df, base['state']['kind'], base['state'].get('col'), base['state'].get('nbin', 4),
                      base['state'].get('channel'))
    Za = pd.DataFrame({c: adaptive_z(df, c, st, win_days=base['adaptive']['win_days']) for c in channels})
    Zf = pd.DataFrame({c: frozen_z(df, c, base['frozen'][c], st, base['floor'][c]) for c in channels})
    sa = topk_score(Za, 3); sf = topk_score(Zf, 3)
    win = window_of(sf.index, base['ratio']['window_days'])
    rr = (sf.rolling(win, min_periods=8).median() / base['ratio']['base_median']).astype(float)
    ev_rows = []
    for tag, score in [('adaptive', sa), ('frozen', sf)]:
        for (s0, e0) in make_events(score, base['threshold']['value'], **base['event']):
            ratio_now = float(rr.iloc[min(e0, len(rr) - 1)])
            level = 1 if (np.isfinite(ratio_now) and ratio_now >= base['ratio']['level1']) else 2
            ev_rows.append(dict(起点=df.index[s0], 结束=df.index[min(e0, len(df) - 1)],
                                持续分钟=int((df.index[min(e0, len(df) - 1)] - df.index[s0]).total_seconds() // 60),
                                来源通道=tag, 峰值分数=round(float(np.nanmax(score.iloc[s0:max(e0, s0 + 1)])), 2),
                                判据阈值=round(base['threshold']['value'], 3), 分布位置比值=round(ratio_now, 3), 等级=level))
    ratio_hi = (rr >= base['ratio']['level3'])
    for (s0, e0) in make_events(ratio_hi.astype(float), 0.5, enter=1, exit_=2, ratio=0.5, cooldown=1):
        ev_rows.append(dict(起点=df.index[s0], 结束=df.index[min(e0, len(df) - 1)],
                            持续分钟=int((df.index[min(e0, len(df) - 1)] - df.index[s0]).total_seconds() // 60),
                            来源通道='ratio', 峰值分数=round(float(np.nanmax(rr.iloc[s0:max(e0, s0 + 1)])), 3),
                            判据阈值=round(base['ratio']['level3'], 3), 分布位置比值=round(float(np.nanmax(rr.iloc[s0:max(e0, s0 + 1)])), 3), 等级=3))
    A = pd.DataFrame(ev_rows)
    if len(A) and warmup is not None:
        A = A[A['起点'] >= (df.index[0] + pd.Timedelta(warmup))].reset_index(drop=True)
    if len(A):
        A = A.sort_values('起点').reset_index(drop=True)
    summary = dict(告警总数=int(len(A)),
                   分级={int(k): int(v) for k, v in (A['等级'].value_counts().items() if len(A) else [])},
                   首报=(str(A['起点'].iloc[0]) if len(A) else None))
    return A, summary

def selftest(seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range('2026-01-01', periods=20000, freq='1min')
    base = 10 + 2 * np.sin(np.arange(len(idx)) / 1440 * 2 * np.pi) + rng.normal(0, .1, len(idx))
    step_fault = base.copy(); step_fault[8000:8200] += 6
    drift = base.copy(); drift[6000:] += np.linspace(0, 5, len(idx) - 6000)
    df = pd.DataFrame({'chA': base, 'chB': base * .5, 'chC': base * 1.2}, index=idx)
    for nm, y in [('阶跃', step_fault), ('慢漂移', drift)]:
        d = df.copy(); d['chA'] = y
        b = calibrate(d.iloc[:5000], ['chA', 'chB', 'chC'], ref_frac=(0, .3))
        A, sm = watch(d, b)
        print('  [自检] %s：告警 %d 个，分级 %s，首报 %s' % (nm, sm['告警总数'], sm['分级'], sm['首报']))
    return True
