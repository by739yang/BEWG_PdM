# -*- coding: utf-8 -*-
"""生成静态版数字孪生演示页（纯图片，无 JS）与总览图
产物：demo/lanmai_twin_static.html、results/2026-09-20/dsh/twin_<场景>.png、twin_overview.png
用法：python src/dsh/2026-09-20_16_twin_static.py"""
import sys, os, io, base64, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dual_baseline import frozen_z, topk_score, _scale_floor
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif']=['Microsoft YaHei']; plt.rcParams['axes.unicode_minus']=False
OUT='results/2026-09-20/dsh'; OUT2='results/2026-09-21/dsh'; os.makedirs('demo',exist_ok=True)
def fpath(f):
    for d in (OUT,OUT2):
        if os.path.exists(os.path.join(d,f)): return os.path.join(d,f)
    raise FileNotFoundError(f)
CH=['SO3','SO4','SO5','SNH_eff','Ntot_eff','TSS_eff','sludge_h']
BL,RD,GO,GR,GY='#1f4e79','#c00000','#d99b1f','#2fa36b','#7f7f7f'
SCEN=[
 ('healthy','健康运行（无退化）','设备正常：SO3 平稳，模型健康分数一直在阈值下方。冻结通道 120 天报警 0 次。','bsm1_120d_baseline.csv',None,None,None),
 ('deg20','慢退化 -20% / 100 天','曝气能力 100 天缓慢衰减 20%：反应池溶解氧（DO）几乎不变，模型分数开始抬升；第 110 天才越线，提前量 70 天。','bsm1_120d_baseline.csv','bsm1_sweep_keep80_ramp100.csv',40.28,110.34),
 ('deg40','慢退化 -40% / 100 天（最完整一例）','第 20 天开始退化 → 第 40 天报警 → 第 47 天反应池溶解氧（DO）真实失效。机理-溶解氧外推剩余寿命 3.24 天，真值 7.27 天，误差 4.04 天。','bsm1_120d_baseline.csv','bsm1_120d_degraded.csv',40.28,47.34),
 ('deg80','慢退化 -80% / 100 天','衰减幅度加大到 80%，但报警时刻仍在第 40 天附近 —— 说明单点越限的“时刻”不含严重度信息（严重度要看分布位置或机理量）。','bsm1_120d_baseline.csv','bsm1_sweep_keep20_ramp100.csv',40.28,44.33),
 ('fast80','快退化 -80% / 40 天','同样衰减 80%，压缩到 40 天完成：报警第 20.3 天、失效第 29.4 天，提前量只有 2.06 天。','bsm1_120d_baseline.csv','bsm1_sweep_keep20_ramp040.csv',20.32,29.39),
 ('std40','标准进水（BSM1 干天）退化 -40%','换成 BSM1 自带的干天进水（设计负荷，非包默认的 BSM2 动态进水）：溶解氧 1.94→0.16，出水氨氮均值 5.69→18.28 mg/L（最大 41.87），冻结通道第 57.45 天报警、第 93.33 天曝气功能失效。自适应通道在本工况漏检。','bsm1std_baseline.csv','bsm1std_degraded.csv',57.45,93.33),
 ('storm','雨/暴雨工况 -40% / 100 天','换成干天+雨天循环、每 28 天插 2 天暴雨的进水工况：健康运行时单一阈值就报了 26 次 —— 阈值必须按工况自身基线标定。','bsm1_R3_add_storm_baseline.csv','bsm1_R3_add_storm_degraded.csv',20.04,95.32)]
def prep(df):
    x=df.copy(); x.index=pd.to_datetime(x.t_day*86400,unit='s'); return x
hod=lambda X: ((X.t_day*24)%24).astype(int).values
rows=[]
for sid,title,note,fb,fd,alarm,fail in SCEN:
    B=prep(pd.read_csv(fpath(fb)))
    X=D=prep(pd.read_csv(fpath(fd))) if fd else B
    REF=B[(B.t_day>=30)&(B.t_day<45)]; FL=_scale_floor(B,CH)
    def sc(Y): return np.asarray(topk_score(frozen_z(Y,CH,REF,state=hod(Y),state_ref=hod(REF),floor=FL),3),dtype=float).ravel()
    s=sc(X); thr=float(np.quantile(np.asarray(topk_score(frozen_z(REF,CH,REF,state=hod(REF),state_ref=hod(REF),floor=FL),3),dtype=float).ravel(),0.999))
    kbase=float(B[B.t_day<20].kla_sum.mean()); kla=np.asarray(X.kla_sum)/kbase
    fig,ax=plt.subplots(2,1,figsize=(11,5.6),sharex=True,gridspec_kw={'height_ratios':[3,2]})
    ax[0].plot(X.t_day,X.SO3,color=BL,lw=1.1,label='反应池溶解氧 DO₃（mg/L）')
    ax[0].axhline(0.5,color=RD,ls='--',lw=1.1)
    ax[0].text(1,0.56,'曝气功能失效线 DO=0.5（持续 1 天）',color=RD,fontsize=8)
    ax[0].set_ylabel('SO3（mg/L）'); ax[0].set_ylim(0,3.2)
    a2=ax[0].twinx(); a2.plot(X.t_day,kla,color=GR,lw=1.1,label='曝气能力 KLa（相对健康值）'); a2.set_ylim(0,1.35); a2.set_ylabel('KLa 相对值')
    if alarm: ax[0].axvline(alarm,color=GO,ls=':',lw=1.6); ax[0].text(alarm+0.7,2.9,'报警 %.2f 天'%alarm,color=GO,fontsize=8)
    if fail: ax[0].axvline(fail,color=RD,ls=':',lw=1.6); ax[0].text(fail+0.7,2.6,'真实失效 %.2f 天'%fail,color=RD,fontsize=8)
    ax[0].set_title('%s ｜ 报警 %s ｜ 失效 %s ｜ 提前量 %s 天' % (title,
        ('%.2f 天'%alarm) if alarm else '无（健康运行不报警）', ('%.2f 天'%fail) if fail else '无',
        ('%.2f'%(fail-alarm)) if (alarm and fail) else '-'), fontsize=11)
    ax[0].legend(loc='upper left',fontsize=8); ax[0].grid(alpha=.3)
    ax[1].plot(X.t_day,s,color='#b8860b',lw=0.7,label='模型健康分数（15 分钟分辨率）')
    ax[1].axhline(thr,color=RD,ls='--',lw=1.1); ax[1].text(1,thr+0.6,'判据阈值 %.1f'%thr,color=RD,fontsize=8)
    ax[1].set_ylabel('健康分数'); ax[1].set_xlabel('时间（天）'); ax[1].set_xlim(0,120); ax[1].legend(loc='upper left',fontsize=8); ax[1].grid(alpha=.3)
    png=os.path.join(OUT,'twin_%s.png'%sid); plt.tight_layout(); plt.savefig(png,dpi=110); plt.close()
    rows.append(dict(id=sid,title=title,note=note,alarm=alarm,fail=fail,
        lead=(None if (alarm is None or fail is None) else round(fail-alarm,2)), thr=round(thr,2), png=png))
    print('  已出图', png)
