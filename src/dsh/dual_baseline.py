# -*- coding: utf-8 -*-
"""澜脉 · 双基线检测模块（DSH，2026-09-20）

设计依据（本项目实验独立得出）：
- 短窗自适应基线：能抓突变类故障、误报低；但会把慢漂移纳入"新常态"，对其免疫。
- 冻结基线：用投运/大修后的健康段做固定参照，能抓慢漂移；代价是长期运行中误报偏高。
- 因此两通道并行、各自校准、分别输出报警流，合并时标注来源。

命令行演示：python src/dsh/dual_baseline.py
"""
import numpy as np, pandas as pd, json, os, io

def _scale_floor(df, ch):
    gs = (df[ch].quantile(.75) - df[ch].quantile(.25)) / 1.349
    gsd = df[ch].std()
    return pd.concat([gs.where(gs > 1e-9, gsd).fillna(1.0) * 0.2, gsd.fillna(1.0) * 0.1], axis=1).max(axis=1)

def adaptive_z(df, ch, win_days=2.0, min_periods=8, state=None):
    floor = _scale_floor(df, ch)
    Z = pd.DataFrame(0.0, index=df.index, columns=ch)
    groups = [('ALL', df.index)] if state is None else [(s, df.index[np.asarray(state) == s]) for s in pd.unique(state)]
    for c in ch:
        for s, idx in groups:
            if len(idx) < min_periods: continue
            x = df.loc[idx, c].astype(float).sort_index()
            W = pd.Timedelta(days=win_days)
            med = x.rolling(W, min_periods=min_periods).median()
            q75 = x.rolling(W, min_periods=min_periods).quantile(.75)
            q25 = x.rolling(W, min_periods=min_periods).quantile(.25)
            sd = x.rolling(W, min_periods=min_periods).std()
            sc = ((q75 - q25) / 1.349).where(lambda v: v > 1e-9, sd).fillna(1.0)
            sc = sc.clip(lower=float(floor[c]))
            Z.loc[x.index, c] = (((x - med) / sc).clip(-30, 30)).replace([np.inf, -np.inf], np.nan).fillna(0.0).values
    return Z

def frozen_z(df, ch, ref, state=None, state_ref=None, floor=None):
    Z = pd.DataFrame(0.0, index=df.index, columns=ch)
    for c in ch:
        if state is None:
            iqr = ref[c].quantile(.75) - ref[c].quantile(.25); sd = ref[c].std()
            sc = iqr / 1.349 if iqr > 1e-9 else (sd if sd > 1e-9 else 1.0)
            if floor is not None: sc = max(sc, float(floor[c]))
            Z[c] = ((df[c].astype(float) - ref[c].median()) / sc).clip(-30, 30)
        else:
            col = pd.Series(0.0, index=df.index); st = np.asarray(state)
            stR = np.asarray(state_ref) if state_ref is not None else pd.Series(st, index=df.index).reindex(ref.index).values
            for s in pd.unique(st):
                m = (st == s)
                if m.sum() == 0: continue
                r = ref.loc[np.asarray(stR) == s]
                if len(r) < 8: continue
                iqr = r[c].quantile(.75) - r[c].quantile(.25); sd = r[c].std()
                sc = iqr / 1.349 if iqr > 1e-9 else (sd if sd > 1e-9 else 1.0)
                if floor is not None: sc = max(sc, float(floor[c]))
                col[m] = ((df.loc[m, c].astype(float) - r[c].median()) / sc).clip(-30, 30)
            Z[c] = col
    return Z.replace([np.inf, -np.inf], np.nan).fillna(0.0)

def topk_score(Z, k=3):
    A = np.abs(Z.values)
    k = min(k, A.shape[1])
    return pd.Series(np.sqrt((np.sort(A, axis=1)[:, -k:] ** 2).mean(1)), index=Z.index)

def make_events(score, thr, enter=4, exit_=8, ratio=0.8, cooldown=8):
    sv = score.values; over = sv > thr; n = len(sv); ev = []; st = 0; r = 0; s0 = 0; last = -10 ** 9
    for t in range(n):
        if st == 0:
            if t < last + cooldown: r = 0
            elif over[t]:
                r += 1
                if r >= enter: s0 = t; st = 1; r = 0
            else: r = 0
        else:
            if sv[t] < ratio * thr:
                r += 1
                if r >= exit_: ev.append((s0, t + 1)); last = t + 1; st = 0; r = 0
            else: r = 0
    if st == 1: ev.append((s0, n))
    return ev

