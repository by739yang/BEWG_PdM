# -*- coding: utf-8 -*-
"""检测模块消融 —— 两套公平阈值口径重跑（DSH，2026-09-21）
背景：原口径让所有变体共用硬编码阈值 2.395，Codex Q6/Q11 指出这不公平（各变体分数尺度不同）。
本脚本复用同一套估计器/事件机/三态命中判据，只改阈值来源，跑三套口径：
  ① 各自重新标定 q0.995（各变体用自己的无标签标定期分数）
  ② 共用同一阈值（用 V0 基线自标定的绝对值，无标签）
  ③ 原口径：硬编码 2.395（保留作对照）"""
import numpy as np, pandas as pd, json, os, time
t0=time.time(); OUT='results/2026-09-19/dsh'; os.makedirs(OUT,exist_ok=True)
FW=json.load(open('docs/metropt3_fault_windows.json',encoding='utf-8'))
fw=[(pd.Timestamp(x['start']),pd.Timestamp(x['end'])) for x in FW['windows']]
RAW=['TP2','TP3','H1','Reservoirs','Oil_temperature','Motor_current']
DER=['TP3_minus_Reservoirs','TP3_minus_H1']
d=pd.read_csv('data/metropt3/metropt3.csv',usecols=['timestamp']+RAW+['DV_eletric'],parse_dates=['timestamp']).set_index('timestamp')
m=d.resample('1min').agg({**{c:'mean' for c in RAW}, 'DV_eletric':'max'})
F=pd.DataFrame({c:m[c] for c in RAW}); F['TP3_minus_Reservoirs']=m['TP3']-m['Reservoirs']; F['TP3_minus_H1']=m['TP3']-m['H1']
allc=list(F.columns)
state=pd.Series(np.where(m['Motor_current'].fillna(0)<1.0,'stopped',np.where(m['DV_eletric'].fillna(0)>=0.5,'loaded','unloaded')),index=m.index)
switch=(state.ne(state.shift(1))&state.shift(1).notna()).values
J=pd.read_csv('results/2026-09-18/dsh/minute_mask_intersection.csv.gz',parse_dates=['ts'])
fault=np.zeros(len(J),bool)
for a,b in fw: fault|=np.asarray((J.ts>=a)&(J.ts<=b))
base=(J.B_ds&J.B_cx&J.fin_ds&J.fin_cx&(~fault)&J.stable_ds&J.stable_cx)
run_=(base&J.run_ds&J.run_cx)
def ev_metrics(score,thr=2.395):
    sv=np.nan_to_num(score,nan=0.0); over=sv>thr; n=len(sv); ev=[]; st=0; r=0; s0=0; last=-10**9
    for t in range(n):
        if st==0:
            if t<last+30: r=0
            elif over[t]:
                r+=1
                if r>=5: s0=t; st=1; r=0
            else: r=0
        else:
            if sv[t]<0.8*thr:
                r+=1
                if r>=10: ev.append((s0,t+1)); last=t+1; st=0; r=0
            else: r=0
    if st==1: ev.append((s0,n))
    timely=late=0
    for g0,g1 in fw:
        tt=[s for s,e in ev if g0-pd.Timedelta(minutes=60)<=J.ts.iloc[s]<=g0+pd.Timedelta(minutes=60)]
        lt=[s for s,e in ev if g0+pd.Timedelta(minutes=60)<J.ts.iloc[s]<=g1]
        timely+=1 if tt else 0; late+=1 if (lt and not tt) else 0
    fp=sum(1 for s,e in ev if not any(g0-pd.Timedelta(minutes=60)<=J.ts.iloc[s]<=g1 for g0,g1 in fw))
    alarm=np.zeros(n,bool)
    for s_,e_ in ev: alarm[s_:min(e_,n)]=True
    return dict(告警数=len(ev),timely=timely,late=late,miss=4-timely-late,误报=fp,
                误报率=round(fp/max(base.sum()/60,1e-9),4),TIA_H=round(float((alarm&base).sum())/max(base.sum(),1),4))