# 总览（2x3）
nrow=(len(SCEN)+2)//3
fig,ax=plt.subplots(nrow,3,figsize=(16,4*nrow)); ax=ax.ravel()
for k,(sid,title,note,fb,fd,alarm,fail) in enumerate(SCEN):
    a=ax[k]
    B=prep(pd.read_csv(fpath(fb))); X=prep(pd.read_csv(fpath(fd))) if fd else B
    a.plot(X.t_day,X.SO3,color=BL,lw=0.9)
    a.axhline(0.5,color=RD,ls='--',lw=0.9)
    a.set_title(title,fontsize=10); a.set_ylim(0,3.2); a.grid(alpha=.3); a.set_xlabel('天')
    if alarm: a.axvline(alarm,color=GO,ls=':',lw=1.4)
    if fail: a.axvline(fail,color=RD,ls=':',lw=1.4)
    a.text(2,2.9,'报警 %s ｜ 失效 %s ｜ 提前量 %s 天' % (('%.1f'%alarm) if alarm else '无',('%.1f'%fail) if fail else '无',('%.1f'%(fail-alarm)) if (alarm and fail) else '-'),fontsize=8)
plt.tight_layout(); ov=os.path.join(OUT,'twin_overview.png'); plt.savefig(ov,dpi=110); plt.close()
print('  已出总览图', ov)
def b64(p): return base64.b64encode(open(p,'rb').read()).decode()
cards=[]
for r in rows:
    kpi=('<tr><td>报警时刻</td><td>%s</td><td>真实失效</td><td>%s</td><td>提前量</td><td>%s 天</td></tr>' % (
        ('%.2f 天'%r['alarm']) if r['alarm'] else '无（健康运行）', ('%.2f 天'%r['fail']) if r['fail'] else '无',
        ('%.2f'%r['lead']) if r['lead'] is not None else '-'))
    cards.append('<div class="card"><h2>%s</h2><img src="data:image/png;base64,%s"><table>%s<tr><td colspan="6" class="n">%s</td></tr></table></div>'%(r['title'],b64(r['png']),kpi,r['note']))
html=('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>澜脉 · 数字孪生效果（静态版）</title><style>'
 'body{font-family:-apple-system,"Microsoft YaHei",sans-serif;margin:0;background:#f5f7fa;color:#1a2733}'
 '.wrap{max-width:1180px;margin:0 auto;padding:20px}.card{background:#fff;border-radius:10px;padding:16px 18px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,.07)}'
 'h1{font-size:21px;margin:0 0 6px}h2{font-size:15px;color:#12507b;margin:0 0 8px}img{width:100%;border-radius:8px}'
 'table{border-collapse:collapse;width:100%;font-size:13px}td,th{border-bottom:1px solid #e6ecf2;padding:5px 8px}'
 'td:first-child,td:nth-child(3),td:nth-child(5){color:#5b6b7c;width:12%}.n{color:#6b7b8c;font-size:12.5px;line-height:1.7}'
 '.sub{color:#5b6b7c;font-size:13px;margin-bottom:16px}</style></head><body><div class="wrap">'
 '<h1>澜脉 · 数字孪生效果（静态版，纯图片，无需脚本）</h1>'
 '<div class="sub">IWA BSM1 仿真，120 天，设备=曝气系统。上曲线：反应池溶解氧 DO₃ 与曝气能力 KLa；下曲线：模型健康分数与判据阈值。黄色竖线=模型报警，红色竖线=真实失效。'
 '总览图：results/2026-09-20/dsh/twin_overview.png。交互版：demo/lanmai_twin.html（需浏览器支持脚本）。</div>'
 +''.join(cards)+'</div></body></html>')
io.open('demo/lanmai_twin_static.html','w',encoding='utf-8').write(html)
print('已生成 demo/lanmai_twin_static.html %.0f KB' % (os.path.getsize('demo/lanmai_twin_static.html')/1024))
