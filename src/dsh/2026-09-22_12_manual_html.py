# -*- coding: utf-8 -*-
"""把 docs/11_项目说明书.md 渲染成自包含可打印 HTML（内嵌真实截图与结果图）。
产物：deliverables/澜脉_项目说明书.html（浏览器打开 → Ctrl+P → 另存为 PDF；A4 打印样式）
用法：python src/dsh/2026-09-22_12_manual_html.py
"""
import io, os, re, base64, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
MD = 'docs/11_项目说明书.md'
OUT = 'deliverables/澜脉_项目说明书.html'
NL = chr(10)

FIG = [
    ('deliverables/shots/s1_landing.png', '图 1　线上落地页（index.html）：作品入口与三条主线'),
    ('deliverables/shots/s2_demo_dashboard.png', '图 2　十节演示看板（demo/lanmai_demo.html）：从检测到决策的全部结果与口径'),
    ('deliverables/shots/s3_twin.png', '图 3　交互式数字孪生演示台（demo/lanmai_twin.html）：健康/退化轨迹与告警回放'),
    ('deliverables/shots/s4_report_metropt3.png', '图 4　企业版报告（真实空压机 MetroPT-3，214 天）：KPI 与分级告警'),
    ('deliverables/shots/s6_workbench.png', '图 5　本地工作台（lanmai serve）：上传 CSV → 标定基线 → 出报告，数据不出本机'),
    ('deliverables/shots/s5_report_bsm1.png', '图 6　企业版报告（BSM1 仿真退化轨迹）：相对时间按「第 X 天」呈现'),
    ('results/2026-09-18/dsh/figures_4in1.png', '图 7　真实数据四图：误报-召回曲线 / 维护策略成本 / 敏感性网格 / RUL 散点'),
    ('results/2026-09-20/dsh/bsm1_4in1.png', '图 8　数字孪生闭环四图（BSM1）：退化注入 → 检测 → RUL → 决策'),
    ('results/2026-09-21/dsh/sludge_line2.png', '图 9　污泥线闭环（路线 A）：泥饼含固率、湿泥饼量、滤液 TSS 与检测分数'),
    ('results/2026-09-22/dsh/bsm2_route_b_detect.png', '图 10　BSM2 整厂退化（路线 B）：原始量 vs 设备级比值通道'),
    ('results/2026-09-22/dsh/bsm2_route_b_cond.png', '图 11　补强①：工况条件化与同工况对拍差分的检出延迟对比'),
    ('results/2026-09-22/dsh/bsm2_route_b_drift.png', '图 12　补强②：标定漂移的结构 × 幅度 × 缓解手段'),
]


def esc(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def inline(s):
    s = esc(s)
    s = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', s)
    s = re.sub(r'(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)', r'<i>\1</i>', s)
    return s


def md2html(md):
    out = []
    lines = md.split(NL)
    i = 0
    while i < len(lines):
        l = lines[i]
        if not l.strip():
            i += 1
            continue
        if re.match(r'^---+$', l.strip()):
            out.append('<hr>'); i += 1; continue
        m = re.match(r'^(#{1,4})\s+(.*)$', l)
        if m:
            lvl = len(m.group(1))
            out.append('<h%d>%s</h%d>' % (lvl, inline(m.group(2)), lvl)); i += 1; continue
        if l.strip().startswith('>'):
            buf = []
            while i < len(lines) and lines[i].strip().startswith('>'):
                buf.append(inline(lines[i].strip()[1:].strip())); i += 1
            out.append('<div class=quote>%s</div>' % '<br>'.join(buf)); continue
        if l.lstrip().startswith('|') and i + 1 < len(lines) and re.match(r'^\s*\|[\s:|-]+\|\s*$', lines[i + 1]):
            head = [c.strip() for c in l.strip().strip('|').split('|')]
            i += 2
            rows = []
            while i < len(lines) and lines[i].lstrip().startswith('|'):
                rows.append([c.strip() for c in lines[i].strip().strip('|').split('|')]); i += 1
            t = ['<table><thead><tr>' + ''.join('<th>%s</th>' % inline(h) for h in head) + '</tr></thead><tbody>']
            for r in rows:
                t.append('<tr>' + ''.join('<td>%s</td>' % inline(c) for c in r) + '</tr>')
            t.append('</tbody></table>')
            out.append(''.join(t)); continue
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
        out.append('<p>%s</p>' % inline(l.strip()))
        i += 1
    return NL.join(out)


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
       '@media print{body{background:#fff}.page{box-shadow:none;max-width:none;padding:0 8mm}h2{page-break-after:avoid}table,pre{page-break-inside:avoid}}')

md = io.open(MD, encoding='utf-8').read()
body = md2html(md)
figs = []
for p, cap in FIG:
    if os.path.exists(p):
        b64 = base64.b64encode(io.open(p, 'rb').read()).decode()
        figs.append('<div class=fig><img src="data:image/png;base64,%s"><div class=cap>%s</div></div>' % (b64, esc(cap)))
    else:
        figs.append('<div class=fig><div class=cap>（缺图：%s）</div></div>' % esc(p))

H = []
A = H.append
A('<!DOCTYPE html><html lang=zh-CN><head><meta charset=utf-8>')
A('<meta name=viewport content="width=device-width,initial-scale=1">')
A('<title>澜脉 · 项目说明书 / 技术报告</title><style>%s</style></head><body><div class=page>' % CSS)
A('<div class=cover><h1>澜脉（AquaPulse）· 污水厂设备 AI 预测性维护系统</h1>')
A('<div class=meta>北控水务杯第九届中国国际生态环境创新大赛 ｜ 创意转化组 ｜ 命题方向 2-6「基于 AI 设备预测性维护与管理技术与解决方案」<br>')
A('项目说明书 / 技术报告 ｜ 生成时间 %s ｜ 全部数字可在项目仓库复现（结果文件 + 一键复现命令）</div></div>' % datetime.datetime.now().strftime('%Y-%m-%d %H:%M'))
A(body)
A('<h2>附图：真实截图与结果图</h2>')
A(''.join(figs))
A('<hr><div class=meta>本文档由仓库脚本生成：docs/11_项目说明书.md（正文）→ 本页（自包含 HTML，可直接打印为 PDF）。</div>')
A('</div></body></html>')
io.open(OUT, 'w', encoding='utf-8').write(NL.join(H))
print('已生成 %s（%.1f KB，内嵌图 %d 张）' % (OUT, os.path.getsize(OUT) / 1024.0, len(figs)))
