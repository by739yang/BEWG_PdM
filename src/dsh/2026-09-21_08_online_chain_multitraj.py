# -*- coding: utf-8 -*-
"""在线链路（门禁 + 机理 RUL）在多轨迹上的评估（DSH，2026-09-21）
把第 21 节的因果门禁与机理 RUL 合成一条在线链路，在 7 条轨迹上跑：
  每条轨迹：双基线检测 → 首个（退化起始之后）告警 t0 → 因果门禁（S1 分布位置漂移 且 M1 机理漂移）
           → 若判"挂 RUL"，用告警前 5 天的反应池溶解氧指数拟合外推到 0.5 mg/L，得在线 RUL
           → 与真值（曝气功能失效时刻 − t0）比较；并给出"事后"RUL 作为非因果上界参照。
产物：results/2026-09-21/dsh/online_chain.{csv,md,png}
用法：python src/dsh/2026-09-21_08_online_chain_multitraj.py"""
import sys, os, io, json, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dual_baseline import dual_detect, frozen_z, topk_score, _scale_floor
D20='results/2026-09-20/dsh'; D21='results/2026-09-21/dsh'
CH=['SO3','SO4','SO5','SNH_eff','Ntot_eff','TSS_eff','sludge_h']
TRAJ=[('基准（第 20 天起）','bsm1_120d_baseline.csv','bsm1_120d_degraded.csv',20.0),
      ('起始第 40 天','bsm1_120d_baseline.csv','bsm1mt_start40.csv',40.0),
      ('起始第 60 天','bsm1_120d_baseline.csv','bsm1mt_start60.csv',60.0),
      ('进水平移 3 天','bsm1_120d_baseline.csv','bsm1mt_phase3.csv',20.0),
      ('进水平移 7 天','bsm1_120d_baseline.csv','bsm1mt_phase7.csv',20.0),
      ('标准进水 -40%','bsm1std_baseline.csv','bsm1std_degraded.csv',20.0),
      ('快退化 -80%/40d','bsm1_120d_baseline.csv','bsm1_sweep_keep20_ramp040.csv',20.0)]
def fpath(f):
    for d in (D20,D21):
        if os.path.exists(os.path.join(d,f)): return os.path.join(d,f)
    raise FileNotFoundError(f)
def prep(df):
    x=df.copy(); x.index=pd.to_datetime(x.t_day*86400,unit='s'); return x
hod=lambda X: ((X.t_day*24)%24).astype(int).values
KD=96
def gate_v2(score, mech, t0_idx, mech_dir=-1, day=KD, ref_lo=30, ref_hi=3, win=3, thr_ratio=1.25, mech_ratio=0.85):
    j0=max(0, t0_idx-win*day+1); r0=max(0, t0_idx-ref_lo*day); r1=max(0, t0_idx-ref_hi*day+1)
    S_now=float(np.nanmedian(score[j0:t0_idx+1])); S_ref=float(np.nanmedian(score[r0:r1])) if r1>r0 else np.nan
    S1=bool(np.isfinite(S_ref) and S_ref>0 and S_now/S_ref>thr_ratio)
    m_now=float(np.nanmedian(mech[j0:t0_idx+1])); m_ref=float(np.nanmedian(mech[r0:r1])) if r1>r0 else np.nan
    M1=False; ratio=np.nan
    if np.isfinite(m_now) and np.isfinite(m_ref) and m_ref>0:
        ratio=m_now/m_ref; M1=bool((ratio<mech_ratio) if mech_dir<0 else (ratio>(1.0/mech_ratio)))
    return S1, M1, bool(S1 and M1), (S_now/S_ref if np.isfinite(S_ref) and S_ref>0 else np.nan), ratio
def rul_fit(do, i0, i1, target=0.5, day=KD):
    """拟合 [i0, i1] 段内的反应池溶解氧（指数），返回距 i0 的天数（窗内 x 从 0 起）。"""
    y=np.asarray(do[i0:i1+1],dtype=float)
    y=np.where(~np.isfinite(y)|(y<=0),1e-3,y); x=np.arange(len(y),dtype=float)
    if len(y)<20: return None
    b,a=np.polyfit(x,np.log(y),1)
    if b>=-1e-9: return None
    return float(max((np.log(target)-a)/b,0.0)/day)
