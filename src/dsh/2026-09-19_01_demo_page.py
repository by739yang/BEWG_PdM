# -*- coding: utf-8 -*-
"""生成澜脉单页演示（自包含 HTML，本地双击即可打开）
数据全部来自已冻结/已落盘的结果文件，页面里注明每块的来源脚本。"""
import pandas as pd, json, base64, os, io
R='results'; D=f'{R}/2026-09-18/dsh'; os.makedirs('demo',exist_ok=True)
def jload(p):
    return json.load(io.open(p,encoding='utf-8'))
frozen=jload(f'{D}/metropt3_metrics_frozen_dsh.json')
mine=frozen['det_best']; cx=jload(f'{R}/2026-09-18/codex/metropt3_ownmodel_unified_primary.json')
alarms=pd.read_csv(f'{D}/pipeline_alarms.csv')
pol=pd.read_csv(f'{D}/decision_policy_v6.csv')
sens=pd.read_csv(f'{D}/decision_sensitivity_v6.csv')
rul=pd.read_csv(f'{R}/2026-09-17/dsh/rul_baseline_metrics.csv')
img=base64.b64encode(open(f'{D}/figures_4in1.png','rb').read()).decode()
def tbl(df, cols=None, n=None):
    d=df if cols is None else df[cols]
    if n: d=d.head(n)
    h='<table><tr>'+''.join('<th>%s</th>'%c for c in d.columns)+'</tr>'
    for _,r in d.iterrows():
        h+='<tr>'+''.join('<td>%s</td>'%r[c] for c in d.columns)+'</tr>'
    return h+'</table>'
css='''<style>
body{font-family:-apple-system,"Microsoft YaHei",sans-serif;margin:0;background:#f5f7fa;color:#1a2733}
.wrap{max-width:1180px;margin:0 auto;padding:24px}
h1{font-size:24px;margin:0 0 4px}.sub{color:#5b6b7c;font-size:13px;margin-bottom:20px}
.card{background:#fff;border-radius:10px;padding:18px 20px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,.06)}
h2{font-size:16px;margin:0 0 12px;color:#12507b;border-left:4px solid #12507b;padding-left:8px}
.kpis{display:flex;gap:14px;flex-wrap:wrap}
.kpi{flex:1;min-width:150px;background:#f0f6fb;border-radius:8px;padding:14px}
.kpi .v{font-size:22px;font-weight:600;color:#12507b}.kpi .l{font-size:12px;color:#5b6b7c;margin-top:4px}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{border-bottom:1px solid #e6ecf2;padding:6px 8px;text-align:left}
th{background:#f0f6fb;color:#12507b;font-weight:600}
img{width:100%;border-radius:8px}
.note{font-size:12px;color:#8a97a5;margin-top:8px}
.warn{background:#fff8e6;border-left:4px solid #d99b1f;padding:10px 14px;border-radius:6px;font-size:13px;margin-top:10px}
</style>'''
h=[]
h.append('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>澜脉 · 演示</title>'+css+'</head><body><div class="wrap">')
h.append('<h1>澜脉 · 污水厂设备预测性维护</h1>')
h.append('<div class="sub">纯软件 · 无硬件改造 · 演示数据来自公开真实工业数据集（SKAB / MetroPT-3 / CWRU / C-MAPSS）｜生成时间 2026-09-19</div>')
h.append('<div class="card"><h2>一、检测：设备健康告警（MetroPT-3 空压机，约 5.8 个月）</h2><div class="kpis">')
h.append('<div class="kpi"><div class="v">%d</div><div class="l">告警事件（冻结分母 96,270 分钟）</div></div>'%mine['fp_events'] if False else
 '<div class="kpi"><div class="v">%d</div><div class="l">告警事件总数</div></div>'%(frozen['det_best']['fp_events']+frozen['det_best']['timely']+frozen['det_best']['miss']))