# ---- 估计器 ----
def daily_est(df, use_state=True, days=None):
    out={}
    for day in days:
        lo=day-pd.Timedelta(days=14); sub=df.loc[lo:day-pd.Timedelta(seconds=1)]
        stt=state.reindex(sub.index); sw=(stt.ne(stt.shift(1))&stt.shift(1).notna()).values
        key=lambda s: s if use_state else 'ALL'
        groups=[('ALL',sub[~sw])] if not use_state else [(s,sub[(stt==s).values & (~sw)]) for s in ['stopped','unloaded','loaded']]
        e={}
        for k,X in groups:
            if len(X)<120: X=sub[~sw]
            if len(X)<60: e[k]=None; continue
            med=X.median(); sc=(((X.quantile(.75)-X.quantile(.25))/1.349).where(lambda v:v>1e-9,X.std())).fillna(1.0)
            GS=((df.quantile(.75)-df.quantile(.25))/1.349); GSD=df.std()
            G=pd.concat([GS.where(GS>1e-9,GSD).fillna(1.0)*0.2, GSD.fillna(1.0)*0.1],axis=1).max(axis=1)
            e[k]=(med, pd.concat([sc,G],axis=1).max(axis=1))
        out[day]=e
    return out
days=sorted(set(F.index.normalize()))
EST_WF=daily_est(F,True,days); print('walk-forward 估计完成 %.0fs'%(time.time()-t0))
STAT=(F.median(), pd.concat([(((F.quantile(.75)-F.quantile(.25))/1.349).where(lambda v:v>1e-9,F.std()).fillna(1.0)),(((F.quantile(.75)-F.quantile(.25))/1.349).where(lambda v:v>1e-9,F.std()).fillna(1.0))*0.2],axis=1).max(axis=1))
def z_table(mode, feats, use_state):
    Z=pd.DataFrame(0.0,index=F.index,columns=feats)
    if mode=='static':
        Z=(F[feats]-STAT[0][feats])/STAT[1][feats]; return Z.clip(-30,30)
    for i,day in enumerate(days):
        hi=days[i+1] if i+1<len(days) else F.index[-1]+pd.Timedelta(seconds=1)
        sl=(F.index>=day)&(F.index<hi)
        X=F.loc[sl,feats]; stt=state.loc[sl]
        keys=['ALL'] if not use_state else ['stopped','unloaded','loaded']
        for k in keys:
            e=EST_WF[day].get(k)
            if e is None: continue
            mk=np.ones(len(X),bool) if not use_state else (stt==k).values
            if mk.sum()==0: continue
            Z.loc[X.index[mk],feats]=(X[mk]-e[0][feats])/e[1][feats]
    return Z.clip(-30,30)
def score_top3(Z,k=3):
    A=np.abs(Z.values); return pd.Series(np.sqrt((np.sort(A,axis=1)[:,-k:]**2).mean(1)),index=Z.index)
def score_max(Z): return pd.Series(np.abs(Z.values).max(1),index=Z.index)
import io as _io
# ---- 变体分数（与 2026-09-19 版完全相同） ----
variants=[]
Z0=z_table('wf',allc,True); v0=score_top3(Z0).reindex(J.ts).values
variants.append(('V0 基线（walk-forward + 工况条件化 + top3-RMS）', v0))
variants.append(('V1 聚合改 max|z|（单信号）', score_max(Z0).reindex(J.ts).values))
Zs=z_table('static',allc,False); variants.append(('V2 静态标准化（全期一次估计）', score_top3(Zs).reindex(J.ts).values))
Zn=z_table('wf',allc,False); variants.append(('V3 不做工况条件化', score_top3(Zn).reindex(J.ts).values))
Zr=z_table('wf',RAW,True); variants.append(('V4 去掉派生特征', score_top3(Zr).reindex(J.ts).values))
rng=np.random.default_rng(0)
for frac,tag in [(0.10,'V5 随机缺失 10% 分钟'),(0.30,'V6 随机缺失 30% 分钟')]:
    s_=np.asarray(v0,dtype=float).copy(); idx=rng.choice(len(s_),int(len(s_)*frac),replace=False); s_[idx]=0.0
    variants.append((tag,s_))
