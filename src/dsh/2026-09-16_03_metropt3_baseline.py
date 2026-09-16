# -*- coding: utf-8 -*-
"""MetroPT-3 独立基线（DSH 侧）：时间型窗口 + 工况条件化 + 维修后健康段标定 + 因果滚动基线"""
import pandas as pd, numpy as np, os, io, json
OUT='results/2026-09-16/dsh'
CSV='data/metropt3/metropt3.csv'
ANALOG=['TP2','TP3','H1','Reservoirs','Oil_temperature','Motor_current']
DIGITAL=['COMP','DV_eletric','Towers','MPG','LPS','Pressure_switch','Oil_level']
BLOCK='10min'; BASE_H=6; MIN_PER=12            # 6 小时因果滚动基线
ENTER=2; EXIT=3; RATIO=0.8; COOL=18            # 块级状态机（1 块 = 10 分钟）
Q=0.995
# 论文（Scientific Data 2022）公开的四个空气泄漏区间，边界待与 Codex 口径核对
FAULTS=[('2020-04-18 00:00','2020-04-18 23:59'),('2020-05-29 23:30','2020-05-30 06:00'),
        ('2020-06-05 10:00','2020-06-07 23:59'),('2020-07-15 14:30','2020-07-15 19:00')]

d=pd.read_csv(CSV, usecols=['timestamp']+ANALOG+DIGITAL, parse_dates=['timestamp'])
d=d.set_index('timestamp')
blk=d.resample(BLOCK).agg({**{c:'mean' for c in ANALOG}, **{c:'max' for c in DIGITAL}}).dropna(how='all')
blk['工况']=(blk['COMP'].fillna(0).round().astype(int).astype(str)+'_'+blk['DV_eletric'].fillna(0).round().astype(int).astype(str))
print('块数', len(blk), '工况分布', blk['工况'].value_counts().head(4).to_dict())

# 因果滚动稳健标准化（按工况分别维护基线）
GMED=blk[ANALOG].median()
GSC=(blk[ANALOG].quantile(.75)-blk[ANALOG].quantile(.25))/1.349
GSC=GSC.where(GSC>1e-6, blk[ANALOG].std()).fillna(1.0)
print('全局稳健尺度:', GSC.round(3).to_dict())
Z=pd.DataFrame(index=blk.index, columns=ANALOG, dtype=float)
for st,g in blk.groupby('工况'):
    med=g[ANALOG].rolling(BASE_H*6, min_periods=MIN_PER).median().fillna(GMED)
    Z.loc[g.index,:]=(g[ANALOG].values-med.values)/GSC.values[None,:]
score=Z.abs().max(axis=1)
print('有效评分块', score.notna().sum())

# 标定：首个故障之前的运行段（2020-02-01 至 2020-04-17），并用前 12 块预热
cal=score.loc[:'2020-04-17 23:59'].dropna()
cal=cal.iloc[MIN_PER:]
thr=cal.quantile(Q)
print('标定块数 %d  阈值 %.3f' % (len(cal), thr))

over=(score>thr).fillna(False).values; scv=score.fillna(0).values
n=len(over); ev=[]; state=0; run=0; start=0; last_end=-10**9
for t in range(n):
    if state==0:
        if t<last_end+COOL: run=0
        elif over[t]:
            run+=1
            if run>=ENTER: start=t; state=1; run=0
        else: run=0
    else:
        if scv[t]<RATIO*thr:
            run+=1
            if run>=EXIT: ev.append((start,t+1)); last_end=t+1; state=0; run=0
        else: run=0
if state==1: ev.append((start,n))
idx=blk.index
print('告警事件数', len(ev))

fw=[(pd.Timestamp(a),pd.Timestamp(b)) for a,b in FAULTS]
def hit_of(s):
    ts=idx[s]
    for a,b in fw:
        if a-pd.Timedelta(hours=1)<=ts<=b: return (a,b)
    return None
hits=[];fps=[]
for s,e in ev:
    g=hit_of(s)
    if g: hits.append((g,s,e))
    else:
        if blk['COMP'].iloc[s]==0 or True: fps.append((s,e))
# 覆盖到的故障
covered={g for g,_,_ in hits}
recall=len(covered)/len(fw)
alarm=np.zeros(n,bool)
for s,e in ev: alarm[s:min(e,n)]=True
fault_mask=np.zeros(n,bool)
for a,b in fw: fault_mask |= (idx>=a)&(idx<=b)
healthy=(~fault_mask)&blk['COMP'].fillna(0).gt(0).values   # 只把"压缩机在运行"的健康块算作分母
hs=healthy.sum()*10/60
tia=(alarm&healthy).sum()/max(hs*60/10,1)
delays=[(idx[s]-g[0]).total_seconds()/3600 for g,s,e in hits]
res=dict(dataset='MetroPT-3', blocks=int(n), block='10min', threshold=round(float(thr),4),
         cal_blocks=int(len(cal)), alarm_events=len(ev), fp_events=len(fps),
         healthy_hours=round(hs,1), fp_per_healthy_hour=round(len(fps)/max(hs,1e-9),3),
         tia_h=round(float(tia),4), true_events=len(fw), detected=len(covered),
         event_recall=round(recall,4),
         delay_hours_median=round(float(np.median(delays)),2) if delays else None)
io.open(os.path.join(OUT,'metropt3_baseline_summary.json'),'w',encoding='utf-8').write(json.dumps(res,ensure_ascii=False,indent=2))
pd.DataFrame([{'event':i+1,'start':str(a),'end':str(b)} for i,(a,b) in enumerate(fw)]).to_csv(
    os.path.join(OUT,'metropt3_fault_windows_dsh.csv'),index=False,encoding='utf-8-sig')
pd.DataFrame([{'t_start':str(idx[s]),'t_end':str(idx[min(e,n-1)]),'hit':bool(hit_of(s))} for s,e in ev]).to_csv(
    os.path.join(OUT,'metropt3_alarm_events_dsh.csv'),index=False,encoding='utf-8-sig')
print(json.dumps(res,ensure_ascii=False,indent=2))
