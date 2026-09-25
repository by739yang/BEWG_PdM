# -*- coding: utf-8 -*-
"""把 docs/11_项目说明书.md 渲染成自包含可打印 HTML（图按章节插入；全图内嵌 base64）。
产物：deliverables/澜脉_项目说明书.html
用法：python src/dsh/2026-09-22_12_manual_html.py
"""
import io, os, re, base64, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
MD = 'docs/11_项目说明书.md'
OUT = 'deliverables/澜脉_项目说明书.html'
NL = chr(10)

# 图库：路径 -> 图注
FIGS = {
 'deliverables/figs/figA_arch.png': '图 A　系统架构：数据 → 算法 → 服务 → 交付四层（全部可离线运行）',
 'deliverables/figs/figB_pipeline.png': '图 B　四段技术链路与每段的关键数字',
 'deliverables/figs/figC_criterion.png': '图 C　检测判据机制示意：双基线 + 事件机 + P1/P2/P3 分级',
 'deliverables/figs/figD_deploy.png': '图 D　三种部署形态与数据流向（默认离线、数据不出厂）',
 'deliverables/figs/figE_poc.png': '图 E　现场试点（POC）四步走',
 'deliverables/shots/s2_demo_dashboard.png': '图 1　十节演示看板全貌（检测到决策的全部结果与口径）',
 'deliverables/shots/s10_demo_detect.png': '图 2　看板·检测节：双基线分数、阈值与告警等级',
 'deliverables/shots/s11_demo_twin.png': '图 3　看板·数字孪生节：退化轨迹与检测/RUL',
 'deliverables/shots/s12_demo_routeb.png': '图 4　看板·整厂闭环节（路线 B）：原始量 vs 设备级比值通道',
 'deliverables/shots/s3_twin.png': '图 5　交互式数字孪生演示台（静态版）',
 'deliverables/shots/s13_twin_anim.png': '图 6　动画演示台：健康/退化两条轨迹回放',
 'deliverables/shots/s6_workbench.png': '图 7　本地工作台：上传 CSV → 标定基线 → 出报告（数据不出本机）',
 'deliverables/shots/s4_report_metropt3.png': '图 8　企业版报告（真实空压机 MetroPT-3）首屏：KPI 与数据体检',
 'deliverables/shots/s7_report_metro_kpi.png': '图 9　报告·体检与标定摘要（含参考窗健康度提示）',
 'deliverables/shots/s8_report_metro_alarms.png': '图 10　报告·分级告警明细（P1/P2/P3）',
 'deliverables/shots/s9_report_metro_tail.png': '图 11　报告·图表与口径局限',
 'deliverables/shots/s5_report_bsm1.png': '图 12　企业版报告（BSM1 仿真）：相对时间按「第 X 天」呈现',
 'deliverables/shots/s1_landing.png': '图 13　线上落地页：作品入口与三条主线',
 'results/2026-09-18/dsh/figures_4in1.png': '图 14　真实数据四图：误报-召回 / 策略成本 / 敏感性 / RUL 散点',
 'results/2026-09-16/dsh/det_curve_skab.png': '图 15　SKAB 检测误差权衡（DET）曲线：三种方法',
 'results/2026-09-19/dsh/ablation_two_regimes.png': '图 16　消融两套阈值口径：共用硬编码阈值 vs 各自无标签标定',
 'results/2026-09-19/dsh/calib_window_sensitivity.png': '图 17　标定期敏感性：同一模型换健康段，阈值差 2–4 倍',
 'results/2026-09-20/dsh/bsm1_4in1.png': '图 18　BSM1 数字孪生闭环四图：注入 → 检测 → RUL → 决策',
 'results/2026-09-20/dsh/bsm1_sweep_3in1.png': '图 19　BSM1 退化幅值-斜率扫描：首报与幅值无关（严重度需另算）',
 'results/2026-09-20/dsh/bsm1_influent_robustness.png': '图 20　进水工况泛化：绝对阈值跨工况失效',
 'results/2026-09-20/dsh/bsm1_rain_storm.png': '图 21　雨/暴雨冲击工况：工况事件必须单独处理',
 'results/2026-09-20/dsh/bsm1_ratio_rule.png': '图 22　比值判据跨工况检验',
 'results/2026-09-20/dsh/multitraj.png': '图 23　多轨迹稳健性：不同退化起始与速率的检出表现',
 'results/2026-09-21/dsh/online_gate.png': '图 24　在线因果 RUL 门禁：判据与误挂率',
 'results/2026-09-21/dsh/online_chain.png': '图 25　在线链路多轨迹：门禁挂载与在线 RUL 可算性',
 'results/2026-09-20/dsh/alarm_strategy.png': '图 26　组合报警策略（单点/比值/并集/与门）对比',
 'results/2026-09-21/dsh/sludge_line2.png': '图 27　污泥线闭环（路线 A）：含固率、湿泥饼量、滤液与检测分数',
 'results/2026-09-21/dsh/sludge_sweep.png': '图 28　污泥线幅值/速率扫描：8 场景首报一致',
 'results/2026-09-21/dsh/sludge_decision.png': '图 29　维护策略对比：RUL 驱动 vs 固定周期（占位成本）',
 'results/2026-09-22/dsh/bsm2_route_b_detect.png': '图 30　BSM2 整厂退化：原始量检不出、设备级比值通道可检出',
 'results/2026-09-22/dsh/bsm2_route_b_sweep.png': '图 31　整厂幅值/速率扫描：延迟随速率与幅值单调变化',
 'results/2026-09-22/dsh/bsm2_route_b_cond.png': '图 32　补强①：工况条件化与同工况对拍差分的延迟对比',
 'results/2026-09-22/dsh/bsm2_route_b_seasons.png': '图 33　跨相位稳健性：三个进水相位结论一致',
 'results/2026-09-22/dsh/bsm2_route_b_drift.png': '图 34　补强②：标定漂移的结构 × 幅度 × 缓解手段',
}
# 章节锚点 -> 该节末尾插入哪些图（顺序即展示顺序）
GROUPS = [
 ('第 1 章 作品简介', ['deliverables/figs/figA_arch.png', 'deliverables/figs/figB_pipeline.png', 'deliverables/figs/figC_criterion.png']),
 ('2.2 可行性分析', ['deliverables/figs/figD_deploy.png']),
 ('2.3 本项目的特色与创新之处', ['results/2026-09-18/dsh/figures_4in1.png', 'results/2026-09-16/dsh/det_curve_skab.png',
                                 'results/2026-09-19/dsh/ablation_two_regimes.png', 'results/2026-09-19/dsh/calib_window_sensitivity.png']),
 ('2.4 预测内容与预期成效', ['results/2026-09-20/dsh/bsm1_4in1.png', 'results/2026-09-20/dsh/bsm1_sweep_3in1.png',
                              'results/2026-09-20/dsh/bsm1_influent_robustness.png', 'results/2026-09-20/dsh/bsm1_rain_storm.png',
                              'results/2026-09-20/dsh/bsm1_ratio_rule.png']),
 ('3.1 系统架构', ['results/2026-09-20/dsh/multitraj.png', 'results/2026-09-21/dsh/online_gate.png', 'results/2026-09-21/dsh/online_chain.png']),
 ('3.2 核心模块设计', ['results/2026-09-20/dsh/alarm_strategy.png', 'results/2026-09-21/dsh/sludge_line2.png',
                        'results/2026-09-21/dsh/sludge_sweep.png', 'results/2026-09-21/dsh/sludge_decision.png']),
 ('3.4 实验与验证手段', ['results/2026-09-22/dsh/bsm2_route_b_detect.png', 'results/2026-09-22/dsh/bsm2_route_b_sweep.png']),
 ('3.5 关键技术方案', ['results/2026-09-22/dsh/bsm2_route_b_cond.png', 'results/2026-09-22/dsh/bsm2_route_b_seasons.png',
                        'results/2026-09-22/dsh/bsm2_route_b_drift.png']),
 ('3.6 实现形态与使用说明', ['deliverables/shots/s6_workbench.png', 'deliverables/shots/s8_report_metro_alarms.png',
                              'deliverables/shots/s7_report_metro_kpi.png', 'deliverables/shots/s9_report_metro_tail.png',
                              'deliverables/shots/s5_report_bsm1.png', 'deliverables/shots/s4_report_metropt3.png',
                              'deliverables/figs/figE_poc.png']),
 ('附录 D 文件与复现地图', ['deliverables/shots/s1_landing.png', 'deliverables/shots/s2_demo_dashboard.png',
                             'deliverables/shots/s10_demo_detect.png', 'deliverables/shots/s11_demo_twin.png',
                             'deliverables/shots/s12_demo_routeb.png', 'deliverables/shots/s3_twin.png',
                             'deliverables/shots/s13_twin_anim.png']),
]