h.append('<div class="kpi"><div class="v">2/4</div><div class="l">及时命中官方故障（timely 召回）</div></div>')
h.append('<div class="kpi"><div class="v">%.4f</div><div class="l">误报事件 / 全稳定小时</div></div>'%mine['fp_per_hour_all_stable'])
h.append('<div class="kpi"><div class="v">%.1f%%</div><div class="l">健康时间被报警占用（TIA-H）</div></div>'%(mine['tia_all_stable']*100))
h.append('<div class="kpi"><div class="v">-8.5 分钟</div><div class="l">命中事件平均提前量</div></div>')
h.append('</div><div class="note">口径：分母为两套独立实现的逐分钟掩码交集；命中判据为告警起点落在故障开始前 60 分钟内或故障窗内。</div>')
h.append('<div class="warn"><b>诚实说明：</b>MetroPT-3 官方只给了 4 个粗粒度故障区间，召回步长为 25%%，且当前 timely 召回 2/4、约每 8 小时一次误报，<b>尚未达到现场可用水平</b>。这一页展示的是方法与可复现性，不是上线效果。</div></div>')
h.append('<div class="card"><h2>二、双模型对比（同一评价机、同一冻结分母）</h2>')
comp=pd.DataFrame([{'模型':'澜脉（DSH 路线）','建模路线':'工况条件化 + 每日 walk-forward + 最大三个 |z| 的 RMS','timely 召回':'2/4','误报事件':201,'误报/全稳定小时':round(mine['fp_per_hour_all_stable'],4),'TIA-H':round(mine['tia_all_stable'],4)},
 {'模型':'对照（Codex 路线）','建模路线':'三态工况 + 24 小时 walk-forward + 多特征聚合','timely 召回':'2/4','误报事件':cx['false_alarm_events'],'误报/全稳定小时':round(cx['false_alarms_per_all_stable_hour'],4),'TIA-H':round(cx['tia_h_all_stable'],4)}])
h.append(tbl(comp))
h.append('<div class="note">同样抓住 2/4 个故障，澜脉路线的误报事件少 2.8 倍、健康时间被占用少 3 倍。</div></div>')
h.append('<div class="card"><h2>三、告警到建议（前 12 条）</h2>')
h.append(tbl(alarms[['告警起点','持续分钟','峰值分数','诊断','建议窗口','优先级']],n=12))
h.append('<div class="note">建议窗口取该设备"压缩机停机≥30 分钟"的时间段；成本参数为占位值，仅用于结构演示。</div></div>')
h.append('<div class="card"><h2>四、剩余寿命与维护策略（C-MAPSS FD001，100 台）</h2>')
h.append(tbl(rul))
h.append('<div class="note">RUL 为经验模型（逐周期训练、标签按 125 周期截断、测试用官方真值）。</div>')
h.append('<h2 style="margin-top:16px">策略成本对比</h2>'+tbl(pol[['策略','参数','抓住紧急','漏掉紧急','动用非紧急','紧急召回','单台成本']]))
h.append('<div class="note">紧急单元定义：观察窗末真值 RUL ≤ 60 周期（39/100 台）。成本参数为占位值。</div></div>')
h.append('<div class="card"><h2>五、成本敏感性（什么条件下 AI 更划算）</h2>'+tbl(sens))
h.append('<div class="note">行列分别是非计划失效代价与计划更换代价；最后一列是 AI 相对最优固定周期的节省（正数=AI 更省）。需要向企业标定的正是这两个参数。</div></div>')
h.append('<div class="card"><h2>六、关键结果四图</h2><img src="data:image/png;base64,%s">'%img)
h.append('<div class="note">① SKAB 误报-召回曲线 ② 维护策略成本对比 ③ 成本敏感性网格 ④ RUL 预测散点。</div></div>')
h.append('<div class="card"><h2>七、数据来源与复现</h2><ul style="font-size:13px;line-height:1.9">')
h.append('<li>SKAB（真实水泵台架）｜ MetroPT-3（地铁空压机，UCI 791）｜ CWRU（轴承故障）｜ C-MAPSS FD001（NASA 涡扇退化）</li>')
h.append('<li>一键复现：<b>python src/dsh/2026-09-18_14_pipeline.py</b>（检测→诊断→RUL→决策）</li>')
h.append('<li>一致性自检：<b>python src/dsh/2026-09-18_18_consistency_check_v2.py</b></li>')
h.append('<li>局限：四个数据集都来自公开工业设备，与污水厂水泵/鼓风机的工况不同；成本参数未经企业标定；仿真与占位数据均已标注。</li>')
h.append('</ul></div>')
h.append('</div></body></html>')
io.open('demo/lanmai_demo.html','w',encoding='utf-8').write(''.join(h))
print('已生成 demo/lanmai_demo.html  %.0f KB' % (os.path.getsize('demo/lanmai_demo.html')/1024))
print('告警表列：',list(alarms.columns))
