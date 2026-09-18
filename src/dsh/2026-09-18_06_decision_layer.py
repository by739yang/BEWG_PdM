# -*- coding: utf-8 -*-
"""决策层 v1（DSH，2026-09-18）：把检测告警转成可执行的维护建议
链路：冻结告警(检测) → 故障类型假设(诊断，Plug-in 接口) → 剩余时间估计(RUL 代理) → 维护窗口 + 优先级 + 成本模型
诚实说明：RUL 为经验代理；成本参数为占位值，需企业数据标定；诊断在 MetroPT-3 上只有单一故障模式（空气泄漏）。"""
import numpy as np, pandas as pd, json, os
OUT='results/2026-09-18/dsh'; os.makedirs(OUT,exist_ok=True)
FW=json.load(open('docs/metropt3_fault_windows.json',encoding='utf-8'))
fw=[(pd.Timestamp(x['start']),pd.Timestamp(x['end'])) for x in FW['windows']]
sc=pd.read_csv('results/2026-09-16/dsh/metropt3_score_minutes_dsh.csv.gz',index_col=0,parse_dates=True)['score']
J=pd.read_csv(os.path.join(OUT,'minute_mask_intersection.csv.gz'),parse_dates=['ts'])
J=J.merge(sc.rename('score'),left_on='ts',right_index=True,how='left')
fault=np.zeros(len(J),bool)
for a,b in fw: fault |= np.asarray((J.ts>=a)&(J.ts<=b))
base=(J.B_ds&J.B_cx&J.fin_ds&J.fin_cx&(~fault)&J.stable_ds&J.stable_cx).values
run=(base&J.run_ds&J.run_cx).values
# ---- 1) 检测：冻结口径的事件机 ----
def events(sv,thr,ENTER=5,EXIT=10,RATIO=0.8,COOL=30):
    sv=np.nan_to_num(sv,nan=0.0); over=sv>thr; n=len(sv); ev=[]; st=0; r=0; s0=0; last=-10**9
    for t in range(n):
        if st==0:
            if t<last+COOL: r=0
            elif over[t]:
                r+=1
                if r>=ENTER: s0=t; st=1; r=0
            else: r=0
        else:
            if sv[t]<RATIO*thr:
                r+=1
                if r>=EXIT: ev.append((s0,t+1)); last=t+1; st=0; r=0
            else: r=0
    if st==1: ev.append((s0,n))
    return ev