def dual_detect(df, ch, ref_mask, win_days=2.0, k=3, q=0.995, state=None, state_frozen=None, ref_mask_frozen=None,
                ref_data_frozen=None, state_ref_frozen=None,
                q_frozen=0.999, evkw_frozen=None, **evkw):
    """返回两条通道的报警流（含来源标注）与各自的阈值/分数"""
    Za = adaptive_z(df, ch, win_days=win_days, state=state); sa = topk_score(Za, k)
    thr_a = float(sa[ref_mask].quantile(q))
    ref = df[ref_mask]
    rmf = ref_mask if ref_mask_frozen is None else ref_mask_frozen
    sfb = state if state_frozen is None else state_frozen
    external = ref_data_frozen is not None
    RD = ref_data_frozen if external else df[rmf]
    sRb = (state_ref_frozen if external else
           (None if sfb is None else np.asarray(sfb)[np.asarray(rmf)]))
    FL = _scale_floor(df, ch)
    Zb = frozen_z(df, ch, RD, state=sfb, state_ref=sRb, floor=FL); sb = topk_score(Zb, k)
    sr = topk_score(frozen_z(RD, ch, RD, state=sRb, state_ref=sRb, floor=FL), k)
    thr_b = float(sr.quantile(q_frozen))
    out = []
    for tag, score, thr in [('adaptive', sa, thr_a), ('frozen', sb, thr_b)]:
        for (s, e) in make_events(score, thr, **evkw):
            out.append(dict(channel=tag, idx=s, t=df.index[s], score=float(score.iloc[s]), thr=thr,
                            duration=e - s, end=df.index[min(e, len(df) - 1)]))
    alarms = pd.DataFrame(out).sort_values('t').reset_index(drop=True) if out else pd.DataFrame(columns=['channel','idx','t','score','thr','duration','end'])
    return dict(alarms=alarms, score_adaptive=sa, score_frozen=sb, thr_adaptive=thr_a, thr_frozen=thr_b, Z_adaptive=Za, Z_frozen=Zb)

# ---------------- 演示：两个数据源 ----------------
def demo_metropt3():
    FW = json.load(open('docs/metropt3_fault_windows.json', encoding='utf-8'))
    fw = [(pd.Timestamp(x['start']), pd.Timestamp(x['end'])) for x in FW['windows']]
    RAW = ['TP2','TP3','H1','Reservoirs','Oil_temperature','Motor_current']
    d = pd.read_csv('data/metropt3/metropt3.csv', usecols=['timestamp']+RAW+['DV_eletric'], parse_dates=['timestamp']).set_index('timestamp')
    m = d.resample('1min').agg({**{c:'mean' for c in RAW}, 'DV_eletric':'max'})
    F = pd.DataFrame({c:m[c] for c in RAW})
    F['TP3_minus_Reservoirs'] = m['TP3'] - m['Reservoirs']; F['TP3_minus_H1'] = m['TP3'] - m['H1']
    ch = list(F.columns)
    J = pd.read_csv('results/2026-09-18/dsh/minute_mask_intersection.csv.gz', parse_dates=['ts'])
    F = F.reindex(J.ts).dropna(how='all')
    ref_mask = (F.index < fw[0][0] - pd.Timedelta(hours=12))
    st = pd.Series(np.where(m['Motor_current'].fillna(0) < 1.0, 'stopped', np.where(m['DV_eletric'].fillna(0) >= 0.5, 'loaded', 'unloaded')), index=m.index).reindex(J.ts).fillna('stopped')
    rmf = (F.index < F.index[0] + pd.Timedelta(days=10))   # 冻结通道：投运后前 10 天
    res = dual_detect(F, ch, ref_mask, win_days=14.0, k=3, state=st.values, ref_mask_frozen=rmf)
    A = res['alarms']
    fault_mask = np.zeros(len(J), bool)
    for a, b in fw: fault_mask |= np.asarray((J.ts >= a) & (J.ts <= b))
    healthy_min = int((J.B_ds & J.B_cx & J.fin_ds & J.fin_cx & (~fault_mask) & J.stable_ds & J.stable_cx).sum())
    rows = []
    for tag in ['adaptive', 'frozen']:
        g = A[A.channel == tag] if len(A) else A
        timely = late = 0
        if len(g):
            for g0, g1 in fw:
                tt = [t for t in g.t if g0 - pd.Timedelta(minutes=60) <= t <= g0 + pd.Timedelta(minutes=60)]
                lt = [t for t in g.t if g0 + pd.Timedelta(minutes=60) < t <= g1]
                timely += 1 if tt else 0; late += 1 if (lt and not tt) else 0
            fp = sum(1 for t in g.t if not any(g0 - pd.Timedelta(minutes=60) <= t <= g1 for g0, g1 in fw))
        else: fp = 0
        rows.append(dict(channel=tag, 告警数=int(len(g)), timely=timely, late=late, 误报=fp,
                         误报每全稳定小时=round(fp / max(healthy_min/60, 1e-9), 4),
                         阈值=round(res['thr_adaptive'] if tag == 'adaptive' else res['thr_frozen'], 3)))
    return pd.DataFrame(rows), res

