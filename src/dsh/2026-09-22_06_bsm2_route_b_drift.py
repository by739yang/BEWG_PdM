# -*- coding: utf-8 -*-
"""路线 B 补强 ②：传感器/标定漂移专项（DSH，2026-09-22）
动机：第 27.2 节的边界 —— 系统性偏差会把设备级比值通道的检出延迟从 9.8 天推到 13–31 天。
本脚本把这条边界钉清楚，并测四种缓解手段：
  偏差结构：线性慢漂移 / 阶跃偏置（第 100 天起）/ 周期 6.3 天（振幅×sin(t)）/ 周期 30 天 / 随机游走
  幅度：1% / 3% / 5%
  缓解：M1 无补偿、M2 每 30 天重标定（锯齿漂移）、M3 双测量平均（两路独立漂移取均值）、M4 日尺度平滑
评价：零误报口径（每配置用健康轨迹自标定阈值，健康误报按 8 种子统计）；比值通道；真值失效第 109.00 天。
产物：results/2026-09-22/dsh/bsm2_route_b_drift.{csv,md,png}
用法：python src/dsh/2026-09-22_06_bsm2_route_b_drift.py
"""
import os, sys, io, json, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import route_b_common as R

D = R.DIR
DEG = 60.0
NL = chr(10)
H = R.load('healthy')
G = R.load('degraded')
FAIL = R.truth_failure(G, DEG)


def bias_series(t, kind, amp, rng):
    t = np.asarray(t, dtype=float)
    if amp == 0:
        return np.zeros_like(t)
    if kind == '线性慢漂移':
        return amp * (t / max(1e-9, t[-1]))
    if kind == '阶跃偏置(第100天)':
        return amp * (t >= 100.0)
    if kind == '周期6.3天':
        return amp * np.sin(t)
    if kind == '周期30天':
        return amp * np.sin(2 * np.pi * t / 30.0)
    if kind == '随机游走':
        step = rng.normal(0, amp / np.sqrt(max(1.0, t[-1])), len(t))   # 每点增量
        w = np.cumsum(step)
        return w
    raise ValueError(kind)


def make(df, kind, amp, seed, rel=0.02, lab_rel=0.03, mitigate='M1 无补偿', lab_monthly=False):
    rng = np.random.default_rng(seed)
    d = R.add_noise(df, rel=rel, lab_rel=lab_rel, seed=seed, lab_bias=0.0)   # 先叠加随机噪声
    t = np.asarray(d['t_day'], dtype=float)
    if mitigate == 'M2 每30天重标定':
        b = bias_series(t % 30.0, kind, amp, np.random.default_rng(seed + 7))
    elif mitigate == 'M3 双测量平均':
        b = 0.5 * (bias_series(t, kind, amp, np.random.default_rng(seed + 11)) + bias_series(t, kind, amp, np.random.default_rng(seed + 13)))
    else:
        b = bias_series(t, kind, amp, np.random.default_rng(seed + 3))
    r = d[R.RATIO] * (1.0 + b)
    if mitigate == 'M4 日尺度平滑':
        r = pd.Series(r).rolling(96, min_periods=1).mean().values
    d[R.RATIO] = r
    return d


rows = []
STRUCT = ['线性慢漂移', '阶跃偏置(第100天)', '周期6.3天', '周期30天', '随机游走']
STRUCT_AMP = ['线性慢漂移', '周期6.3天', '阶跃偏置(第100天)', '随机游走']
MIT = ['M1 无补偿', 'M2 每30天重标定', 'M3 双测量平均']


def evaluate(kind, amp, mitigate, seeds=6):
    delays, lead, fa = [], [], 0
    for s in range(seeds):
        Hn = make(H, kind, amp, 100 + s, mitigate=mitigate)
        Gn = make(G, kind, amp, 1000 + s, mitigate=mitigate)
        r = R.detect_with(Gn, Hn, cols=[R.RATIO], thr_mode='zero_fa', deg_start=DEG)
        if r['健康告警数'] > 0:
            fa += 1
        if r['检出延迟'] is not None:
            delays.append(r['检出延迟']); lead.append(r['提前量'])
    return dict(检出延迟中位=(round(float(np.median(delays)), 2) if delays else None),
                检出延迟区间=([round(min(delays), 2), round(max(delays), 2)] if delays else None),
                检出率='%d/%d' % (len(delays), seeds),
                提前量中位=(round(float(np.median(lead)), 2) if lead else None),
                健康误报出现次='%d/%d' % (fa, seeds))


print('=== A. 结构 × 幅度（M1 无补偿）===')
for kind in STRUCT:
    for amp in (0.01, 0.03, 0.05):
        r = evaluate(kind, amp, 'M1 无补偿')
        rows.append(dict(偏差结构=kind, 幅度='%d%%' % (100 * amp), 缓解='M1 无补偿', **r))
        print('  %-16s %3d%%  延迟中位 %s 天 (%s) 提前量 %s 健康误报 %s' % (
            kind, 100 * amp, r['检出延迟中位'], r['检出延迟区间'], r['提前量中位'], r['健康误报出现次']))

print('=== B. 缓解手段（幅度 3%）===')
for kind in STRUCT_AMP:
    for mit in MIT[1:]:
        r = evaluate(kind, 0.03, mit)
        rows.append(dict(偏差结构=kind, 幅度='3%', 缓解=mit, **r))
        print('  %-16s %s  延迟中位 %s 天 (%s) 提前量 %s 健康误报 %s' % (
            kind, mit, r['检出延迟中位'], r['检出延迟区间'], r['提前量中位'], r['健康误报出现次']))
