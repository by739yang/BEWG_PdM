# -*- coding: utf-8 -*-
"""澜脉 · 一键复现入口
用法：
  python run_all.py              # 快速链路（约 2-4 分钟）：评估 → 链路 → 自检 → 演示页
  python run_all.py --full       # 全量（约 10-15 分钟）：额外跑 SKAB 协议、RUL 训练、诊断实验
  python run_all.py --only 名称  # 只跑某一阶段
阶段清单在 STAGES 里，每条含脚本、是否属于全量、产物路径。"""
import subprocess, sys, time, os, json

STAGES=[
 dict(name='env',        title='环境与依赖检查', script=None, full=False),
 dict(name='data',       title='数据资产检查',   script=None, full=False),
 dict(name='metropt3',   title='MetroPT-3 冻结口径评估', script='src/dsh/2026-09-18_03_frozen_metrics.py', full=False),
 dict(name='pipeline',   title='端到端链路（检测→诊断→RUL→决策）', script='src/dsh/2026-09-18_14_pipeline.py', full=False),
 dict(name='check',      title='一致性自检', script='src/dsh/2026-09-18_18_consistency_check_v2.py', full=False),
 dict(name='demo',       title='生成单页演示', script='src/dsh/2026-09-19_01_demo_page.py', full=False),
 dict(name='dual_baseline', title='双基线检测模块（MetroPT-3 + BSM1 120 天）', script='src/dsh/dual_baseline.py', full=True),
 dict(name='skab',       title='SKAB 冻结协议（v1.4）', script='src/dsh/2026-09-15_16_protocol_v14.py', full=True),
 dict(name='rul',        title='C-MAPSS RUL 基线（精确斜率版）', script='src/dsh/2026-09-17_05_rul_baseline.py', full=True),
 dict(name='diag_cross', title='诊断跨记录验证（多尺寸）', script='src/dsh/2026-09-18_15_cwru_multiseverity.py', full=True),
 dict(name='diag_norm',  title='诊断归一化策略对照', script='src/dsh/2026-09-19_02_cwru_domain_adapt.py', full=True),
 dict(name='influent_bsm1', title='BSM1 进水工况泛化分析', script='src/dsh/2026-09-20_11_bsm1_influent_robustness.py', full=True),
 dict(name='sweep_bsm1', title='BSM1 退化幅值-斜率扫描分析', script='src/dsh/2026-09-20_10_bsm1_sweep_analysis.py', full=True),
 dict(name='figures_bsm1', title='BSM1 数字孪生闭环四图', script='src/dsh/2026-09-20_08_bsm1_figure.py', full=True),
 dict(name='figures',    title='材料四图', script='src/dsh/2026-09-18_16_figures.py', full=True),
]
DATA=[
 ('SKAB 真实水泵台架','data/SKAB-master','**/*.csv'),
 ('MetroPT-3 空压机','data/metropt3','metropt3.csv'),
 ('C-MAPSS FD001','data/cmapss','*.txt'),
 ('CWRU 轴承','data/cwru','*.npz'),
]
def env_check():
    import importlib.util
    need=['numpy','pandas','sklearn','scipy','matplotlib']
    miss=[m for m in need if importlib.util.find_spec(m) is None]
    print('  Python %s' % sys.version.split()[0])
    print('  依赖：%s' % ('齐全' if not miss else '缺失 -> '+', '.join(miss)))
    return not miss
def data_check():
    import glob
    ok=True
    for name,d,pat in DATA:
        files=glob.glob(os.path.join(d,pat),recursive=True) if os.path.isdir(d) else []
        print('  %-22s %-28s %s' % (name, d, ('%d 个文件'%len(files)) if files else '缺失（请先跑对应的 fetch 脚本）'))
        if not files: ok=False
    return ok
def main():
    try: sys.stdout.reconfigure(errors='replace')
    except Exception: pass
    args=sys.argv[1:]
    full='--full' in args
    only=None
    if '--only' in args: only=args[args.index('--only')+1]
    sel=[s for s in STAGES if (only is None) and ((not only) and (full or not s['full'])) or (only and s['name']==only)]
    if not sel: print('没有匹配的阶段'); return 2
    print('澜脉 · 一键复现  模式=%s  阶段数=%d' % ('全量' if full else '快速', len(sel)))
    results=[]; t_all=time.time()
    for s in sel:
        print()
        print('='*70)
        print('[%s] %s' % (s['name'], s['title']))
        t0=time.time()
        if s['script'] is None:
            ok = env_check() if s['name']=='env' else data_check()
            dt=time.time()-t0
        else:
            if not os.path.exists(s['script']):
                print('  脚本不存在：%s' % s['script']); results.append((s['name'],False,0)); continue
            p=subprocess.run([sys.executable, s['script']], capture_output=True, text=True, encoding='utf-8', errors='replace')
            dt=time.time()-t0
            tail=(p.stdout or '').strip().split(chr(10))[-6:]
            for l in tail: print('  | '+l)
            if p.returncode!=0:
                print('  失败，stderr 末尾：')
                for l in (p.stderr or '').strip().split(chr(10))[-6:]: print('  ! '+l)
            ok = p.returncode==0
        print('  --> %s（%.1f 秒）' % ('通过' if ok else '未通过', dt))
        results.append((s['name'],ok,dt))
    print()
    print('='*70)
    print('汇总（总耗时 %.1f 秒）' % (time.time()-t_all))
    for n,ok,dt in results: print('  %-12s %-6s %.1fs' % (n,'通过' if ok else '未通过',dt))
    bad=[n for n,ok,_ in results if not ok]
    print('结论：%s' % ('全部通过' if not bad else '存在未通过阶段 -> '+', '.join(bad)))
    return 0 if not bad else 1
if __name__=='__main__':
    sys.exit(main())
