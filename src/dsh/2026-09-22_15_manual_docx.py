# -*- coding: utf-8 -*-
"""把 docs/11_项目说明书.md 渲染成 Word（.docx）：A4、中文样式、表格、代码块、按章节插入 38 张图。
产物：deliverables/澜脉_项目说明书.docx
用法：python src/dsh/2026-09-22_15_manual_docx.py
"""
import io, os, re, datetime
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
MD = 'docs/11_项目说明书.md'
OUT = 'deliverables/澜脉_项目说明书.docx'
NL = chr(10)
BLUE, DARK = '12507B', '1B2733'

# 图与章节映射（与说明书正文的【图 X】引用一致）
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


def shade(cell_or_par, fill):
    el = cell_or_par._tc.get_or_add_tcPr() if hasattr(cell_or_par, '_tc') else cell_or_par._p.get_or_add_pPr()
    shd = OxmlElement('w:shd'); shd.set(qn('w:val'), 'clear'); shd.set(qn('w:fill'), fill); el.append(shd)


def set_cjk(run, name='Microsoft YaHei'):
    run.font.name = name
    rpr = run._element.get_or_add_rPr()
    rf = rpr.find(qn('w:rFonts'))
    if rf is None:
        rf = OxmlElement('w:rFonts'); rpr.append(rf)
    rf.set(qn('w:eastAsia'), name)


def add_runs(p, text, size=10.5, color=None):
    for seg in re.split(r'(\*\*.+?\*\*)', text):
        if not seg:
            continue
        bold = seg.startswith('**') and seg.endswith('**')
        r = p.add_run(seg[2:-2] if bold else seg)
        r.bold = bold; r.font.size = Pt(size)
        if color:
            r.font.color.rgb = RGBColor.from_string(color)
        set_cjk(r)
    return p


def parse(md):
    toks, lines, i = [], md.split(NL), 0
    while i < len(lines):
        l = lines[i]
        if not l.strip():
            i += 1; continue
        if re.match(r'^---+$', l.strip()):
            toks.append(('hr', None)); i += 1; continue
        m = re.match(r'^(#{1,4})\s+(.*)$', l)
        if m:
            toks.append(('h%d' % len(m.group(1)), m.group(2).strip())); i += 1; continue
        if l.strip().startswith('>'):
            buf = []
            while i < len(lines) and lines[i].strip().startswith('>'):
                buf.append(lines[i].strip()[1:].strip()); i += 1
            toks.append(('quote', ' '.join(buf))); continue
        if l.lstrip().startswith('|') and i + 1 < len(lines) and re.match(r'^\s*\|[\s:|-]+\|\s*$', lines[i + 1]):
            head = [c.strip() for c in l.strip().strip('|').split('|')]; i += 2; rows = []
            while i < len(lines) and lines[i].lstrip().startswith('|'):
                rows.append([c.strip() for c in lines[i].strip().strip('|').split('|')]); i += 1
            toks.append(('table', (head, rows))); continue
        if re.match(r'^\s{4,}\S', l):
            buf = []
            while i < len(lines) and (re.match(r'^\s{4,}\S', lines[i]) or not lines[i].strip()):
                if lines[i].strip():
                    buf.append(lines[i][4:])
                i += 1
            toks.append(('pre', NL.join(buf))); continue
        if re.match(r'^\s*[-*]\s+', l):
            buf = []
            while i < len(lines) and re.match(r'^\s*[-*]\s+', lines[i]):
                buf.append(re.sub(r'^\s*[-*]\s+', '', lines[i])); i += 1
            toks.append(('ul', buf)); continue
        if re.match(r'^\s*\d+\.\s+', l):
            buf = []
            while i < len(lines) and re.match(r'^\s*\d+\.\s+', lines[i]):
                buf.append(re.sub(r'^\s*\d+\.\s+', '', lines[i])); i += 1
            toks.append(('ol', buf)); continue
        toks.append(('p', l.strip())); i += 1
    return toks


