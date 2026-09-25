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
 dict(name='sludge_sweep', title='污泥线幅值/速率扫描', script='src/dsh/2026-09-21_12_sludge_sweep.py', full=True),
 dict(name='sludge_decision', title='污泥线决策层（维护策略对比）', script='src/dsh/2026-09-21_13_sludge_decision.py', full=True),
 dict(name='sludge_line', title='污泥线闭环（路线 A）', script='src/dsh/2026-09-21_11_sludge_line_loop_v2.py', full=True),
 dict(name='online_chain', title='在线链路多轨迹评估（门禁+RUL）', script='src/dsh/2026-09-21_08_online_chain_multitraj.py', full=True),
 dict(name='calib_window_sensitivity', title='标定期敏感性（5 段健康期）', script='src/dsh/2026-09-21_07_calib_window_sensitivity.py', full=True),
 dict(name='strategy_sensitivity', title='组合策略倍数敏感性扫描', script='src/dsh/2026-09-21_06_strategy_sensitivity.py', full=True),
 dict(name='ablation_two_regimes', title='消融两套阈值口径重跑', script='src/dsh/2026-09-21_05_ablation_two_regimes.py', full=True),
 dict(name='multitraj_bsm1', title='BSM1 多轨迹稳健性分析', script='src/dsh/2026-09-21_03_bsm1_multitraj.py', full=True),
 dict(name='lanmai_cli', title='接入标定工具自检（lanmai CLI）', script='src/dsh/2026-09-21_04_lanmai_selftest.py', full=False),
 dict(name='lanmai_report', title='企业版样例报告（离线单文件 HTML ×2）', script='src/dsh/2026-09-22_10_lanmai_report_demo.py', full=False),
 dict(name='deck', title='商业计划书 PPT（在官方模板上填内容，30 页）', script='src/dsh/2026-09-22_16_deck_template_fill.py', full=True),
 dict(name='manual', title='生成项目说明书 Word（内嵌 38 张图）', script='src/dsh/2026-09-22_15_manual_docx.py', full=False),
 dict(name='lanmai_serve_smoke', title='本地工作台（lanmai serve）冒烟：首页/样例/上传/标定', script='src/dsh/2026-09-22_11_lanmai_serve_smoketest.py', full=False),
 dict(name='demo_twin', title='交互式数字孪生演示台', script='src/dsh/2026-09-20_15_demo_twin.py', full=True),
 dict(name='alarm_strategy_bsm1', title='组合报警策略评估', script='src/dsh/2026-09-20_14_alarm_strategy.py', full=True),
 dict(name='ratio_rule_bsm1', title='比值判据跨工况检验', script='src/dsh/2026-09-20_13_ratio_rule.py', full=True),
 dict(name='rain_storm_bsm1', title='BSM1 雨/暴雨冲击工况分析', script='src/dsh/2026-09-20_12_bsm1_rain_storm.py', full=True),
 dict(name='influent_bsm1', title='BSM1 进水工况泛化分析', script='src/dsh/2026-09-20_11_bsm1_influent_robustness.py', full=True),
 dict(name='sweep_bsm1', title='BSM1 退化幅值-斜率扫描分析', script='src/dsh/2026-09-20_10_bsm1_sweep_analysis.py', full=True),
 dict(name='figures_bsm1', title='BSM1 数字孪生闭环四图', script='src/dsh/2026-09-20_08_bsm1_figure.py', full=True),
 dict(name='route_b_sim', title='路线 B 整厂仿真（BSM2 + 脱水机退化）', script='src/dsh/2026-09-22_02_bsm2_route_b_sim.py', full=True),
 dict(name='route_b_detect', title='路线 B 检测/RUL/噪声/旁证', script='src/dsh/2026-09-22_03_bsm2_route_b_detect.py', full=True),
 dict(name='route_b_sweep', title='路线 B 幅值/速率扫描（6 场景，各约 64 秒）', script='src/dsh/2026-09-22_04_bsm2_route_b_sweep.py', full=True),
 dict(name='route_b_cond', title='路线 B 补强①：工况条件化 + 同工况对拍差分', script='src/dsh/2026-09-22_05_bsm2_route_b_conditioned.py', full=True),
 dict(name='route_b_drift', title='路线 B 补强②：标定漂移专项', script='src/dsh/2026-09-22_06_bsm2_route_b_drift.py', full=True),
 dict(name='route_b_seasons', title='路线 B 跨相位稳健性（缺哪个相位补哪个，之后汇总）', script='src/dsh/2026-09-22_07_bsm2_route_b_seasons.py', full=True),
 dict(name='route_b_drift_ext', title='路线 B 漂移扩展（10% 幅度 + AR(1) + 对拍样本量）', script='src/dsh/2026-09-22_09_bsm2_route_b_drift_ext.py', full=True),
 dict(name='route_b_freeze_check', title='冻结前数字总检（数字↔结果文件↔文档 + 文件名自检）', script='src/dsh/2026-09-22_08_freeze_check.py', full=True),
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
