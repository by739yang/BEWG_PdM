# -*- coding: utf-8 -*-
"""生成澜脉 · 数字孪生演示台（自包含交互 HTML）
数据来源：results/2026-09-20/dsh/bsm1_*.csv（IWA BSM1 仿真轨迹，全部已入库）
展示：SO3（出水氨氮指标）/ KLa（曝气能力退化）/ 模型健康分数 三条曲线 + 告警与失效时刻 + 时间游标
用法：python src/dsh/2026-09-20_15_demo_twin.py"""
import sys, os, io, json, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dual_baseline import frozen_z, topk_score, _scale_floor
OUT='results/2026-09-20/dsh'; OUT2='results/2026-09-21/dsh'
CH=['SO3','SO4','SO5','SNH_eff','Ntot_eff','TSS_eff','sludge_h']
os.makedirs('demo', exist_ok=True)

# 场景：(id, 标题, 一句话说明, 健康文件, 退化文件, 告警天, 失效天, 机理RUL估计, RUL真值, 诚实边界)
SCEN=[
 ('healthy','健康运行','设备正常：反应池溶解氧 DO₃ 平稳，模型健康分数一直在阈值之下。','bsm1_120d_baseline.csv',None,None,None,None,None,
  '这是"误报检验"场景：冻结通道在 120 天里报 0 次。'),
 ('deg20','慢退化 -20%','曝气能力在 100 天里缓慢衰减 20%：反应池溶解氧（DO）几乎不变，但模型分数开始抬升。','bsm1_120d_baseline.csv','bsm1_sweep_keep80_ramp100.csv',40.28,110.34,None,None,
  '退化很慢时，报警确实来了，但反应池溶解氧（DO）到第 110 天才越线 —— 提前量 70 天，代价是这 70 天里指标看不出问题。'),
 ('deg40','慢退化 -40%','曝气能力 100 天衰减 40%：第 40 天报警，第 47 天反应池溶解氧（DO）失效。','bsm1_120d_baseline.csv','bsm1_120d_degraded.csv',40.28,47.34,3.24,7.27,
  '这是最完整的一例：报警 → 剩余寿命 → 维护窗口。机理-溶解氧外推 3.24 天，真值 7.27 天，误差 4.04 天。'),
 ('deg80','慢退化 -80%','衰减幅度加大到 80%：分数抬得更快，但报警时刻仍在第 40 天附近 —— 报警"时刻"不含严重度信息。','bsm1_120d_baseline.csv','bsm1_sweep_keep20_ramp100.csv',40.28,44.33,None,None,
  '这一例专门说明第 18.2 节的核心发现：单点越限的"时刻"与退化幅值无关，严重度要靠分布位置或机理量表达。'),
 ('fast80','快退化 -80%/40 天','同样衰减 80%，但压缩到 40 天完成：第 20 天报警、第 29 天失效，提前量只有 2 天。','bsm1_120d_baseline.csv','bsm1_sweep_keep20_ramp040.csv',20.32,29.39,None,None,
  '退化越快，提前量越小（2.06 天）。这说明"能不能预判"高度依赖退化速率。'),
 ('std40','标准进水（BSM1 干天）退化 -40%','换成 BSM1 自带的干天进水（设计负荷）：溶解氧 1.94→0.16，出水氨氮均值 5.69→18.28 mg/L，第 57.45 天报警、第 93.33 天曝气功能失效。','bsm1std_baseline.csv','bsm1std_degraded.csv',57.45,93.33,None,None,'本工况自适应通道漏检；出水氨氮相对自身基线翻 3.2 倍。'),
 ('storm','雨/暴雨工况 -40%','换成干天+雨天循环、每 28 天插 2 天暴雨的进水工况：健康运行时单一阈值就报了 26 次。','bsm1_R3_add_storm_baseline.csv','bsm1_R3_add_storm_degraded.csv',20.04,95.32,None,None,
  '这一例说明"0 误报"不跨工况：同一条阈值在雨/暴雨工况的健康运行上就报 26 次 —— 所以阈值必须按工况自身基线标定。'),
]

def prep(df):
    x=df.copy(); x.index=pd.to_datetime(x.t_day*86400,unit='s'); return x
hod=lambda X: ((X.t_day*24)%24).astype(int).values

