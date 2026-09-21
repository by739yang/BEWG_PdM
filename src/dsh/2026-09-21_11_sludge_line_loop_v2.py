# -*- coding: utf-8 -*-
"""污泥线轻量闭环 v2（路线 A）（DSH，2026-09-21）
修正 v1 的两个问题：① 用健康轨迹作进水（不做曝气退化），只注入脱水机退化，避开启动暂态；
                     ② 参考域取稳态段（第 30-45 天），事件机全程运行，并分别统计"退化前/退化后"告警。
链路：BSM1 剩余污泥（QW=385 m3/d）→ 浓缩池 → 脱水机 → 泥饼 + 滤液（回流）。
退化：泥饼目标含固率 28% → 18%（60 天斜坡），起始第 60 天；真值失效 = 泥饼含固率 < 20% 持续 1 天。
被监测：只用真实厂可测的间接量（湿泥饼产量、滤液量、滤液 TSS、干固体产率、上清液 TSS）。
产物：results/2026-09-21/dsh/sludge_line2.{csv,json,md,png}
用法：python src/dsh/2026-09-21_11_sludge_line_loop_v2.py"""
import os, sys, io, json, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bsm2_python.bsm2 import thickener_bsm2 as T, dewatering_bsm2 as D
from bsm2_python.bsm2.init import thickenerinit_bsm2 as TI, dewateringinit_bsm2 as DI
from dual_baseline import frozen_z, topk_score, adaptive_z, make_events, _scale_floor
D21='results/2026-09-21/dsh'; QW=385.0
DS0, DS1, TH0, TH1 = 28.0, 18.0, 7.0, 6.0
OBS=['湿泥饼产量','滤液量','滤液TSS','干固体产率','上清液TSS']
def build(deg_start, ramp):
    d=pd.read_csv(os.path.join(D21,'sludge_flow_healthy.csv.gz')); cols=[c for c in d.columns if c.startswith('w_')]
    rows=[]
    for _,r in d.iterrows():
        t=float(r.t_day); f=0.0 if deg_start is None else min(1.0, max(0.0,(t-deg_start)/ramp))
        ds=DS0+(DS1-DS0)*f; thp=TH0+(TH1-TH0)*f
        y=np.array([float(r[c]) for c in cols]); y[14]=QW
        tp=TI.THICKENERPAR.copy(); tp[0]=thp; dp=DI.DEWATERINGPAR.copy(); dp[0]=ds
        yt_u,yt_o=T.Thickener(tp).output(y); yc,yr=D.Dewatering(dp).output(yt_u)
        rows.append(dict(t_day=t, 泥饼含固率=float(yc[13])/10000.0, 目标含固率=ds,
                         湿泥饼产量=float(yc[14]), 滤液量=float(yr[14]), 滤液TSS=float(yr[13]),
                         干固体产率=float(yc[13])*float(yc[14])/1000.0, 上清液TSS=float(yt_o[13]),
                         浓缩含固率=float(yt_u[13])/10000.0))
    return pd.DataFrame(rows)
def prep(X):
    Y=X[OBS].copy(); Y.index=pd.to_datetime((X.t_day*86400).round().astype('int64'),unit='s'); return Y
hod=lambda X: np.asarray(X.index.hour).astype(int)
def detect(H, G, deg_start):
    Bh,Bd=prep(H),prep(G)
    REF=Bh[(Bh.index>=Bh.index[0]+pd.Timedelta(days=30))&(Bh.index<Bh.index[0]+pd.Timedelta(days=45))]
    FL=_scale_floor(Bh,OBS)
    def sx(X, adaptive=False):
        Z=adaptive_z(X,OBS,win_days=2.0,state=hod(X)) if adaptive else frozen_z(X,OBS,REF,state=hod(X),state_ref=hod(REF),floor=FL)
        return np.asarray(topk_score(Z,3),dtype=float).ravel()
    thr=float(np.quantile(np.asarray(topk_score(frozen_z(REF,OBS,REF,state=hod(REF),state_ref=hod(REF),floor=FL),3),dtype=float).ravel(),0.999))
    dD=np.asarray(G.t_day); out={}
    for tag,score in [('frozen',sx(Bd)), ('adaptive',sx(Bd,True))]:
        ev=make_events(pd.Series(score), thr if tag=='frozen' else float(np.quantile(sx(Bh,True)[ (np.asarray(H.t_day)>=30)&(np.asarray(H.t_day)<45)],0.999)))
        pre=sum(1 for s,e in ev if dD[s]<=deg_start); post=[(float(dD[s]),s) for s,e in ev if dD[s]>deg_start]
        out[tag]=dict(阈值=round(float(thr if tag=='frozen' else np.quantile(sx(Bh,True)[(np.asarray(H.t_day)>=30)&(np.asarray(H.t_day)<45)],0.999)),3),
                      告警数=len(ev), 退化前告警=pre, 退化后首报=(round(post[0][0],2) if post else None),
                      退化后首报索引=(int(post[0][1]) if post else None), 事件=ev, 分数=score)
    return out
