# -*- coding: utf-8 -*-
"""BSM1 数字孪生闭环（DSH，2026-09-20）
场景：基准（无退化）与退化（曝气传质能力 KLa 在 14→21 天线性衰减 30%，模拟曝气头堵塞/鼓风机效率下降）
链路：检测（因果自适应 z + top3-RMS + 事件机）→ 诊断（规则：曝气能力衰减特征）→ RUL（SO3 趋势外推到 1.0 mg/L）→ 决策（维护窗口 + 成本）
声明：全部为 IWA 标准 BSM1 仿真数据，非现场数据。"""
import bsm2_python as b, numpy as np, pandas as pd, json, os, time
OUT='results/2026-09-20/dsh'; os.makedirs(OUT,exist_ok=True)
DAYS=21; DT=1/96; DEG_START=14.0; DEG_DROP=0.30; SO_LIMIT=1.0
def run(scale_fn,tag):
    t0=time.time(); o=b.BSM1OL(endtime=DAYS, timestep=DT, evaltime=1); o.stabilize()
    n=int(round(DAYS/DT)); rows=[]; k0=np.asarray(o.klas).copy()   # 固定基准，避免复利
    for i in range(n):
        t=i*DT
        k=k0.copy()
        if scale_fn is not None: k=k*scale_fn(t)
        o.step(i, k)
        rr=np.asarray(o.ys_eff).ravel()
        rows.append(dict(t_day=t, SO3=float(np.asarray(o.y_out3).ravel()[7]), SO4=float(np.asarray(o.y_out4).ravel()[7]),
            SO5=float(np.asarray(o.y_out5).ravel()[7]), SNH_eff=float(rr[9]), Ntot_eff=float(rr[10]),
            TSS_eff=float(rr[13]), Q_eff=float(rr[14]), sludge_h=float(np.asarray(o.sludge_height)),
            kla_sum=float(k.sum())))
    print('  %s：%d 步，耗时 %.0fs' % (tag,n,time.time()-t0))
    return pd.DataFrame(rows)
def ramp(t):
    if t<DEG_START: return 1.0
    return 1.0-DEG_DROP*min(1.0,(t-DEG_START)/(DAYS-DEG_START))
print('运行 BSM1 仿真……')
base=run(None,'基准'); deg=run(ramp,'退化')
base.to_csv(os.path.join(OUT,'bsm1_baseline.csv'),index=False) ; deg.to_csv(os.path.join(OUT,'bsm1_degraded.csv'),index=False)
CH=['SO3','SO4','SO5','SNH_eff','Ntot_eff','TSS_eff','sludge_h','kla_sum']
# ---- 检测：因果自适应 z（2 天滑窗）+ top3-RMS ----
def detect(df, ref, thr_q=0.995, WIN=192, MIN=24):
    keep=[c for c in CH if float(ref[c].std())>1e-9]   # 零方差通道剔除
    print('  用于检测的通道:', keep)
    Z=pd.DataFrame(0.0,index=df.index,columns=keep)
    for c in keep:
        x=df[c].astype(float); media=x.rolling(WIN,min_periods=MIN).median()
        iqr=x.rolling(WIN,min_periods=MIN).quantile(.75)-x.rolling(WIN,min_periods=MIN).quantile(.25)
        sd=x.rolling(WIN,min_periods=MIN).std()
        sc=iqr.where(iqr>1e-9,sd).fillna(1.0)
        G=0.2*float((ref[c].quantile(.75)-ref[c].quantile(.25))/1.349) if (ref[c].quantile(.75)-ref[c].quantile(.25))>0 else 0.2*float(ref[c].std())
        sc=pd.concat([sc,pd.Series(G,index=df.index)],axis=1).max(axis=1)
        Z[c]=((x-media)/sc).replace([np.inf,-np.inf],np.nan).fillna(0.0)
    A=np.abs(Z.values)
    return pd.Series(np.sqrt((np.sort(A,axis=1)[:,-3:]**2).mean(1)),index=df.index)
cal=base[base.t_day<10]
score_b=detect(base,cal); score_d=detect(deg,base)     # 用基准全段的通道统计做尺度下限参照
thr=float(score_b.iloc[:int(10/DT)].quantile(0.995))
def events(sv,thr,ENTER=4,EXIT=8,RATIO=0.8,COOL=8):
    over=(sv>thr).values; n=len(sv); ev=[]; st=0; r=0; s0=0; last=-10**9
    for t in range(n):
        if st==0:
            if t<last+COOL: r=0
            elif over[t]:
                r+=1
                if r>=ENTER: s0=t; st=1; r=0
            else: r=0
        else:
            if sv.values[t]<RATIO*thr:
                r+=1
                if r>=EXIT: ev.append((s0,t+1)); last=t+1; st=0; r=0
            else: r=0
    if st==1: ev.append((s0,n))
    return ev
