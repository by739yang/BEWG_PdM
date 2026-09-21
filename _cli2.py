import io, os
NL=chr(10)
# 1) pipeline.calibrate：支持多段参考期 + 阈值策略（中位 / 上界）
p='src/lanmai/pipeline.py'; t=io.open(p,encoding='utf-8').read()
a="""def calibrate(df, channels, state_kind='none', state_col=None, nbin=4, quantile_channel=None,
              ref_frac=(0.0, 0.3), win_days=DEF_ADAPT['win_days'], q=DEF_THR_Q, event=None,
              trend_warn=0.5):"""
b="""def calibrate(df, channels, state_kind='none', state_col=None, nbin=4, quantile_channel=None,
              ref_frac=(0.0, 0.3), ref_segments=None, thr_policy='median',
              win_days=DEF_ADAPT['win_days'], q=DEF_THR_Q, event=None, trend_warn=0.5):
    \"\"\"ref_segments: [(lo, hi), ...] 多段健康期（按行分数比例）；给定时逐段标定阈值，
    再按 thr_policy（median 折中 / upper 保守压误报）汇总；同时报告阈值影响范围。
    单段模式仍走 ref_frac。\"\"\""""
assert a in t; t=t.replace(a,b,1)
a2="""    Zref = pd.DataFrame({c: frozen_z(ref, c, frozen[c], st_ref, floor[c]) for c in channels})
    score_ref = topk_score(Zref, 3)
    thr = float(score_ref.quantile(q))"""
b2="""    def _thr_of(lo, hi):
        r = df.iloc[lo:hi]
        if len(r) < 20: return None
        Z = pd.DataFrame({c: frozen_z(r, c, frozen[c], st_local(lo, hi), floor[c]) for c in channels})
        return float(topk_score(Z, 3).quantile(q))
    def st_local(lo, hi):
        return st.iloc[lo:hi]
    seg_rows=[]
    if ref_segments:
        for (lo_f, hi_f) in ref_segments:
            lo, hi = int(len(df)*lo_f), max(int(len(df)*lo_f)+20, int(len(df)*hi_f))
            v=_thr_of(lo, hi)
            if v is not None:
                seg_rows.append(dict(段='%.2f-%.2f' % (lo_f, hi_f), 起始行=lo, 结束行=hi, 行数=hi-lo, 阈值=round(v,3)))
    if seg_rows:
        vals=[r['阈值'] for r in seg_rows]
        thr = float(max(vals)) if thr_policy=='upper' else float(pd.Series(vals).median())
    else:
        Zref = pd.DataFrame({c: frozen_z(ref, c, frozen[c], st_ref, floor[c]) for c in channels})
        thr = float(topk_score(Zref, 3).quantile(q))"""
assert a2 in t; t=t.replace(a2,b2,1)
a3="""                adaptive=dict(win_days=float(win_days)),
                threshold=dict(q=float(q), value=float(thr)), event=event,"""
b3="""                adaptive=dict(win_days=float(win_days)),
                threshold=dict(q=float(q), value=float(thr), policy=(thr_policy if seg_rows else 'single'),
                               per_segment=seg_rows,
                               阈值范围=(None if not seg_rows else dict(最小=min(r['阈值'] for r in seg_rows),
                                                                     中位=float(pd.Series([r['阈值'] for r in seg_rows]).median()),
                                                                     最大=max(r['阈值'] for r in seg_rows),
                                                                     极差比=round(max(r['阈值'] for r in seg_rows)/max(min(r['阈值'] for r in seg_rows),1e-9),2)))),
                event=event,"""
assert a3 in t; t=t.replace(a3,b3,1)
io.open('_tmp_lp.py','w',encoding='utf-8',newline=NL).write(t); os.replace('_tmp_lp.py',p)

# 2) cli：新增 --ref-segments 与 --thr-policy，并打印逐段阈值
p='src/lanmai/cli.py'; t=io.open(p,encoding='utf-8').read()
a4="""    base = calibrate(df, chans, state_kind=args.state, state_col=args.state_col, nbin=args.nbin,
                     quantile_channel=args.quantile_channel, ref_frac=(r0, r1), win_days=args.win_days,
                     q=args.q, event=dict(enter=args.enter, exit_=args.exit, ratio=args.ratio, cooldown=args.cooldown))"""
b4="""    segs=None
    if getattr(args, 'ref_segments', None):
        segs=[]
        for part in args.ref_segments.split(';'):
            a_, b_ = part.split(',')
            segs.append((float(a_), float(b_)))
    base = calibrate(df, chans, state_kind=args.state, state_col=args.state_col, nbin=args.nbin,
                     quantile_channel=args.quantile_channel, ref_frac=(r0, r1), ref_segments=segs,
                     thr_policy=args.thr_policy, win_days=args.win_days,
                     q=args.q, event=dict(enter=args.enter, exit_=args.exit, ratio=args.ratio, cooldown=args.cooldown))"""
assert a4 in t; t=t.replace(a4,b4,1)
a5="""    print('判据阈值（冻结分数 %.3f 分位）= %.3f' % (args.q, base['threshold']['value']))"""
b5="""    for r in base['threshold'].get('per_segment', []):
        print('  参考段 %-12s 行 %6d-%6d（%6d 行）阈值 %.3f' % (r['段'], r['起始行'], r['结束行'], r['行数'], r['阈值']))
    tr=base['threshold'].get('阈值范围')
    if tr: print('  → 阈值策略 %s；范围 最小 %.3f / 中位 %.3f / 最大 %.3f（极差比 %.2f 倍）'
                 % (base['threshold']['policy'], tr['最小'], tr['中位'], tr['最大'], tr['极差比']))
    print('判据阈值（冻结分数 %.3f 分位）= %.3f' % (args.q, base['threshold']['value']))"""
assert a5 in t; t=t.replace(a5,b5,1)
a6="            sp.add_argument('--ref', default='0,0.3')"
b6=("            sp.add_argument('--ref', default='0,0.3')\n"
    "            sp.add_argument('--ref-segments', default=None, help='多段健康期，如 0,0.1;0.2,0.3;0.45,0.55（分号分隔）')\n"
    "            sp.add_argument('--thr-policy', default='median', choices=['median','upper'], help='多段阈值汇总策略：median 折中 / upper 保守压误报')")
assert a6 in t; t=t.replace(a6,b6,1)
io.open('_tmp_lc.py','w',encoding='utf-8',newline=NL).write(t); os.replace('_tmp_lc.py',p)
import ast
for f in ['src/lanmai/pipeline.py','src/lanmai/cli.py']: ast.parse(io.open(f,encoding='utf-8').read())
print('CLI 已支持多段标定与阈值策略')