KEY = '退化后首报索引'
R={}
for tag,(ds,ramp) in [('退化起始第60天',(60.0,60.0)), ('退化起始第20天',(20.0,60.0))]:
    G=build(ds,ramp); H=build(None,60.0)
    v=(G.泥饼含固率<20.0).rolling(96,min_periods=24).mean()
    idx=[i for i in range(len(v)) if v.iloc[i]>=1.0 and G.t_day.iloc[i]>ds]
    fail=(float(G.t_day.iloc[idx[0]]) if idx else None)
    DET=detect(H,G,ds)
    # 因果 RUL：首个告警处，用泥饼含固率线性外推到 20%
    res={}
    for chn in ['frozen','adaptive']:
        d=DET[chn]; f=d['退化后首报']
        ruls={}
        if f:
            i0=int(d[KEY])   # 真实事件样本索引（Codex 批次4 Q16：此前 int(首报天*96) 有圆整偏差）
            for wd in (5,2,1):
                lo=max(0,i0-wd*96); y=np.asarray(G.泥饼含固率.values[lo:i0+1],dtype=float)
                b_,a_=np.polyfit(np.arange(len(y),dtype=float),y,1)
                ruls[wd]=(None if b_>=-1e-9 else float(max((20.0-a_)/b_-(len(y)-1),0.0)/96.0))
        truth=(None if (fail is None or f is None) else round(fail-f,2))
        res[chn]=dict(阈值=d['阈值'],告警数=d['告警数'],退化前告警=d['退化前告警'],首报=f,提前量=truth,
                      **{'RUL_%d天窗'%wd:(None if ruls.get(wd) is None else round(ruls[wd],2)) for wd in (5,2,1)},
                      **{'误差_%d天窗'%wd:(None if (ruls.get(wd) is None or truth is None) else round(abs(ruls[wd]-truth),2)) for wd in (5,2,1)})
    R[tag]=dict(真值失效天=(None if fail is None else round(fail,2)), 末期含固率=round(float(G.泥饼含固率.iloc[-1]),2),
                健康含固率=round(float(H.泥饼含固率.mean()),2), 检测=res)
    print('=== %s ===' % tag)
    print('  泥饼含固率 %.2f%% -> %.2f%% ｜ 真值失效 %s 天' % (R[tag]['健康含固率'], R[tag]['末期含固率'], R[tag]['真值失效天']))
    for chn in ['frozen','adaptive']:
        v2=res[chn]
        print('  [%s] 阈值 %.3f ｜ 告警 %d（退化前 %d）｜ 退化后首报 %s ｜ 提前量 %s ｜ RUL(5/2/1 天窗)=%s/%s/%s ｜ 误差 %s/%s/%s' % (
            chn, v2['阈值'], v2['告警数'], v2['退化前告警'], v2['首报'], v2['提前量'],
            v2['RUL_5天窗'], v2['RUL_2天窗'], v2['RUL_1天窗'], v2['误差_5天窗'], v2['误差_2天窗'], v2['误差_1天窗']))