rows=[]
for tag,fb,fd,ds in TRAJ:
    B=prep(pd.read_csv(fpath(fb))); D=prep(pd.read_csv(fpath(fd)))
    REF=B[(B.t_day>=30)&(B.t_day<45)]; FL=_scale_floor(B,CH)
    def sc(X): return np.asarray(topk_score(frozen_z(X,CH,REF,state=hod(X),state_ref=hod(REF),floor=FL),3),dtype=float).ravel()
    sD=sc(D); dD=np.asarray(D.t_day); do=np.asarray(D.SO3,dtype=float)
    res=dual_detect(D, CH, D.t_day<ds, win_days=2.0, k=3, ref_mask_frozen=(B.t_day>=30)&(B.t_day<45),
                    ref_data_frozen=REF, state_frozen=hod(D), state_ref_frozen=hod(REF))
    A=res['alarms']; first=None
    for chn in ['adaptive','frozen']:
        g=A[A.channel==chn] if len(A) else A
        v=[(float(D.t_day.loc[t]), int(D.index.get_loc(t))) for t in g.t if float(D.t_day.loc[t])>ds]
        if v and (first is None or v[0][0]<first[0]): first=(v[0][0], v[0][1], chn)   # (天, 行号, 通道)
    if first is None:
        rows.append(dict(轨迹=tag,首报通道=None,告警天=None,S1=None,M1=None,门禁挂RUL=None,在线RUL=None,真值RUL=None,误差=None,事后RUL=None)); continue
    t0,i0,chn=first
    S1,M1,att,sr,mr=gate_v2(sD, do, i0)
    v=(D.SO3<0.5).rolling(96,min_periods=24).mean()
    idx=[k for k in range(len(v)) if v.iloc[k]>=1.0 and dD[k]>ds]
    fail=(float(dD[idx[0]]) if idx else None)
    truth=(None if fail is None else round(fail-t0,2))
    r_win=rul_fit(do, max(0,i0-5*KD), i0)          # 告警前 5 天窗：估计距窗口起点，减 5 得距告警
    rul=(None if (not att or r_win is None) else round(r_win-5.0,2))
    retro=(rul_fit(do, i0, int(fail*KD)) if (att and fail and int(fail*KD)>i0) else None)   # 非因果上界：从告警拟合到失效
    retro=(None if retro is None else round(retro,2))
    rows.append(dict(轨迹=tag,首报通道=chn,告警天=round(t0,2),S1=bool(S1),M1=bool(M1),门禁挂RUL=bool(att),
                     分布位置比=round(float(sr),2),机理比=round(float(mr),3),
                     在线RUL=(None if rul is None else round(rul,2)),真值RUL=truth,
                     误差=(None if (rul is None or truth is None) else round(abs(rul-truth),2)),
                     事后RUL=(None if retro is None else round(retro,2))))
T=pd.DataFrame(rows); T.to_csv(os.path.join(D21,'online_chain.csv'),index=False,encoding='utf-8-sig')
print(T.to_string(index=False))
err=T.误差.dropna()
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif']=['Microsoft YaHei']; plt.rcParams['axes.unicode_minus']=False
fig,ax=plt.subplots(1,2,figsize=(15,4.6)); x=np.arange(len(T))
ax[0].bar(x-0.2,T.在线RUL.fillna(0),0.4,color='#1f4e79',label='在线 RUL（因果）')
ax[0].bar(x+0.2,T.真值RUL.fillna(0),0.4,color='#c00000',label='真值剩余寿命')
for i,(a1,b1) in enumerate(zip(T.在线RUL,T.真值RUL)):
    if pd.notna(a1): ax[0].text(i-0.2,a1+0.4,'%.1f'%a1,ha='center',fontsize=8)
    if pd.notna(b1): ax[0].text(i+0.2,b1+0.4,'%.1f'%b1,ha='center',fontsize=8)
