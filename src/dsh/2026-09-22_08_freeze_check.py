# -*- coding: utf-8 -*-
"""冻结前数字总检（DSH，2026-09-22）
目的：技术冻结（10/07）前，把每一个对外数字回溯到结果文件，并检查文档/演示页是否一致、有无残留旧值。
做法：① 强校验 = 从结果 JSON/CSV 现场复算，再在目标文档里找该数字（多种格式变体）；② 弱校验 = 结果文件文本里含该数字；
      ③ 反向检查 = 已作废的旧值不得出现在对外文档（历史台账与日志除外）。
产物：results/2026-09-22/dsh/freeze_check.{json,md}
用法：python src/dsh/2026-09-22_08_freeze_check.py
"""
import os, io, json, re, numpy as np, pandas as pd

D = 'results/2026-09-22/dsh'
DOCS = ['PROJECT_STATE.md', 'docs/07_BP四栏大纲.md', 'docs/08_成果验收清单.md', 'docs/09_评委视角_五分钟看懂.md', 'demo/lanmai_demo.html']
NL = chr(10)
TXT = {p: (io.open(p, encoding='utf-8').read() if os.path.exists(p) else '') for p in DOCS}
JOINED = NL.join(TXT.values())


def variants(v):
    """同一数值的常见书写形式。"""
    out = set()
    for fmt in ['%g', '%.1f', '%.2f', '%.3f', '%.4f']:
        out.add(fmt % v)
    return {x for x in out if x}


def in_docs(v, exclude=()):
    hit = []
    for s in variants(v):
        for p, t in TXT.items():
            if p in exclude:
                continue
            if s in t:
                hit.append('%s:%s' % (os.path.basename(p), s))
    return sorted(set(hit))


def weak(file_has, v):
    return any(s in file_has for s in variants(v))


items = []


def check(name, value, source, doc_ok=None, note=''):
    doc_ok = in_docs(value) if doc_ok is None else doc_ok
    items.append(dict(检查项=name, 数值=(None if value is None else round(float(value), 4)), 结果文件=source,
                      文档命中=doc_ok, 通过=bool(doc_ok), 备注=note))


def weak_check(name, value, path, note='弱校验：结果文件文本含该值'):
    has = io.open(path, encoding='utf-8').read() if os.path.exists(path) else ''
    items.append(dict(检查项=name, 数值=round(float(value), 4), 结果文件=path,
                      文档命中=(['(弱校验通过)'] if weak(has, value) else []), 通过=weak(has, value), 备注=note))


# ---------- 路线 B（强校验：现场复算）----------
J = json.load(io.open(os.path.join(D, 'bsm2_route_b_detect.json'), encoding='utf-8'))
t1 = {r['通道集'] + '|' + r['阈值口径']: r for r in J['通道集口径表']}
check('路线B 真值失效天', J['真值失效天'], 'bsm2_route_b_detect.json')
check('路线B q999 阈值', t1['5 个原始量|参考域 0.999 分位']['阈值'], 'bsm2_route_b_detect.json')
check('路线B 零误报阈值', t1['5 个原始量|零误报（健康轨迹最大 × 1.02）']['阈值'], 'bsm2_route_b_detect.json')
check('路线B 原始量零误报延迟', t1['5 个原始量|零误报（健康轨迹最大 × 1.02）']['检出延迟'], 'bsm2_route_b_detect.json', note='负结果：晚于失效')
check('路线B 原始量首报（q999）', t1['5 个原始量|参考域 0.999 分位']['退化后首报'], 'bsm2_route_b_detect.json', note='误报抢跑')
nb = {r['噪声结构']: r for r in J['噪声结构敏感性']}
base = [r for r in J['噪声结构敏感性'] if r['噪声结构'].startswith('基线')][0]
check('路线B 比值通道含噪延迟中位', base['检出延迟中位'], 'bsm2_route_b_detect.json')
check('路线B 比值通道提前量中位', base['提前量中位'], 'bsm2_route_b_detect.json')
rw = [r for r in J['RUL窗长敏感性']][0]
check('路线B RUL 1 天窗误差', rw['无平滑误差中位'], 'bsm2_route_b_detect.json')
rw10 = [r for r in J['RUL窗长敏感性']][3]
check('路线B RUL 10 天窗误差', rw10['无平滑误差中位'], 'bsm2_route_b_detect.json')
SW = pd.read_csv(os.path.join(D, 'bsm2_route_b_sweep.csv'))
check('路线B 速率轴延迟（30/60/120 天）', SW['比值含噪延迟中位'].iloc[0], 'bsm2_route_b_sweep.csv', note='另两点 %.2f/%.2f' % (SW['比值含噪延迟中位'].iloc[1], SW['比值含噪延迟中位'].iloc[2]))
check('路线B 湿泥饼量增幅（18%% 终值）', SW['泥饼流量相对健康'].iloc[1] * 100, 'bsm2_route_b_sweep.csv')
check('路线B 120 天斜坡实际终值', SW['终值含固率'].iloc[2], 'bsm2_route_b_sweep.csv')
PD = pd.read_csv(os.path.join(D, 'bsm2_route_b_pairdiff.csv'))
check('补强① 对拍差分（原始量）延迟', PD[PD.通道集.str.contains('原始量')]['检出延迟中位'].iloc[0], 'bsm2_route_b_pairdiff.csv')
check('补强① 对拍差分（比值）延迟', PD[PD.通道集.str.contains('比值')]['检出延迟中位'].iloc[0], 'bsm2_route_b_pairdiff.csv')
DR = pd.read_csv(os.path.join(D, 'bsm2_route_b_drift.csv'))
dr = DR[(DR.缓解 == 'M1 无补偿')]
check('补强② 随机游走 3%% 延迟', dr[(dr.偏差结构 == '随机游走') & (dr.幅度 == '3%')]['检出延迟中位'].iloc[0], 'bsm2_route_b_drift.csv')
check('补强② 随机游走 5%% 延迟', dr[(dr.偏差结构 == '随机游走') & (dr.幅度 == '5%')]['检出延迟中位'].iloc[0], 'bsm2_route_b_drift.csv')
m3 = DR[(DR.偏差结构 == '随机游走') & (DR.缓解 == 'M3 双测量平均') & (DR.幅度 == '3%')]
check('补强② 双测量平均（随机游走 3%%）', m3['检出延迟中位'].iloc[0], 'bsm2_route_b_drift.csv')