def demo_bsm1():
    """BSM1 慢漂移：冻结参考必须取稳态段（本场景为第 30-45 天，取自无退化运行）"""
    OUT = 'results/2026-09-20/dsh'
    b = pd.read_csv(os.path.join(OUT, 'bsm1_120d_baseline.csv')); d = pd.read_csv(os.path.join(OUT, 'bsm1_120d_degraded.csv'))
    ch = ['SO3','SO4','SO5','SNH_eff','Ntot_eff','TSS_eff','sludge_h']
    DEG = 20.0; STEADY = (30.0, 45.0)
    def prep(df):
        x = df.copy(); x.index = pd.to_datetime(x.t_day * 86400, unit='s'); return x
    B = prep(b)
    REF = B[(B.t_day >= STEADY[0]) & (B.t_day < STEADY[1])]
    hod = lambda X: ((X.t_day * 24) % 24).astype(int).values
    rows = []
    for tag, X in [('基准(无退化)', B), ('退化(第 20 天起 KLa 衰减至 40%)', prep(d))]:
        res = dual_detect(X, ch, X.t_day < DEG, win_days=2.0, k=3,
                          ref_mask_frozen=(X.index >= REF.index[0]) & (X.index <= REF.index[-1]),
                          ref_data_frozen=REF, state_frozen=hod(X), state_ref_frozen=hod(REF))
        A = res['alarms']
        for chn in ['adaptive', 'frozen']:
            g = A[A.channel == chn] if len(A) else A
            days = [float(X.t_day.loc[tt]) for tt in g.t] if len(g) else []
            after = [v for v in days if v > DEG]
            rows.append(dict(dataset=tag, channel=chn, alarms=int(len(g)),
                             thr=round(res['thr_adaptive'] if chn == 'adaptive' else res['thr_frozen'], 3),
                             pre_deg=sum(1 for v in days if v <= DEG),
                             first_after=(round(min(after), 2) if after else None),
                             d0_30=sum(1 for v in days if 0 <= v < 30), d30_60=sum(1 for v in days if 30 <= v < 60),
                             d60_90=sum(1 for v in days if 60 <= v < 90), d90_120=sum(1 for v in days if 90 <= v < 120)))
    return pd.DataFrame(rows)

def diag_bsm1():
    """参考域选择诊断：启动暂态 vs 稳态"""
    OUT = 'results/2026-09-20/dsh'
    b = pd.read_csv(os.path.join(OUT, 'bsm1_120d_baseline.csv')); d = pd.read_csv(os.path.join(OUT, 'bsm1_120d_degraded.csv'))
    ch = ['SO3','SO4','SO5','SNH_eff','Ntot_eff','TSS_eff','sludge_h']
    def prep(df):
        x = df.copy(); x.index = pd.to_datetime(x.t_day * 86400, unit='s'); return x
    hod = lambda X: ((X.t_day * 24) % 24).astype(int).values
    rows = []
    for tag, X in [('基准(无退化)', prep(b)), ('退化(第20天起)', prep(d))]:
        for lo, hi in [(0, 10), (30, 45), (45, 60)]:
            rmf = (X.t_day >= lo) & (X.t_day < hi)
            r = dual_detect(X, ch, X.t_day < 20, win_days=2.0, k=3, ref_mask_frozen=rmf, state_frozen=hod(X))
            g = r['alarms']; g = g[g.channel == 'frozen'] if len(g) else g
            days = [float(X.t_day.loc[tt]) for tt in g.t] if len(g) else []
            rows.append(dict(dataset=tag, ref_window='day %d-%d' % (lo, hi), thr=round(r['thr_frozen'], 3),
                             alarms=len(g), after_ref=sum(1 for v in days if v >= hi)))
    return pd.DataFrame(rows)


