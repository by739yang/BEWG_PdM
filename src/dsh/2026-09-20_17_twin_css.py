# -*- coding: utf-8 -*-
"""生成 CSS 纯标签页版数字孪生演示页（不需要任何脚本，双击必定能打开）
输入：results/2026-09-20/dsh/twin_<场景>.png（由 2026-09-20_16_twin_static.py 生成）
产物：demo/lanmai_twin.html（标签页版，覆盖此前的 canvas 版）
用法：python src/dsh/2026-09-20_17_twin_css.py"""
import os, io, base64
OUT='results/2026-09-20/dsh'
SCEN=[('healthy','健康运行（无退化）','设备正常：SO3 平稳，模型健康分数一直在阈值下方。冻结通道 120 天报警 0 次。',None,None),
 ('deg20','慢退化 -20% / 100 天','曝气能力 100 天缓慢衰减 20%：反应池溶解氧（DO）几乎不变，模型分数开始抬升；第 110 天才越线，提前量 70 天。',40.28,110.34),
 ('deg40','慢退化 -40% / 100 天（最完整一例）','第 20 天开始退化 → 第 40 天报警 → 第 47 天反应池溶解氧（DO）真实失效。机理-溶解氧外推剩余寿命 3.24 天，真值 7.27 天，误差 4.04 天。',40.28,47.34),
 ('deg80','慢退化 -80% / 100 天','衰减幅度加大到 80%，但报警时刻仍在第 40 天附近 —— 单点越限的“时刻”不含严重度信息，严重度要看分布位置或机理量。',40.28,44.33),
 ('fast80','快退化 -80% / 40 天','同样衰减 80%，压缩到 40 天完成：报警第 20.3 天、失效第 29.4 天，提前量只有 2.06 天。',20.32,29.39),
 ('std40','标准进水（BSM1 干天）退化 -40%','换成 BSM1 自带的干天进水（设计负荷）：溶解氧 1.94→0.16，出水氨氮均值 5.69→18.28 mg/L，冻结通道第 57.45 天报警、第 93.33 天曝气功能失效；自适应通道漏检。',57.45,93.33),
 ('storm','雨/暴雨工况 -40% / 100 天','换成干天+雨天循环、每 28 天插 2 天暴雨的进水工况：健康运行时单一阈值就报了 26 次 —— 阈值必须按工况自身基线标定。',20.04,95.32)]
def b64(p): return base64.b64encode(open(p,'rb').read()).decode()

inputs=''.join('<input type="radio" name="sc" id="r%d"%s>'%(i,' checked' if i==0 else '') for i in range(len(SCEN)))
labels=''.join('<label for="r%d">%s</label>'%(i,s[1]) for i,s in enumerate(SCEN))
tabs=inputs+'<div class="tabs">'+labels+'</div>'
panes=[]
for i,(sid,title,note,alarm,fail) in enumerate(SCEN):
    img=b64(os.path.join(OUT,'twin_%s.png'%sid))
    lead=('%.2f'%(fail-alarm)) if (alarm and fail) else '-'
    panes.append('<div class="pane" id="p%d"><h2>%s</h2><img src="data:image/png;base64,%s">'
      '<table><tr><td>模型报警时刻</td><td><b>%s</b></td><td>真实失效时刻</td><td><b>%s</b></td><td>预警提前量</td><td><b>%s 天</b></td></tr>'
      '<tr><td colspan="6" class="n">%s</td></tr></table></div>'%(
      i,title,img,('%.2f 天'%alarm) if alarm else '无（健康运行不报警）',('%.2f 天'%fail) if fail else '无',lead,note))
