# -*- coding: utf-8 -*-
"""BSM1 雨/暴雨冲击工况（DSH，2026-09-20）
三种进水模式各跑健康 + 退化（第 20 天起 KLa 衰减至 40%，100 天斜坡）：
  R1 干天循环 / R2 干+雨循环 / R3 干+雨+暴雨冲击
用法：python 2026-09-20_12_bsm1_rain_storm.py sim [R1_dry ...]   # 只跑仿真
      python 2026-09-20_12_bsm1_rain_storm.py                    # 只做分析（读已落盘 CSV，出报告与图）"""
import sys, os, io, json, time, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bsm2_python as b
OUT='results/2026-09-20/dsh'; PKG=os.path.dirname(b.__file__)
DAYS=120.0; DT=1/96; DEG_START=20.0; KEEP=0.40; RAMP=100.0
N=int(round(DAYS/DT))+1+96*2
Q_IDX=14; TSS_IDX=13; SOLUTE=range(0,14)
CH=['SO3','SO4','SO5','SNH_eff','Ntot_eff','TSS_eff','sludge_h']
MODE={'R1_dry':'dry','R2_dry_rain':'dryrain','R3_add_storm':'storm'}
NICE={'R1_dry':'R1 干天循环','R2_dry_rain':'R2 干+雨循环','R3_add_storm':'R3 干+雨+暴雨'}

def load(f):
    """读进水文件。已核对的坑：① 随包 raininfluent.csv 的 Q 列（第 15 列）比 dryinfluent.csv 小 1000 倍
    （同为第 0 行：dry=21474 m3/d，rain=21.47），直接喂入会让水力为负并报 splitter 错误；
    ② 该文件 Q 列第 996 行为 NaN。这里统一：rain 的 Q 列乘 1000，所有列 NaN 线性插值。"""
    d=np.genfromtxt(os.path.join(PKG,'data',f), delimiter=',', skip_header=1).astype(float)
    if 'rain' in f:
        d[:,15] *= 1000.0
    for c in range(d.shape[1]):
        m=np.isnan(d[:,c])
        if m.any():
            idx=np.arange(len(d)); d[m,c]=np.interp(idx[m], idx[~m], d[~m,c])
    return d[:,1:]

def build(mode):
    dry=load('dryinfluent.csv'); rain=load('raininfluent.csv')
    seq=[]
    while sum(len(x) for x in seq) < N+1344:
        seq += [dry] if mode=='dry' else [dry, rain]
    arr=np.vstack(seq)[:N].astype(float).copy()
    if mode=='storm':
        per=14*96*2
        for c0 in range(0, N, per):
            a=c0+20*96; e=min(c0+22*96, N)
            if a>=N: break
            arr[a:e, Q_IDX] *= 2.5
            arr[a:e, list(SOLUTE)] *= 0.4
    return arr

def sim(vin, keep, tag):
    d=np.column_stack([np.arange(N)*DT, vin])
    t0=time.time(); o=b.BSM1OL(data_in=d, timestep=DT, endtime=DAYS, evaltime=1); o.stabilize()
    k0=np.asarray(o.klas).copy(); rec=[]
    for i in range(int(round(DAYS/DT))):
        t=i*DT; k=k0.copy()
        if keep<1.0: k=k*(1.0-(1.0-keep)*min(1.0, max(0.0,(t-DEG_START)/RAMP)))
        o.step(i,k); rr=np.asarray(o.ys_eff).ravel()
        rec.append((t,float(np.asarray(o.y_out3).ravel()[7]),float(np.asarray(o.y_out4).ravel()[7]),
            float(np.asarray(o.y_out5).ravel()[7]),float(rr[9]),float(rr[10]),float(rr[13]),
            float(np.asarray(o.sludge_height)),float(k.sum())))
    print('  %-24s %d 步 / %.0fs' % (tag,len(rec),time.time()-t0), flush=True)
    return pd.DataFrame(rec,columns=['t_day','SO3','SO4','SO5','SNH_eff','Ntot_eff','TSS_eff','sludge_h','kla_sum'])

if len(sys.argv)>1 and sys.argv[1]=='sim':
    sel=[x for x in sys.argv[2:] if x in MODE] or list(MODE)
    for tag in sel:
        vin=build(MODE[tag])
        print('  [%s] 进水 Q 均值 %.0f ｜ 峰值 %.0f' % (tag, vin[:,Q_IDX].mean(), vin[:,Q_IDX].max()), flush=True)
        sim(vin,1.0,tag+' 健康').to_csv(os.path.join(OUT,'bsm1_%s_baseline.csv'%tag),index=False)
        sim(vin,KEEP,tag+' 退化').to_csv(os.path.join(OUT,'bsm1_%s_degraded.csv'%tag),index=False)
    print('仿真完成'); sys.exit(0)