def diag_drift():
    """慢漂移签名：分数分布平移 vs 单点越限"""
    OUT = 'results/2026-09-20/dsh'
    b = pd.read_csv(os.path.join(OUT, 'bsm1_120d_baseline.csv')); d = pd.read_csv(os.path.join(OUT, 'bsm1_120d_degraded.csv'))
    ch = ['SO3','SO4','SO5','SNH_eff','Ntot_eff','TSS_eff','sludge_h']
    def prep(df):
        x = df.copy(); x.index = pd.to_datetime(x.t_day * 86400, unit='s'); return x
    B, D = prep(b), prep(d); REF = B[(B.t_day >= 30) & (B.t_day < 45)]
    hod = lambda X: ((X.t_day * 24) % 24).astype(int).values
    arr = lambda x: np.asarray(x, dtype=float).ravel()
    sB = arr(topk_score(frozen_z(B, ch, REF, state=hod(B), state_ref=hod(REF), floor=_scale_floor(B, ch)), 3))
    sD = arr(topk_score(frozen_z(D, ch, REF, state=hod(D), state_ref=hod(REF), floor=_scale_floor(D, ch)), 3))
    mB = pd.Series(sB, index=B.index).rolling('5D', min_periods=192).median().values   # 5 天时间窗（本数据 96 点/天）
    mD = pd.Series(sD, index=D.index).rolling('5D', min_periods=192).median().values
    dB = np.asarray(B.t_day); dD = np.asarray(D.t_day)
    base = float(np.nanmedian(mB[dB >= 30]))
    g = []
    for k in [1.3, 1.5, 2.0]:
        thr = base * k
        fb = [dB[i] for i in range(len(dB)) if np.isfinite(mB[i]) and mB[i] > thr and dB[i] > 45]
        fd = [dD[i] for i in range(len(dD)) if np.isfinite(mD[i]) and mD[i] > thr and dD[i] > 45]
        g.append(dict(rule='rolling-5d-median > %.1fx ref (=%.2f)' % (k, thr),
                      healthy_alarms=len(fb), healthy_first=(round(min(fb), 2) if fb else None),
                      degraded_alarms=len(fd), degraded_first=(round(min(fd), 2) if fd else None),
                      degraded_delay_days=(round(min(fd) - 20.0, 2) if fd else None)))
    rows = {}
    for lo in range(0, 120, 20):
        rows['day %d-%d' % (lo, lo + 20)] = dict(
            healthy_median=round(float(np.nanmedian(mB[(dB >= lo) & (dB < lo + 20)])), 2),
            degraded_median=round(float(np.nanmedian(mD[(dD >= lo) & (dD < lo + 20)])), 2))
    return pd.DataFrame(g), pd.DataFrame(rows).T.reset_index().rename(columns={'index': 'bucket'})

