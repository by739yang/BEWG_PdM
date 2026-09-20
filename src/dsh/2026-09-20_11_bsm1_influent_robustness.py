# -*- coding: utf-8 -*-
"""BSM1 进水工况泛化（DSH，2026-09-20）
用 BSM2 动态进水的不同 120 天窗口（天气/季节不同）做工况泛化：
窗口 A=[0,120)（已有）、B=[120,240)、C=[240,360)，各跑健康 + 退化（第 20 天起 KLa 衰减至 40%）。
用法：python 2026-09-20_11_bsm1_influent_robustness.py sim    # 只跑仿真并落盘
      python 2026-09-20_11_bsm1_influent_robustness.py        # 只做分析（读已落盘 CSV）"""
import sys, os, io, json, time, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bsm2_python as b
OUT='results/2026-09-20/dsh'; PKG=os.path.dirname(b.__file__)
DAYS=120.0; DT=1/96; DEG_START=20.0; KEEP=0.40; RAMP=100.0
WIN={'A_0_120':0.0,'B_120_240':120.0,'C_240_360':240.0}
CH=['SO3','SO4','SO5','SNH_eff','Ntot_eff','TSS_eff','sludge_h']

def window_influent(start):
    d=np.genfromtxt(os.path.join(PKG,'data','dyninfluent_bsm2.csv'), delimiter=',', skip_header=1)
    m=(d[:,0]>=start-1e-9)&(d[:,0]<start+DAYS+1.0)   # 多取 1 天，覆盖到 endtime 之外
    arr=d[m].copy(); arr[:,0]=arr[:,0]-start
    return arr

def sim(arr, keep, tag):
    t0=time.time(); o=b.BSM1OL(data_in=arr, timestep=DT, endtime=DAYS, evaltime=1); o.stabilize()
    n=int(round(DAYS/DT)); k0=np.asarray(o.klas).copy(); rows=[]
    for i in range(n):
        t=i*DT; k=k0.copy()
        if keep<1.0: k=k*(1.0-(1.0-keep)*min(1.0, max(0.0,(t-DEG_START)/RAMP)))
        o.step(i,k); rr=np.asarray(o.ys_eff).ravel()
        rows.append((t,float(np.asarray(o.y_out3).ravel()[7]),float(np.asarray(o.y_out4).ravel()[7]),
            float(np.asarray(o.y_out5).ravel()[7]),float(rr[9]),float(rr[10]),float(rr[13]),
            float(np.asarray(o.sludge_height)),float(k.sum())))
    print('  %-22s %d 步 / %.0fs' % (tag,n,time.time()-t0), flush=True)
    return pd.DataFrame(rows,columns=['t_day','SO3','SO4','SO5','SNH_eff','Ntot_eff','TSS_eff','sludge_h','kla_sum'])

if len(sys.argv)>1 and sys.argv[1]=='sim':
    for w,st in WIN.items():
        f=os.path.join(OUT,'bsm1_win%s_baseline.csv'%w)
        if st==0.0 and os.path.exists(os.path.join(OUT,'bsm1_120d_baseline.csv')):
            print('窗口 %s：复用已有 120 天基准/退化' % w, flush=True); continue
        arr=window_influent(st)
        sim(arr,1.0,w+' 健康').to_csv(f,index=False)
        sim(arr,KEEP,w+' 退化').to_csv(os.path.join(OUT,'bsm1_win%s_degraded.csv'%w),index=False)
    print('仿真完成'); sys.exit(0)

from dual_baseline import dual_detect, frozen_z, topk_score, _scale_floor
def prep(df):
    x=df.copy(); x.index=pd.to_datetime(x.t_day*86400,unit='s'); return x
