# -*- coding: utf-8 -*-
"""MetroPT-3 评价 v3：共同评估掩码 + 三态命中（timely/late/miss）+ 双分母
口径来源：handoff/2026-09-16_codex_to_dsh_r2.md（Codex 确认版）"""
import pandas as pd, numpy as np, os, json
OUT='results/2026-09-17/dsh'; os.makedirs(OUT,exist_ok=True)
FW=json.load(open('docs/metropt3_fault_windows.json',encoding='utf-8'))
fw=[(pd.Timestamp(x['start']),pd.Timestamp(x['end'])) for x in FW['windows']]
sc=pd.read_csv('results/2026-09-16/dsh/metropt3_score_minutes_dsh.csv.gz',index_col=0,parse_dates=True)['score']
idx=sc.index
d=pd.read_csv('data/metropt3/metropt3.csv',usecols=['timestamp','Motor_current','DV_eletric'],parse_dates=['timestamp']).set_index('timestamp')
m=d.resample('1min').agg({'Motor_current':'mean','DV_eletric':'max'})
cur=m['Motor_current'].fillna(0); dve=m['DV_eletric'].fillna(0)
state=pd.Series(np.where(cur<1.0,'stopped',np.where(dve>=0.5,'loaded','unloaded')),index=m.index).reindex(idx).fillna('stopped')
switch=(state.ne(state.shift(1))&state.shift(1).notna()).values
finite=sc.notna().values
fault=np.zeros(len(idx),bool)
for a,b in fw: fault |= np.asarray((idx>=a)&(idx<=b))
# 两种评估域候选
domA = np.asarray(idx>=fw[0][0])                                  # A：官方首个故障窗口起
anchor=[('2020-02-01 00:00','2020-02-08 00:00')]               # B：Codex 式固定标定窗排除
for a0,start in [('2020-04-30 12:00','2020-05-01 00:00'),('2020-06-08 16:00','2020-06-09 04:00'),('2020-07-16 00:00','2020-07-16 12:00')]:
    s0=pd.Timestamp(start); anchor.append((str(s0),str(s0+pd.Timedelta(days=7))))
calB=np.zeros(len(idx),bool)
for a0,b0 in anchor: calB |= np.asarray((idx>=pd.Timestamp(a0))&(idx<pd.Timestamp(b0)))
domB = domA & (~calB)
def masks(dom): 
    base=dom&finite&(~fault)&(~switch)
    return dict(domain=int(dom.sum()), healthy_all_stable=int(base.sum()),
                healthy_running=int((base & (state.values!='stopped')).sum()),
                fault_minutes_in_domain=int((dom&fault).sum()), switch_in_domain=int((dom&switch).sum()))
MA, MB = masks(domA), masks(domB)
print('掩码整数：A域', MA); print('掩码整数：B域', MB)
np.savez_compressed(os.path.join('results/2026-09-17/dsh','metropt3_masks_dsh.npz'),
    in_eval_domain_A=domA, in_eval_domain_B=domB, score_finite=finite, stable_state=~switch,
    running_state=(state.values!='stopped'), in_fault_window=fault, in_calibration_B=calB)
pd.DataFrame({'t':idx,'score':sc.values,'state':state.values,'switch':switch,'fault':fault,
              'in_eval_A':domA,'in_eval_B':domB}).to_csv(os.path.join(OUT,'metropt3_minute_masks_dsh.csv.gz'),compression='gzip',index=False)

def events(thr, ENTER=5, EXIT=10, RATIO=0.8, COOL=30):
    sv=sc.values; over=sv>thr; n=len(sv); ev=[]; s_=0; r=0; s0=0; last=-10**9
    for t in range(n):
        if s_==0:
            if t<last+COOL: r=0
            elif over[t]:
                r+=1
                if r>=ENTER: s0=t; s_=1; r=0
            else: r=0
        else:
            if sv[t]<RATIO*thr:
                r+=1
                if r>=EXIT: ev.append((s0,t+1)); last=t+1; s_=0; r=0
            else: r=0
    if s_==1: ev.append((s0,n))
    return ev