def build(sid, fb, fd):
    def fp_(f):
        for d in (OUT,OUT2):
            if os.path.exists(os.path.join(d,f)): return os.path.join(d,f)
        raise FileNotFoundError(f)
    B=prep(pd.read_csv(fp_(fb)))
    D=prep(pd.read_csv(fp_(fd))) if fd else None
    REF=B[(B.t_day>=30)&(B.t_day<45)]; FL=_scale_floor(B,CH)
    def sc(X):
        return np.asarray(topk_score(frozen_z(X,CH,REF,state=hod(X),state_ref=hod(REF),floor=FL),3),dtype=float).ravel()
    X = D if D is not None else B
    s = sc(X)
    kbase=float(B[B.t_day<20].kla_sum.mean())
    step=8   # 2 小时一个点（96 点/天 / 8 = 12 点/天）
    d=np.asarray(X.t_day)[::step]; so3=np.asarray(X.SO3)[::step]
    kla=(np.asarray(X.kla_sum)[::step]/kbase)
    sco=s[::step]
    ref_thr=float(np.quantile(np.asarray(topk_score(frozen_z(REF,CH,REF,state=hod(REF),state_ref=hod(REF),floor=FL),3),dtype=float).ravel(),0.999))
    return dict(days=np.round(d,3).tolist(), so3=np.round(so3,3).tolist(), kla=np.round(kla,3).tolist(),
                score=np.round(sco,2).tolist(), thr=round(ref_thr,2),
                daysF=np.round(np.asarray(X.t_day),3).tolist(), scoreF=np.round(s,1).tolist())   # 分数用 15 分钟全分辨率，才看得见"连续 4 点越阈"的脉冲

DATA=[]
for sid,title,desc,fb,fd,alarm,fail,rul_est,rul_true,note in SCEN:
    d=build(sid,fb,fd)
    DATA.append(dict(id=sid, title=title, desc=desc, note=note, alarm=alarm, fail=fail,
                     rul_est=rul_est, rul_true=rul_true,
                     lead=(None if (alarm is None or fail is None) else round(fail-alarm,2)), **d))
    print('  %-9s 点数 %d ｜ 分数阈值 %.2f' % (sid, len(d['days']), d['thr']))

payload=json.dumps(DATA, ensure_ascii=False, separators=(',',':'))

