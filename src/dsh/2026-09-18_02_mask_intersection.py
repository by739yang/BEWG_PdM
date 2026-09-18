# -*- coding: utf-8 -*-
"""冻结分母 = 双方逐分钟掩码的交集（避免继续争论同名异义）"""
import numpy as np, pandas as pd, json, os
OUT='results/2026-09-18/dsh'; os.makedirs(OUT,exist_ok=True)
mine=np.load('results/2026-09-18/dsh/metropt3_masks_dsh_v2.npz', allow_pickle=True)
ts_mine=pd.to_datetime(mine['timestamp'])
M=pd.DataFrame({'ts':ts_mine,
    'fin':mine['score_finite'],'stable':mine['stable_state'],'run':mine['running_state'],
    'fault':mine['in_fault_window'],'A':mine['in_eval_domain_A'],'B':mine['in_eval_domain_B'],
    'cal':mine['in_calibration_B']})
C=np.load('results/2026-09-17/codex/metropt3_masks_codex.npz', allow_pickle=True)
K=pd.DataFrame({'ts':pd.to_datetime(C['timestamp']),
    'fin':C['score_finite'],'stable':C['stable_state'],'run':C['running_state'],
    'fault':C['in_fault_window'],'A':C['in_eval_domain_A'],'B':C['in_eval_domain_B']})
J=M.merge(K,on='ts',suffixes=('_ds','_cx'),how='inner')
print('对齐分钟数 %d（我 %d / 它 %d）' % (len(J), len(M), len(K)))
def cmp(col):
    d=int((J[col+'_ds']!=J[col+'_cx']).sum())
    print('  %-8s 不一致 %6d 分钟 (%.2f%%)' % (col, d, 100*d/len(J)))
for c in ['fin','stable','run','fault','A','B']: cmp(c)
J['fin_both']=J.fin_ds&J.fin_cx; J['stable_both']=J.stable_ds&J.stable_cx; J['run_both']=J.run_ds&J.run_cx
out={}
for dom in ['A','B']:
    base=J[dom+'_ds']&J[dom+'_cx']&J.fin_both&(~J.fault_ds)&J.stable_both
    run=base&J.run_both
    out[dom]={'eval_domain':int((J[dom+'_ds']&J[dom+'_cx']).sum()),
              'healthy_all_stable_交集':int(base.sum()),
              'healthy_running_交集':int(run.sum()),
              '我_alone_all_stable':int((J[dom+'_ds']&J.fin_ds&(~J.fault_ds)&J.stable_ds).sum()),
              '它_alone_all_stable':int((J[dom+'_cx']&J.fin_cx&(~J.fault_cx)&J.stable_cx).sum()),
              '我_alone_running':int((J[dom+'_ds']&J.fin_ds&(~J.fault_ds)&J.stable_ds&J.run_ds).sum()),
              '它_alone_running':int((J[dom+'_cx']&J.fin_cx&(~J.fault_cx)&J.stable_cx&J.run_cx).sum())}
print()
print(json.dumps(out,ensure_ascii=False,indent=2))
json.dump(out,open(os.path.join(OUT,'frozen_denominator.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
J[['ts','A_ds','B_ds','fin_ds','stable_ds','run_ds','A_cx','B_cx','fin_cx','stable_cx','run_cx']].to_csv(
    os.path.join(OUT,'minute_mask_intersection.csv.gz'),compression='gzip',index=False)
print()
print('误差归因示例（前 6 个不一致分钟，按 fin 不一致排序）')
bad=J[J.fin_ds!=J.fin_cx][['ts','fin_ds','fin_cx']].head(6)
print(bad.to_string(index=False))