def esc(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def inline(s):
    s = esc(s)
    s = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', s)
    s = re.sub(r'(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)', r'<i>\1</i>', s)
    return s


def md2html(md):
    out, lines, i = [], md.split(NL), 0
    while i < len(lines):
        l = lines[i]
        if not l.strip():
            i += 1; continue
        if re.match(r'^---+$', l.strip()):
            out.append('<hr>'); i += 1; continue
        m = re.match(r'^(#{1,4})\s+(.*)$', l)
        if m:
            out.append('<h%d>%s</h%d>' % (len(m.group(1)), inline(m.group(2)), len(m.group(1)))); i += 1; continue
        if l.strip().startswith('>'):
            buf = []
            while i < len(lines) and lines[i].strip().startswith('>'):
                buf.append(inline(lines[i].strip()[1:].strip())); i += 1
            out.append('<div class=quote>%s</div>' % '<br>'.join(buf)); continue
        if l.lstrip().startswith('|') and i + 1 < len(lines) and re.match(r'^\s*\|[\s:|-]+\|\s*$', lines[i + 1]):
            head = [c.strip() for c in l.strip().strip('|').split('|')]
            i += 2; rows = []
            while i < len(lines) and lines[i].lstrip().startswith('|'):
                rows.append([c.strip() for c in lines[i].strip().strip('|').split('|')]); i += 1
            t = ['<table><thead><tr>' + ''.join('<th>%s</th>' % inline(h) for h in head) + '</tr></thead><tbody>']
            for r in rows:
                t.append('<tr>' + ''.join('<td>%s</td>' % inline(c) for c in r) + '</tr>')
            t.append('</tbody></table>'); out.append(''.join(t)); continue
        if re.match(r'^\s{4,}\S', l):
            buf = []
            while i < len(lines) and (re.match(r'^\s{4,}\S', lines[i]) or not lines[i].strip()):
                if lines[i].strip():
                    buf.append(esc(lines[i][4:]))
                i += 1
            out.append('<pre>%s</pre>' % NL.join(buf)); continue
        if re.match(r'^\s*[-*]\s+', l):
            buf = []
            while i < len(lines) and re.match(r'^\s*[-*]\s+', lines[i]):
                buf.append('<li>%s</li>' % inline(re.sub(r'^\s*[-*]\s+', '', lines[i]))); i += 1
            out.append('<ul>%s</ul>' % ''.join(buf)); continue
        if re.match(r'^\s*\d+\.\s+', l):
            buf = []
            while i < len(lines) and re.match(r'^\s*\d+\.\s+', lines[i]):
                buf.append('<li>%s</li>' % inline(re.sub(r'^\s*\d+\.\s+', '', lines[i]))); i += 1
            out.append('<ol>%s</ol>' % ''.join(buf)); continue
        out.append('<p>%s</p>' % inline(l.strip())); i += 1
    return NL.join(out)


def fig_block(path):
    cap = FIGS.get(path)
    if not os.path.exists(path):
        return '<div class=fig><div class=cap>（缺图：%s）</div></div>' % esc(path)
    b64 = base64.b64encode(io.open(path, 'rb').read()).decode()
    return '<div class=fig><img src="data:image/png;base64,%s"><div class=cap>%s</div></div>' % (b64, esc(cap or os.path.basename(path)))


CSS = ('body{margin:0;background:#f2f4f7;color:#1b2733;font-family:Microsoft YaHei,Helvetica,Arial,sans-serif;font-size:13.5px;line-height:1.75}'
       '.page{max-width:900px;margin:0 auto;background:#fff;padding:40px 46px 60px;box-shadow:0 2px 14px rgba(0,0,0,.06)}'
       '.cover{border-bottom:3px solid #12507b;padding-bottom:16px;margin-bottom:22px}'
       '.cover h1{font-size:26px;margin:0 0 6px}.cover .meta{font-size:12.5px;color:#5b6b7c}'
       'h1{font-size:21px;margin:26px 0 8px}h2{font-size:17px;margin:24px 0 8px;padding-left:9px;border-left:4px solid #12507b}'
       'h3{font-size:15px;margin:18px 0 6px}h4{font-size:14px;margin:14px 0 6px}'
       'table{width:100%;border-collapse:collapse;margin:10px 0;font-size:12.5px}'
       'th,td{border:1px solid #d8dfe7;padding:6px 8px;text-align:left;vertical-align:top}th{background:#f0f6fb}'
       'pre{background:#f7f9fb;border:1px solid #e3e8ee;border-radius:6px;padding:10px 12px;font-size:12.5px;overflow-x:auto}'
       'ul,ol{margin:8px 0 8px 22px}li{margin:3px 0}'
       '.quote{background:#f0f6fb;border-left:4px solid #9dc3e6;padding:8px 12px;margin:10px 0;font-size:12.5px;color:#31465a}'
       '.fig{margin:16px 0;page-break-inside:avoid}.fig img{width:100%;border:1px solid #e3e8ee;border-radius:6px}'
       '.fig .cap{font-size:12px;color:#5b6b7c;margin-top:4px}'
       'hr{border:0;border-top:1px solid #e3e8ee;margin:22px 0}'
       '@media print{body{background:#fff}.page{box-shadow:none;max-width:none;padding:0 8mm}h2{page-break-after:avoid}table,pre,.fig{page-break-inside:avoid}}')

html = md2html(io.open(MD, encoding='utf-8').read())
missed = []
for anchor, paths in GROUPS:
    blk = ''.join(fig_block(p) for p in paths)
    i = html.find(anchor)
    if i < 0:
        missed.append(anchor); continue
    j = html.find('<h', i + len(anchor))
    if j < 0:
        j = len(html)
    html = html[:j] + blk + html[j:]

H = []
A = H.append
A('<!DOCTYPE html><html lang=zh-CN><head><meta charset=utf-8>')
A('<meta name=viewport content="width=device-width,initial-scale=1">')
A('<title>澜脉 · 项目说明书 / 技术报告</title><style>%s</style></head><body><div class=page>' % CSS)
A('<div class=cover><h1>澜脉（AquaPulse）· 污水厂设备 AI 预测性维护系统</h1>')
A('<div class=meta>北控水务杯第九届中国国际生态环境创新大赛 ｜ 创意转化组 ｜ 命题方向 2-6「基于 AI 设备预测性维护与管理技术与解决方案」<br>')
A('项目说明书 / 技术报告 ｜ 生成时间 %s ｜ 内嵌 %d 张图（自制示意图 + 真实界面截图 + 结果图）｜ 全部数字可在项目仓库复现</div></div>' % (
    datetime.datetime.now().strftime('%Y-%m-%d %H:%M'), len(FIGS)))
A(html)
A('<hr><div class=meta>正文源文件 docs/11_项目说明书.md ｜ 本页由 src/dsh/2026-09-22_12_manual_html.py 生成 ｜ 打印：Ctrl+P → 另存为 PDF（A4）</div>')
A('</div></body></html>')
io.open(OUT, 'w', encoding='utf-8').write(NL.join(H))
n_img = io.open(OUT, encoding='utf-8').read().count('data:image/png;base64,')
print('已生成 %s（%.1f MB）｜ 内嵌图 %d 张 ｜ 未匹配章节：%s' % (OUT, os.path.getsize(OUT) / 1048576.0, n_img, missed or '无'))
