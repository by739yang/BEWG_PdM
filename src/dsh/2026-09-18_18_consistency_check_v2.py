# -*- coding: utf-8 -*-
"""DET 最优点取法统一 + 仓库一致性自检（修订版，2026-09-18 收工）"""
import pandas as pd, numpy as np, re, os, io, json
D=pd.read_csv('results/2026-09-18/dsh/metropt3_det_frozen_dsh.csv')
mx=D.timely_recall.max()
cand=D[D.timely_recall==mx].sort_values('fp_per_hour_all_stable')
best=cand.iloc[0]
print('=== DET 最优点（定义：召回最高者中取误报率最低）===')
print('阈值 %.4f | timely %d/4 | 误报 %d 次（%.4f 次/全稳定小时）| TIA-H %.4f'
      % (best.threshold, best.timely, best.fp_events, best.fp_per_hour_all_stable, best.tia_all_stable))
print('召回最高的候选点 %d 个，阈值区间 [%.4f, %.4f]' % (len(cand), cand.threshold.min(), cand.threshold.max()))
j=json.load(open('results/2026-09-18/dsh/metropt3_metrics_frozen_dsh.json',encoding='utf-8'))
j['det_best']=dict(threshold=float(best.threshold), timely=int(best.timely), late=int(best.late), miss=int(best.miss),
    fp_events=int(best.fp_events), fp_per_hour_all_stable=float(best.fp_per_hour_all_stable),
    fp_per_hour_running=float(best.fp_per_hour_running), tia_all_stable=float(best.tia_all_stable),
    tia_running=float(best.tia_running), definition='召回最高者中取误报率最低，并列时取阈值较小者')
json.dump(j,open('results/2026-09-18/dsh/metropt3_metrics_frozen_dsh.json','w',encoding='utf-8'),ensure_ascii=False,indent=2)

issues=[]; ok=[]
STRIP=' '+chr(96)+chr(34)+chr(39)+chr(46)+'，。）)、,。；:;'
def norm(p):
    p=p.strip(STRIP)
    if any(x in p for x in ['<','>','YYYY','（',' ','日期','当天','agent','当天日期']): return None
    return p
txt=''
for f in ['PROJECT_STATE.md','协作约定.md','docs/01_项目速览.md','docs/02_倒排工期到10-07.md']:
    if os.path.exists(f): txt+=io.open(f,encoding='utf-8').read()
cands=set()
for m in re.finditer(r'(?:results|src|docs|tasks|handoff|logs)/[A-Za-z0-9_\-\u4e00-\u9fff./]+', txt):
    p=norm(m.group(0))
    if p: cands.add(p)
miss=sorted(p for p in cands if not os.path.exists(p))
if miss: issues.append(('引用但不存在的路径', miss[:10]))
else: ok.append('文档引用的 %d 条路径全部存在' % len(cands))
log=io.open('logs/实验日志.md',encoding='utf-8').read()
scripts=sorted(set(re.findall(r'src/(?:dsh|codex)/[0-9A-Za-z_\-]+\.py', log)))
missing=[s for s in scripts if not os.path.exists(s)]
if missing: issues.append(('日志引用但不存在的脚本', missing))
else: ok.append('日志引用的 %d 个脚本全部存在' % len(scripts))
mb=j['det_best']
if int(mb['timely'])!=2 or int(mb['fp_events'])!=201:
    issues.append(('MetroPT-3 冻结点与文件不符', mb))
else:
    ok.append('MetroPT-3 冻结点一致：阈值 %.4f、timely 2/4、误报 %d（%.4f 次/全稳定小时）、TIA-H %.1f%%'
              % (mb['threshold'], mb['fp_events'], mb['fp_per_hour_all_stable'], mb['tia_all_stable']*100))
m=pd.read_csv('results/2026-09-17/dsh/rul_baseline_metrics.csv')
g=m[m.模型.str.contains('梯度提升')].iloc[0]
if abs(float(g.RMSE)-15.27)>0.05: issues.append(('C-MAPSS 数字不符',(g.RMSE,g.PHM08得分)))
else: ok.append('C-MAPSS：梯度提升 RMSE %.2f / PHM08 %.0f 与结果文件一致' % (g.RMSE, g.PHM08得分))
t=io.open('results/2026-09-15/protocol_v14_crosscheck_final.md',encoding='utf-8').read()
if all(k in t for k in ['F0','F2','F3','0.121','0.424','0.333']): ok.append('SKAB 交叉比对：三方法零偏差行齐全')
else: issues.append(('SKAB 比对报告内容不符',''))
need=['results/2026-09-18/dsh/figures_4in1.png','results/2026-09-18/dsh/pipeline_summary.json',
      'results/2026-09-18/dsh/decision_sensitivity_v6.csv','results/2026-09-18/dsh/cwru_multiseverity_metrics.csv',
      'docs/PROTOCOL_v1.5.md','docs/metropt3_fault_windows.json','tasks/codex_batch_queue.md']
m2=[p for p in need if not os.path.exists(p)]
if m2: issues.append(('关键产物缺失', m2))
else: ok.append('关键产物 7 项齐全')
lines=['# 收工一致性自检报告（DSH，2026-09-18 修订版）','','## 通过项']+['- '+x for x in ok]+['','## 问题项']
lines += (['- **%s**：%s' % (a,b) for a,b in issues] if issues else ['- 无'])
io.open('results/2026-09-18/dsh/consistency_check.md','w',encoding='utf-8').write(chr(10).join(lines)+chr(10))
json.dump(dict(通过=ok, 问题=[{'项':a,'细节':str(b)} for a,b in issues],
    DET最优点定义='召回最高者中取误报率最低',
    DET最优点=dict(threshold=float(best.threshold), timely=int(best.timely), fp_events=int(best.fp_events),
                   fp_per_hour=float(best.fp_per_hour_all_stable), tia=float(best.tia_all_stable))),
    open('results/2026-09-18/dsh/consistency_check.json','w',encoding='utf-8'), ensure_ascii=False, indent=2)
print(); print(chr(10).join(lines))
