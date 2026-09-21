# -*- coding: utf-8 -*-
"""lanmai.core —— 接入/标定/告警的核心实现（澜脉，DSH，2026-09-21）
说明：本文件是已验证检测链路（src/dsh/dual_baseline.py）的**独立可搬运实现**，
      供客户现场/合作方直接调用，不依赖 results/ 下的任何中间产物。
设计原则（来自项目实验）：
  1) 双基线并行：短窗自适应抓突变，冻结基线抓慢漂移；
  2) 工况条件化（按负荷/时段分层）是刚需，不做会失效；
  3) 冻结参考域必须取自「验收合格且已进入稳态」的时段（本文件会做趋势体检并告警）；
  4) 慢漂移的严重度用分布位置统计量（滚动中位数比值）表达，不用单点越限；
  5) 危险阈值按工况自身健康基线标定，不用绝对值。
"""
import numpy as np, pandas as pd, json, hashlib, io, os

DEF_EVENT = dict(enter=4, exit_=8, ratio=0.8, cooldown=8)
DEF_ADAPT = dict(win_days=2.0, min_periods=8)
DEF_THR_Q = 0.999

def points_per_day(index):
    if isinstance(index, pd.DatetimeIndex) and len(index) > 2:
        dt = np.median(np.diff(index.values).astype('timedelta64[s]').astype(float))
        if np.isfinite(dt) and dt > 0: return 86400.0 / dt
    return 1440.0

def window_of(index, days, min_points=8):
    """时间窗：DatetimeIndex 直接用 Timedelta；整数索引按采样率折算成点数（避免把时间窗当点数用）。"""
    if isinstance(index, pd.DatetimeIndex):
        return pd.Timedelta(days=days)
    return max(min_points, int(round(points_per_day(index) * days)))

def load_table(path, time_col=None, resample=None, channels=None, sep=None):
    head = io.open(path, encoding='utf-8', errors='replace').readline()
    if sep is None:
        sep = ';' if head.count(';') > head.count(',') else ','
    df = pd.read_csv(path, sep=sep)
    if df.shape[1] == 1 and sep == ',':
        df = pd.read_csv(path, sep=';')       # 兜底：分号分隔
    if time_col is None:
        time_col = _pick_time_col(df)
    t = pd.to_datetime(df[time_col], errors='coerce')
    d = df.drop(columns=[time_col])
    keep = {}
    for c in d.columns:
        s = d[c]
        if pd.api.types.is_numeric_dtype(s):
            keep[c] = s.astype(float)
        else:
            conv = pd.to_numeric(s, errors='coerce')
            keep[c] = conv if conv.notna().mean() >= 0.9 else s   # 看着像数值才转，否则保留分类列（工况/标签）
    d = pd.DataFrame(keep, index=d.index)
    d.index = t
    d = d[~d.index.isna()].sort_index()
    if channels:                                  # 过滤必须在重采样之前：否则工况列（字符串）会被 .mean() 撞上
        d = d[[c for c in channels if c in d.columns]]
    if resample:
        d = d.resample(resample).mean()
    return d

def _pick_time_col(df):
    """严格挑时间列：先按常见名精确匹配，再按前缀匹配，最后按可解析成功率兜底。
    注意：不能用子串匹配（'TSS_eff' 含 'ts'，会被误判成时间列）。"""
    exact = {'time','timestamp','datetime','date','ts','t','时间','日期','时间戳','采集时间','record_time'}
    lower = {c: str(c).strip().lower() for c in df.columns}
    for c in df.columns:
        if lower[c] in exact:
            return c
    prefixes = ('time','ts_','_ts','datetime','date','时间','日期')
    for c in df.columns:
        if lower[c].startswith(prefixes):
            return c
    for c in df.columns:
        s = df[c]
        if not pd.api.types.is_numeric_dtype(s):
            try:
                ok = pd.to_datetime(s, errors='coerce').notna().mean()
                if ok > 0.9:
                    return c
            except Exception:
                pass
    return df.columns[0]

def state_series(df, kind='none', state_col=None, nbin=4, channel=None):
    if kind == 'none':
        return pd.Series('ALL', index=df.index)
    if kind == 'hour':
        return pd.Series(df.index.hour.astype(str), index=df.index)
    if kind == 'col':
        if state_col not in df.columns:
            raise ValueError('state-col 不存在: %s' % state_col)
        return df[state_col].astype(str)
    if kind == 'quantile':
        ch = channel or df.columns[0]
        q = pd.qcut(df[ch], nbin, duplicates='drop')
        return q.astype(str)
    raise ValueError('未知 state kind: %s' % kind)

