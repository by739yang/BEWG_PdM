# -*- coding: utf-8 -*-
"""生成澜脉单页演示（自包含 HTML，本地双击即可打开）
数据全部来自已冻结/已落盘的结果文件，页面里注明每块的来源脚本。"""
import pandas as pd, json, base64, os, io
R='results'; D=f'{R}/2026-09-18/dsh'; os.makedirs('demo',exist_ok=True)
def jload(p):
    return json.load(io.open(p,encoding='utf-8'))
frozen=jload(f'{D}/metropt3_metrics_frozen_dsh.json')
pipe=jload(f'{D}/pipeline_summary.json')
mine=frozen['det_best']; cx=jload(f'{R}/2026-09-18/codex/metropt3_ownmodel_unified_primary.json')
alarms=pd.read_csv(f'{D}/pipeline_alarms.csv')
pol=pd.read_csv(f'{D}/decision_policy_v6.csv')
sens=pd.read_csv(f'{D}/decision_sensitivity_v6.csv')
rul=pd.read_csv(f'{R}/2026-09-17/dsh/rul_baseline_metrics.csv')
img=base64.b64encode(open(f'{D}/figures_4in1.png','rb').read()).decode()
D20=f'{R}/2026-09-20/dsh'
bsm1img=base64.b64encode(open(f'{D20}/bsm1_4in1.png','rb').read()).decode()
sd=pd.read_csv(f'{D20}/bsm1_slow_drift_detectors.csv')
rm=pd.read_csv(f'{D20}/bsm1_rul_methods.csv')
db=pd.read_csv(f'{D20}/dual_baseline_bsm1.csv')
sweepimg=base64.b64encode(open(f'{D20}/bsm1_sweep_3in1.png','rb').read()).decode()
sw=pd.read_csv(f'{D20}/bsm1_amp_sweep.csv')
inf=pd.read_csv(f'{D20}/bsm1_influent_robustness.csv')
infimg=base64.b64encode(open(f'{D20}/bsm1_influent_robustness.png','rb').read()).decode()
rs=pd.read_csv(f'{D20}/bsm1_rain_storm.csv')
rsimg=base64.b64encode(open(f'{D20}/bsm1_rain_storm.png','rb').read()).decode()
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
h.append('<div class="sub">纯软件 · 无硬件改造 · 演示数据来自公开真实工业数据集（SKAB / MetroPT-3 / CWRU / C-MAPSS）与 IWA BSM1 数字孪生仿真｜生成时间 2026-09-20</div>')
h.append('<div class="card"><h2>一、检测：设备健康告警（MetroPT-3 空压机，约 5.8 个月）</h2><div class="kpis">')
h.append('<div class="kpi"><div class="v">%d</div><div class="l">告警事件总数（由结果对象生成，不硬编码）</div></div>'%pipe['检测']['告警数'])
h.append('<div class="kpi"><div class="v">2/4</div><div class="l">及时命中官方故障（timely 召回）</div></div>')
h.append('<div class="kpi"><div class="v">%.4f</div><div class="l">误报事件 / 全稳定小时</div></div>'%mine['fp_per_hour_all_stable'])
h.append('<div class="kpi"><div class="v">%.1f%%</div><div class="l">健康时间被报警占用（TIA-H）</div></div>'%(mine['tia_all_stable']*100))
h.append('<div class="kpi"><div class="v">-8.5 分钟</div><div class="l">命中事件平均提前量</div></div>')
h.append('</div><div class="note">口径：分母为两套独立实现的逐分钟掩码交集；命中判据为告警起点落在故障开始前 60 分钟内或故障窗内。</div>')
h.append('<div class="note"><b>阈值性质：</b>2.3954 是用官方 4 个故障窗按 DET 规则（召回优先、并列取误报最低）选出的工作点，属<b>标签辅助选点</b>；4 个窗同时用于选点与汇报，因此这 2/4 是<b>同集工作点表现，不是独立前瞻验证</b>。无标签 0.995 标定分位工作点为 13.139（timely 0/4、误报 13 次、0.0081 次/全稳定小时）。</div>')
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
h.append('<div class="note">RUL 为经验模型（逐周期训练、标签按 125 周期截断、测试用官方真值）。MetroPT-3 侧的 RUL 门禁为<b>事后(retrospective)</b>判断，使用了告警时点之后的数据，只能用于「瞬态告警不挂 RUL」的离线结论，不作在线决策依据。</div>')
h.append('<h2 style="margin-top:16px">策略成本对比</h2>'+tbl(pol[['策略','参数','抓住紧急','漏掉紧急','动用非紧急','紧急召回','单台成本']]))
h.append('<div class="note">紧急单元定义：观察窗末真值 RUL ≤ 60 周期（39/100 台）。成本参数为占位值。</div></div>')
h.append('<div class="card"><h2>五、成本敏感性（什么条件下 AI 更划算）</h2>'+tbl(sens))
h.append('<div class="note">行列分别是非计划失效代价与计划更换代价；最后一列是 AI 相对最优固定周期的节省（正数=AI 更省）。需要向企业标定的正是这两个参数。</div></div>')
h.append('<div class="card"><h2>六、关键结果四图</h2><img src="data:image/png;base64,%s">'%img)
h.append('<div class="note">① SKAB 误报-召回曲线 ② 维护策略成本对比 ③ 成本敏感性网格 ④ RUL 预测散点。</div></div>')
h.append('<div class="card"><h2>八、数字孪生闭环：慢退化检测与剩余寿命（BSM1，IWA 标准活性污泥模型）</h2>')
h.append('<img src="data:image/png;base64,%s">'%bsm1img)
h.append('<div class="note">① 退化过程与报警/失效时刻 ② 慢漂移检测方案对照 ③ RUL 方法对照 ④ 冻结参考域选择诊断。全部为仿真数据（15 分钟步长），非现场数据。</div>')
h.append('<h2 style="margin-top:16px">慢漂移检测方案对照（60 天场景，第 20 天起 KLa 衰减 40%）</h2>'+tbl(sd[['方案','阈值','报警时刻','检出延迟','基准误报采样数']]))
h.append('<div class="note">自适应基线把慢漂移逐步纳入「新常态」，因此完全漏检；静态（冻结）基线能检出，且基准运行零误报。</div>')
h.append('<h2 style="margin-top:16px">RUL 方法对照（真值剩余寿命 7.27 天）</h2>'+tbl(rm[['方法','RUL估计','RUL真值','绝对误差']]))
h.append('<div class="note">通用健康指数外推高估 3.8 倍；机理指标（溶解氧）误差 4.0-4.1 天。失效是悬崖式时，RUL 必须挂机理指标。</div>')
h.append('<h2 style="margin-top:16px">双基线并行检测：两条独立通道、各自校准</h2>'+tbl(db))
h.append('<div class="note">MetroPT-3（突变类故障）两通道误报率相近；BSM1 120 天慢漂移中两条独立通道指向同一时刻（40.24 / 40.28 天），健康运行中冻结通道零误报。</div>')
h.append('<h2 style="margin-top:16px">退化幅值-斜率扫描（120 天，6 个场景）</h2>')
h.append('<img src="data:image/png;base64,%s">'%sweepimg)
h.append('<div class="note">① 检出延迟与预警提前量 vs 退化速率 ② 刀锋边缘：健康运行越限 6 点/最长连续 3 点，事件机要求 4 点 ③ 分布位置随严重度单调变化。</div>')
h.append(tbl(sw[['最终KLa比例','斜坡天','检出延迟天','提前量SO3_0_5','提前量SO3_1_0','健康运行误报_自适应','健康运行误报_冻结']]))
h.append('<div class="warn"><b>必须一起看的两条自我限定：</b>① 冻结通道的首报时刻在所有退化场景下都是第 40.3 天，与退化幅值无关 —— 它只能判「有没有异常」，不含严重度信息；② 健康运行越限 6 个样本、最长连续 3 个，事件机要求连续 4 个，「0 误报」与「误报」只差一个采样点，因此 120 天/0 误报是刀锋边缘结果，不能当稳健性结论。对 -60%/100 天及更快的退化，报警不早于出水指标劣化。</div></div>')
h.append('<h2 style="margin-top:16px">进水工况泛化（三种进水窗口，同一退化配置）</h2>')
h.append('<img src="data:image/png;base64,%s">'%infimg)
h.append(tbl(inf[['工况窗口','健康SO3均值','健康持续低于0_5','健康误报_自适应','健康误报_冻结','检出延迟天','失效前提前量']]))
h.append('<div class="warn"><b>三条要一起看的结论：</b>① 三种工况都检出了退化（无漏检）；② 「120 天 0 误报」只在 A 窗成立（B/C 窗健康运行误报 4 / 3 次），不能用它宣称稳健；③ B、C 窗进水使健康运行 SO3 本底降到 1.01 / 0.61 mg/L，健康运行本身就长期低于 0.5 mg/L 的绝对危险线 —— 绝对阈值判据在该工况下失真，危险线必须按工况自身的健康基线标定。</div>')
h.append('<h2 style="margin-top:16px">雨/暴雨冲击工况（三种进水模式，同一退化配置）</h2>')
h.append('<img src="data:image/png;base64,%s">'%rsimg)
h.append(tbl(rs[['工况','健康误报_自适应','健康误报_冻结','自适应首报','冻结首报','检出延迟天','健康滚动5天中位数','退化滚动5天中位数']]))
h.append('<div class="warn"><b>两个方向要一起看：</b>① 负面：冻结通道健康误报 26 / 18 / 26 次（对照 BSM2 A 窗 0 次），「0 误报」再次被证伪；自适应通道在干天循环与暴雨工况下完全漏检。② 正面：分布位置统计量在同一工况内健康与退化可分离 3-5 倍（0.85/1.10/1.38 对 4.49/4.65/4.78），远优于单点事件机 —— 这正是我们下一步要把冻结通道换成「滚动 N 天中位数 / 工况健康基线」比值判据的实验依据。</div>')
h.append('<h2 style="margin-top:16px">五条设计原则（均为本项目实验独立得出）</h2>')
h.append('<ul style="font-size:13px;line-height:1.9">')
h.append('<li><b>① 双基线并行：</b>短窗自适应管突变（对慢漂移免疫），冻结基线管慢漂移（对突变不灵敏）；取并集报警并标注来源。</li>')
h.append('<li><b>② RUL 挂机理指标：</b>不要用通用健康指数外推代替机理量。</li>')
h.append('<li><b>③ 冻结参考域必须取自「验收合格且已进入稳态」的历史段：</b>BSM1 第 0-10 天是启动暂态，拿它当参考会让阈值被压到 4.4、健康运行 120 天误报 75 次；改用稳态段（第 30-45 天）后阈值 20.2、误报 0。</li>')
h.append('<li><b>④ 慢漂移的严重度用分布位置统计量（滚动中位数/分位数偏移）或机理指标表达：</b>单点越限的时刻不含严重度信息 —— 6 个退化场景的冻结通道首报都在第 40.3 天，而滚动 5 天中位数随严重度从 1.78 单调升到 4.32。</li>')
h.append('<li><b>⑤ 危险/失效阈值按工况自身的健康基线标定（相对劣化幅度），不能用绝对值：</b>换一段进水，健康运行的 SO3 本底就从 1.65 降到 0.61 mg/L，绝对阈值 SO3<0.5 在健康运行中就已经长期成立。</li>')
h.append('</ul>')
h.append('<div class="warn"><b>诚实说明：</b>BSM1 为公开标准模型仿真；本节阈值分位、退化幅值与成本参数均为演示设置，未经现场标定。</div></div>')
h.append('<div class="card"><h2>九、数据来源与复现</h2><ul style="font-size:13px;line-height:1.9">')
h.append('<li>SKAB（真实水泵台架）｜ MetroPT-3（地铁空压机，UCI 791）｜ CWRU（轴承故障）｜ C-MAPSS FD001（NASA 涡扇退化）｜ BSM1（IWA 标准活性污泥模型，自建仿真闭环）</li>')
h.append('<li>一键复现：<b>python src/dsh/2026-09-18_14_pipeline.py</b>（检测→诊断→RUL→决策）</li>')
h.append('<li>一致性自检：<b>python src/dsh/2026-09-18_18_consistency_check_v2.py</b></li>')
h.append('<li>局限：四个数据集都来自公开工业设备，与污水厂水泵/鼓风机的工况不同；成本参数未经企业标定；仿真与占位数据均已标注。</li>')
h.append('</ul></div>')
h.append('</div></body></html>')
io.open('demo/lanmai_demo.html','w',encoding='utf-8').write(''.join(h))
print('已生成 demo/lanmai_demo.html  %.0f KB' % (os.path.getsize('demo/lanmai_demo.html')/1024))
print('告警表列：',list(alarms.columns))