PAGE = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>澜脉 · 数字孪生演示台</title>
<style>
body{font-family:-apple-system,"Microsoft YaHei",sans-serif;margin:0;background:#0f1720;color:#e8eef5}
.wrap{max-width:1240px;margin:0 auto;padding:18px 20px 40px}
h1{font-size:21px;margin:0 0 4px}.sub{color:#93a4b6;font-size:13px;margin-bottom:14px}
.row{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}
button.b{background:#1b2836;color:#cfe0f0;border:1px solid #2c3e50;border-radius:8px;padding:8px 12px;font-size:13px;cursor:pointer}
button.b:hover{background:#243447}button.b.on{background:#12507b;border-color:#3f8ec9;color:#fff}
.panel{background:#141e2a;border:1px solid #22303f;border-radius:10px;padding:14px 16px;margin-bottom:12px}
.plot{width:100%;height:300px;display:block}
.plot2{width:100%;height:150px;display:block}
.kpis{display:flex;gap:10px;flex-wrap:wrap}
.kpi{flex:1;min-width:130px;background:#101a24;border-radius:8px;padding:10px 12px}
.kpi .v{font-size:19px;font-weight:600;color:#7fc4ff}.kpi .l{font-size:11px;color:#8ea3b8;margin-top:3px}
.ctl{display:flex;align-items:center;gap:12px}
input[type=range]{flex:1}
.note{font-size:12.5px;color:#a9bccf;line-height:1.75}
.warn{background:#2a2313;border-left:3px solid #d99b1f;padding:9px 12px;border-radius:6px;font-size:12.5px;color:#f0dcb4;margin-top:10px}
.good{background:#12251d;border-left:3px solid #2fa36b}
h2{font-size:15px;color:#9ecbff;margin:0 0 8px;border-left:3px solid #3f8ec9;padding-left:8px}
table{border-collapse:collapse;width:100%%;font-size:12.5px}
th,td{border-bottom:1px solid #22303f;padding:5px 8px;text-align:left}th{color:#9ecbff}
.t{font-size:12.5px;color:#93a4b6}
</style></head><body><div class="wrap">
<h1>澜脉 · 数字孪生演示台（IWA BSM1 仿真，120 天）</h1>
<div class="sub">设备 = 曝气系统（KLa）。曲线是真实仿真轨迹，箭头是模型报警与真实失效时刻。数据全部来自 results/2026-09-20/dsh/bsm1_*.csv。</div>

<div class="row" id="btns"></div>

<div class="panel">
  <div class="ctl">
    <button class="b" id="play">▶ 播放</button>
    <input type="range" id="sl" min="0" max="120" step="0.25" value="120">
    <div class="t" id="tlab" style="min-width:90px;text-align:right">第 120.0 天</div>
  </div>
  <div class="kpis" style="margin-top:12px">
    <div class="kpi"><div class="v" id="k_so3">-</div><div class="l">反应池溶解氧 DO₃（mg/L）</div></div>
    <div class="kpi"><div class="v" id="k_kla">-</div><div class="l">曝气能力 KLa（相对健康值）</div></div>
    <div class="kpi"><div class="v" id="k_score">-</div><div class="l">模型健康分数（阈值 <span id="k_thr">-</span>）</div></div>
    <div class="kpi"><div class="v" id="k_alarm">-</div><div class="l">模型报警时刻</div></div>
    <div class="kpi"><div class="v" id="k_fail">-</div><div class="l">真实失效时刻（SO3&lt;0.5 持续 1 天）</div></div>
    <div class="kpi"><div class="v" id="k_lead">-</div><div class="l">预警提前量（天）</div></div>
    <div class="kpi"><div class="v" id="k_rul">-</div><div class="l">剩余寿命：估计 / 真值（天）</div></div>
  </div>
</div>

<div class="panel">
  <h2 id="sc_title">场景</h2>
  <div class="note" id="sc_desc"></div>
  <canvas id="cv1" class="plot"></canvas>
  <canvas id="cv2" class="plot2"></canvas>
  <div class="note" style="margin-top:6px">
    <b>上：</b>反应池溶解氧 DO₃（蓝，越低于 0.5 越接近失效）与曝气能力 KLa（绿，退化时下降）；
    <b>下（15 分钟全分辨率）：</b>模型看到的健康分数（黄）与判据阈值（红虚线）。注意看：<b>健康运行也有零星尖峰越过阈值，但因为不满足"连续 4 个采样点（1 小时）越阈"，所以不报警</b>——这就是我们文档里说的"刀锋边缘"；退化运行时越阈脉冲变长，事件机才触发报警。
  </div>
  <div class="warn" id="sc_note"></div>
</div>

<div class="panel">
  <h2>评委常问的三问（我们怎么回答，含不说什么）</h2>
  <table>
  <tr><th>问题</th><th>我们的回答</th><th>不能说</th></tr>
  <tr><td>你们凭什么说能<b>预判设备维修/报废</b>？</td>
      <td>我们不预测"某天会坏"，而是预测"离越过危险线还有多少天"：先把失效定义为可测量的阈值（反应池溶解氧（DO）持续越限 / 机理量越过危险线），再给剩余寿命。在数字孪生里，机理-溶解氧外推误差 <b>4.04 天</b>（真值剩余 7.27 天），通用健康指数误差 20.55 天 —— 这就是"必须挂机理指标"的证据。</td>
      <td>不说"准确率 100%""已上线""省多少钱"。</td></tr>
  <tr><td>这些是<b>真实污水厂</b>的数据吗？</td>
      <td>检测方法在<b>真实公开工业数据</b>上验证（SKAB 真实水泵台架、MetroPT-3 地铁空压机 5.8 个月、CWRU 轴承、C-MAPSS 涡扇退化）；退化过程与工况泛化在 <b>IWA BSM1 标准模型仿真</b>里验证。我们要的现场数据是"接入后跑一遍基线标定"，这也是我们最需要厂区配合的一件事。</td>
      <td>不把仿真说成现场结果。</td></tr>
  <tr><td>报警<b>准不准</b>？</td>
      <td>给区间，不给口号：在 MetroPT-3 上同召回下我方误报事件比对照路线少 2.8 倍；但官方只有 4 个故障窗、召回步长 25%，且阈值是标签辅助选点后的同集表现（无标签工作点为 0/4）。在数字孪生 6 个工况里，健康运行误报 0-26 次不等 —— 所以我们结论是"阈值必须按工况自身基线标定"。</td>
      <td>不说"零误报"。</td></tr>
  </table>
  <div class="warn good"><b>一句话总结：</b>我们做的不是"又一个报警器"，而是把<b>设备退化的可测量后果</b>（反应池溶解氧（DO））+ <b>机理量</b>（溶解氧/曝气能力）+ <b>剩余寿命 + 维护窗口</b>串成一条可复现的软件链，并且把自己试过但<b>被实验否证</b>的方案也写进材料（比如"滚动中位数越限判据"）。</div>
</div>
</div>
<script>
var DATA = __PAYLOAD__;
var cur = null, timer = null;
var cv1 = document.getElementById('cv1'), cv2 = document.getElementById('cv2');
function fit(c){var w=c.clientWidth, h=c.clientHeight, r=window.devicePixelRatio||1; c.width=w*r; c.height=h*r; var g=c.getContext('2d'); g.setTransform(r,0,0,r,0,0); return {g:g,w:w,h:h};}
function draw(){
  if(!cur) return;
  var t = parseFloat(document.getElementById('sl').value);
  var i = Math.min(cur.days.length-1, Math.round(t/(120/(cur.days.length-1))));
  var o1 = fit(cv1), g = o1.g, W = o1.w, H = o1.h, pad = 34, pw = W-pad-12, ph = H-26;
  g.clearRect(0,0,W,H);
  g.strokeStyle = '#22303f'; g.fillStyle = '#93a4b6'; g.font = '11px sans-serif';
  g.beginPath(); g.moveTo(pad,12); g.lineTo(pad,H-14); g.lineTo(W-12,H-14); g.stroke();
  for(var dd=0; dd<=120; dd+=20){ var x = pad+pw*dd/120; g.fillText(dd+'d', x-8, H-2); g.strokeStyle='#1a2532'; g.beginPath(); g.moveTo(x,12); g.lineTo(x,H-14); g.stroke(); }
  var smax = 6.0;   // SO3 轴
  function X(day){ return pad+pw*day/120; }
  function Y(v){ return 12+ph*(1-Math.min(v,smax)/smax); }
  [0,1,2,3,4,5,6].forEach(function(v){ g.fillStyle='#5c728a'; g.fillText(v.toFixed(1), 4, Y(v)+4); });
  g.beginPath(); g.moveTo(pad, Y(0.5)); g.lineTo(W-12, Y(0.5)); g.strokeStyle='#c00000'; g.setLineDash([5,4]); g.stroke();
  g.fillStyle='#c00000'; g.fillText('曝气功能失效线 DO=0.5（持续 1 天）', W-120, Y(0.5)-4);
  g.setLineDash([]);
  g.beginPath(); for(var k=0;k<cur.so3.length;k++){ var xx=X(cur.days[k]), yy=Y(cur.so3[k]); k? g.lineTo(xx,yy): g.moveTo(xx,yy); }
  g.strokeStyle='#4ea3ff'; g.lineWidth=1.4; g.stroke();
  var kmin = 0.0, kmax = 1.25;
  function YK(v){ return 12+ph*(1-Math.max(0,Math.min(v,kmax))/kmax); }
  g.beginPath(); for(var k2=0;k2<cur.kla.length;k2++){ var xx2=X(cur.days[k2]), yy2=YK(cur.kla[k2]); k2? g.lineTo(xx2,yy2): g.moveTo(xx2,yy2); }
  g.strokeStyle='#2fa36b'; g.lineWidth=1.2; g.globalAlpha=.85; g.stroke(); g.globalAlpha=1;
  g.fillStyle='#2fa36b'; g.fillText('曝气能力 KLa（右轴 0~1.25）', pad+8, 24);
  function mark(day,color,label){
    if(day===null||day===undefined) return;
    g.strokeStyle=color; g.lineWidth=1.6; g.beginPath(); g.moveTo(X(day),12); g.lineTo(X(day),H-14); g.stroke();
    g.fillStyle=color; g.fillText(label, X(day)+3, 40);
  }
  mark(cur.alarm, '#d99b1f', '报警 '+(cur.alarm===null?'-':cur.alarm.toFixed(1)+'d'));
  mark(cur.fail, '#ff6b6b', '失效 '+(cur.fail===null?'-':cur.fail.toFixed(1)+'d'));
  g.strokeStyle='#ffffff'; g.lineWidth=1; g.beginPath(); g.moveTo(X(t),12); g.lineTo(X(t),H-14); g.stroke();
  // 第二条：健康分数
  var o2 = fit(cv2), g2 = o2.g, W2=o2.w, H2=o2.h, p2=34, pw2=W2-p2-12, ph2=H2-22;
  g2.clearRect(0,0,W2,H2);
  g2.strokeStyle='#22303f'; g2.beginPath(); g2.moveTo(p2,10); g2.lineTo(p2,H2-12); g2.lineTo(W2-12,H2-12); g2.stroke();
  var vmax = 24;
  function X2(day){ return p2+pw2*day/120; }
  function Y2(v){ return 10+ph2*(1-Math.min(v,vmax)/vmax); }
  g2.fillStyle='#5c728a'; g2.font='11px sans-serif'; [0,6,12,18,24].forEach(function(v){ g2.fillText(v, 6, Y2(v)+4); });
  g2.beginPath(); g2.moveTo(p2, Y2(cur.thr)); g2.lineTo(W2-12, Y2(cur.thr)); g2.strokeStyle='#c00000'; g2.setLineDash([5,4]); g2.stroke(); g2.setLineDash([]);
  g2.fillStyle='#c00000'; g2.fillText('判据阈值 '+cur.thr.toFixed(1), W2-130, Y2(cur.thr)-4);
  var sf = cur.scoreF, df = cur.daysF;
  g2.beginPath(); for(var m=0;m<sf.length;m++){ var x3=X2(df[m]), y3=Y2(sf[m]); m? g2.lineTo(x3,y3): g2.moveTo(x3,y3); }
  g2.strokeStyle='#e8c14a'; g2.lineWidth=1.1; g2.stroke();
  g2.strokeStyle='#ffffff'; g2.beginPath(); g2.moveTo(X2(t),10); g2.lineTo(X2(t),H2-12); g2.stroke();
  // KPI
  document.getElementById('tlab').textContent = '第 '+t.toFixed(1)+' 天';
  document.getElementById('k_so3').textContent = cur.so3[i].toFixed(3);
  document.getElementById('k_kla').textContent = cur.kla[i].toFixed(3);
  document.getElementById('k_score').textContent = cur.score[i].toFixed(2);
  document.getElementById('k_thr').textContent = cur.thr.toFixed(2);
  document.getElementById('k_alarm').textContent = (cur.alarm===null?'未报警（健康）':cur.alarm.toFixed(2)+' 天');
  document.getElementById('k_fail').textContent = (cur.fail===null?'未失效':cur.fail.toFixed(2)+' 天');
  document.getElementById('k_lead').textContent = (cur.lead===null?'-':cur.lead.toFixed(2));
  document.getElementById('k_rul').textContent = (cur.rul_est===null?'-（本例未做机理 RUL）':(cur.rul_est+' / '+cur.rul_true));
}
function select(id){
  cur = DATA.filter(function(x){return x.id===id;})[0];
  document.getElementById('sc_title').textContent = cur.title;
  document.getElementById('sc_desc').textContent = cur.desc;
  document.getElementById('sc_note').textContent = '诚实边界：' + cur.note;
  var bs = document.querySelectorAll('button.b'), ids = DATA.map(function(d){return d.id;});
  for(var i=0;i<bs.length;i++){ bs[i].className = (bs[i].dataset.id===id)? 'b on':'b'; }
  draw();
}
(function init(){
  var box = document.getElementById('btns');
  DATA.forEach(function(d,i){
    var b = document.createElement('button');
    b.className='b'; b.textContent=d.title; b.dataset.id=d.id;
    b.onclick=function(){ select(d.id); };
    box.appendChild(b);
  });
  document.getElementById('sl').oninput = draw;
  var pl = document.getElementById('play');
  pl.onclick = function(){
    if(timer){ clearInterval(timer); timer=null; pl.textContent='▶ 播放'; return; }
    pl.textContent='⏸ 暂停';
    var sl = document.getElementById('sl');
    timer = setInterval(function(){
      var v = parseFloat(sl.value) + 1.0;
      if(v>120){ v=0; }
      sl.value = v; draw();
    }, 60);
  };
  window.addEventListener('resize', draw);
  select('deg40');
})();
</script></body></html>"""

io.open('demo/lanmai_twin_anim.html','w',encoding='utf-8').write(PAGE.replace('__PAYLOAD__', payload))
print('已生成 demo/lanmai_twin_anim.html（动画版）%.0f KB' % (os.path.getsize('demo/lanmai_twin_anim.html')/1024))