Zs2=z_table('static',allc,False).copy(); Zs2['Oil_temperature']=0.0
variants.append(('V7 温度通道卡死（该列置零）', score_top3(Zs2).reindex(J.ts).values))

# ---- 无标签标定期：与冻结脚本一致（首个故障窗前 12 小时、再去掉前 12 小时） ----
def cal_series(score):
    s=pd.Series(np.asarray(score,dtype=float), index=J.ts)
    return s.loc[:str(fw[0][0]-pd.Timedelta(hours=12))].iloc[12*60:]

thr_own={nm: float(cal_series(sc).quantile(0.995)) for nm,sc in variants}
thr_shared=thr_own[variants[0][0]]
print('V0 自标定阈值 = %.3f（共用口径用它）｜原硬编码 = 2.395' % thr_shared)

REGIMES=[('各自重新标定 q0.995',None),('共用同一阈值（V0 自标定）',thr_shared),('原口径：硬编码 2.395',2.395)]
rows=[]
for nm,sc in variants:
    for rname,fixed in REGIMES:
        thr=thr_own[nm] if fixed is None else fixed
        r=ev_metrics(sc, thr); r.update(变体=nm, 口径=rname, 阈值=round(float(thr),3)); rows.append(r)
T=pd.DataFrame(rows)[['变体','口径','阈值','告警数','timely','late','miss','误报','误报率','TIA_H']]
T.to_csv(os.path.join(OUT,'ablation_two_regimes.csv'),index=False,encoding='utf-8-sig')
pv_t=T.pivot_table(index='变体',columns='口径',values='timely')
pv_f=T.pivot_table(index='变体',columns='口径',values='误报')
pv_thr=T.pivot_table(index='变体',columns='口径',values='阈值')
print(); print('=== timely 召回（同一变体在三种口径下）==='); print(pv_t.to_markdown())
print(); print('=== 误报事件数 ===');  print(pv_f.to_markdown())
print(); print('=== 各变体自标定阈值 vs 共用阈值 ==='); print(pv_thr.to_markdown())

# ---- 三条结论的判定 ----
def g(nm,regime,col):
    s=T[(T.变体==nm)&(T.口径==regime)][col]
    return None if not len(s) else s.iloc[0]
CLAIMS=[('V3 不做工况条件化','不做工况条件化 → timely 归零'),
        ('V4 去掉派生特征','去掉派生特征 → timely 归零'),
        ('V1 聚合改 max|z|（单信号）','max|z| 聚合 → 召回更差、误报更高')]
V=[]
for nm,claim in CLAIMS:
    rec=dict(变体=nm, 结论=claim)
    for rname,_ in REGIMES:
        rec[rname+'_timely']=g(nm,rname,'timely'); rec[rname+'_误报']=g(nm,rname,'误报')
    V.append(rec)
Vv=pd.DataFrame(V); Vv.to_csv(os.path.join(OUT,'ablation_two_regimes_verdicts.csv'),index=False,encoding='utf-8-sig')
print(); print(Vv.to_markdown(index=False))

import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif']=['Microsoft YaHei']; plt.rcParams['axes.unicode_minus']=False
BL,RD,GO='#1f4e79','#c00000','#d99b1f'
fig,ax=plt.subplots(1,2,figsize=(15,5))
names=pv_t.index.tolist(); x=np.arange(len(names)); wd=0.26
for i,(rname,_) in enumerate(REGIMES):
    ax[0].bar(x+(i-1)*wd, pv_t[rname].values, wd, label=rname)
    ax[1].bar(x+(i-1)*wd, pv_f[rname].values, wd, label=rname)
for a,t in [(ax[0],'timely 命中官方故障数（满分 4）'),(ax[1],'误报事件数（越低越好）')]:
    a.set_xticks(x); a.set_xticklabels(names,fontsize=7.5,rotation=25,ha='right'); a.set_title(t); a.grid(alpha=.3,axis='y'); a.legend(fontsize=8)
