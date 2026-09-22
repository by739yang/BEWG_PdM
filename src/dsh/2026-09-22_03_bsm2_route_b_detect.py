# -*- coding: utf-8 -*-
"""路线 B：BSM2 整厂脱水机退化的检测 / RUL / 全厂旁证 / 噪声敏感性（DSH，2026-09-22）
结论骨架（详见 PROJECT_STATE 第 27 节）：
 ① 整厂尺度上，5 个原始可测量按固定参考域标定 → 首报被「进水工况事件」抢跑（健康轨迹同刻同样越限）；
 ② 零误报口径（阈值 = 健康轨迹分数最大值 × 1.02）下，原始量通道要 86 天才能检出 → 晚于真值失效 37 天（负结果）；
 ③ 机理性比值通道「干固体产率 / 湿泥饼量」（= 泥饼含固率，两个都可测）免疫工况漂移：2%% 仪表 + 3%% 日粒度实验室噪声下 9.8 天检出、提前 37.5 天；
 ④ 含噪下 RUL 窗长必须由「退化时标 + 噪声」共同决定：1 天窗误差 26.5 天，10 天窗 13.9 天。
产物：results/2026-09-22/dsh/bsm2_route_b_detect.{json,md,png}、bsm2_route_b_{channel_modes,noise,rul_window}.csv
用法：python src/dsh/2026-09-22_03_bsm2_route_b_detect.py
"""
import os, sys, io, json, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import route_b_common as R
from dual_baseline import frozen_z, topk_score, _scale_floor

D = R.DIR
DEG = 60.0
NL = chr(10)
H = R.load('healthy')
G = R.load('degraded')
FAIL = R.truth_failure(G, DEG)

rows = []
for cols, label in [(R.MON, '5 个原始量'), ([R.RATIO], '比值通道（干固体/湿泥饼量）'), (R.MON_R, '5 原始量 + 比值')]:
    for mode, mlabel in [('q999', '参考域 0.999 分位'), ('zero_fa', '零误报（健康轨迹最大 × 1.02）')]:
        r = R.detect_with(G, H, cols=cols, thr_mode=mode, deg_start=DEG)
        rows.append(dict(通道集=label, 阈值口径=mlabel, 阈值=round(r['阈值'], 3), 健康告警数=r['健康告警数'],
                         健康首报=r['健康首报'], 退化后首报=r['首报'], 检出延迟=r['检出延迟'],
                         真值失效=r['真值失效'], 提前量=r['提前量'], RUL误差_1天窗=r['RUL误差_1天窗'],
                         自适应告警数=r['自适应告警数']))
T1 = pd.DataFrame(rows)

Bh = R.prep(H); REF = R.ref_window(Bh); FL = _scale_floor(Bh, R.MON)
scH = np.asarray(topk_score(frozen_z(Bh, R.MON, REF, state=R.hod(Bh), state_ref=R.hod(REF), floor=FL), 3), dtype=float)
ih = int(np.argmax(scH))
PKG = os.path.dirname(__import__('bsm2_python').__file__)
din = np.genfromtxt(os.path.join(PKG, 'data', 'dyninfluent_bsm2.csv'), delimiter=',', skip_header=1)
QQ, tt = din[:, 15], din[:, 0]
mref = (tt >= 30) & (tt < 45)
mnow = (tt >= H.t_day[ih] - 2) & (tt <= H.t_day[ih] + 2)
q_chg = 100.0 * (QQ[mnow].mean() / QQ[mref].mean() - 1.0)
diag = dict(健康最高分天=round(float(H.t_day[ih]), 2), 健康最高分=round(float(scH[ih]), 2),
            参考域进水均值=round(float(QQ[mref].mean()), 1), 该时刻进水均值=round(float(QQ[mnow].mean()), 1),
            进水变化pct=round(q_chg, 1),
            该时刻泥饼流量=round(float(Bh['泥饼流量'].values[ih]), 2),
            参考域泥饼流量中位=round(float(np.median(REF['泥饼流量'].values)), 2),
            说明='健康轨迹的最高分由进水工况事件（流量上升）驱动，与脱水机退化无关；同刻退化轨迹同样越限，因此固定参考域下原始量的首报是被误报抢跑的。')

