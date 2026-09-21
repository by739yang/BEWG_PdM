# -*- coding: utf-8 -*-
"""组合报警策略的倍数敏感性扫描（DSH，2026-09-21）
第 18.6 节的局限：P1 与门的抬升倍数（1.15）、比值判据倍数（1.3）、分布位置窗（5 天）都没扫过。
本脚本在同样的 12 个工况对上扫：k_and ∈ {1.05,1.10,1.15,1.25,1.40}、k_ratio ∈ {1.15,1.25,1.40}、窗 ∈ {1,3,5} 天。
单点事件机不随倍数变化（阈值固定），因此它构成基线行。
产物：results/2026-09-21/dsh/strategy_sensitivity.{csv,md,png}
用法：python src/dsh/2026-09-21_06_strategy_sensitivity.py"""
import sys, os, io, json, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dual_baseline import frozen_z, topk_score, make_events, _scale_floor
D20='results/2026-09-20/dsh'; D21='results/2026-09-21/dsh'
CH=['SO3','SO4','SO5','SNH_eff','Ntot_eff','TSS_eff','sludge_h']
PAIRS=[
 ('A 窗[0,120)','bsm1_120d_baseline.csv','bsm1_120d_degraded.csv'),
 ('B 窗[120,240)','bsm1_winB_120_240_baseline.csv','bsm1_winB_120_240_degraded.csv'),
 ('C 窗[240,360)','bsm1_winC_240_360_baseline.csv','bsm1_winC_240_360_degraded.csv'),
 ('慢 -20%/100d','bsm1_120d_baseline.csv','bsm1_sweep_keep80_ramp100.csv'),
 ('慢 -40%/100d','bsm1_120d_baseline.csv','bsm1_sweep_keep60_ramp100.csv'),
 ('慢 -60%/100d','bsm1_120d_baseline.csv','bsm1_120d_degraded.csv'),
 ('慢 -80%/100d','bsm1_120d_baseline.csv','bsm1_sweep_keep20_ramp100.csv'),
 ('快 -60%/40d','bsm1_120d_baseline.csv','bsm1_sweep_keep40_ramp040.csv'),
 ('快 -80%/40d','bsm1_120d_baseline.csv','bsm1_sweep_keep20_ramp040.csv'),
 ('雨暴雨 -40%','bsm1_R3_add_storm_baseline.csv','bsm1_R3_add_storm_degraded.csv'),
 ('标准进水 -40%','bsm1std_baseline.csv','bsm1std_degraded.csv'),
 ('R1 干天循环','bsm1_R1_dry_baseline.csv','bsm1_R1_dry_degraded.csv')]
def fpath(f):
    for d in (D20,D21):
        if os.path.exists(os.path.join(d,f)): return os.path.join(d,f)
    raise FileNotFoundError(f)
def prep(df):
    x=df.copy(); x.index=pd.to_datetime(x.t_day*86400,unit='s'); return x
hod=lambda X: ((X.t_day*24)%24).astype(int).values
def rollmed(sv, X, days):
    return pd.Series(sv, index=X.index).rolling('%dD'%days, min_periods=96).median().values
def episodes(mask, days_arr, lo, hi):
    m=np.asarray(mask)&(days_arr>=lo)&(days_arr<=hi); out=[]; c=0
    for i,v in enumerate(m):
        if v: c+=1
        elif c: out.append(days_arr[i-c]); c=0
    if c: out.append(days_arr[len(m)-c])
    return out
CACHE=[]
for tag,fb,fd in PAIRS:
    B=prep(pd.read_csv(fpath(fb))); D=prep(pd.read_csv(fpath(fd)))
    REF=B[(B.t_day>=30)&(B.t_day<45)]; FL=_scale_floor(B,CH)
    def sc(X): return np.asarray(topk_score(frozen_z(X,CH,REF,state=hod(X),state_ref=hod(REF),floor=FL),3),dtype=float).ravel()
    sH=sc(B); sD=sc(D)
    thr=float(np.quantile(np.asarray(topk_score(frozen_z(REF,CH,REF,state=hod(REF),state_ref=hod(REF),floor=FL),3),dtype=float).ravel(),0.999))
    evH=make_events(pd.Series(sH), thr); evD=make_events(pd.Series(sD), thr)
    dB=np.asarray(B.t_day); dD=np.asarray(D.t_day)
    CACHE.append(dict(tag=tag, sH=sH, sD=sD, dB=dB, dD=dD, thr=thr, evH=evH, evD=evD))
    print('  已缓存', tag, '｜健康单点告警 %d，退化单点告警 %d' % (len(evH), len(evD)), flush=True)