def scale_floor(df, ch):
    gs = (df[ch].quantile(.75) - df[ch].quantile(.25)) / 1.349
    gsd = df[ch].std()
    return float(max((gs if gs > 1e-9 else gsd) * 0.2, gsd * 0.1))

def adaptive_z(df, ch, state, win_days=2.0, min_periods=8):
    Z = pd.Series(0.0, index=df.index)
    st = np.asarray(state)
    for s in pd.unique(st):
        idx = df.index[st == s]
        if len(idx) < min_periods:
            continue
        x = df.loc[idx, ch].astype(float).sort_index()
        W = window_of(x.index, win_days)
        med = x.rolling(W, min_periods=min_periods).median()
        q75 = x.rolling(W, min_periods=min_periods).quantile(.75)
        q25 = x.rolling(W, min_periods=min_periods).quantile(.25)
        sd = x.rolling(W, min_periods=min_periods).std()
        sc = ((q75 - q25) / 1.349).where(lambda v: v > 1e-9, sd).fillna(1.0)
        sc = sc.clip(lower=scale_floor(df, ch))
        Z.loc[x.index] = (((x - med) / sc).clip(-30, 30)).replace([np.inf, -np.inf], np.nan).fillna(0.0).values
    return Z

def frozen_stats(ref, ch, state_ref=None):
    out = {}
    if state_ref is None:
        iqr = ref[ch].quantile(.75) - ref[ch].quantile(.25)
        sd = ref[ch].std()
        sc = iqr / 1.349 if iqr > 1e-9 else (sd if sd > 1e-9 else 1.0)
        out['ALL'] = dict(median=float(ref[ch].median()), scale=float(sc))
        return out
    st = np.asarray(state_ref)
    for s in pd.unique(st):
        r = ref.loc[st == s, ch]
        if len(r) < 8:
            continue
        iqr = r.quantile(.75) - r.quantile(.25)
        sd = r.std()
        sc = iqr / 1.349 if iqr > 1e-9 else (sd if sd > 1e-9 else 1.0)
        out[str(s)] = dict(median=float(r.median()), scale=float(sc))
    return out

def frozen_z(df, ch, stats, state, floor=None):
    Z = pd.Series(0.0, index=df.index)
    st = np.asarray(state)
    for s in pd.unique(st):
        key = str(s) if str(s) in stats else ('ALL' if 'ALL' in stats else None)
        if key is None:
            continue
        m = (st == s)
        med = stats[key]['median']
        sc = stats[key]['scale']
        if floor is not None:
            sc = max(sc, floor)
        Z.loc[df.index[m]] = (((df.loc[m, ch].astype(float) - med) / sc).clip(-30, 30)).values
    return Z

def topk_score(Z, k=3):
    A = np.abs(np.asarray(Z))
    k = min(k, A.shape[1])
    idx = np.argsort(A, axis=1)[:, -k:]
    return pd.Series(np.sqrt((np.take_along_axis(A, idx, axis=1) ** 2).mean(axis=1)), index=Z.index)

def make_events(score, thr, enter=4, exit_=8, ratio=0.8, cooldown=8):
    s = np.asarray(score, dtype=float)
    over = s > thr
    n = len(s)
    ev = []
    st = 0
    r = 0
    s0 = 0
    last = -10 ** 9
    for t in range(n):
        if st == 0:
            if t < last + cooldown:
                r = 0
            elif over[t]:
                r += 1
                if r >= enter:
                    s0 = t
                    st = 1
                    r = 0
            else:
                r = 0
        else:
            if s[t] < ratio * thr:
                r += 1
                if r >= exit_:
                    ev.append((s0, t + 1))
                    last = t + 1
                    st = 0
                    r = 0
            else:
                r = 0
    if st == 1:
        ev.append((s0, n))
    return ev

def trends(ref, ch):
    y = np.asarray(ref[ch], dtype=float)
    y = y[np.isfinite(y)]
    if len(y) < 20:
        return 0.0, 0.0
    x = np.arange(len(y), dtype=float)
    x = x - x.mean()
    slope = float((x * (y - y.mean())).sum() / (x * x).sum())
    span = slope * (len(y) - 1)
    scale = float(np.std(y) + 1e-12)
    return span / scale, slope