css_tabs=''.join('#r%d:checked~.tabs label[for="r%d"]{background:#12507b;color:#fff;border-color:#3f8ec9;box-shadow:0 2px 6px rgba(18,80,123,.35)}'%(i,i) for i in range(len(SCEN)))
css_panes=''.join('#r%d:checked~.panes #p%d{display:block}'%(i,i) for i in range(len(SCEN)))
html=('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>澜脉 · 数字孪生演示台（标签页版）</title><style>'
 'body{font-family:-apple-system,"Microsoft YaHei",sans-serif;margin:0;background:#f5f7fa;color:#1a2733}'
 '.wrap{max-width:1180px;margin:0 auto;padding:20px}h1{font-size:21px;margin:0 0 6px}'
 '.sub{color:#5b6b7c;font-size:13px;margin-bottom:16px}'
 'input[type=radio]{position:absolute;opacity:0;width:0;height:0}.hint{font-size:13px;color:#12507b;font-weight:600;margin:0 0 8px}.tabs{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:16px}.tabs label{display:inline-block;min-width:170px;text-align:center;background:#fff;border:2px solid #cfdae5;border-radius:10px;padding:11px 15px;font-size:13.5px;cursor:pointer;color:#2c3e50;user-select:none;box-shadow:0 1px 2px rgba(0,0,0,.05)}.tabs label:hover{border-color:#3f8ec9;background:#f2f8ff}.tabs label:active{transform:translateY(1px)}'
 '.tabs label{background:#fff;border:1px solid #d5dee7;border-radius:8px;padding:8px 13px;font-size:13px;cursor:pointer;color:#2c3e50}'
 '.tabs label:hover{border-color:#3f8ec9}'
 '.panes .pane{display:none;background:#fff;border-radius:10px;padding:16px 18px;box-shadow:0 1px 3px rgba(0,0,0,.07)}'
 'h2{font-size:15px;color:#12507b;margin:0 0 8px}img{width:100%;border-radius:8px}'
 'table{border-collapse:collapse;width:100%;font-size:13px;margin-top:8px}td,th{border-bottom:1px solid #e6ecf2;padding:5px 8px}'
 'td:nth-child(odd){color:#5b6b7c;width:14%}.n{color:#6b7b8c;font-size:12.5px;line-height:1.7}'
 '.qa{background:#fff;border-radius:10px;padding:16px 18px;margin-top:16px;box-shadow:0 1px 3px rgba(0,0,0,.07)}'
 '.qa table{font-size:12.5px}.qa th{text-align:left;color:#12507b}'
 '.warn{background:#fff8e6;border-left:4px solid #d99b1f;padding:9px 12px;border-radius:6px;font-size:12.5px;margin-top:10px}'
 +css_tabs+css_panes+'</style></head><body><div class="wrap">'
 '<h1>澜脉 · 数字孪生演示台（IWA BSM1 仿真，120 天）</h1>'
 '<div class="sub">点下面的标签切换 6 个场景。图上半：反应池溶解氧 DO₃（蓝）+ 曝气能力 KLa（绿）；下半：模型健康分数 + 判据阈值（红虚线）。黄竖线=模型报警，红竖线=真实失效。'
 '本页为纯 HTML+图片，不需要脚本；动画版见 demo/lanmai_twin_anim.html。</div>'
 +'<div class="hint">👇 点下面任意一个按钮切换场景（当前选中的按钮是深蓝色）</div>'+tabs+'<div class="panes">'+''.join(panes)+'</div>'
 '<div class="qa"><h2>评委常问的三问</h2><table>'
 '<tr><th>问题</th><th>怎么答</th><th>别说什么</th></tr>'
 '<tr><td>凭什么说能预判维修/报废？</td><td>不预测“哪天坏”，而是预测“离越过危险线还剩多少天”。危险线可测量（反应池溶解氧（DO）持续越限），所以剩余寿命可验证：本例机理-溶解氧外推误差 <b>4.04 天</b>，通用健康指数误差 20.55 天。</td><td>准确率 95%、一定提前 X 天</td></tr>'
 '<tr><td>是真污水厂数据吗？</td><td>检测方法用真实公开工业数据验证（SKAB 水泵台架、MetroPT-3 空压机 5.8 个月、CWRU 轴承、C-MAPSS 涡扇）；退化与工况泛化用 IWA 标准模型仿真。我们需要厂区数据做迁移验证。</td><td>已在某厂上线、有客户</td></tr>'
 '<tr><td>报警准不准？</td><td>给区间与口径：同召回下误报比对照少 2.8 倍；数字孪生 6 个工况健康运行误报 0–26 次不等，所以输出分级上报（P1 立即派工 / P2 复核排计划 / P3 趋势观察）。</td><td>零误报、不用人管</td></tr>'
 '</table><div class="warn"><b>一句话：</b>我们把“设备退化的可测量后果 + 机理量 + 剩余寿命 + 维护窗口”串成一条可复现的软件链，并且把自己试过但被实验否证的方案也写进材料。</div></div>'
 '</div></body></html>')
io.open('demo/lanmai_twin.html','w',encoding='utf-8').write(html)
print('已生成 demo/lanmai_twin.html（标签页版，无脚本）%.0f KB' % (os.path.getsize('demo/lanmai_twin.html')/1024))
