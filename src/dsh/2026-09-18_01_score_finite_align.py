# -*- coding: utf-8 -*-
"""score_finite 语义对齐：把"因果基线样本不足"的分钟标为不可评分，重算健康分母
口径：某分钟可评分 ⇔ 其所在工况在过去 14 天有 >=120 个非切换样本，或全部工况合计 >=60（实现里的兜底）"""
import numpy as np, pandas as pd, json, os
OUT='results/2026-09-18/dsh'; os.makedirs(OUT,exist_ok=True)
FW=json.load(open('docs/metropt3_fault_windows.json',encoding='utf-8'))
fw=[(pd.Timestamp(x['start']),pd.Timestamp(x['end'])) for x in FW['windows']]
sc=pd.read_csv('results/2026-09-16/dsh/metropt3_score_minutes_dsh.csv.gz',index_col=0,parse_dates=True)['score']
idx=sc.index
d=pd.read_csv('data/metropt3/metropt3.csv',usecols=['timestamp','Motor_current','DV_eletric'],parse_dates=['timestamp']).set_index('timestamp')
m=d.resample('1min').agg({'Motor_current':'mean','DV_eletric':'max'})
cur=m['Motor_current'].fillna(0); dve=m['DV_eletric'].fillna(0)
state=pd.Series(np.where(cur<1.0,'stopped',np.where(dve>=0.5,'loaded','unloaded')),index=m.index).reindex(idx).fillna('stopped')
switch=(state.ne(state.shift(1))&state.shift(1).notna()).values
ok=(~switch)
# 每日、每工况在过去 14 天的可用样本数
day=idx.normalize()
df=pd.DataFrame({'day':day,'state':state.values,'ok':ok})
cnt=df[df.ok].pivot_table(index='day',columns='state',values='ok',aggfunc='sum').fillna(0)
cnt_all=df[df.ok].groupby('day')['ok'].sum()
cnt=cnt.reindex(sorted(set(day)))
roll=cnt.rolling(14,min_periods=1).sum().shift(0)          # 含当日（与实现一致：当日估计用当日前的数据，这里近似）
roll_all=cnt_all.reindex(sorted(set(day))).rolling(14,min_periods=1).sum()
per_state=roll.reindex(day.values).reset_index(drop=True)
per_state.index=idx
allc=roll_all.reindex(day.values).reset_index(drop=True); allc.index=idx
finite=np.zeros(len(idx),bool)
for s_ in ['stopped','unloaded','loaded']:
    col=per_state[s_].values if s_ in per_state.columns else np.zeros(len(idx))
    finite |= (state.values==s_) & (col>=120)
finite |= (allc.values>=60)
fault=np.zeros(len(idx),bool)
for a,b in fw: fault |= np.asarray((idx>=a)&(idx<=b))
domA=np.asarray(idx>=fw[0][0]); calB=np.zeros(len(idx),bool)
for a0,b0 in [('2020-02-01 00:00','2020-02-08 00:00'),('2020-05-01 00:00','2020-05-08 00:00'),
              ('2020-06-09 04:00','2020-06-16 04:00'),('2020-07-16 12:00','2020-07-23 12:00')]:
    calB |= np.asarray((idx>=pd.Timestamp(a0))&(idx<pd.Timestamp(b0)))
domB=domA&(~calB)
base=lambda dom: dom & finite & (~fault) & ok
run =lambda dom: base(dom) & (state.values!='stopped')
res={'score_finite_new':int(finite.sum()),'score_finite_old':int(sc.notna().sum())}
for nm,dom in [('A',domA),('B',domB)]:
    res['A' if nm=='A' else 'B']={'eval_domain':int(dom.sum()),
        'healthy_all_stable':int(base(dom).sum()),'healthy_running':int(run(dom).sum())}
print(json.dumps(res,ensure_ascii=False,indent=2))
json.dump(res,open(os.path.join(OUT,'mask_align_result.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
np.savez_compressed(os.path.join(OUT,'metropt3_masks_dsh_v2.npz'),score_finite=finite,stable_state=ok,
                    running_state=(state.values!='stopped'),in_eval_domain_A=domA,in_eval_domain_B=domB,
                    in_fault_window=fault,in_calibration_B=calB,timestamp=idx.values)
print()
print('对照 Codex：B 域 all_stable 108,854 / running 50,912；A 域 all_stable 113,790 / running 65,677')