def build():
    doc = Document()
    s = doc.sections[0]
    s.page_width, s.page_height = Cm(21), Cm(29.7)
    s.left_margin = s.right_margin = Cm(2.2); s.top_margin = s.bottom_margin = Cm(2.2)
    st = doc.styles['Normal']; st.font.name = 'Microsoft YaHei'; st.font.size = Pt(10.5)
    st.element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')
    for lvl, size, color in [(1, 16, BLUE), (2, 13.5, BLUE), (3, 12, DARK), (4, 11, DARK)]:
        h = doc.styles['Heading %d' % lvl]
        h.font.name = 'Microsoft YaHei'; h.font.size = Pt(size); h.font.bold = True
        h.font.color.rgb = RGBColor.from_string(color)
        h.element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')

    # 封面
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    add_runs(p, '**澜脉（AquaPulse）· 污水厂设备 AI 预测性维护系统**', 20, BLUE)
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    add_runs(p, '北控水务杯第九届中国国际生态环境创新大赛 ｜ 创意转化组 ｜ 命题方向 2-6', 11)
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    add_runs(p, '「基于 AI 设备预测性维护与管理技术与解决方案」', 11)
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    add_runs(p, '项目说明书 / 技术报告　｜　生成时间 %s　｜　内嵌 %d 张图' % (
        datetime.datetime.now().strftime('%Y-%m-%d'), len(FIGS)), 10)
    doc.add_paragraph()

    toks = parse(io.open(MD, encoding='utf-8').read())
    n_img = 0; n_tbl = 0
    for idx, (kind, val) in enumerate(toks):
        if kind == 'h1':
            if idx > 3:
                doc.add_page_break()
            doc.add_heading(val, level=1)
        elif kind in ('h2', 'h3', 'h4'):
            doc.add_heading(val, level=int(kind[1]))
        elif kind == 'p':
            add_runs(doc.add_paragraph(val.replace('**', '**')), val)
        elif kind == 'quote':
            pp = doc.add_paragraph(); shade(pp, 'F0F6FB')
            add_runs(pp, val, 9.5, '31465A')
        elif kind == 'pre':
            for ln in val.split(NL):
                pp = doc.add_paragraph(); rr = pp.add_run(ln if ln else ' ')
                rr.font.name = 'Consolas'; rr.font.size = Pt(8.5); set_cjk(rr, 'Consolas')
        elif kind in ('ul', 'ol'):
            for item in val:
                add_runs(doc.add_paragraph(style='List Bullet' if kind == 'ul' else 'List Number'), item)
        elif kind == 'table':
            head, rows = val
            t = doc.add_table(rows=1, cols=len(head)); t.style = 'Table Grid'; n_tbl += 1
            for j, h in enumerate(head):
                c = t.rows[0].cells[j]; c.text = ''
                add_runs(c.paragraphs[0], h, 9.5, DARK); shade(c, 'F0F6FB')
                for rr in c.paragraphs[0].runs:
                    rr.bold = True
            for r in rows:
                cells = t.add_row().cells
                for j, x in enumerate(r[:len(head)]):
                    cells[j].text = ''
                    add_runs(cells[j].paragraphs[0], x, 9)
        elif kind == 'hr':
            doc.add_paragraph()
        # 章节末尾插图
        title = val if isinstance(val, str) else ''
        for anchor, paths in GROUPS:
            if kind == 'h2' and anchor in title or (kind == 'h3' and anchor in title):
                for ip in paths:
                    if not os.path.exists(ip):
                        continue
                    doc.add_picture(ip, width=Cm(15.5))
                    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
                    cp = doc.add_paragraph(); cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    add_runs(cp, FIGS.get(ip, os.path.basename(ip)), 8.5, '5B6B7C')
                    n_img += 1
    doc.save(OUT)
    print('已生成 %s（%.1f MB）｜ 插图 %d 张 ｜ 表格 %d 个 ｜ 段落 %d 个' % (
        OUT, os.path.getsize(OUT) / 1048576.0, n_img, n_tbl, len(doc.paragraphs)))


if __name__ == '__main__':
    build()