THR=2.395
ev=events(J.score.values,THR)
# ---- 2) 诊断（接口）：MetroPT 官方四事件均为空气泄漏，单模式；多模式需多故障标签数据 ----
def diagnose(ev_row): return '空气泄漏（已知单一故障模式）'
# ---- 3) RUL 经验代理：失败阈值 = 历史故障窗内分数的 p90；用事件内线性趋势外推 ----
inwin=J.score.values[fault]
thr_fail=float(np.nanpercentile(inwin,90)) if len(inwin) else 8.0
rows=[]
for (s0,e0) in ev:
    t0,t1=J.ts.iloc[s0],J.ts.iloc[min(e0,len(J)-1)]
    seg=J.score.values[s0:e0]
    i0=J.ts.searchsorted(t0-pd.Timedelta(hours=6))
    pre=J.score.values[i0:s0]
    y=np.r_[pre,seg]; y=np.nan_to_num(y)
    x=np.arange(len(y),dtype=float)
    slope=np.polyfit(x,y,1)[0] if len(y)>=10 else 0.0
    cur=float(y[-1]) if len(y) else 0.0
    rul_h=((thr_fail-cur)/slope/60.0) if slope>1e-6 else np.nan
    rows.append(dict(告警起点=str(t0),告警结束=str(t1),持续分钟=int((t1-t0).total_seconds()//60),
        峰值分数=round(float(np.nanmax(seg)) if len(seg) else 0.0,2),
        故障类型=diagnose(None),RUL估计小时=None if np.isnan(rul_h) else round(float(max(0,min(720,rul_h))),1)))
D=pd.DataFrame(rows)
# ---- 4) 维护窗口：下一个"停机"（压缩机停）连续 >=30 分钟的时间段 ----
st=pd.read_csv('data/metropt3/metropt3.csv',usecols=['timestamp','Motor_current','DV_eletric'],parse_dates=['timestamp']).set_index('timestamp')
mm=st.resample('1min').agg({'Motor_current':'mean','DV_eletric':'max'})
off=((mm['Motor_current'].fillna(0)<1.0).values)
wins=[]; i=0
while i<len(off):
    if off[i]:
        j=i
        while j+1<len(off) and off[j+1]: j+=1
        if j-i+1>=30: wins.append((mm.index[i],mm.index[j]))
        i=j+1
    else: i+=1
print('检测告警 %d 个；失败阈值(经验 p90) = %.2f；可用维护窗口(停机>=30分钟) %d 个' % (len(D),thr_fail,len(wins)))
def next_window(ts):
    for a,b in wins:
        if a>ts: return a
    return None
D['建议维护窗口']=[str(next_window(pd.Timestamp(t))) if next_window(pd.Timestamp(t)) is not None else '无可用窗口' for t in D.告警起点]
# ---- 5) 成本模型（占位参数，需标定）与优先级 ----
COST=dict(非计划停机损失元=50000, 计划检修成本元=8000, 提前更换损失元=3000, 出动一次成本元=2000)
def priority(rul):
    if pd.isna(rul): return 'P3-观察'
    if rul<=24: return 'P1-紧急（24小时内）'
    if rul<=168: return 'P2-计划（一周内）'
    return 'P3-观察'
D['优先级']=[priority(r) for r in D.RUL估计小时]
D.to_csv(os.path.join(OUT,'decision_layer_alarms.csv'),index=False,encoding='utf-8-sig')
# 成本：以"每次避免非计划停机"为收益口径，扣掉误报导致的无效检修
acc=2/4.0   # 冻结结论里的 timely 召回（4 个真值事件命中 2 个）——用作命中概率上界估计
gain=COST['非计划停机损失元']-COST['计划检修成本元']
exp_benefit=acc*gain-(1-acc)*COST['出动一次成本元']
summary=dict(告警数=len(D), 失败阈值=round(thr_fail,2), 维护窗口数=len(wins),
     timely召回=acc, 成本参数=COST, 单次期望收益元=round(exp_benefit,0),
     期望收益说明='命中概率×避免停机收益 - 误报概率×无效出动成本；参数为占位值，需企业数据标定')
if len(D):
    summary['优先级分布']=D.优先级.value_counts().to_dict()
    summary['RUL可得告警数']=int(D.RUL估计小时.notna().sum())
json.dump(summary,open(os.path.join(OUT,'decision_layer_summary.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
with open(os.path.join(OUT,'decision_layer.md'),'w',encoding='utf-8') as f:
    f.write('# 决策层 v1（DSH，2026-09-18）\n\n命令：python src/dsh/2026-09-18_06_decision_layer.py\n\n')
    f.write('链路：冻结检测告警 → 故障类型（接口）→ RUL 经验代理 → 维护窗口与优先级 → 成本模型。\n\n')
    f.write('## 汇总\n\n'+json.dumps(summary,ensure_ascii=False,indent=2)+'\n\n')
    f.write('## 前 12 条建议\n\n'+D.head(12).to_markdown(index=False)+'\n\n')
    f.write('## 必须说明的局限\n1. RUL 是经验代理（把历史故障窗内分数的 p90 当失败阈值，用事件内趋势外推），不是物理寿命模型；\n'
            '2. 诊断在该数据集上只有单一故障模式（官方四事件均为空气泄漏），多模式诊断需多故障标签数据；\n'
            '3. 成本参数是占位值，必须用企业数据标定后才能对外给金额；本报告只给结构与敏感性；\n'
            '4. 维护窗口取"压缩机停机≥30分钟"，现实中还要叠加人员与备件约束。\n')
print(json.dumps(summary,ensure_ascii=False,indent=2))
print()
print(D.head(6).to_string(index=False))