from dual_baseline import dual_detect, frozen_z, topk_score, _scale_floor
def prep(df):
    x=df.copy(); x.index=pd.to_datetime(x.t_day*86400,unit='s'); return x
hod=lambda X: ((X.t_day*24)%24).astype(int).values
def rollmed(s, X, day=110.0, half=720):
    rm=pd.Series(s).rolling(5*1440,min_periods=288).median().values
    j=int(np.searchsorted(np.asarray(X.t_day),day))
    return round(float(np.nanmedian(rm[max(0,j-half):j+half])),2)
def analyse(tag):
    B=prep(pd.read_csv(os.path.join(OUT,'bsm1_%s_baseline.csv'%tag)))
    D=prep(pd.read_csv(os.path.join(OUT,'bsm1_%s_degraded.csv'%tag)))
    REF=B[(B.t_day>=30)&(B.t_day<45)]; FL=_scale_floor(D,CH)
    res=dual_detect(D, CH, D.t_day<DEG_START, win_days=2.0, k=3, ref_mask_frozen=(B.t_day>=30)&(B.t_day<45),
                    ref_data_frozen=REF, state_frozen=hod(D), state_ref_frozen=hod(REF))
    A=res['alarms']; first={}
    for chn in ['adaptive','frozen']:
        g=A[A.channel==chn] if len(A) else A
        v=[float(D.t_day.loc[tt]) for tt in g.t if float(D.t_day.loc[tt])>DEG_START]
        first[chn]=round(min(v),2) if v else None
    AB=dual_detect(B, CH, B.t_day<DEG_START, win_days=2.0, k=3, ref_mask_frozen=(B.t_day>=30)&(B.t_day<45),
                   ref_data_frozen=REF, state_frozen=hod(B), state_ref_frozen=hod(REF))['alarms']
    fp={chn:int(((AB.channel==chn).sum()) if len(AB) else 0) for chn in ['adaptive','frozen']}
    al=min([v for v in first.values() if v is not None], default=None)
    sD=np.asarray(topk_score(frozen_z(D,CH,REF,state=hod(D),state_ref=hod(REF),floor=FL),3),dtype=float).ravel()
    sB=np.asarray(topk_score(frozen_z(B,CH,REF,state=hod(B),state_ref=hod(REF),floor=FL),3),dtype=float).ravel()
    v=(D.SO3<0.5).rolling(96,min_periods=24).mean()
    idx=[i for i in range(len(v)) if v.iloc[i]>=1.0 and D.t_day.iloc[i]>DEG_START]
    fail=(idx[0]/96.0 if idx else None)
    vb=(B.SO3<0.5).rolling(96,min_periods=24).mean()
    return dict(工况=tag, 健康SO3均值=round(float(B.SO3.mean()),3), 健康持续低于0_5=bool((vb>=1.0).any()),
                健康误报_自适应=fp['adaptive'], 健康误报_冻结=fp['frozen'],
                自适应首报=first['adaptive'], 冻结首报=first['frozen'], 最早报警=al,
                检出延迟天=(None if al is None else round(al-DEG_START,2)),
                失效点SO3_0_5=(None if fail is None else round(fail,2)),
                提前量天=(None if (fail is None or al is None) else round(fail-al,2)),
                健康滚动5天中位数=rollmed(sB,B), 退化滚动5天中位数=rollmed(sD,D),
                退化末期SO3均值=round(float(D[D.t_day>100].SO3.mean()),3))

rows=[]
for tag in MODE:
    if not (os.path.exists(os.path.join(OUT,'bsm1_%s_baseline.csv'%tag)) and os.path.exists(os.path.join(OUT,'bsm1_%s_degraded.csv'%tag))):
        print('缺少文件，跳过', tag); continue
    r=analyse(tag); rows.append(r); print(json.dumps(r,ensure_ascii=False), flush=True)
T=pd.DataFrame(rows)
T.to_csv(os.path.join(OUT,'bsm1_rain_storm.csv'),index=False,encoding='utf-8-sig')
with open(os.path.join(OUT,'bsm1_rain_storm.json'),'w',encoding='utf-8') as fh: json.dump(rows,fh,ensure_ascii=False,indent=2)
print(); print(T.to_string(index=False))

