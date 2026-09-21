# -*- coding: utf-8 -*-
"""路线 B 冒烟测试：官方 BSM2 整厂类 + 官方初值，能否稳定推进（ADM1 刚性 / 耗时量化）。
只跑 N 天，报告：是否 NaN、每模拟天耗时、Settler 输出是否有限。
"""
import time, numpy as np, json, os
from bsm2_python.bsm2_base import BSM2Base

DAYS = float(os.environ.get('PROBE_DAYS', '5'))
t0 = time.time()
p = BSM2Base(endtime=DAYS)
t_build = time.time() - t0
n = len(p.simtime)
print('构建 %.1f s，模拟步数 %d，步长 %.6f 天，总时长 %.2f 天' % (t_build, n, float(p.timesteps[0]), float(p.simtime[-1])))
t1 = time.time()
ok = True
err = None
for i in range(n):
    try:
        p.step(i)
    except Exception as e:
        ok = False; err = '%s: %s' % (type(e).__name__, e); break
    if (i + 1) % max(1, n // 10) == 0:
        print('  步 %d/%d  用时 %.1f s' % (i + 1, n, time.time() - t1))
t_run = time.time() - t1
fin = lambda a: int(np.sum(~np.isfinite(np.asarray(a, dtype=float))))
res = dict(
    days=DAYS, steps_run=(i + 1), build_s=round(t_build, 2), run_s=round(t_run, 2),
    s_per_day=round(t_run / max(1e-9, DAYS * (i + 1) / n), 3), ok=ok, err=err,
    nan_y_eff=fin(p.y_eff_all[:i + 1]), nan_settler_eff=fin(p.y_eff_all[:i + 1]))
print(json.dumps(res, ensure_ascii=False, indent=1))
os.makedirs('results/2026-09-22/dsh', exist_ok=True)
json.dump(res, open('results/2026-09-22/dsh/bsm2_route_b_probe.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
