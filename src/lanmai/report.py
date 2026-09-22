# -*- coding: utf-8 -*-
"""lanmai.report —— 企业版离线报告（自包含单文件 HTML；澜脉，DSH，2026-09-22）

用途：把「一份现场数据 + 一份已标定基线」变成可以直接发给设备科/厂长的报告：
体检摘要 / 标定摘要 / 分级告警明细 / 四张图 / 口径与局限 / 复现命令。

设计约束：
 ① 只调用 core 与 pipeline 里同一套函数，不引入第二套算法；
 ② 自包含（图 base64 内嵌），可离线双击打开，数据不出本机；
 ③ 没有 matplotlib 时降级为无图报告；
 ④ **时间口径**：真实现场数据（真实日期）按日期展示；仿真/相对时间数据（数值时间列、起点 0 → 显示为 1970 年）
    自动切换为「第 X 天」，并在报告顶部显著说明，避免误读；
 ⑤ 固定写明局限（阈值须现场标定、参考段须人工确认、工具只做检测与标定…）。
"""
import os, io, json, base64, datetime
import numpy as np
import pandas as pd

TOOL = 'lanmai 报告生成器 v1.1 · 澜脉（AquaPulse）· DSH 2026-09-22'


def _scores(df, base):
    from .core import state_series, adaptive_z, frozen_z, topk_score, window_of
    st = state_series(df, base['state']['kind'], base['state'].get('col'), base['state'].get('nbin', 4),
                      base['state'].get('channel'))
    Za = pd.DataFrame({c: adaptive_z(df, c, st, win_days=base['adaptive']['win_days']) for c in base['channels']})
    Zf = pd.DataFrame({c: frozen_z(df, c, base['frozen'][c], st, base['floor'][c]) for c in base['channels']})
    sa = topk_score(Za, 3).astype(float)
    sf = topk_score(Zf, 3).astype(float)
    win = window_of(sf.index, base['ratio']['window_days'])
    rr = (sf.rolling(win, min_periods=8).median() / base['ratio']['base_median']).astype(float)
    return sa, sf, rr


def _is_relative(df):
    """时间列是否为相对时间（数值起点 0 → 1970 占位）。"""
    return bool(df.index[0].year <= 1970)


def _days(series, t0):
    return np.asarray([(pd.Timestamp(x) - t0).total_seconds() / 86400.0 for x in series], dtype=float)


def _tbl(headers, rows, cls='tbl'):
    h = ''.join('<th>%s</th>' % x for x in headers)
    body = ''.join('<tr>' + ''.join('<td>%s</td>' % x for x in r) + '</tr>' for r in rows)
    return '<table class=tbl><thead><tr>%s</tr></thead><tbody>%s</tbody></table>' % (h, body)