def classify(ev):
    res=[]
    for g0,g1 in fw:
        t0=[s for s,e in ev if g0-pd.Timedelta(minutes=60)<=idx[s]<=g0+pd.Timedelta(minutes=60)]
        lt=[s for s,e in ev if g0+pd.Timedelta(minutes=60)<idx[s]<=g1]
        res.append(dict(truth_start=str(g0), truth_end=str(g1),
            timely=bool(t0), late=bool(lt and not t0),
            delay_min=(idx[min(t0)]-g0).total_seconds()/60 if t0 else None,
            late_delay_min=(idx[min(lt)]-g0).total_seconds()/60 if (lt and not t0) else None))
    return res
def evaluate(thr, dom, label):
    ev=events(thr); cls=classify(ev)
    matched=set()
    for c,(g0,g1) in zip(cls,fw):
        if c['timely'] or c['late']: matched.add((g0,g1))
    fp=[]
    for s,e in ev:
        ts=idx[s]
        if not any(g0-pd.Timedelta(minutes=60)<=ts<=g1 for g0,g1 in fw): fp.append((s,e))
    base=dom&finite&(~fault)&(~switch)
    run=base&(state.values!='stopped')
    alarm=np.zeros(len(idx),bool)
    for s,e in ev: alarm[s:min(e,len(idx))]=True
    return dict(domain=label, threshold=round(float(thr),4), alarm_events=len(ev),
        timely=sum(c['timely'] for c in cls), late=sum(c['late'] for c in cls),
        miss=sum((not c['timely']) and (not c['late']) for c in cls),
        main_recall=round(sum(c['timely'] for c in cls)/len(fw),3),
        fp_events=len(fp),
        all_stable_minutes=int(base.sum()), fp_per_hour_all_stable=round(len(fp)/max(base.sum()/60,1e-9),4),
        tia_all_stable=round(float((alarm&base).sum())/max(base.sum(),1),4),
        running_minutes=int(run.sum()), fp_per_hour_running=round(len(fp)/max(run.sum()/60,1e-9),4),
        tia_running=round(float((alarm&run).sum())/max(run.sum(),1),4),
        delay_timely_min=[c['delay_min'] for c in cls if c['timely']],
        events=cls)
cal=sc.loc[:str(fw[0][0]-pd.Timedelta(hours=12))].iloc[12*60:]
thr_main=float(cal.quantile(0.995))
rep=dict(threshold_main=round(thr_main,3), masks={'A_post_first_fault':MA,'B_codex_style_excluding_cal':MB},
         main={'A':evaluate(thr_main,domA,'A_post_first_fault'),'B':evaluate(thr_main,domB,'B_codex_style_excluding_cal')})
json.dump(rep,open(os.path.join(OUT,'metropt3_eval_v3_summary.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
qs=np.linspace(0.90,0.9999,30); rows=[]
for q in qs:
    t=float(cal.quantile(q))
    for lab,dom in [('A_post_first_fault',domA),('B_codex_style_excluding_cal',domB)]:
        r=evaluate(t,dom,lab); r.pop('events'); rows.append(r)
D=pd.DataFrame(rows); D.to_csv(os.path.join(OUT,'metropt3_eval_v3_det.csv'),index=False,encoding='utf-8-sig')
for lab,dom in [('A_post_first_fault',domA),('B_codex_style_excluding_cal',domB)]:
    sub=D[D.domain==lab]
    ok=sub[sub.main_recall>=0.5]
    b=ok.sort_values('fp_per_hour_all_stable').iloc[0] if len(ok) else sub.sort_values('fp_per_hour_all_stable').iloc[0]
    print('%s 域：最高及时召回 %.0f%% 出现在阈值 %.3f（误报 %.4f/全稳定小时，TIA %.1f%%）' % (
        lab, sub.main_recall.max()*100, b.threshold, b.fp_per_hour_all_stable, b.tia_all_stable*100))
print('主阈值下的三态：', [(r['domain'], r['timely'], r['late'], r['miss']) for r in rep['main'].values()])