nrows = []
for cols, label in [(R.MON, '5 个原始量'), ([R.RATIO], '比值通道')]:
    for rel, lab in [(0.0, 0.0), (0.01, 0.02), (0.02, 0.03), (0.05, 0.05)]:
        if rel == 0.0:
            r = R.detect_with(G, H, cols=cols, thr_mode='zero_fa', deg_start=DEG)
            nrows.append(dict(通道集=label, 仪表噪声=0.0, 实验室噪声=0.0, 阈值中位=round(r['阈值'], 3),
                              健康误报出现次=0, 种子数=1, 检出延迟中位=r['检出延迟'], 检出延迟区间=None,
                              提前量中位=r['提前量'], RUL误差_1天窗中位=r['RUL误差_1天窗']))
        else:
            n = R.noise_median(H, G, cols=cols, rel=rel, lab_rel=lab, seeds=8, thr_mode='zero_fa', deg_start=DEG)
            nrows.append(dict(通道集=label, 仪表噪声=rel, 实验室噪声=lab,
                              阈值中位=(None if n['阈值中位'] is None else round(n['阈值中位'], 3)),
                              健康误报出现次=n['健康误报出现次数'], 种子数=8,
                              检出延迟中位=(None if n['检出延迟中位'] is None else round(n['检出延迟中位'], 2)),
                              检出延迟区间=(None if not n['检出延迟区间'] else [round(x, 2) for x in n['检出延迟区间']]),
                              提前量中位=(None if n['提前量中位'] is None else round(n['提前量中位'], 2)),
                              RUL误差_1天窗中位=(None if n['RUL误差_1天窗中位'] is None else round(n['RUL误差_1天窗中位'], 2))))
T2 = pd.DataFrame(nrows)


def rul_at(y, i0, target=20.0, wd=1, smooth=0, ppd=96):
    y = np.asarray(y, dtype=float)[max(0, i0 - wd * ppd):i0 + 1]
    if smooth > 0:
        y = np.convolve(y, np.ones(smooth) / smooth, mode='valid')
    b, a = np.polyfit(np.arange(len(y), dtype=float), y, 1)
    if b >= -1e-9:
        return None
    return max((target - a) / b - (len(y) - 1), 0.0) / ppd


rrows = []
for wd in (1, 2, 5, 10):
    for sm in (0, 3):
        e = []
        for s in range(12):
            Hn = R.add_noise(H, rel=0.02, lab_rel=0.03, seed=100 + s)
            Gn = R.add_noise(G, rel=0.02, lab_rel=0.03, seed=1000 + s)
            r = R.detect_with(Gn, Hn, cols=[R.RATIO], thr_mode='zero_fa', deg_start=DEG)
            if r['首报索引'] is None or r['提前量'] is None:
                continue
            est = rul_at(Gn[R.RATIO].values, r['首报索引'], wd=wd, smooth=sm)
            if est is not None:
                e.append(abs(est - r['提前量']))
        rrows.append(dict(窗长天=wd, 平滑日=sm, RUL误差中位天=(round(float(np.median(e)), 2) if e else None), 有效样本=len(e)))
T3 = pd.DataFrame(rrows)


def pair(col):
    h2 = H[H.t_day >= 150][col].mean(); g2 = G[G.t_day >= 150][col].mean()
    return dict(通道=col, 末期健康=round(float(h2), 4), 末期退化=round(float(g2), 4),
                同刻配对比pct=round(float(g2 / h2 - 1.0) * 100, 3) if h2 else None)


side = pd.DataFrame([pair(c) for c in ['泥饼流量', '滤液量', '滤液TSS', '干固体产率', '出水氨氮', '出水TSS',
                                       '沼气CH4', '沼气流', '曝气能耗', '泵能耗', '搅拌能耗', '消化罐进泥TSS', '回流污泥TSS']])

out = dict(脚本='2026-09-22_03_bsm2_route_b_detect.py', 天数=float(G.t_day.iloc[-1]), 退化起始=DEG,
           真值失效天=FAIL, 通道集口径表=T1.to_dict('records'), 工况诊断=diag,
           噪声敏感性=T2.to_dict('records'), RUL窗长敏感性=T3.to_dict('records'), 全厂旁证=side.to_dict('records'))