def _figs(df, base, sa, sf, rr, alarms, max_pts=2500):
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        plt.rcParams['font.sans-serif'] = ['Microsoft YaHei']
        plt.rcParams['axes.unicode_minus'] = False
    except Exception as e:
        return [], '未安装 matplotlib（%s）→ 本报告不含图，数值部分不受影响' % type(e).__name__
    rel = _is_relative(df)
    t0 = df.index[0]
    step = max(1, len(df) // max_pts)
    if rel:
        ix = _days(df.index, t0)[::step]
        xlab = '第 X 天（相对时间：该数据集时间列是数值，1970 年仅为占位）'
        A0, A1 = _days(alarms['起点'], t0), _days(alarms['结束'], t0)
        ref0, ref1 = _days([base['meta']['参考窗起点'], base['meta']['参考窗终点']], t0)
    else:
        ix = np.asarray(df.index)[::step]
        xlab = ''
        A0, A1 = np.asarray(alarms['起点']), np.asarray(alarms['结束'])
        ref0, ref1 = pd.Timestamp(base['meta']['参考窗起点']), pd.Timestamp(base['meta']['参考窗终点'])
    S = lambda s: np.asarray(s, dtype=float)[::step]
    thr = float(base['threshold']['value'])
    figs = []

    fig, ax = plt.subplots(2, 2, figsize=(12.4, 7.2))
    ax[0, 0].plot(ix, S(sa), color='#1f77b4', lw=.8, label='自适应（短窗，抓突变）')
    ax[0, 0].plot(ix, S(sf), color='#d62728', lw=.8, label='冻结（固定基线，抓慢漂移）')
    ax[0, 0].axhline(thr, color='#2ca02c', ls='--', lw=1)
    ax[0, 0].text(ix[0], thr + thr * .05, '判据阈值 %.3f' % thr, color='#2ca02c', fontsize=8)
    for k in range(len(alarms)):
        c = {1: '#d62728', 2: '#ff7f0e', 3: '#7f7f7f'}.get(int(alarms.iloc[k]['等级']), '#7f7f7f')
        ax[0, 0].axvspan(A0[k], A1[k], color=c, alpha=.12)
    ax[0, 0].set_title('① 双基线分数与告警区间（底色=告警等级）')
    ax[0, 0].set_xlabel(xlab); ax[0, 0].legend(fontsize=8); ax[0, 0].grid(alpha=.3)

    ax[0, 1].plot(ix, S(rr), color='#9467bd', lw=.8, label='分布位置比值（滚动中位 / 基线中位）')
    ax[0, 1].axhline(1.0, color='#7f7f7f', lw=1)
    for lv, col, lab in [(base['ratio']['level1'], '#ff7f0e', 'P1 门限'), (base['ratio']['level3'], '#d62728', 'P3 门限')]:
        ax[0, 1].axhline(lv, color=col, ls='--', lw=1, label='%s %.2f' % (lab, lv))
    ax[0, 1].set_title('② 分布位置漂移（慢退化的严重度指标）')
    ax[0, 1].set_xlabel(xlab); ax[0, 1].legend(fontsize=8); ax[0, 1].grid(alpha=.3)

    for c in list(base['channels'])[:3]:
        v = np.asarray(df[c], dtype=float)[::step]
        m = np.nanmedian(np.asarray(df[c], dtype=float))
        ax[1, 0].plot(ix, v / m if m else v, lw=.8, label=c)
    ax[1, 0].axvspan(ref0, ref1, color='#2ca02c', alpha=.10)
    ax[1, 0].text(ref0, ax[1, 0].get_ylim()[1], ' 标定参考窗', color='#2ca02c', fontsize=8, va='top')
    ax[1, 0].set_title('③ 通道相对变化（/参考中位；绿区=标定参考窗）')
    ax[1, 0].set_xlabel(xlab); ax[1, 0].legend(fontsize=8); ax[1, 0].grid(alpha=.3)

    if len(alarms):
        for lv, col in [(1, '#d62728'), (2, '#ff7f0e'), (3, '#7f7f7f')]:
            idx = [k for k in range(len(alarms)) if int(alarms.iloc[k]['等级']) == lv]
            if idx:
                ax[1, 1].barh([A0[k] for k in idx],
                              [alarms.iloc[k]['持续分钟'] / 60.0 for k in idx],
                              height=.35, color=col, label='P%d' % lv)
        ax[1, 1].set_title('④ 告警时间线（横条长度=持续小时）')
        ax[1, 1].set_xlabel('持续小时'); ax[1, 1].legend(fontsize=8)
    else:
        ax[1, 1].text(.5, .5, '本次数据无告警', ha='center', va='center', fontsize=12)
        ax[1, 1].set_title('④ 告警时间线')
    if rel:
        ax[1, 1].set_ylabel('第 X 天')
    ax[1, 1].grid(alpha=.3)
    fig.suptitle('澜脉 · 设备健康报告（%s）' % os.path.basename(base.get('meta', {}).get('source', '')), fontsize=13)
    fig.tight_layout()
    buf = io.BytesIO(); fig.savefig(buf, format='png', dpi=115); plt.close(fig)
    figs.append(('综合四图', base64.b64encode(buf.getvalue()).decode()))
    return figs, None


def build_report(data, baseline, out, time_col=None, resample=None, warmup=None,
                 title=None, max_alarms=40, no_fig=False):
    from .core import load_table
    from .pipeline import inspect, watch
    df = load_table(data, time_col, resample, None)
    base = json.load(io.open(baseline, encoding='utf-8'))
    A, sm = watch(df, base, warmup=warmup)
    info = inspect(df)
    rel = _is_relative(df)
    t0 = df.index[0]
    span_days = (df.index[-1] - t0).total_seconds() / 86400.0
    sa, sf, rr = _scores(df, base)
    figs, fig_note = ([], '按 --no-fig 跳过出图') if no_fig else _figs(df, base, sa, sf, rr, A)
    missing = [c for c in base['channels'] if c not in df.columns]
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    def _v(x):
        return '—' if x is None else x
    st_rows = [[c, st['缺失率'], _v(st['均值']), _v(st['标准差']), _v(st['最小值']), _v(st['最大值']),
                '是' if st.get('零方差') else '', st.get('类型', '数值'),
                (st.get('取值数') if st.get('类型') == '非数值' else '')] for c, st in info['通道统计'].items()]

    first_alarm = sm['首报']
    if rel and first_alarm:
        first_alarm_txt = '第 %.2f 天' % _days([first_alarm], t0)[0]
    else:
        first_alarm_txt = first_alarm or '无告警'
    kpi = [('数据行数', '{:,}'.format(info['行数'])), ('通道数', info['通道数']),
           ('时间跨度', ('%.2f 天（相对时间）' % span_days) if rel else '%.1f 天' % span_days),
           ('告警总数', sm['告警总数']),
           ('P1 立即处置', sm['分级'].get(1, 0)), ('P2 复核排计划', sm['分级'].get(2, 0)),
           ('P3 趋势观察', sm['分级'].get(3, 0)), ('首报', first_alarm_txt)]
    kpi_html = ''.join('<div class=v><div class=n>%s</div><div class=l>%s</div></div>' % (v, k) for k, v in kpi)

    rel_block = ''
    if rel:
        rel_block = ('<div class=warn><b>时间口径（重要）：</b>该数据集的时间列是<b>相对时间</b>（数值、起点 0），'
                     '因此报告里的 1970 年日期只是占位 —— 请按「<b>第 X 天</b>」阅读（全文与四张图均已用相对天数，'
                     '本次数据跨度为 %.2f 天）。真实现场数据（例如 MetroPT-3 空压机）会显示真实日期。</div>' % span_days)

    m = base['meta']; t = base['threshold']
    if rel:
        d_span = _days([m['时间起点'], m['时间终点'], m['参考窗起点'], m['参考窗终点']], t0)
        rng_row = '第 %.2f 天 → 第 %.2f 天（相对时间；1970 年日期仅为占位）' % (d_span[0], d_span[1])
        ref_row = '第 %.2f 天 → 第 %.2f 天（%d 行）' % (d_span[2], d_span[3], m['参考窗行数'])
    else:
        rng_row = '%s → %s' % (m['时间起点'], m['时间终点'])
        ref_row = '%s → %s（%d 行）' % (m['参考窗起点'], m['参考窗终点'], m['参考窗行数'])
    cal_rows = [['数据时间范围', rng_row],
                ['标定参考窗', ref_row],
                ['工况分层', base['state']['kind'] + ('' if not base['state'].get('col') else '（列：%s）' % base['state']['col'])],
                ['判据阈值（冻结分数分位）', '%.4f → %.4f' % (base.get('q', float('nan')), t['value'])],
                ['自适应窗', '%.1f 天' % base['adaptive']['win_days']],
                ['事件机（进入/退出/退出比/冷却）', '%s / %s / %s / %s' % (base['event']['enter'], base['event']['exit_'], base['event']['ratio'], base['event']['cooldown'])],
                ['分级门限', 'P1 分布位置比值 ≥ %.2f；P3 ≥ %.2f' % (base['ratio']['level1'], base['ratio']['level3'])]]
    if t.get('per_segment'):
        cal_rows.append(['多段标定', '；'.join('%s → %.3f' % (r['段'], r['阈值']) for r in t['per_segment'])])
    if t.get('阈值范围'):
        r = t['阈值范围']
        cal_rows.append(['阈值范围（多段）', '最小 %.3f / 中位 %.3f / 最大 %.3f（极差比 %.2f 倍，策略 %s）'
                         % (r['最小'], r['中位'], r['最大'], r['极差比'], t['policy'])])
    warn_html = ''.join('<li>%s</li>' % w for w in base.get('warnings', []))
    warn_block = ('<div class=warn><b>标定时工具给出的警告（必须人工处理）：</b><ul>%s</ul></div>' % warn_html) if warn_html else ''
    miss_block = ('<div class=warn><b>数据缺少基线里的通道：</b>%s → 这些通道本次未参与判据</div>' % '、'.join(missing)) if missing else ''

    show = A.head(max_alarms)
    if rel:
        alarm_rows = [[('第 %.2f 天' % _days([r['起点']], t0)[0]), ('第 %.2f 天' % _days([r['结束']], t0)[0]),
                       r['持续分钟'], r['来源通道'], r['峰值分数'], r['判据阈值'], r['分布位置比值'], 'P%d' % int(r['等级'])]
                      for _, r in show.iterrows()]
        a_headers = ['起点（相对时间）', '结束（相对时间）', '持续分钟', '来源通道', '峰值分数', '判据阈值', '分布位置比值', '等级']
    else:
        alarm_rows = [[r['起点'], r['结束'], r['持续分钟'], r['来源通道'], r['峰值分数'], r['判据阈值'],
                       r['分布位置比值'], 'P%d' % int(r['等级'])] for _, r in show.iterrows()]
        a_headers = ['起点', '结束', '持续分钟', '来源通道', '峰值分数', '判据阈值', '分布位置比值', '等级']
    more = '' if len(A) <= max_alarms else '<p class=note>（仅列前 %d 条，共 %d 条；完整明细见 watch 输出的 CSV）</p>' % (max_alarms, len(A))
    level_tbl = _tbl(['等级', '含义', '现场动作'], [
        ['P1', '报警 ∧ 分布位置比值 ≥ %.2f' % base['ratio']['level1'], '立即处置：安排检查/停机窗口，优先核对机理量'],
        ['P2', '仅分数越限（未达 P1 门限）', '复核后合并到计划检修，不必单独停机'],
        ['P3', '仅分布位置漂移（慢退化趋势）', '趋势观察：纳入月度报表，跟踪漂移速度']])

    figs_html = ''.join('<figure><img src=data:image/png;base64,%s><figcaption>%s</figcaption></figure>' % (b, c) for c, b in figs)
    if not figs:
        figs_html = '<div class=warn>本报告未包含图：%s</div>' % (fig_note or '')
    cmd = ['python -m lanmai report --data %s --baseline %s --out %s' % (os.path.basename(data), os.path.basename(baseline), os.path.basename(out))]
    if resample:
        cmd.append('--resample %s' % resample)
    if warmup:
        cmd.append('--warmup %s' % warmup)

    H = []
    A_ = H.append
    A_('<!DOCTYPE html><html lang=zh-CN><head><meta charset=utf-8>')
    A_('<meta name=viewport content=width=device-width,initial-scale=1>')
    A_('<title>%s</title>' % (title or '澜脉 · 设备健康报告'))
    A_('<style>')
    A_('body{margin:0;background:#f6f8fa;color:#1b2733;font-family:Microsoft YaHei,Helvetica,Arial,sans-serif;font-size:14px;line-height:1.7}')
    A_('.wrap{max-width:1080px;margin:0 auto;padding:24px 18px 60px}')
    A_('h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:26px 0 8px;padding-left:9px;border-left:4px solid #12507b}')
    A_('.sub{color:#5b6b7c;font-size:12px;margin-bottom:14px}')
    A_('.kpis{display:flex;gap:10px;flex-wrap:wrap;margin:10px 0 4px}')
    A_('.v{flex:1;min-width:120px;background:#fff;border:1px solid #e3e8ee;border-radius:8px;padding:10px 12px}')
    A_('.v .n{font-size:19px;font-weight:600;color:#12507b}.v .l{font-size:12px;color:#5b6b7c}')
    A_('table.tbl{width:100%;border-collapse:collapse;background:#fff;font-size:12.5px}')
    A_('table.tbl th,table.tbl td{border:1px solid #e3e8ee;padding:5px 7px;text-align:left}')
    A_('table.tbl th{background:#f0f6fb;font-weight:600}')
    A_('.warn{background:#fff7e6;border:1px solid #ffd591;border-radius:6px;padding:9px 12px;margin:10px 0;font-size:13px}')
    A_('.note{color:#5b6b7c;font-size:12px}')
    A_('figure{margin:10px 0}img{width:100%;border:1px solid #e3e8ee;border-radius:6px;background:#fff}')
    A_('figcaption{font-size:12px;color:#5b6b7c;margin-top:4px}')
    A_('code{background:#eef2f6;padding:1px 5px;border-radius:4px;font-size:12px}')
    A_('</style></head><body><div class=wrap>')
    A_('<h1>%s</h1>' % (title or '澜脉 · 设备健康报告'))
    A_('<div class=sub>工具：%s ｜ 生成时间：%s ｜ 数据：%s ｜ 基线：%s</div>' % (TOOL, now, os.path.basename(data), os.path.basename(baseline)))
    A_('<div class=sub>本报告在本机离线生成，数据未上传任何外部服务。</div>')
    A_(rel_block)
    A_('<div class=kpis>%s</div>' % kpi_html)
    A_('<h2>一、数据体检</h2>')
    if rel:
        rng_txt = '第 %.2f 天 → 第 %.2f 天（相对时间）' % (0.0, span_days)
    else:
        rng_txt = '%s → %s' % (info['起始'], info['结束'])
    A_('<p>行数 %s ｜ 时间范围 %s ｜ 采样间隔中位 %s 秒 ｜ 通道数 %s%s</p>' % (
        '{:,}'.format(info['行数']), rng_txt,
        ('%.0f' % info['采样间隔中位秒']) if info['采样间隔中位秒'] else '未知', info['通道数'],
        ('（零方差通道：%s）' % '、'.join(info['零方差通道'])) if info['零方差通道'] else ''))
    A_(_tbl(['通道', '缺失率', '均值', '标准差', '最小', '最大', '零方差', '类型', '取值数'], st_rows))
    A_('<h2>二、基线标定摘要</h2>')
    A_(_tbl(['项目', '取值'], cal_rows))
    A_(warn_block + miss_block)
    A_('<h2>三、分级告警</h2>')
    A_(level_tbl)
    A_('<p>本次共 <b>%d</b> 个告警（P1 %d / P2 %d / P3 %d），首报 %s</p>' % (
        sm['告警总数'], sm['分级'].get(1, 0), sm['分级'].get(2, 0), sm['分级'].get(3, 0), first_alarm_txt))
    if len(A):
        A_(_tbl(a_headers, alarm_rows))
        A_(more)
    else:
        A_('<div class=warn>本次数据在给定阈值下无告警。注意：无告警不等于设备健康，只说明没有越过你标定的判据。</div>')
    A_('<h2>四、图</h2>')
    A_(figs_html)
    A_('<h2>五、口径与局限（务必与数字一起读）</h2>')
    A_('<ul>')
    A_('<li><b>阈值必须按现场标定</b>：本报告的阈值来自你提供的健康期数据；换一段参考窗，阈值可以差 2–4 倍（多段标定更稳）。</li>')
    A_('<li><b>参考窗是否健康，工具判不了</b>：我们只能告警「该段有显著趋势」，是否有过检修/故障必须由现场确认。</li>')
    A_('<li><b>分级规则是工程折中</b>：P1 = 报警 ∧ 分布位置比值 ≥ %.2f；该门限未做敏感性扫描。</li>' % base['ratio']['level1'])
    A_('<li><b>本工具只做检测与标定</b>：不含故障诊断与剩余寿命（RUL）；那两段在我们另一条研究链路上（见 PROJECT_STATE 第 18 / 25 / 27 节）。</li>')
    A_('<li><b>工况列质量决定上限</b>：没有可靠的状态列时只能用时段近似，效果会下降。</li>')
    A_('<li><b>设备级退化要盯设备本体的物料平衡量</b>：全厂能耗/沼气/出水水质对这类退化几乎不敏感（第 27 节实测 ±0.03%）；且比值法怕系统性标定漂移，需配多源冗余与独立漂移监控（第 29.2 / 30.2 节）。</li>')
    A_('<li><b>成本与收益不在本报告内</b>：本项目所有成本参数为占位值，不得作为真实金额。</li>')
    A_('</ul>')
    A_('<h2>六、复现命令</h2>')
    A_('<p><code>%s</code></p>' % ' '.join(cmd))
    A_('<div class=sub>报告由 lanmai 生成；检测判据与阈值口径见 docs/10 使用手册与 PROJECT_STATE.md。</div>')
    A_('</div></body></html>')
    io.open(out, 'w', encoding='utf-8').write(''.join(H))
    return out