ax[0].set_xticks(x); ax[0].set_xticklabels(T.轨迹,fontsize=8,rotation=20,ha='right'); ax[0].set_ylabel('天')
ax[0].set_title('① 在线（因果）RUL vs 真值（7 条轨迹）'); ax[0].legend(fontsize=8); ax[0].grid(alpha=.3,axis='y')
ax[1].bar(x,T.门禁挂RUL.astype(int),color=['#2fa36b' if b else '#c00000' for b in T.门禁挂RUL])
ax[1].set_xticks(x); ax[1].set_xticklabels(T.轨迹,fontsize=8,rotation=20,ha='right'); ax[1].set_ylim(0,1.3); ax[1].set_yticks([0,1])
ax[1].set_yticklabels(['不挂 RUL','挂 RUL']); ax[1].set_title('② 因果门禁判定'); ax[1].grid(alpha=.3,axis='y')
plt.tight_layout(); plt.savefig(os.path.join(D21,'online_chain.png'),dpi=130)
NL=chr(10)+chr(10)
f=io.open(os.path.join(D21,'online_chain_report.md'),'w',encoding='utf-8'); W=f.write
W('# 在线链路（门禁 + 机理 RUL）多轨迹评估（DSH，2026-09-21）'+NL)
W('把第 21 节的**因果门禁**与**机理 RUL** 合成一条在线链路，在 7 条轨迹（不同退化起始时刻 / 进水相位 / 进水类型 / 退化速度）上评估。'+NL)
W('## 1. 逐轨迹结果'+NL+T.to_markdown(index=False)+NL)
W('## 2. 结论（实测）'+NL)
W('**① 因果门禁在多轨迹上只挂 3/7**：基准（第 20 天起）、起始第 40 天、进水平移 3 天判「挂 RUL」；起始第 60 天、进水平移 7 天、标准进水、快退化被判「不挂」。失败原因分两类：S1（分布位置比 < 1.25，如起始第 60 天 2.11 但机理比 1.507 未下降、进水平移 7 天 0.81）或 M1（机理比 ≥ 0.85，如标准进水 0.921）。'+NL)
W('**② 在线 RUL 只在 1/7 条轨迹上可算**：3 条「挂 RUL」里有 2 条（起始第 40 天、进水平移 3 天）在告警前 5 天内**反应池溶解氧还没有可测的下降段**（它们的告警来得早：0.22 / 17.28 天），指数拟合的斜率不显著 → 返回 None。可算的那一例是基准轨迹：在线 RUL **4.86 天 vs 真值 7.10 天（误差 2.24 天）**。'+NL)
W('**③ 因果约束本身的代价很小**：同一基准轨迹上，非因果上界（从告警处拟合到失效）给 4.59 天，与在线 4.86 天只差 **0.27 天**。也就是说精度损失主要不来自「不能用未来数据」，而来自**机理下降段尚未出现**。'+NL)
W('**④ 工程含义（写进产品设计）**：对早期告警，应当**推迟 RUL 计算**（等机理量出现显著下降段，或改用相对化窗口），而不是硬报一个数；告警分级上体现为「P1 立即派工、RUL 待机理段出现后再给」。'+NL)
W('**⑤ 真值 RUL 从 2.05 到 35.89 天不等**：RUL 的可预测性本身与「报警时刻相对失效的位置」强相关 —— 报警越早，RUL 越长、越难估准（这也是 22 节「延迟随工况阶段变化」的另一面）。'+NL)
W('## 3. 局限'+NL)
W('- 7 条轨迹、每类各 1 条；门禁与 RUL 的参数（3 天窗、0.85 机理比、5 天拟合窗）未做联合敏感性扫描；'+NL)
W('- 真值失效判据为功能性指标（曝气能力无法维持，DO<0.5 持续 1 天），不是排放超标。'+NL)
f.close(); print('报告与图已写入', D21)