hod=lambda X: ((X.t_day*24)%24).astype(int).values
def analyse(tag, fb, fd):
    B=prep(pd.read_csv(fb)); D=prep(pd.read_csv(fd)); REF=B[(B.t_day>=30)&(B.t_day<45)]
    res=dual_detect(D, CH, D.t_day<DEG_START, win_days=2.0, k=3,
                    ref_mask_frozen=(B.index>=REF.index[0])&(B.index<=REF.index[-1]) if False else (B.t_day>=30)&(B.t_day<45),
                    ref_data_frozen=REF, state_frozen=hod(D), state_ref_frozen=hod(REF))
    A=res['alarms']; out={}
    for chn in ['adaptive','frozen']:
        g=A[A.channel==chn] if len(A) else A
        v=[float(D.t_day.loc[tt]) for tt in g.t if float(D.t_day.loc[tt])>DEG_START]
        out[chn]=round(min(v),2) if v else None
    Ar=dual_detect(B, CH, B.t_day<DEG_START, win_days=2.0, k=3,
                   ref_mask_frozen=(B.t_day>=30)&(B.t_day<45), ref_data_frozen=REF,
                   state_frozen=hod(B), state_ref_frozen=hod(REF))['alarms']
    fp={chn:int(((Ar.channel==chn).sum()) if len(Ar) else 0) for chn in ['adaptive','frozen']}
    FL=_scale_floor(D,CH)
    s=np.asarray(topk_score(frozen_z(D,CH,REF,state=hod(D),state_ref=hod(REF),floor=FL),3),dtype=float).ravel()
    rm=pd.Series(s).rolling(5*1440,min_periods=288).median().values
    j=int(np.searchsorted(np.asarray(D.t_day),110.0))
    v=(D.SO3<0.5).rolling(96,min_periods=24).mean(); idx=[i for i in range(len(v)) if v.iloc[i]>=1.0 and D.t_day.iloc[i]>DEG_START]
    fail=(idx[0]/96.0 if idx else None)
    al=min([x for x in out.values() if x is not None], default=None)
    vb=(B.SO3<0.5).rolling(96,min_periods=24).mean()
    return dict(工况窗口=tag, 健康SO3均值=round(float(B.SO3.mean()),3),
                健康持续低于0_5=bool((vb>=1.0).any()),
                进水SO3基准均值=round(float(B.SO3.mean()),3),
                健康误报_自适应=fp['adaptive'], 健康误报_冻结=fp['frozen'],
                自适应首报=out['adaptive'], 冻结首报=out['frozen'], 最早报警=al,
                检出延迟天=(None if al is None else round(al-DEG_START,2)),
                失效点SO3_0_5=(None if fail is None else round(fail,2)),
                失效前提前量=(None if (fail is None or al is None) else round(fail-al,2)),
                第110天滚动5天中位数=round(float(np.nanmedian(rm[max(0,j-720):j+720])),2),
                退化末期SO3均值=round(float(D[D.t_day>100].SO3.mean()),3))
rows=[]
for w,st in WIN.items():
    fb=os.path.join(OUT,'bsm1_120d_baseline.csv' if st==0.0 else 'bsm1_win%s_baseline.csv'%w)
    fd=os.path.join(OUT,'bsm1_120d_degraded.csv' if st==0.0 else 'bsm1_win%s_degraded.csv'%w)
    if not (os.path.exists(fb) and os.path.exists(fd)): print('缺少文件，跳过', w); continue
    r=analyse(w,fb,fd); rows.append(r); print(json.dumps(r,ensure_ascii=False), flush=True)
T=pd.DataFrame(rows); T.to_csv(os.path.join(OUT,'bsm1_influent_robustness.csv'),index=False,encoding='utf-8-sig')
with open(os.path.join(OUT,'bsm1_influent_robustness.json'),'w',encoding='utf-8') as fh: json.dump(rows,fh,ensure_ascii=False,indent=2)
print(); print(T.to_string(index=False))

# ---- 图 ----
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif']=['Microsoft YaHei']; plt.rcParams['axes.unicode_minus']=False
BL,RD,GO,GY='#1f4e79','#c00000','#d99b1f','#7f7f7f'
fig,ax=plt.subplots(1,2,figsize=(13,4.6))
x=range(len(T)); wd=0.35
hb=[float(pd.read_csv(os.path.join(OUT,'bsm1_120d_baseline.csv' if i==0 else 'bsm1_win%s_baseline.csv'%w)).SO3.mean()) for i,(w,_) in enumerate(WIN.items())]
ax[0].bar([i-wd/2 for i in x],hb,wd,color=BL,label='健康运行 SO3 均值')
ax[0].bar([i+wd/2 for i in x],T.退化末期SO3均值,wd,color=RD,label='退化末期 SO3 均值')
ax[0].axhline(0.5,color=GO,ls='--',lw=1.4)
ax[0].text(len(T)-0.5,0.56,'危险阈值 SO3=0.5 mg/L（绝对值）',fontsize=8,color=GO,ha='right')
for i,(w,_) in enumerate(WIN.items()):
    if bool(T.健康持续低于0_5.iloc[i]): ax[0].text(i-wd/2,hb[i]+0.05,'健康运行即已持续低于阈值',fontsize=7.5,color=RD,ha='center')