KS_AND=[1.05,1.10,1.15,1.25,1.40]; KS_R=[1.15,1.25,1.40]; WINS=[1,3,5]
rows=[]
for W in WINS:
    for c in CACHE:
        c['rH']=rollmed(c['sH'], None, W) if False else pd.Series(c['sH'], index=pd.to_datetime(c['dB']*86400,unit='s')).rolling('%dD'%W, min_periods=96).median().values
        c['rD']=pd.Series(c['sD'], index=pd.to_datetime(c['dD']*86400,unit='s')).rolling('%dD'%W, min_periods=96).median().values
        c['base']=float(np.nanmedian(c['rH'][(c['dB']>=30)&(c['dB']<45)]))
    for kr in KS_R:
        for ka in KS_AND:
            sp_h=rat_h=p1_h=0; d_sp=[]; d_rat=[]; d_p1=[]; d_un=[]; d_sp_nostorm=[]; p1_h_nostorm=0
            for c in CACHE:
                dB,dD,rH,rD,base=c['dB'],c['dD'],c['rH'],c['rD'],c['base']
                storm=('雨暴雨' in c['tag'])
                spHh=[float(dB[i]) for i,_ in c['evH'] if float(dB[i])>=45.0]
                spHd=[float(dD[i]) for i,_ in c['evD'] if float(dD[i])>20.0]
                sp_h+=len(spHh)
                def near(r,d,day,half=1.0):
                    m=(d>=day-half)&(d<=day+half)&np.isfinite(r)
                    return bool(np.max(r[m])>ka*base) if m.any() else False
                p1h=[x for x in spHh if near(rH,dB,x)]; p1d=[x for x in spHd if near(rD,dD,x)]
                p1_h+=len(p1h)
                if not storm: p1_h_nostorm+=len(p1h)
                eh=episodes(rH>kr*base, dB, 45,120); ed=episodes(rD>kr*base, dD, 45,120)   # 比值判据评估窗自第 45 天起（参考窗到 45 天才结束）
                rat_h+=len(eh)
                # 逐工况：检出标志与首次延迟（口径同 18.6：12 个工况里有几个被检出）
                if spHd: d_sp.append(min(spHd)-20.0)
                if not storm and spHd: d_sp_nostorm.append(min(spHd)-20.0)
                if ed: d_rat.append(min(ed)-20.0)
                if p1d: d_p1.append(min(p1d)-20.0)
                u=[x for x in ([min(spHd)] if spHd else [])+([min(ed)] if ed else [])]
                if u: d_un.append(min(u)-20.0)
            med=lambda a: (None if not a else round(float(np.median(a)),1))
            rows.append(dict(窗天=W, k_and=ka, k_ratio=kr,
                             健康_单点=sp_h, 健康_比值段=rat_h, 健康_并集=sp_h+rat_h, 健康_P1与门=p1_h,
                             健康_P1与门_非暴雨=p1_h_nostorm,
                             检出数_单点=len(d_sp), 检出数_比值=len(d_rat), 检出数_并集=len(d_un), 检出数_P1与门=len(d_p1),
                             延迟中位_单点=med(d_sp), 延迟中位_并集=med(d_un), 延迟中位_P1=med(d_p1)))
T=pd.DataFrame(rows); T.to_csv(os.path.join(D21,'strategy_sensitivity.csv'),index=False,encoding='utf-8-sig')
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif']=['Microsoft YaHei']; plt.rcParams['axes.unicode_minus']=False
fig,ax=plt.subplots(1,3,figsize=(16,4.6))
g3=T[T.窗天==3]
for j,key in enumerate(['健康_P1与门','健康_单点','健康_并集']):
    piv=g3.pivot_table(index='k_and',columns='k_ratio',values=key)
    ax[j].imshow(piv.values,cmap='YlOrRd',aspect='auto')
    ax[j].set_xticks(range(piv.shape[1])); ax[j].set_xticklabels(piv.columns)
    ax[j].set_yticks(range(piv.shape[0])); ax[j].set_yticklabels(piv.index)
    for a in range(piv.shape[0]):
        for b in range(piv.shape[1]):
            ax[j].text(b,a,'%d'%piv.values[a,b],ha='center',va='center',fontsize=9)
    ax[j].set_xlabel('k_ratio（P3 阈值倍数）'); ax[j].set_ylabel('k_and（与门抬升倍数）')
    ax[j].set_title(['① 健康上报：P1 与门','② 健康上报：单点事件机','③ 健康上报：并集'][j]+'（窗 3 天）')
