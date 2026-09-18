# -*- coding: utf-8 -*-
"""仓库一致性自检（DSH，2026-09-18 收工复核）
检查三件事：① PROJECT_STATE/docs 里引用的文件是否存在；② 日志里引用的脚本是否存在；
③ 三个已冻结结论章节的数字能否从结果文件复算出来。"""
import re, os, json, io, glob
import pandas as pd
R='.'; issues=[]; ok=[]
# ---------- ① 路径存在性 ----------
def check_paths(files):
    txt=''
    for f in files:
        if os.path.exists(f): txt+=io.open(f,encoding='utf-8').read()
    cands=set(re.findall(r'[A-Za-z0-9_\-]+\.(?:md|csv|json|py|gz|png|npz|npy)', txt))
    cands|=set(re.findall(r'(?:results|src|docs|tasks|handoff|logs)/[^\s\)\]\|、，。]+', txt))
    miss=[]
    for c in sorted(cands):
        c=c.rstrip('.,;:')
        if c.startswith(('results','src','docs','tasks','handoff','logs')) and not os.path.exists(c):
            miss.append(c)
    return sorted(set(miss))
miss=check_paths(['PROJECT_STATE.md','协作约定.md','docs/01_项目速览.md','docs/02_倒排工期到10-07.md'])
if miss: issues.append(('引用但不存在的文件', miss[:12]))
else: ok.append('PROJECT_STATE/协作文档引用的路径全部存在')
# ---------- ② 日志里的脚本 ----------
log=io.open('logs/实验日志.md',encoding='utf-8').read()
scripts=set(re.findall(r'(src/(?:dsh|codex)/[0-9A-Za-z_\-]+\.py)', log))
missing=[s for s in sorted(scripts) if not os.path.exists(s)]
if missing: issues.append(('日志引用但不存在的脚本', missing))
else: ok.append('日志引用的 %d 个脚本全部存在' % len(scripts))
# ---------- ③ 冻结数字复算 ----------
# (a) MetroPT-3
d=json.load(open('results/2026-09-18/dsh/metropt3_metrics_frozen_dsh.json',encoding='utf-8'))
mt=d['main_threshold']
exp=dict(timely=2,late=1,miss=1,fp_events=201)
bad=[k for k,v in exp.items() if int(mt[k])!=v]
fph=mt['fp_per_hour_all_stable']; tia=mt['tia_all_stable']
if bad: issues.append(('MetroPT-3 冻结数字与结果文件不符', bad))
else: ok.append('MetroPT-3：timely 2 / late 1 / miss 1 / 误报 201 与结果文件一致（%.4f 次/小时，TIA-H %.1f%%）'%(fph,tia*100))
# (b) C-MAPSS RUL
m=pd.read_csv('results/2026-09-17/dsh/rul_baseline_metrics.csv')
g=m[m.模型.str.contains('梯度提升')].iloc[0]
gb_rmse,gb_phm=float(g.RMSE),float(g.PHM08得分)
if not (abs(gb_rmse-15.27)<0.05 and abs(gb_phm-434)<3): issues.append(('C-MAPSS 冻结数字与结果文件不符',(gb_rmse,gb_phm)))
else: ok.append('C-MAPSS RUL：梯度提升 RMSE %.2f / PHM08 %.0f 与结果文件一致'%(gb_rmse,gb_phm))
# (c) SKAB
t=io.open('results/2026-09-15/protocol_v14_crosscheck_final.md',encoding='utf-8').read()
nums=dict(re.findall(r'\|\s*(F[0-3])\s*\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|\s*通过', t))
if len(nums)>=3: ok.append('SKAB：交叉比对报告含 F0/F2/F3 三行且判定为通过')
else: issues.append(('SKAB 交叉比对报告结构异常', list(nums.keys())))
# (d) 关键产物存在性
need=['results/2026-09-18/dsh/figures_4in1.png','results/2026-09-18/dsh/pipeline_summary.json',
      'results/2026-09-18/dsh/decision_sensitivity_v6.csv','results/2026-09-18/dsh/cwru_multiseverity_metrics.csv',
      'docs/PROTOCOL_v1.5.md','docs/metropt3_fault_windows.json','tasks/codex_batch_queue.md']
miss2=[p for p in need if not os.path.exists(p)]
if miss2: issues.append(('关键产物缺失', miss2))
else: ok.append('关键产物 %d 项齐全' % len(need))
# ---------- 报告 ----------
lines=['# 收工一致性自检报告（DSH，2026-09-18）','','## 通过项']
lines += ['- '+x for x in ok]
lines += ['','## 问题项']
if issues:
    for name,detail in issues: lines.append('- **%s**：%s' % (name,detail))
else:
    lines.append('- 无')
io.open('results/2026-09-18/dsh/consistency_check.md','w',encoding='utf-8').write('\n'.join(lines)+'\n')
json.dump(dict(通过=ok,问题=[{'项':a,'细节':str(b)} for a,b in issues]),
          open('results/2026-09-18/dsh/consistency_check.json','w',encoding='utf-8'),ensure_ascii=False,indent=2)
print('\n'.join(lines))
print()
print('结论：%s' % ('全部通过' if not issues else '发现 %d 类问题，需处理' % len(issues)))