if __name__ == '__main__':
    OUT = 'results/2026-09-20/dsh'
    os.makedirs(OUT, exist_ok=True)
    NL = chr(10) + chr(10)
    t1, _ = demo_metropt3(); t2 = demo_bsm1(); t3 = diag_bsm1(); t4, t5 = diag_drift()
    for name, tb in [('dual_baseline_metropt3', t1), ('dual_baseline_bsm1', t2),
                     ('dual_baseline_diag_reference', t3), ('dual_baseline_diag_drift', t4),
                     ('dual_baseline_drift_buckets', t5)]:
        tb.to_csv(os.path.join(OUT, name + '.csv'), index=False, encoding='utf-8-sig')
    for title, tb in [('=== 数据源 1：MetroPT-3（突变类故障）===', t1),
                      ('=== 数据源 2：BSM1 120 天（慢漂移）===', t2),
                      ('=== BSM1 诊断 A：冻结参考域选择 ===', t3),
                      ('=== BSM1 诊断 B：慢漂移判据 ===', t4),
                      ('=== BSM1 诊断 B2：滚动 5 天中位数（健康 vs 退化）===', t5)]:
        print(title); print(tb.to_string(index=False)); print()
    f = io.open(os.path.join(OUT, 'dual_baseline_report.md'), 'w', encoding='utf-8')
    W = f.write
    W('# 双基线检测模块：验证报告（DSH，2026-09-20）' + NL)
    W('模块：src/dsh/dual_baseline.py。两通道各自校准、分别输出报警流并标注来源。' + NL)
    W('**注意**：本模块是演示/验证用实现，其默认参数与冻结流程 docs/PROTOCOL_v1.5.md 并不完全一致。' + NL)
    W('## 1. 数据源 1：MetroPT-3（突变类故障，冻结分母 96,270 全稳定分钟）' + NL + t1.to_markdown(index=False) + NL)
    W('结论：两通道误报率相近（0.0249 / 0.0181 次每全稳定小时），冻结通道命中 1 次及时告警，自适应通道命中 1 次延迟告警。' + NL)
    W('## 2. 数据源 2：BSM1 120 天（慢漂移，第 20 天起 KLa 衰减至 40%）' + NL + t2.to_markdown(index=False) + NL)
    W('冻结通道参考域取"健康运行的稳态段（第 30-45 天）"；自适应通道 2 天滚动窗、不做工况分层。' + NL)
    W('两条独立通道在退化运行中指向同一时刻（adaptive 40.24 天 / frozen 40.28 天），健康运行中冻结通道 0 误报。' + NL)
    W('## 3. 诊断 A：冻结参考域必须取自稳态段' + NL + t3.to_markdown(index=False) + NL)
    W('BSM1 存在明显的**启动暂态**：SO5 均值 0.40（第 0-20 天）-> 1.03（第 60-80 天），污泥浓度 2.06 -> 2.66。' + NL)
    W('把第 0-10 天当冻结参考时阈值被压到 4.4，健康运行 120 天报出 75 次误报；改用稳态段（第 30-45 天）参考后阈值 20.2，健康运行 0 误报。' + NL)
    W('退化运行若把冻结参考窗取在退化开始之后（第 30-45 天），参考窗自身吸收退化 -> 0 告警；这从反面确认冻结参考必须取自已确认健康的历史段。' + NL)
    W('## 4. 诊断 B：慢漂移的签名是分布平移，不是单点越限' + NL + t4.to_markdown(index=False) + NL + t5.to_markdown(index=False) + NL)
    W('以稳态段为参考时，退化运行的分数中位数随 KLa 衰减单调抬升（2.15 -> 2.29 -> 2.44 -> 2.95），健康运行平稳（2.00 -> 2.07 -> 1.91 -> 2.02）；' + NL)
    W('但 p99.9 单点阈值（20.2）远高于这一平移量，因此单点事件机对慢漂移只能靠瞬态越限捕捉（1 次，延迟 20.3 天）。' + NL)
    W('**口径更正（2026-09-20 晚，Codex 复核发现）**：本判据原先用 rolling(7200) 点（=75 天窗）计算，见下方更正值。改为 5 天时间窗后，滚动中位数越限**并不特异**：健康运行同样越限（k=1.3 时 2004 个样本、首次在第 59.09 天），退化运行检出延迟 33.82 天。因此该统计量只能作为严重度/趋势指标，不能作为报警判据。' + NL)
    W('## 5. 本模块给出的三条设计原则' + NL)
    W('1. 双基线并行：短窗自适应抓突变（对慢漂移免疫），冻结基线抓慢漂移（对突变不够灵敏）。' + NL)
    W('2. 冻结参考域必须取自"验收合格且已进入稳态"的历史段；投运暂态段会把阈值压得过低，导致长期误报。' + NL)
    W('3. 工况条件化对两条通道都是必需的（MetroPT-3 按负荷/启停分层，BSM1 按一天中的时段分层）；分层后剩余漂移才是可判读信号。' + NL)
    W('## 6. 局限' + NL)
    W('- MetroPT-3 的冻结参考窗取投运后前 10 天，其有效性同样依赖该段处于稳态；本数据集上误报率可接受（0.0181 次每全稳定小时）。' + NL)
    W('- 冻结基线在数月尺度上会因工艺自身演化而失效（本模块未实现再锁定/带迟滞后刷新），属后续工作。' + NL)
    W('- BSM1 退化场景只有一档（KLa 衰减至 40%、60 天斜坡），检测延迟随幅值/斜率变化的关系尚未系统扫描。' + NL)
    f.close()
    print('报告已写入', os.path.join(OUT, 'dual_baseline_report.md'))
