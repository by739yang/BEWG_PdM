# -*- coding: utf-8 -*-
"""生成两份企业版样例报告（离线单文件 HTML）——run_all 的阶段 lanmai_report 用（DSH，2026-09-22）
数据与基线都取自仓库内已提交的 results/2026-09-21/lanmai_demo/，因此可一键复现：
  BSM1（IWA 标准模型仿真退化轨迹）与 MetroPT-3（真实地铁空压机 214 天）。
用法：python src/dsh/2026-09-22_10_lanmai_report_demo.py
"""
import os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
D = os.path.join(ROOT, 'results', '2026-09-21', 'lanmai_demo')
JOBS = [
    ('bsm1_120d_degraded_ts.csv', 'bsm1_baseline.json', 'demo/report_bsm1.html',
     '澜脉 · 设备健康报告（示例：BSM1 数字孪生退化轨迹）', '1D'),
    ('metropt3_prepared.csv.gz', 'metropt3_baseline.json', 'demo/report_metropt3.html',
     '澜脉 · 设备健康报告（示例：MetroPT-3 真实空压机 214 天）', None),
]
env = dict(os.environ)
env['PYTHONPATH'] = os.path.join(ROOT, 'src') + (os.pathsep + env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
for data, base, out, title, warm in JOBS:
    cmd = [sys.executable, '-m', 'lanmai', 'report',
           '--data', os.path.join(D, data), '--baseline', os.path.join(D, base),
           '--out', os.path.join(ROOT, out), '--title', title]
    if warm:
        cmd += ['--warmup', warm]
    print('[样例报告] %s <- %s' % (out, data))
    subprocess.run(cmd, cwd=ROOT, env=env, check=True)
print('两份样例报告已生成：demo/report_bsm1.html、demo/report_metropt3.html')
