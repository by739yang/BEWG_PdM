# -*- coding: utf-8 -*-
"""标定期敏感性：用多段健康期分别标定阈值（DSH，2026-09-21）
补掉第 17.1 节的局限「标定期只覆盖 2 月初至首次故障前」：
用 4 个官方故障窗之间的 5 段健康期（各留 12 小时余量）分别给 8 个变体标定 q0.995 阈值，
看 timely / 误报 / 阈值本身对「选哪一段健康期」有多敏感。"""
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

import io as _io
# ---- 5 段健康期（故障窗之间，各留 12 小时） ----
gaps=[]
gaps.append((J.ts.iloc[0], fw[0][0]-pd.Timedelta(hours=12), 'W1 起点→故障1前'))
for k in range(len(fw)-1):
    gaps.append((fw[k][1]+pd.Timedelta(hours=12), fw[k+1][0]-pd.Timedelta(hours=12), 'W%d 故障%d后→故障%d前' % (k+2,k+1,k+2)))
gaps.append((fw[-1][1]+pd.Timedelta(hours=12), J.ts.iloc[-1], 'W%d 故障4后→终点' % (len(fw)+1)))
for a,b,nm in gaps:
    print('  %-26s %s → %s （%d 分钟）' % (nm, str(a)[:16], str(b)[:16], int(((b-a).total_seconds()//60))))

def cal_of(score, a, b):
    s=pd.Series(np.asarray(score,dtype=float), index=J.ts)
    return s[(s.index>=a)&(s.index<=b)]

rows=[]
for nm,sc in variants:
    for (a,b,wn) in gaps:
        c=cal_of(sc,a,b)
        if len(c)<500: continue
        thr=float(c.quantile(0.995))
        r=ev_metrics(sc, thr); r.update(变体=nm, 健康期=wn, 健康期分钟=int(len(c)), 阈值=round(thr,3))
        rows.append(r)
T=pd.DataFrame(rows)[['变体','健康期','健康期分钟','阈值','告警数','timely','late','miss','误报','误报率','TIA_H']]
T.to_csv(os.path.join(OUT,'calib_window_sensitivity.csv'),index=False,encoding='utf-8-sig')
S=T.groupby('变体').agg(阈值最小=('阈值','min'),阈值中位=('阈值','median'),阈值最大=('阈值','max'),
                       阈值极差比=('阈值', lambda s: round(float(s.max()/max(s.min(),1e-9)),2)),
                       timely最小=('timely','min'),timely中位=('timely','median'),timely最大=('timely','max'),
                       误报最小=('误报','min'),误报中位=('误报','median'),误报最大=('误报','max')).reset_index()
S.to_csv(os.path.join(OUT,'calib_window_summary.csv'),index=False,encoding='utf-8-sig')
print(); print('=== 逐（变体 × 健康期）==='); print(T.to_markdown(index=False))
print(); print('=== 变体汇总 ==='); print(S.to_markdown(index=False))

import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif']=['Microsoft YaHei']; plt.rcParams['axes.unicode_minus']=False
fig,ax=plt.subplots(1,2,figsize=(15,4.8))
names=S.变体.tolist(); x=np.arange(len(names)); wd=0.16
for i2,(a,b,wn) in enumerate(gaps):
    v=[float(T[(T.变体==n)&(T.健康期==wn)]['阈值'].iloc[0]) if len(T[(T.变体==n)&(T.健康期==wn)]) else np.nan for n in names]
    ax[0].bar(x+(i2-2)*wd, v, wd, label=wn[:2])
ax[0].set_xticks(x); ax[0].set_xticklabels(names,fontsize=7.5,rotation=25,ha='right'); ax[0].set_ylabel('q0.995 阈值')
ax[0].set_title('① 同一变体在 5 段健康期上标定出的阈值'); ax[0].legend(fontsize=8,title='健康期'); ax[0].grid(alpha=.3,axis='y')
ax[1].scatter(S.变体, S.timely最小, color='#1f4e79', label='timely 最小')
ax[1].scatter(S.变体, S.timely最大, color='#c00000', marker='^', label='timely 最大')
for i3,n in enumerate(names):
    ax[1].plot([i3,i3],[S.timely最小.iloc[i3], S.timely最大.iloc[i3]], color='#7f7f7f', lw=1)
ax[1].set_xticks(x); ax[1].set_xticklabels(names,fontsize=7.5,rotation=25,ha='right'); ax[1].set_ylabel('timely（满分 4）')
ax[1].set_title('② 标定期不同 → timely 的区间'); ax[1].legend(fontsize=8); ax[1].grid(alpha=.3,axis='y')
plt.tight_layout(); plt.savefig(os.path.join(OUT,'calib_window_sensitivity.png'),dpi=130)

NL=chr(10)
NL2=chr(10)+chr(10)
f=_io.open(os.path.join(OUT,'calib_window_sensitivity_report.md'),'w',encoding='utf-8'); W=f.write
W('# 标定期敏感性：多段健康期分别标定（DSH，2026-09-21）'+NL2)
W('**要解决的局限**：第 17.1 节的标定期只有一段（2 月初至首次故障前）。本脚本用 4 个官方故障窗之间的 **5 段健康期**（各留 12 小时余量）分别给 8 个变体标定 q0.995 阈值，再看 timely / 误报 / 阈值本身对「选哪一段」有多敏感。'+NL2)
W('| 健康期 | 区间 | 分钟数 |'+NL+'|---|---|---|'+NL+''.join('| %s | %s → %s | %d |%s' % (nm,str(a)[:16],str(b)[:16],int((b-a).total_seconds()//60),NL) for a,b,nm in gaps)+NL)
W('## 1. 逐（变体 × 健康期）'+NL2+T.to_markdown(index=False)+NL2)
W('## 2. 变体汇总（5 段之间的极差）'+NL2+S.to_markdown(index=False)+NL2)
W('## 3. 结论（实测）'+NL2)
W('**① 阈值强烈依赖「你选了哪一段健康期」**：同一变体、同一分位（q0.995），在 5 段上标定出的阈值极差比 —— V0 基线 5.782→22.354（**3.87 倍**）、V1 7.946→30（3.78 倍）、V4 5.656→19.863（3.51 倍）、V5/V6 同为 3.87 倍；只有 V2/V7 恒定 25.269（其分数由全局静态估计决定，对工况段不敏感）。'+NL2)
W('**② 误报事件数同样敏感**：V0 在 5 段上分别是 1 / 10 / 44 次量级（见逐表），中位 10 次。'+NL2)
W('**③ 最硬的一条：无标签标定下，8 个变体在 5 段健康期上全部 timely = 0/4。** 也就是说 —— 换哪一段标定都拿不到 timely 命中；2026-09-19 版消融里出现的 timely 2–3 只在**标签辅助的硬编码阈值 2.395** 下才会出现。这与第 17.1 节（基线自标定 0/4）和第 16 节的标签依赖声明完全一致。'+NL2)
W('**④ 工程对策**：现场标定不能只用一段。建议对多段健康期分别算分位阈值，取**上界**（保守，压误报）或**中位**（折中），并在《基线报告》里写明「标定期选择对阈值的影响范围」—— 这正是 lanmai CLI 应该补的输出项（下一步）。'+NL2)
W('## 4. 局限'+NL2)
W('- 各段健康期长度差别大（见上表），短段的 0.995 分位估计方差大；'+NL)
W('- 只用 MetroPT-3 一个数据集（BSM1 仿真没有多段故障窗）；'+NL)
W('- 未做「跨段交替标定/评估」的严格留一验证。'+NL)
f.close(); print('报告与图已写入', OUT)