# ---------- 污泥线（strong）----------
J2 = json.load(io.open('results/2026-09-21/dsh/sludge_line2.json', encoding='utf-8'))
k0 = list(J2.keys())[0]
fz = J2[k0]['检测']['frozen']
check('污泥线 真值失效天', J2[k0]['真值失效天'], 'sludge_line2.json')
check('污泥线 冻结首报', fz['首报'], 'sludge_line2.json')
check('污泥线 提前量', fz['提前量'], 'sludge_line2.json')
check('污泥线 RUL 1 天窗误差', fz['误差_1天窗'], 'sludge_line2.json')

# ---------- 老数据集（弱校验：结果文件文本含该值）----------
import glob
weak_check('MetroPT-3 无标签阈值 13.139', 13.139, 'results/2026-09-18/dsh/metropt3_metrics_frozen_dsh.json')
weak_check('C-MAPSS RMSE 15.27', 15.27, 'results/2026-09-17/dsh/rul_baseline_metrics.csv')
weak_check('C-MAPSS PHM08 434', 434.0, 'results/2026-09-17/dsh/rul_baseline_metrics.csv')
for f in ['results/2026-09-18/dsh/decision_policy_v6.csv', 'results/2026-09-18/dsh/decision_sensitivity_v6.csv']:
    if os.path.exists(f):
        weak_check('决策层（%s）' % os.path.basename(f), 1.0, f, note='弱校验：文件存在且可读')

# ---------- 产物文件名自检（Codex 批次 6：中文名跨平台风险）----------
bad_names = []
for root, dirs, files in os.walk('results'):
    for f in files:
        if any(ord(ch) > 127 for ch in f):
            bad_names.append(os.path.join(root, f))
items.append(dict(检查项='产物文件名非 ASCII 自检（results/）', 数值=None, 结果文件='results/**',
                  文档命中=(bad_names[:5] if bad_names else []), 通过=(len(bad_names) == 0),
                  备注='docs/ logs/ 协作约定.md 的中文名是给人看的、允许；results/ 下的产物名应为 ASCII'))

# ---------- 反向检查：已作废旧值不得出现在对外文档 ----------
STALE = [('+62%', '污泥线旧增幅'), ('273.08', '污泥线旧 RUL（点索引口径）'), ('0.99 天', '污泥线旧 RUL 误差')]
for s, desc in STALE:
    OUT = {'docs/07_BP四栏大纲.md', 'docs/08_成果验收清单.md', 'docs/09_评委视角_五分钟看懂.md', 'demo/lanmai_demo.html'}
    hits = [os.path.basename(p) for p, t in TXT.items() if (s in t and p in OUT)]   # PROJECT_STATE 的 §26/§28 台账属正常记载
    items.append(dict(检查项='旧值残留检查：%s（%s）' % (s, desc), 数值=None, 结果文件='—',
                      文档命中=hits, 通过=(len(hits) == 0), 备注='历史台账 §26/§28 与日志中的引用属正常记载' if hits else ''))

T = pd.DataFrame(items)
n_ok = int(T['通过'].sum())
out = dict(检查项数=len(T), 通过=n_ok, 未通过=len(T) - n_ok,
           未通过清单=T[~T['通过']]['检查项'].tolist(),
           文档集合=DOCS, 明细=T.to_dict('records'))
json.dump(out, io.open(os.path.join(D, 'freeze_check.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

L = ['# 冻结前数字总检（DSH，2026-09-22）' + NL,
     '> 方法：强校验 = 从结果文件现场复算 + 在目标文档中检索该数值（多格式变体）；弱校验 = 结果文件文本含该值。' + NL,
     '> 目标文档：%s。' % '、'.join(DOCS) + NL,
     '## 总览：%d/%d 通过' % (n_ok, len(T)) + NL]
if len(T) - n_ok:
    L.append('**未通过清单**：%s' % '；'.join(out['未通过清单']) + NL)
L.append(T.to_markdown(index=False) + NL)
io.open(os.path.join(D, 'freeze_check.md'), 'w', encoding='utf-8', newline=NL).write(NL.join(L))
print('总检：%d/%d 通过' % (n_ok, len(T)))
if len(T) - n_ok:
    print('未通过：')
    print(T[~T['通过']][['检查项', '数值', '结果文件']].to_string(index=False))