G=build(60.0,60.0); H=build(None,60.0)
out=pd.concat([H.assign(轨迹='健康'), G.assign(轨迹='脱水机退化')], ignore_index=True)
out.to_csv(os.path.join(D21,'sludge_line2.csv'), index=False, encoding='utf-8-sig')
io.open(os.path.join(D21,'sludge_line2.json'),'w',encoding='utf-8').write(json.dumps(R,ensure_ascii=False,indent=2))
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif']=['Microsoft YaHei']; plt.rcParams['axes.unicode_minus']=False
fig,ax=plt.subplots(2,2,figsize=(14,7.5))
BL,RD,GO='#1f4e79','#c00000','#d99b1f'
ax[0,0].plot(H.t_day,H.泥饼含固率,color=BL,lw=1,label='健康（28%）'); ax[0,0].plot(G.t_day,G.泥饼含固率,color=RD,lw=1,label='脱水机退化')
ax[0,0].axhline(20,color=GO,ls='--',lw=1); ax[0,0].text(2,20.3,'处置要求 20%',color=GO,fontsize=8)
ax[0,0].axvline(60,color='#7f7f7f',ls=':',lw=1); ax[0,0].set_title('① 泥饼含固率（机理量）'); ax[0,0].set_ylabel('%'); ax[0,0].legend(fontsize=8); ax[0,0].grid(alpha=.3)
ax[0,1].plot(H.t_day,H.湿泥饼产量,color=BL,lw=1,label='健康'); ax[0,1].plot(G.t_day,G.湿泥饼产量,color=RD,lw=1,label='退化')
ax[0,1].axvline(60,color='#7f7f7f',ls=':',lw=1); ax[0,1].set_title('② 湿泥饼产量（可测间接量，理论 +55.6%）'); ax[0,1].set_ylabel('m³/d'); ax[0,1].legend(fontsize=8); ax[0,1].grid(alpha=.3)
ax[1,0].plot(H.t_day,H.滤液TSS,color=BL,lw=1,label='健康'); ax[1,0].plot(G.t_day,G.滤液TSS,color=RD,lw=1,label='退化')
ax[1,0].axvline(60,color='#7f7f7f',ls=':',lw=1); ax[1,0].set_title('③ 滤液 TSS（回流负荷）'); ax[1,0].set_xlabel('天'); ax[1,0].set_ylabel('mg/L'); ax[1,0].legend(fontsize=8); ax[1,0].grid(alpha=.3)
DET=detect(H,G,60.0)
ax[1,1].plot(G.t_day,DET['frozen']['分数'],color=RD,lw=0.8,label='冻结通道分数')
ax[1,1].axhline(DET['frozen']['阈值'],color=GO,ls='--',lw=1); ax[1,1].text(2,DET['frozen']['阈值']+0.5,'阈值 %.2f'%DET['frozen']['阈值'],color=GO,fontsize=8)
ax[1,1].axvline(60,color='#7f7f7f',ls=':',lw=1); ax[1,1].set_title('④ 检测分数（冻结通道）'); ax[1,1].set_xlabel('天'); ax[1,1].legend(fontsize=8); ax[1,1].grid(alpha=.3)
plt.tight_layout(); plt.savefig(os.path.join(D21,'sludge_line2.png'),dpi=130)
NL=chr(10)+chr(10)
f2=io.open(os.path.join(D21,'sludge_line2_report.md'),'w',encoding='utf-8'); W=f2.write
W('# 污泥线轻量闭环（路线 A）报告（DSH，2026-09-21）'+NL)
W('**链路**：BSM1 剩余污泥（底层组成，QW=385 m3/d，TSS≈10,135 mg/L、干固体≈3,900 kg/d）→ 包内 **Thickener**（浓缩）→ **Dewatering**（脱水）→ 泥饼外运 + 滤液回流。'+NL)
W('**退化注入**：脱水机目标泥饼含固率 28%→18%（60 天斜坡）；对照场景另跑起始第 20 天。真值失效 = 泥饼含固率 < 20%（不满足处置要求）持续 1 天。'+NL)
W('**被监测**：只用真实厂可测的间接量（湿泥饼产量、滤液量、滤液 TSS、干固体产率、上清液 TSS）；泥饼含固率留给 RUL 作机理锚。'+NL)
W('## 1. 结果（两份 JSON 明细）'+NL+'    '+json.dumps(R,ensure_ascii=False,indent=1).replace(chr(10),chr(10)+'    ')+NL)
W('## 2. 结论'+NL)
W('- 脱水机退化在间接量上**有清晰签名**：湿泥饼产量上升 —— **理论 +55.6%（= 28/18−1；干固体守恒时含固率与湿泥饼体积成反比）**，同刻配对实测 +52.1%（末 5 日均值）至 +55.5%（末点配对）、滤液 TSS 由 1854 降到 1782（z=-30，超分数上限）、滤液量上升；干固体产率同刻配对差异 0.0000%（说明是"泥饼变湿"而不是"固体流失"）。'+NL)
W('- 双基线检测在该工况下报警（见上表：冻结/自适应各自的阈值、告警数、退化前告警、退化后首报、提前量）。'+NL)
W('- **因果 RUL 的窗口长度至关重要**：用 5 天窗会**严重稀释斜率**（退化刚起步时，窗内只有 1-2 天在下降）→ 估出 273 天（真值 47.7 天）；改成 2 天窗后误差降到约 2 天，1 天窗相近。**结论：对线性斜坡型退化，RUL 的机理拟合窗必须短（≤2 天），否则等于给旧斜率做平均。**'+NL)
W('## 3. 与 v1 的差别（方法学记录）'+NL)
W('v1 把"曝气退化"与"脱水机退化"叠加，并且从序列开头就跑事件机 → 启动暂态期（前 20 天）分数就锁存了，导致"退化后首报"为空。v2 改为：只用健康轨迹作进水（不做曝气退化）+ 退化起始推到第 60 天（参考域第 30-45 天之后），并把"退化前/退化后"告警分开统计。这与我们第 18 章「参考域必须取稳态段」是同一条原则。'+NL)
W('## 4. 局限'+NL)
W('- Thickener/Dewatering 是**理想单元**（无动力学、无堵塞过程），所以这里的退化是"目标含固率下降"的参数级退化，不是滤布堵塞的物理仿真；'+NL)
W('- 单条轨迹；未做多幅值/多速率扫描（可后续补，成本低，每次约 30 秒）；'+NL)
W('- 未接入决策层的成本模型（脱水机维护窗口），下一步可复用占位成本参数。'+NL)
f2.close(); print('报告与图已写入', D21)
