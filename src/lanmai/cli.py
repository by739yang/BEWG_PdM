# -*- coding: utf-8 -*-
"""lanmai CLI —— 数据体检 / 基线标定 / 分级告警（澜脉，DSH，2026-09-21）
用法示例：
  python -m lanmai inspect   --data data.csv
  python -m lanmai calibrate --data data.csv --out baseline.json --state hour --ref 0,0.3
  python -m lanmai watch     --data data.csv --baseline baseline.json --out alarms.csv
  python -m lanmai selftest
"""
import argparse, json, io, sys, os, pandas as pd

def _read(args, use_channels=False):
    from .core import load_table
    ch = None
    if use_channels and getattr(args, 'channels', None):
        ch = [c.strip() for c in args.channels.split(',') if c.strip()]
    # 注意：calibrate/watch 不能按通道过滤，否则会把工况列（state）删掉
    return load_table(args.data, args.time, getattr(args, 'resample', None), ch)

def _json(obj, path):
    io.open(path, 'w', encoding='utf-8').write(json.dumps(obj, ensure_ascii=False, indent=1))

def cmd_inspect(args):
    from .pipeline import inspect
    df = _read(args, use_channels=True)     # inspect 尊重 --channels（2026-09-22 修：此前被忽略）
    info = inspect(df)
    print(json.dumps({k: v for k, v in info.items() if k != '通道统计'}, ensure_ascii=False, indent=1))
    for c, st in info['通道统计'].items():
        print('  %-18s 缺失 %-6s 均值 %-10s 标准差 %-10s 零方差 %s' % (c, st['缺失率'], st['均值'], st['标准差'], st['零方差']))
    if args.out:
        _json(info, args.out); print('已写入', args.out)

def cmd_calibrate(args):
    from .pipeline import calibrate
    df = _read(args)
    r0, r1 = [float(x) for x in args.ref.split(',')]
    chans = [c.strip() for c in args.channels.split(',')] if args.channels else \
            [c for c in df.columns if c != args.state_col and pd.api.types.is_numeric_dtype(df[c])]
    segs=None
    if getattr(args, 'ref_segments', None):
        segs=[]
        for part in args.ref_segments.split(';'):
            a_, b_ = part.split(',')
            segs.append((float(a_), float(b_)))
    base = calibrate(df, chans, state_kind=args.state, state_col=args.state_col, nbin=args.nbin,
                     quantile_channel=args.quantile_channel, ref_frac=(r0, r1), ref_segments=segs,
                     thr_policy=args.thr_policy, win_days=args.win_days,
                     q=args.q, event=dict(enter=args.enter, exit_=args.exit, ratio=args.ratio, cooldown=args.cooldown))
    base['meta']['source'] = os.path.abspath(args.data)
    print('参考窗：%s → %s（%d 行）' % (base['meta']['参考窗起点'], base['meta']['参考窗终点'], base['meta']['参考窗行数']))
    for r in base['threshold'].get('per_segment', []):
        print('  参考段 %-12s 行 %6d-%6d（%6d 行）阈值 %.3f' % (r['段'], r['起始行'], r['结束行'], r['行数'], r['阈值']))
    tr=base['threshold'].get('阈值范围')
    if tr: print('  -> 阈值策略 %s；范围 最小 %.3f / 中位 %.3f / 最大 %.3f（极差比 %.2f 倍）'
                 % (base['threshold']['policy'], tr['最小'], tr['中位'], tr['最大'], tr['极差比']))
    print('判据阈值（冻结分数 %.3f 分位）= %.3f' % (args.q, base['threshold']['value']))
    for w in base['warnings']:
        print('  [警告] %s' % w)
    _json(base, args.out); print('基线已写入', args.out)

def cmd_watch(args):
    from .pipeline import watch
    df = _read(args)
    base = json.load(io.open(args.baseline, encoding='utf-8'))
    A, sm = watch(df, base, warmup=args.warmup)
    if len(A):
        A.to_csv(args.out, index=False, encoding='utf-8-sig')
        print('告警 %d 个（P1 立即处置 %d / P2 复核排计划 %d / P3 趋势观察 %d）'
              % (sm['告警总数'], sm['分级'].get(1, 0), sm['分级'].get(2, 0), sm['分级'].get(3, 0)))
        print('首报：%s' % sm['首报'])
        print(A.head(8).to_string(index=False))
        print('明细已写入', args.out)
    else:
        print('无告警')

def cmd_selftest(args):
    from .pipeline import selftest
    selftest(); print('自检完成')

def main(argv=None):
    p = argparse.ArgumentParser(prog='lanmai', description='澜脉 · 设备健康接入与标定工具')
    sub = p.add_subparsers(dest='cmd', required=True)
    for name, fn in [('inspect', cmd_inspect), ('calibrate', cmd_calibrate), ('watch', cmd_watch), ('selftest', cmd_selftest)]:
        sp = sub.add_parser(name)
        if name != 'selftest':
            sp.add_argument('--data', required=True)
            sp.add_argument('--time', default=None, help='时间列名（不填则自动识别）')
            sp.add_argument('--resample', default=None, help='重采样，如 1min / 15min')
        if name in ('inspect', 'calibrate'):
            sp.add_argument('--channels', default=None, help='逗号分隔的通道白名单')
        if name in ('inspect',):
            sp.add_argument('--out', default=None)
        if name == 'calibrate':
            sp.add_argument('--out', required=True); sp.add_argument('--state', default='none', choices=['none', 'hour', 'col', 'quantile'])
            sp.add_argument('--state-col', default=None); sp.add_argument('--nbin', type=int, default=4)
            sp.add_argument('--quantile-channel', default=None); sp.add_argument('--ref', default='0,0.3')
            sp.add_argument('--ref-segments', default=None, help='多段健康期，如 0,0.1;0.2,0.3;0.45,0.55（分号分隔）')
            sp.add_argument('--thr-policy', default='median', choices=['median','upper'], help='多段阈值汇总：median 折中 / upper 保守压误报')
            sp.add_argument('--win-days', type=float, default=2.0); sp.add_argument('--q', type=float, default=0.999)
            sp.add_argument('--enter', type=int, default=4); sp.add_argument('--exit', type=int, default=8, dest='exit')
            sp.add_argument('--ratio', type=float, default=0.8); sp.add_argument('--cooldown', type=int, default=8)
        if name == 'watch':
            sp.add_argument('--baseline', required=True); sp.add_argument('--out', required=True)
            sp.add_argument('--warmup', default=None, help='预热期（如 1D / 6H），该期间告警不计入')
        sp.set_defaults(func=fn)
    a = p.parse_args(argv)
    a.func(a)

if __name__ == '__main__':
    main()
