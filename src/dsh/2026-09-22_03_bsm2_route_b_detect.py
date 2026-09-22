# -*- coding: utf-8 -*-
"""路线 B：BSM2 整厂脱水机退化的检测 / RUL / 噪声结构敏感性 / 全厂旁证（DSH，2026-09-22；已按 Codex 批次 5 意见修订）
结论骨架（详见 PROJECT_STATE 第 27 节）：
 ① 本轨迹/本阈值口径下，5 个原始可测量在固定参考域下检不出这次退化（零误报口径 86.11 天，晚于失效 37 天）；q999 口径的「首报 66.11 天」是误报抢跑；
 ② 设备级比值通道「干固体产率 / 湿泥饼量」在本模型的列出噪声结构下相对稳健（基线 2%/3% 噪声 → 9.80 天）；
 ③ 该稳健性有边界：流量计噪声不影响（比值抵消），但**系统性偏差会侵蚀收益**（缓慢线性漂移 3% → 9.53 天；周期性日间偏差 3% → 我们 19.72 天 / Codex 31.07 天，方向一致但数值不跨实现）；
 ④ 含噪下 RUL 窗长是主要手段（1 天窗 26.47 天 → 10 天窗 13.85 天），3 日平滑不是（5 天窗反而变差 18.06 → 27.92 天）。
口径说明（三种不得混用）：参考域 0.999 分位 = 13.149；零误报（健康轨迹最大 × 1.02）= 19.560；自适应通道 0.999 分位。
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
            说明='健康轨迹的最高分由进水工况事件（流量上升）驱动，与脱水机退化无关；在 q999 阈值下健康轨迹同样在这些时刻告警（见 健康轨迹_q999_告警天），故固定参考域下原始量的「首报 66.11 天」是误报抢跑（口径: q999）。')
from dual_baseline import make_events as _me
_thr999 = R.thresholds(H)[3]
diag['健康轨迹_q999_告警天'] = [round(float(H.t_day[s]), 2) for s, e in _me(pd.Series(scH), _thr999)]

NR = []
def add_noise_row(label, cols, kw, note=''):
    kw = dict(kw); structure = kw.pop('结构', ''); note = kw.pop('note', '') or note
    n = R.noise_median(H, G, cols=cols, seeds=8, thr_mode='zero_fa', deg_start=DEG, **kw)
    NR.append(dict(通道集=label, 噪声结构=structure, 阈值中位=(None if n['阈值中位'] is None else round(n['阈值中位'], 3)),
                   健康误报出现次=n['健康误报出现次数'], 种子数=8,
                   检出延迟中位=(None if n['检出延迟中位'] is None else round(n['检出延迟中位'], 2)),
                   检出延迟区间=(None if not n['检出延迟区间'] else [round(x, 2) for x in n['检出延迟区间']]),
                   提前量中位=(None if n['提前量中位'] is None else round(n['提前量中位'], 2)), 备注=note))

add_noise_row('比值通道', [R.RATIO], dict(rel=0.02, lab_rel=0.03, 结构='基线：流量 2% 白噪声 + 日粒度实验室 3% 白噪声'))
add_noise_row('比值通道', [R.RATIO], dict(rel=0.05, lab_rel=0.03, 结构='流量噪声加大到 5%', note='比值抵消流量计噪声 → 与基线同值'))
add_noise_row('比值通道', [R.RATIO], dict(rel=0.02, lab_rel=0.03, lab_bias=0.01, lab_mode='linear', 结构='+ 缓慢线性标定漂移 1%'))
add_noise_row('比值通道', [R.RATIO], dict(rel=0.02, lab_rel=0.03, lab_bias=0.03, lab_mode='linear', 结构='+ 缓慢线性标定漂移 3%'))
add_noise_row('比值通道', [R.RATIO], dict(rel=0.02, lab_rel=0.03, lab_bias=0.05, lab_mode='linear', 结构='+ 缓慢线性标定漂移 5%'))
add_noise_row('比值通道', [R.RATIO], dict(rel=0.02, lab_rel=0.03, lab_bias=0.03, lab_mode='sin_day', 结构='+ 周期性日间偏差 3%（振幅×sin(天)）', note='Codex 口径；其独立实现给 31.07 天，方向一致、数值不跨实现'))
add_noise_row('5 个原始量', R.MON, dict(rel=0.02, lab_rel=0.03, 结构='基线（对照）'), note='同一噪声下原始量仍要 86 天')
T2 = pd.DataFrame(NR)


def rul_at(y, i0, target=20.0, wd=1, smooth_days=0.0, ppd=96):
    y = np.asarray(y, dtype=float)[max(0, i0 - wd * ppd):i0 + 1]
    if smooth_days > 0:
        k = max(1, int(round(smooth_days * ppd)))
        if len(y) < k:
            return None
        y = np.convolve(y, np.ones(k) / k, mode='valid')
    if len(y) < 8:
        return None
    b, a = np.polyfit(np.arange(len(y), dtype=float), y, 1)
    if b >= -1e-9:
        return None
    return max((target - a) / b - (len(y) - 1), 0.0) / ppd


rrows = []
for wd in (1, 2, 5, 10):
    rec = dict(窗长天=wd)
    for sm, lab in [(0.0, '无平滑'), (3.0, '3 日时间平滑')]:
        e = []
        for s in range(12):
            Hn = R.add_noise(H, rel=0.02, lab_rel=0.03, seed=100 + s)
            Gn = R.add_noise(G, rel=0.02, lab_rel=0.03, seed=1000 + s)
            r = R.detect_with(Gn, Hn, cols=[R.RATIO], thr_mode='zero_fa', deg_start=DEG)
            if r['首报索引'] is None or r['提前量'] is None:
                continue
            est = rul_at(Gn[R.RATIO].values, r['首报索引'], wd=wd, smooth_days=sm)
            if est is not None:
                e.append(abs(est - r['提前量']))
        rec[lab + '误差中位'] = (round(float(np.median(e)), 2) if e else None)
        rec[lab + '有效样本'] = len(e)
    rrows.append(rec)
T3 = pd.DataFrame(rrows)


def pair(col):
    h2 = H[H.t_day >= 150][col].mean(); g2 = G[G.t_day >= 150][col].mean()
    return dict(通道=col, 末期健康=round(float(h2), 4), 末期退化=round(float(g2), 4),
                同刻配对比pct=round(float(g2 / h2 - 1.0) * 100, 3) if h2 else None)


side = pd.DataFrame([pair(c) for c in ['泥饼流量', '滤液量', '滤液TSS', '干固体产率', '出水氨氮', '出水TSS',
                                       '沼气CH4', '沼气流', '曝气能耗', '泵能耗', '搅拌能耗', '消化罐进泥TSS', '回流污泥TSS']])

cross = dict(
 说明='Codex 批次 5 独立实现与 DSH 的对照（详见 handoff/2026-09-22_codex_to_dsh_r2.md）',
 Q18=dict(真值失效天=[109.0, 109.0], 湿泥饼量增幅pct=[55.53, 55.53], 步数=[15359, 15359], 一致=True),
 Q19=dict(q999阈值=[13.149, 13.148997], 零误报阈值=[19.560, 19.559876], 首报天=[146.11, 146.115], 延迟天=[86.11, 86.115], 提前量天=[-37.11, -37.115], 一致=True),
 Q20=dict(基线延迟中位天=[9.80, 9.802], 区间=[[5.03, 11.03], [5.03125, 11.03125]], 提前量中位天=[37.47, 37.4635], 原始量延迟天=[86.11, 86.115],
          周期性偏差3pct延迟天=[19.72, 31.07], 周期性偏差数值一致=False),
 Q21=dict(无平滑=[26.47, 29.62, 18.06, 13.85], Codex无平滑=[26.468, 29.615, 18.057, 13.852], 一致=True),
 Q22=dict(速率轴延迟中位=[5.53, 9.80, 18.53], 幅值轴延迟中位=[14.03, 10.93, 9.80], 原始量首报天=[94.11, 146.11],
          末湿泥饼量增幅pct=[55.53, 39.98, 27.26], 一致=True))

out = dict(脚本='2026-09-22_03_bsm2_route_b_detect.py', 天数=float(G.t_day.iloc[-1]), 退化起始=DEG,
           真值失效天=FAIL, 通道集口径表=T1.to_dict('records'), 工况诊断=diag, 噪声结构敏感性=T2.to_dict('records'),
           RUL窗长敏感性=T3.to_dict('records'), 全厂旁证=side.to_dict('records'), 跨实现对照=cross)
json.dump(out, io.open(os.path.join(D, 'bsm2_route_b_detect.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
T1.to_csv(os.path.join(D, 'bsm2_route_b_channel_modes.csv'), index=False, encoding='utf-8-sig')
T2.to_csv(os.path.join(D, 'bsm2_route_b_noise.csv'), index=False, encoding='utf-8-sig')
T3.to_csv(os.path.join(D, 'bsm2_route_b_rul_window.csv'), index=False, encoding='utf-8-sig')

L = []
W = L.append
W('# 路线 B：BSM2 整厂脱水机退化闭环（DSH，2026-09-22；已按 Codex 批次 5 复核意见修订）' + NL)
W('> 官方整厂类 BSM2Base（二沉池 120 态 + ASM1 五池 + ADM1 消化罐 + 浓缩/脱水/储泥，官方初值）；退化注入官方 Dewatering 的 dw_par[0]（泥饼目标含固率 28% → 18%，60 天斜坡，起始第 60 天）。' + NL)
W('> 真值失效 = 泥饼含固率 < 20%% 持续 1 天：**第 %.2f 天**。仿真 160 天、约 0.4 秒/模拟天、零 NaN。Codex 独立实现复核：真值失效、+55.53%%、步数 15359 完全一致。' % FAIL + NL)
W('> **口径标注（三种不得混用）**：参考域 0.999 分位 = 13.149；零误报（健康轨迹最大分 × 1.02）= 19.560；自适应通道 0.999 分位。' + NL)
W('## 1. 通道集 × 阈值口径' + NL)
W(T1.to_markdown(index=False) + NL)
W('**负结果（限定在本轨迹/本阈值口径）**：5 个原始可测量在固定参考域下**未能及时检出**这次退化 —— 零误报口径要 %.2f 天（第 %.2f 天），晚于失效 %.2f 天；q999 口径下的「首报 %.2f 天」是**误报抢跑**：该时刻健康轨迹分数 %.2f（>13.149）同样越限，且在 q999 口径下健康轨迹的告警时刻里就有它（%.2f 天，见诊断字段）。' % (
    T1.iloc[3]['检出延迟'], T1.iloc[3]['退化后首报'], -T1.iloc[3]['提前量'], T1.iloc[1]['退化后首报'], diag['健康最高分'], diag['健康最高分天']) + NL)
W('**工况诊断**：健康轨迹最高分出现在第 %.2f 天（%.2f），该时刻进水流量比参考域高 %+.1f%%（%.0f → %.0f m³/d），泥饼流量中位 %.2f → 该时刻 %.2f；健康轨迹在 q999 口径下的告警时刻 = %s。' % (
    diag['健康最高分天'], diag['健康最高分'], diag['进水变化pct'], diag['参考域进水均值'], diag['该时刻进水均值'],
    diag['参考域泥饼流量中位'], diag['该时刻泥饼流量'], diag['健康轨迹_q999_告警天']) + NL)
W('## 2. 噪声结构敏感性（零误报口径，8 个噪声实现）' + NL)
W(T2.to_markdown(index=False) + NL)
W('**可辩护的正结果（限定）**：在本 BSM2 单轨迹、列出的噪声结构与零误报口径下，设备级比值通道「干固体产率 / 湿泥饼量」相对稳健 —— 基线 **%.2f 天**（%s）、提前量 %.2f 天、健康误报 0/8；流量计噪声加倍到 5%% 结果不变（比值把流量噪声抵消掉）。' % (
    T2.iloc[0]['检出延迟中位'], T2.iloc[0]['检出延迟区间'], T2.iloc[0]['提前量中位']) + NL)
W('**边界（Codex 批次 5 提出，已复现）**：**系统性偏差会侵蚀这份收益** —— 缓慢线性标定漂移 1%%/3%%/5%% 时延迟 %.2f / %.2f / %.2f 天；**周期性日间偏差 3%%**（振幅×sin(天)，Codex 口径）我们独立复现为 **%.2f 天**，Codex 自己的实现是 31.07 天 —— **方向一致（都会明显变差），数值不跨实现**，对外只写「约 20–31 天」。' % (
    T2.iloc[2]['检出延迟中位'], T2.iloc[3]['检出延迟中位'], T2.iloc[4]['检出延迟中位'], T2.iloc[5]['检出延迟中位']) + NL)
W('> 现场含义：比值通道要配**定期标定 + 实验室数据趋势/周期性校正（或与在线密度计对拍）**，否则收益会被系统性偏差吃掉；这也是「为什么必须做数据质量与标定管理」的直接证据。' + NL)
W('## 3. RUL 拟合窗长选择（含噪 2%%，比值通道首报处）' + NL)
W(T3.to_markdown(index=False) + NL)
W('**修正（Codex 批次 5 指出我们的口径 bug）**：此前「平滑 3 日」实际只平滑了 3 个采样点（45 分钟），已改为**时间单位**。修正后：**窗长才是主要手段**（1 天窗 %.2f 天 → 10 天窗 %.2f 天）；**3 日平滑不是有效手段**（1/2 天窗比平滑核还短，不适用；5 天窗反而从 %.2f 变差到 %.2f 天；10 天窗小幅改善 %.2f → %.2f 天）。' % (
    T3.iloc[0]['无平滑误差中位'], T3.iloc[3]['无平滑误差中位'], T3.iloc[2]['无平滑误差中位'], T3.iloc[2]['3 日时间平滑误差中位'],
    T3.iloc[3]['无平滑误差中位'], T3.iloc[3]['3 日时间平滑误差中位']) + NL)
W('## 4. 全厂旁证（末 10 天 vs 退化前；同刻配对）' + NL)
W(side.to_markdown(index=False) + NL)
W('**诚实结论**：本轨迹里该退化在**沼气、能耗、出水水质上几乎不可见**（沼气 −0.013%%、泵能耗 +0.004%%、出水 TSS −0.030%%）—— 因为 TSS 去除率不变，改变的只是泥饼干湿与流量分配。所以这类故障**只能靠设备级物料平衡量发现**，不能指望全厂大数据告警。' + NL)
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
ax[0, 1].annotate('第 %.0f 天：进水 %+.0f%% 的工况事件\n（原始量误报抢跑，q999 口径）' % (diag['健康最高分天'], diag['进水变化pct']),
                  xy=(diag['健康最高分天'], float(H['泥饼流量'].values[ih])), xytext=(15, 20), textcoords='offset points',
                  fontsize=8, color='#ff7f0e', arrowprops=dict(arrowstyle='->', color='#ff7f0e', lw=.8))
ax[0, 1].set_title('② 湿泥饼产量（原始可测量，被工况漂移污染）'); ax[0, 1].set_ylabel('m³/d'); ax[0, 1].legend(fontsize=8); ax[0, 1].grid(alpha=.3)
ax[1, 0].plot(H.t_day, H['干固体产率'] / H['泥饼流量'] / 10, color='#1f77b4', lw=1, label='健康')
ax[1, 0].plot(G.t_day, G['干固体产率'] / G['泥饼流量'] / 10, color='#d62728', lw=1, label='退化')
ax[1, 0].axhline(20, color='#2ca02c', ls='--', lw=1); ax[1, 0].axvline(DEG, color='#7f7f7f', ls=':', lw=1)
ax[1, 0].set_title('③ 比值通道：干固体/湿泥饼量（= 泥饼含固率）'); ax[1, 0].set_xlabel('天'); ax[1, 0].set_ylabel('%'); ax[1, 0].legend(fontsize=8); ax[1, 0].grid(alpha=.3)
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
fig.suptitle('路线 B：BSM2 整厂脱水机退化 —— 原始量检不出，设备级比值量可检出（限定见第 27 节）', fontsize=12)
fig.tight_layout(); fig.savefig(os.path.join(D, 'bsm2_route_b_detect.png'), dpi=130)
print(T1.to_string(index=False)); print(); print(T2.to_string(index=False)); print(); print(T3.to_string(index=False))
print(); print(json.dumps(diag, ensure_ascii=False, indent=1))