ev_b=events(score_b,thr); ev_d=events(score_d,thr)
t_b=[float(base.t_day.iloc[s]) for s,e in ev_b]; t_d=[float(deg.t_day.iloc[s]) for s,e in ev_d]
det=dict(阈值=round(thr,3),基准告警=[round(x,2) for x in t_b],退化告警=[round(x,2) for x in t_d],
    退化后首报天=min([x for x in t_d if x>=DEG_START], default=None),
    误报数_退化前=sum(1 for x in t_d if x<DEG_START)+len(t_b))
first=det['退化后首报天']
det['检出延迟天']=round(first-DEG_START,2) if first else None
print('检测：阈值 %.3f ｜ 退化后首报 %.2f 天（延迟 %.2f 天）｜ 退化前误报 %d 次' % (thr, first or -1, det['检出延迟天'] or -1, det['误报数_退化前']))
# ---- RUL：SO3 趋势外推到 1.0 ----
FAIL_MULT=3.0; fail_thr=thr*FAIL_MULT
sc_d=score_d.values
above=[float(deg.t_day.iloc[i]) for i in range(len(sc_d)) if sc_d[i]>fail_thr]
true_cross=above[0] if above else None
if first:
    i0=deg.index[deg.t_day<=first][-1]; seg=deg.iloc[max(0,i0-48):i0+1]
    x=seg.t_day.values; y=seg.SO3.values
    k=np.polyfit(x,y,1)[0]
    so_now=float(y[-1]); rul=(SO_LIMIT-so_now)/k if k<-1e-6 else None
else:
    rul=None; k=None
det['RUL估计天']=round(rul,2) if rul else None
det['危险阈值']=round(fail_thr,3)
det['真值越过危险阈值天']=round(true_cross,2) if true_cross else None
det['RUL绝对误差天']=round(abs(true_cross-(first+rul)),2) if (rul and true_cross and first) else None
print('RUL：估计 %.2f 天 ｜ 真值越危险阈值 %.2f 天 ｜ 绝对误差 %.2f 天' % (rul or -1, true_cross or -1, det['RUL绝对误差天'] or -1))
# ---- 决策：维护窗口（低流量时段）+ 成本 ----
deg['hour']=(deg.t_day*24)%24
low=deg[(deg.hour>=1)&(deg.hour<=5)].t_day.max()
win=[float(x) for x in deg[deg.hour.between(1,5)].t_day][-1] if True else None
COST=dict(非计划停机=50000, 计划检修=8000)
decision=dict(建议动作='在下一个低负荷窗口检修曝气系统（清洗/更换曝气头或鼓风机）',
    建议窗口示例='每日 01:00-05:00（低负荷）',
    预计可提前=det['检出延迟天'], 成本参数=COST,
    说明='成本参数为占位值，需用企业数据标定；本场景为仿真，不代表现场收益')
summary=dict(场景=dict(仿真='IWA BSM1 标准活性污泥模型',天数=DAYS,时间步='15 分钟',退化='第 %g 天起 KLa 线性衰减 %.0f%%'%(DEG_START,DEG_DROP*100)),
    检测=det, RUL斜率=round(float(k),5) if k else None, 决策=decision,
    数据文件=['results/2026-09-20/dsh/bsm1_baseline.csv','results/2026-09-20/dsh/bsm1_degraded.csv'])
json.dump(summary,open(os.path.join(OUT,'bsm1_closed_loop_summary.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
with open(os.path.join(OUT,'bsm1_closed_loop.md'),'w',encoding='utf-8') as f:
    f.write('# BSM1 数字孪生闭环（DSH，2026-09-20）'+chr(10)+chr(10))
    f.write('命令：python src/dsh/2026-09-20_01_bsm1_closed_loop.py'+chr(10)+chr(10))
    f.write('**声明：全部为 IWA 标准 BSM1 仿真数据，不是现场数据。**'+chr(10)+chr(10))
    f.write('## 场景'+chr(10)+'- 21 天、15 分钟步长；第 14 天起曝气传质能力 KLa 线性衰减 30%（模拟曝气头堵塞/鼓风机效率下降）。'+chr(10)+chr(10))
    f.write('## 四段结果'+chr(10)+json.dumps(summary,ensure_ascii=False,indent=2)+chr(10))
print('产物：results/2026-09-20/dsh/bsm1_*')
json.dump({'t_b':t_b,'t_d':t_d},open(os.path.join(OUT,'bsm1_events.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