json.dump(out, io.open(os.path.join(D, 'bsm2_route_b_detect.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
T1.to_csv(os.path.join(D, 'bsm2_route_b_channel_modes.csv'), index=False, encoding='utf-8-sig')
T2.to_csv(os.path.join(D, 'bsm2_route_b_noise.csv'), index=False, encoding='utf-8-sig')
T3.to_csv(os.path.join(D, 'bsm2_route_b_rul_window.csv'), index=False, encoding='utf-8-sig')

L = []
W = L.append
W('# 路线 B：BSM2 整厂脱水机退化闭环（DSH，2026-09-22）' + NL)
W('> 官方整厂类 BSM2Base（二沉池 120 态 + ASM1 五池 + ADM1 消化罐 + 浓缩/脱水/储泥，官方初值）；退化注入官方 Dewatering 的 dw_par[0]（泥饼目标含固率 28%% → 18%%，60 天斜坡，起始第 60 天）。' + NL)
W('> 真值失效 = 泥饼含固率 < 20%% 持续 1 天：**第 %.2f 天**。仿真 160 天、约 0.4 秒/模拟天、零 NaN。' % FAIL + NL)
W('## 1. 通道集 × 阈值口径' + NL)
W(T1.to_markdown(index=False) + NL)
W('**负结果（必须写进材料）**：整厂尺度上，5 个原始可测量在固定参考域下**检不出**这次退化 —— 零误报口径要 86.11 天（第 146 天），已晚于失效 37 天；而参考域 0.999 分位口径下的首报 66.11 天其实是**误报抢跑**（健康轨迹同刻分数 19.18、同样越限，只是没凑够连续 4 点）。' + NL)
W('**工况诊断**：健康轨迹最高分出现在第 %.2f 天，该时刻进水流量比参考域高 %+.1f%%（%.0f → %.0f m³/d），泥饼流量中位 %.2f → 该时刻 %.2f —— 这是**进水工况事件**（降雨/季节）驱动的分数抬升，与设备退化无关。' % (
    diag['健康最高分天'], diag['进水变化pct'], diag['参考域进水均值'], diag['该时刻进水均值'], diag['参考域泥饼流量中位'], diag['该时刻泥饼流量']) + NL)
W('## 2. 噪声敏感性（零误报口径）' + NL)
W(T2.to_markdown(index=False) + NL)
W('**正结果**：机理性比值通道「干固体产率 / 湿泥饼量」（两者都可测：皮带秤/流量计 + 实验室干固体）**免疫进水工况漂移**，健康轨迹 0 误报；在 2%% 仪表 + 3%% 日粒度实验室噪声下，8 个噪声实现里检出延迟中位 **9.8 天**（区间 5.0–11.0 天）、提前量中位 37.5 天。' + NL)
W('> 注：模型里浓缩/脱水是**理想单元**（无堵塞、无动力学），故比值通道无噪延迟 0.04 天是理想上界，不可外推；对外用含噪中位数。' + NL)
W('## 3. RUL 拟合窗长选择（含噪，比值通道首报处）' + NL)
W(T3.to_markdown(index=False) + NL)
W('**规则修正（对应设计原则⑥）**：含噪时窗长不能只按退化时标取短 —— 1 天窗在 3%% 日粒度实验室噪声下误差中位 26.5 天，10 天窗降到 13.9 天。建议：**窗内退化幅度需明显大于测量噪声（约 ≥3 倍），否则先做 3–7 日平滑再拟合**。' + NL)
W('## 4. 全厂旁证（末 10 天 vs 退化前；同刻配对）' + NL)
W(side.to_markdown(index=False) + NL)
W('**诚实结论**：该退化在**沼气、能耗、出水水质上几乎不可见**（沼气 −0.013%%、泵能耗 +0.004%%、出水 TSS −0.030%%）—— 因为 TSS 去除率不变，只是泥饼干湿与流量分配改变。所以这类故障**只能靠污泥线本体（设备级物料平衡）的量发现**，不能指望全厂大数据告警。' + NL)
io.open(os.path.join(D, 'bsm2_route_b_detect.md'), 'w', encoding='utf-8', newline=NL).write(NL.join(L))

import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei']; plt.rcParams['axes.unicode_minus'] = False
fig, ax = plt.subplots(2, 2, figsize=(11.5, 7.5))
ax[0, 0].plot(H.t_day, H['泥饼含固率'], color='#1f77b4', lw=1, label='健康')
ax[0, 0].plot(G.t_day, G['泥饼含固率'], color='#d62728', lw=1, label='退化')
ax[0, 0].axhline(20, color='#2ca02c', ls='--', lw=1); ax[0, 0].text(4, 20.4, '处置要求 20%', color='#2ca02c', fontsize=8)
if FAIL:
    ax[0, 0].axvline(FAIL, color='#2ca02c', ls=':', lw=1)
ax[0, 0].axvline(DEG, color='#7f7f7f', ls=':', lw=1)
ax[0, 0].set_title('① 泥饼含固率（机理量，BSM2 整厂）'); ax[0, 0].set_ylabel('%'); ax[0, 0].legend(fontsize=8); ax[0, 0].grid(alpha=.3)
ax[0, 1].plot(H.t_day, H['泥饼流量'], color='#1f77b4', lw=.8, label='健康')
ax[0, 1].plot(G.t_day, G['泥饼流量'], color='#d62728', lw=.8, label='退化')
ax[0, 1].axvline(DEG, color='#7f7f7f', ls=':', lw=1)
ax[0, 1].annotate('第 %.0f 天：进水 %+.0f%% 的工况事件\n（原始量误报抢跑）' % (diag['健康最高分天'], diag['进水变化pct']),
                  xy=(diag['健康最高分天'], float(H['泥饼流量'].values[ih])), xytext=(15, 20), textcoords='offset points',
                  fontsize=8, color='#ff7f0e', arrowprops=dict(arrowstyle='->', color='#ff7f0e', lw=.8))
ax[0, 1].set_title('② 湿泥饼产量（原始可测量，被工况漂移污染）'); ax[0, 1].set_ylabel('m³/d'); ax[0, 1].legend(fontsize=8); ax[0, 1].grid(alpha=.3)
ax[1, 0].plot(H.t_day, H['干固体产率'] / H['泥饼流量'] / 10, color='#1f77b4', lw=1, label='健康')
ax[1, 0].plot(G.t_day, G['干固体产率'] / G['泥饼流量'] / 10, color='#d62728', lw=1, label='退化')
ax[1, 0].axhline(20, color='#2ca02c', ls='--', lw=1); ax[1, 0].axvline(DEG, color='#7f7f7f', ls=':', lw=1)
ax[1, 0].set_title('③ 比值通道：干固体/湿泥饼量（= 泥饼含固率，免疫工况漂移）'); ax[1, 0].set_xlabel('天'); ax[1, 0].set_ylabel('%'); ax[1, 0].legend(fontsize=8); ax[1, 0].grid(alpha=.3)
r_raw = R.detect_with(G, H, cols=R.MON, thr_mode='zero_fa', deg_start=DEG)
r_rat = R.detect_with(G, H, cols=[R.RATIO], thr_mode='zero_fa', deg_start=DEG)
ax[1, 1].plot(G.t_day, r_raw['分数'], color='#9467bd', lw=.8, label='5 原始量')
ax[1, 1].plot(G.t_day, r_rat['分数'] / max(1e-9, np.max(r_rat['分数'])) * np.max(r_raw['分数']), color='#d62728', lw=.8, label='比值通道（归一化到同轴）')
ax[1, 1].axhline(r_raw['阈值'], color='#9467bd', ls='--', lw=1)
ax[1, 1].axvline(DEG, color='#7f7f7f', ls=':', lw=1)
if r_raw['首报']:
    ax[1, 1].axvline(r_raw['首报'], color='#9467bd', ls='-', lw=1)
if r_rat['首报']:
    ax[1, 1].axvline(r_rat['首报'], color='#d62728', ls='-', lw=1)
ax[1, 1].text(DEG + 1, r_raw['阈值'] * .85, '原始量零误报阈值 %.1f → 首报第 %.0f 天' % (r_raw['阈值'], r_raw['首报'] or 0), fontsize=8, color='#9467bd')
ax[1, 1].text(DEG + 1, r_raw['阈值'] * .55, '比值通道首报第 %.2f 天' % (r_rat['首报'] or 0), fontsize=8, color='#d62728')
ax[1, 1].set_title('④ 检测分数（零误报口径）'); ax[1, 1].set_xlabel('天'); ax[1, 1].legend(fontsize=8); ax[1, 1].grid(alpha=.3)
fig.suptitle('路线 B：BSM2 整厂脱水机退化 —— 原始量检不出，设备级比值量检得出', fontsize=13)
fig.tight_layout(); fig.savefig(os.path.join(D, 'bsm2_route_b_detect.png'), dpi=130)
print(T1.to_string(index=False)); print(); print(T2.to_string(index=False)); print(); print(T3.to_string(index=False))
print(); print(json.dumps(diag, ensure_ascii=False, indent=1))