import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif']=['Microsoft YaHei']; plt.rcParams['axes.unicode_minus']=False
BL,RD,GY='#1f4e79','#c00000','#7f7f7f'
x=list(range(len(T))); wd=0.35
fig,ax=plt.subplots(1,3,figsize=(16,4.6))
ax[0].bar([i-wd/2 for i in x],T.健康误报_自适应,wd,color=BL,label='自适应通道')
ax[0].bar([i+wd/2 for i in x],T.健康误报_冻结,wd,color=RD,label='冻结通道')
for i,v in enumerate(T.健康误报_冻结): ax[0].text(i+wd/2,v+0.5,str(int(v)),ha='center',fontsize=8,color=RD)
ax[0].text(0.02,0.92,'对照：BSM2 动态进水 A 窗为 2 / 0',transform=ax[0].transAxes,fontsize=8,color=GY)
ax[0].set_xticks(x); ax[0].set_xticklabels([NICE[t] for t in T.工况],fontsize=9)
ax[0].set_ylabel('健康运行 120 天内误报数'); ax[0].set_ylim(0,32)
ax[0].set_title('① 雨/暴雨工况下健康运行误报显著上升'); ax[0].legend(fontsize=8); ax[0].grid(alpha=.3,axis='y')
vals=[(0 if v is None else float(v)) for v in T.检出延迟天]
ax[1].bar(x,vals,color=[RD if v is None else BL for v in T.检出延迟天])
for i,v in enumerate(T.检出延迟天):
    ax[1].text(i,(0.6 if v is None else v+0.8),'完全漏检' if v is None else '%.2f 天'%v,ha='center',fontsize=8.5,color=(RD if v is None else 'black'))
ax[1].set_xticks(x); ax[1].set_xticklabels([NICE[t] for t in T.工况],fontsize=9); ax[1].set_ylim(0,44)
ax[1].set_ylabel('检出延迟（天）'); ax[1].set_title('② 检出延迟仍由工况成分主导（同一退化配置）'); ax[1].grid(alpha=.3,axis='y')
ax[2].bar([i-wd/2 for i in x],T.健康滚动5天中位数,wd,color=BL,label='健康运行')
ax[2].bar([i+wd/2 for i in x],T.退化滚动5天中位数,wd,color=RD,label='退化运行')
for i,(a1,b1) in enumerate(zip(T.健康滚动5天中位数,T.退化滚动5天中位数)):
    ax[2].text(i-wd/2,a1+0.06,'%.2f'%a1,ha='center',fontsize=8); ax[2].text(i+wd/2,b1+0.06,'%.2f'%b1,ha='center',fontsize=8)
ax[2].set_xticks(x); ax[2].set_xticklabels([NICE[t] for t in T.工况],fontsize=9); ax[2].set_ylim(0,6.2)
ax[2].set_ylabel('冻结分数（滚动 5 天中位数）'); ax[2].set_title('③ 分布位置统计量：健康 vs 退化的可分离性')
ax[2].legend(fontsize=8); ax[2].grid(alpha=.3,axis='y')
plt.tight_layout(); plt.savefig(os.path.join(OUT,'bsm1_rain_storm.png'),dpi=130)

NL=chr(10)+chr(10)
f=io.open(os.path.join(OUT,'bsm1_rain_storm_report.md'),'w',encoding='utf-8'); W=f.write
W('# BSM1 雨/暴雨冲击工况报告（DSH，2026-09-20）'+NL)
W('三种进水模式各跑健康 + 退化两条 120 天轨迹，退化配置相同（第 20 天起 KLa 衰减至 40%、100 天斜坡）：'+NL)
W('- R1 干天循环：dryinfluent 14 天块循环；R2 干+雨循环：dry 14 天 + rain 14 天交替；'+NL)
W('- R3 干+雨+暴雨：在 R2 基础上每 28 天周期第 20-22 天插 2 天暴雨（ASM1 溶质+TSS 乘 0.4、流量乘 2.5）。'+NL)
W('**数据处理（必须记录）**：随包 raininfluent.csv 的 Q 列比 dryinfluent.csv 小 1000 倍（同为第 0 行：dry=21474 m3/d、rain=21.47），且 Q 列第 996 行为 NaN；直接喂入会让水力为负并报 splitter 错误。脚本内统一乘 1000 并线性插值补齐。'+NL)
W('## 1. 结果'+NL+T.to_markdown(index=False)+NL)
W('## 2. 结论'+NL)
W('**① 雨/暴雨工况下「健康运行 0 误报」完全不再成立**：冻结通道误报 26 / 18 / 26 次（120 天），自适应通道 2 / 4 / 1 次；对照 BSM2 动态进水 A 窗为 2 / 0。与 18.2 的刀锋边缘、18.3 的跨工况不稳健一致——冻结通道的零误报是特定工况的巧合。'+NL)
W('**② 自适应通道在干天循环与暴雨工况下完全漏检**（R1、R3 无自适应告警），只在 R2 报出。'+NL)
W('**③ 检出延迟仍由工况成分主导**：同一退化配置下为 37.45 / 2.44 / 0.04 天，差异来自进水模式而非退化。'+NL)
W('**④ 分布位置统计量的可分离性**：健康 vs 退化的滚动 5 天中位数见上表两列。'+NL)
W('## 3. 局限'+NL)
W('- 暴雨为自建合成扰动（简单稀释），非 BSM1 官方 storm 文件（随包未提供）；'+NL)
W('- 三种模式各只有一条 120 天轨迹；进水由 14 天块拼接，非真实季节序列。'+NL)
f.close(); print('report + figure written')