ax[0].set_xticks(list(x)); ax[0].set_xticklabels(list(T.工况窗口),fontsize=9)
ax[0].set_ylabel('SO3（mg/L）'); ax[0].set_ylim(0,2.0)
ax[0].set_title('① 绝对危险阈值在 B/C 工况下对健康运行也成立 -> 判据失真')
ax[0].legend(fontsize=8); ax[0].grid(alpha=.3,axis='y')
ax[1].bar([i-wd/2 for i in x],T.健康误报_自适应,wd,color=BL,label='健康误报（自适应通道）')
ax[1].bar([i+wd/2 for i in x],T.健康误报_冻结,wd,color=RD,label='健康误报（冻结通道）')
for i,v in enumerate(T.检出延迟天):
    ax[1].text(i, max(T.健康误报_自适应.iloc[i],T.健康误报_冻结.iloc[i])+0.25,'检出延迟 %.1f 天'%v,ha='center',fontsize=8,color=GO)
ax[1].set_xticks(list(x)); ax[1].set_xticklabels(list(T.工况窗口),fontsize=9); ax[1].set_ylim(0,8)
ax[1].set_ylabel('健康运行 120 天内误报数'); ax[1].set_title('② 同一退化配置、三种进水工况：误报与检出延迟都随工况变化')
ax[1].legend(fontsize=8); ax[1].grid(alpha=.3,axis='y')
plt.tight_layout(); plt.savefig(os.path.join(OUT,'bsm1_influent_robustness.png'),dpi=130)

NL=chr(10)+chr(10)
f=io.open(os.path.join(OUT,'bsm1_influent_robustness_report.md'),'w',encoding='utf-8'); W=f.write
W('# BSM1 进水工况泛化报告（DSH，2026-09-20）'+NL)
W('做法：用 BSM2 动态进水（dyninfluent_bsm2.csv，609 天）的三个 120 天窗口作为三种进水工况；每个窗口各跑健康与退化两条 120 天轨迹。'+NL)
W('退化配置完全相同：第 20 天起 KLa 线性衰减至 40%（100 天斜坡）。'+NL)
W('## 1. 结果'+NL+T.to_markdown(index=False)+NL)
W('## 2. 结论'+NL)
W('**① 三种工况下都检出了退化（无漏检）**：自适应与冻结通道都在每个窗口报出告警。'+NL)
W('**② 但「120 天 0 误报」不跨工况成立**：健康运行误报 A 2/0、B 6/4、C 2/3（自适应/冻结）——与 18.2 的刀锋边缘结论一致，冻结通道的零误报只在 A 窗成立。'+NL)
W(('**③ 检出延迟由工况成分主导**：同一退化配置的检出延迟为 %.2f / %.2f / %.2f 天，差别主要来自进水工况本身。' % tuple(T.检出延迟天)) + NL)
W('**④ 绝对危险阈值不可用**：B、C 窗的进水工况使健康运行的 SO3 本底降到 1.01 / 0.61 mg/L，健康运行本身就长期满足 SO3<0.5 mg/L，于是「失效点」与「提前量」在该工况下完全失真（表中 B/C 的提前量为负）。'+NL)
W('## 3. 第五条设计原则'+NL)
W('**危险/失效阈值必须按该工况自身的健康基线标定（相对劣化幅度或分位数），不能用绝对值。**'+NL)
W('## 4. 局限'+NL)
W('- 三个窗口取自同一条动态进水序列（同一厂的不同时段），不是三座不同的厂；'+NL)
W('- 未包含雨天/暴雨冲击工况（BSM1 raininfluent 需自行拼接，留作后续）；'+NL)
W('- 每个窗口仍只有一条轨迹，未做多随机种子重复。'+NL)
f.close(); print('report + figure written')