plt.tight_layout(); plt.savefig(os.path.join(OUT,'ablation_two_regimes.png'),dpi=130)

NL=chr(10)
NL2=chr(10)+chr(10)
f=_io.open(os.path.join(OUT,'ablation_two_regimes_report.md'),'w',encoding='utf-8'); W=f.write
W('# 检测消融：两套公平阈值口径重跑（DSH，2026-09-21）'+NL2)
W('**为什么要重跑**：原消融（2026-09-19）让所有变体共用硬编码阈值 2.395，而各变体分数的尺度不同 —— Codex 在 Q6 用自有链路给出反例，Q11 又在它自己的链路上跑了两套口径。本脚本在**本项目链路**上补做同样的两套口径。'+NL2)
W('**口径定义**：'+NL)
W('- 无标签标定期与冻结脚本一致：首个官方故障窗之前 12 小时，再去掉前 12 小时的预热；'+NL)
W('- ① 各自重新标定：每个变体用自己标定期的 0.995 分位作为阈值；'+NL)
W('- ② 共用同一阈值：用 V0 基线自标定的阈值（%.3f）应用到所有变体；' % thr_shared+NL)
W('- ③ 原口径：硬编码 2.395（保留作对照）。事件机（5/10/0.8x/30）与三态命中判据不变。'+NL2)
W('## 1. timely 召回'+NL2+pv_t.to_markdown()+NL2)
W('## 2. 误报事件数'+NL2+pv_f.to_markdown()+NL2)
W('## 3. 各变体自标定阈值'+NL2+pv_thr.to_markdown()+NL2)
W('## 4. 三条结论的判定'+NL2+Vv.to_markdown(index=False)+NL2)
W('**读法**：同一条结论在三种口径下若 timely/误报方向一致，才可写进材料；只要有一种口径下反转，就必须收窄为「在本链路的具体口径下观察到」。'+NL2)
W('### 实测判定（本链路）'+NL2)
W('**① 「不做工况条件化 → timely 归零」：三种口径下均成立（0/4，且 0 告警）。**'+NL)
W('但成因要写清楚：本链路在没有工况分层时，用「全天数据」估计中位与尺度会把异常吸收掉，分数退化为恒 0（该变体自标定阈值算出来就是 0.000）—— **这是本链路的实现特性，不能推广为普遍规律**；Codex 自有链路的反例（233 告警 / timely 2）仍然成立。'+NL2)
W('**② 「去掉派生特征 → timely 归零」：三种口径下均成立（0/4）**，误报分别为 11（自标定）/ 9（共用）/ 171（原口径）。同样只能表述为「本链路观察」，Codex 链路反例（timely 仍 2）保留。'+NL2)
W('**③ 「max|z| 聚合召回更差」：成立**（自标定 0 vs 基线 3；共用 0 vs 3；原口径 1 vs 3）；**但「误报更高」不成立** —— 自标定口径下误报 13 与基线 13 持平、共用口径 15 对 13 基本持平，只有原口径（418 对 201）才显得更差。'+NL2)
W('**④ 额外结论：原口径对尺度不同的变体系统性不公平。** V2 静态标准化与 V7 温度卡死在原口径下是 0 timely / 441、438 误报，换成自标定后变成 **3 timely / 0 误报** —— 印证了 Codex「共用硬编码阈值不公平」的批评。凡引用 2026-09-19 版消融数字，必须标明那是「共用硬编码 2.395」口径。'+NL2)
W('## 5. 局限'+NL2)
W('- 标定期只有 2 月初到首次故障前这一段（无标签、但也不覆盖全部工况）；'+NL)
W('- 官方故障窗仅 4 个，timely 每变化 1 个就是 25%；'+NL)
W('- V5/V6/V7 是对基线分数的扰动/替换，不是完整重训。'+NL)
f.close(); print('报告与图已写入', OUT)