plt.tight_layout(); plt.savefig(os.path.join(D21,'strategy_sensitivity.png'),dpi=130)
NL=chr(10)+chr(10)
f=io.open(os.path.join(D21,'strategy_sensitivity_report.md'),'w',encoding='utf-8'); W=f.write
W('# 组合报警策略：倍数敏感性扫描（DSH，2026-09-21）'+NL)
W('第 18.6 节的局限是「1.15 / 1.3 / 5 天三个倍数没扫过」。本脚本扫 k_and ∈ {1.05,1.10,1.15,1.25,1.40}、k_ratio ∈ {1.15,1.25,1.40}、分布位置窗 ∈ {1,3,5} 天，共 45 组，12 个工况对。'+NL)
W('**单点事件机不随倍数变化**（阈值固定），是恒定基线：健康上报 %d 次、检出 %d/12、延迟中位 %s 天。' % (
    int(T.健康_单点.iloc[0]), int(T.检出数_单点.iloc[0]), str(T.延迟中位_单点.dropna().iloc[0]))+NL)
W('## 1. 汇总（窗 3 天）'+NL+g3[['k_and','k_ratio','健康_P1与门','健康_P1与门_非暴雨','健康_单点','健康_比值段','健康_并集','检出数_P1与门','检出数_并集','延迟中位_P1','延迟中位_并集']].to_markdown(index=False)+NL)
W('## 2. 分布位置窗的敏感性（固定 k_and=1.15、k_ratio=1.25）'+NL+
  T[(T.k_and==1.15)&(T.k_ratio==1.25)][['窗天','健康_P1与门_非暴雨','健康_单点','健康_比值段','健康_并集','检出数_并集','延迟中位_单点','延迟中位_并集']].to_markdown(index=False)+NL)
w3=T[(T.窗天==3)]
best=w3.sort_values(['健康_并集','检出数_并集'],ascending=[True,False]).iloc[0]
W('## 3. 结论（实测）'+NL)
W('1. **与门（P1）几乎没有过滤作用**：分布位置窗取 1 天/3 天时，健康上报恒等于单点（51 次），k_and 1.05→1.40 无变化；**窗取 5 天时随 k_and 从 51 微降到 49**（最多减 2 次）—— 单点告警发生时，分布位置几乎总已抬升到 1.4 倍基线以上，与门不构成有效误报过滤。'+NL+NL+'   （口径更正，Codex 批次 4 Q15：45 组 = 3 个分布位置窗 × 5 个 k_and × 3 个 k_ratio；此前写「全部 45 组恒等于 51」过于绝对，实为 **49–51，几乎等于**。）'+NL)
W('2. **比值判据（P3）只增加上报量**：k_ratio=1.15 / 1.25 / 1.40 时健康上报段数 76 / 83 / 96（单点 51）；并集 127 / 134 / 147，全部大于单点。'+NL)
W('3. **窗长**（k_and=1.15、k_ratio=1.25）：窗 1 / 3 / 5 天的比值段数为 150 / 83 / 62，并集 201 / 134 / 113 —— **窗越短越吵，检出却完全一样（12/12，延迟中位 20.3 天不变）**。作为严重度字段建议取 **5 天**（段数最少且不损失检出）；3 天可接受（更及时）。'+NL)
W('4. **检出侧无差异**：单点 / 与门 / 并集在 12 个工况上都是 12/12，延迟中位 20.3 天 —— 并集与与门既不增检出也不减检出。'+NL)
W('5. **结论：第 18.6 节的修正结论在 45 组倍数下被确认** —— 报警流只用单点事件机（阈值按工况自身基线标定），滚动中位数只作**严重度/趋势字段**随报警附注；把比值判据做成与门或并集上报都不会改善误报-延迟权衡。'+NL)
W('## 4. 局限'+NL)
W('- 仍为 12 个工况对、每对单条轨迹；'+NL)
W('- 倍数网格较粗（5×3×3），未做连续优化；'+NL)
W('- 未把两类错误折算成成本权重（误挂=浪费工时 / 漏挂=失去提前量）。'+NL)
f.close(); print('已写出 CSV / 报告 / 图')
print(); print(T[T.窗天==3][['k_and','k_ratio','健康_P1与门','健康_比值段','健康_并集','检出数_P1与门','检出数_并集']].to_string(index=False))