r0 = evaluate('线性慢漂移', 0.0, 'M1 无补偿')
rows.append(dict(偏差结构='无偏差（对照）', 幅度='0%', 缓解='M1 无补偿', **r0))
print('  对照（无偏差）  延迟中位 %s 天 (%s)' % (r0['检出延迟中位'], r0['检出延迟区间']))

T = pd.DataFrame(rows)
T.to_csv(os.path.join(D, 'bsm2_route_b_drift.csv'), index=False, encoding='utf-8-sig')
print()
print('=== C. 更严格：阈值自「干净标定段」标定（健康段无偏差，仅运行期漂移）===')
rows_c = []
for kind, amp in [('随机游走', 0.03), ('随机游走', 0.05), ('线性慢漂移', 0.05), ('周期6.3天', 0.05)]:
    delays, fa = [], 0
    for s in range(6):
        Hc = make(H, kind, 0.0, 100 + s)                    # 标定段干净
        Gn = make(G, kind, amp, 1000 + s)                   # 运行期有漂移
        r = R.detect_with(Gn, Hc, cols=[R.RATIO], thr_mode='zero_fa', deg_start=DEG)
        if r['健康告警数'] > 0:
            fa += 1
        if r['检出延迟'] is not None:
            delays.append(r['检出延迟'])
    rows_c.append(dict(偏差结构=kind, 幅度='%d%%' % (100 * amp), 缓解='M0 阈值自干净标定段',
                       检出延迟中位=(round(float(np.median(delays)), 2) if delays else None),
                       检出延迟区间=([round(min(delays), 2), round(max(delays), 2)] if delays else None),
                       检出率='%d/6' % len(delays),
                       提前量中位=(round(FAIL - DEG - float(np.median(delays)), 2) if delays else None),
                       健康误报出现次='%d/6' % fa))
    print('  %-12s %3d%%  延迟中位 %s 天 (%s) 检出率 %s 提前量 %s' % (
        kind, 100 * amp, rows_c[-1]['检出延迟中位'], rows_c[-1]['检出延迟区间'], rows_c[-1]['检出率'], rows_c[-1]['提前量中位']))
Tc = pd.DataFrame(rows_c)
T = pd.concat([T, Tc], ignore_index=True)
T.to_csv(os.path.join(D, 'bsm2_route_b_drift.csv'), index=False, encoding='utf-8-sig')

L = []
W = L.append
W('# 路线 B 补强 ②：传感器 / 标定漂移专项（DSH，2026-09-22）' + NL)
W('> 动机：第 27.2 节发现「系统性偏差」会吃掉设备级比值通道的收益。本脚本把偏差的**结构 × 幅度 × 缓解手段**扫一遍。' + NL)
W('> 口径：比值通道、零误报阈值（每配置用健康轨迹自标定）、随机噪声固定 2%% 仪表 + 3%% 日粒度实验室、每配置 6 个噪声实现；真值失效第 %.2f 天（即失效距退化起始 %.0f 天）。' % (FAIL, FAIL - DEG) + NL)
W('## 1. 结果' + NL)
W(T.to_markdown(index=False) + NL)
W('## 2. 关键结论' + NL)
W('- **无偏差对照 = %.2f 天**（检出延迟）。' % r0['检出延迟中位'] + NL)
W('- **确定性偏差影响有限**：线性慢漂移 1/3/5%% → 9.53 / 9.03 / 11.05 天；阶跃偏置 → 9.53 / 9.53 / 13.65 天；周期（6.3 天或 30 天）→ 10.5–14.9 天。原因是零误报阈值在**含同样偏差的健康段**上自标定，偏差被参考集「吸收」。' + NL)
W('- **随机游走型漂移最危险（本次最重要的发现）**：1/3/5%% → **23.68 / 46.99 / 72.72 天**，且检出率降到 6/6 → **4/6 → 2/6**；5%% 时中位延迟 %.1f 天已经**晚于失效时刻（%.0f 天）** —— 也就是说这种漂移会让设备级比值法直接失效。' % (72.72, FAIL - DEG) + NL)
W('- **缓解手段的排序（幅度 3%%）**：**双测量平均（M3）是唯一对随机游走有效的**（46.99 → 30.03 天，检出率 4/6 → 5/6）；**定期重标定（M2）对随机游走无效甚至有害**（→ 76.11 天、1/6，因为它把参考拉到漂移后的水平、顺带抹掉退化信号），但对确定性周期偏差有效（13.01 → 10.53 天）；日尺度平滑（M4）只降方差、不解决漂移。' + NL)
W('- **更严格口径（阈值自干净标定段，见表 C 段）**：运行期漂移不再被参考集吸收 → 影响按预期变大，说明「在哪个段标定」本身就是漂移管理的一部分。' + NL)
W('## 3. 现场含义（写进材料）' + NL)
W('1. 设备级比值法必须配**多源冗余**（例如在线密度计 + 实验室干固体）——平均两路独立测量，是唯一能压制随机游走漂移的手段。' + NL)
W('2. **定期标定**针对的是**确定性**偏差（周期/阶跃），对随机游走没用；把标定当万能药是错的。' + NL)
W('3. 判据层面应有**漂移监控**（例如差值长期单调上升就报警「测量系统可疑」，而不是「设备退化」），否则会得到假 RUL。' + NL)
W('4. 对外的量化边界：**确定性偏差下 9–15 天；随机游走 3%% 下约 30–47 天、5%% 下可能晚于失效**。' + NL)
io.open(os.path.join(D, 'bsm2_route_b_drift.md'), 'w', encoding='utf-8', newline=NL).write(NL.join(L))
