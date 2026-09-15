# -*- coding: utf-8 -*-
"""PROTOCOL_v1.1 双方盲跑交叉比对：先比逐文件整数计数与分母，再比汇总指标"""
import pandas as pd, numpy as np, os, io
R=r'C:\Users\boyi\Desktop\BEWG_PdM'
CD=os.path.join(R,'results','2026-09-15','codex'); DD=os.path.join(R,'results','2026-09-15','dsh')
mine=pd.read_csv(os.path.join(DD,'protocol_v11_per_file.csv'))
mine['file']=mine.file.str.replace('\\','/',regex=False)
rows=[]
for m in ['F0','F2','F3']:
    c=pd.read_csv(os.path.join(CD,f'protocol_v11_{m}.csv'))
    c=c[np.isclose(c.q,0.995)]
    a=mine[mine.method==m]
    j=c.merge(a,on='file',suffixes=('_cx','_ds'))
    j['healthy_samples_ds']=(j.healthy_hours*3600).round().astype(int)
    j['alarm_healthy_ds']=(j.tia*j.healthy_samples_ds).round().astype(int)
    for _,r in j.iterrows():
        rows.append(dict(method=m,file=r.file, N_cx=r.N, eval_start_cx=r.eval_start, cal_n_cx=r.cal_n,
            cal_n_ds=r.cal_len, truth_cx=r.true_event_count, truth_ds=r.events,
            hit_cx=r.hit_event_count, hit_ds=r.hits,
            fp_cx=r.false_alarm_event_count, fp_ds=r.fp_events,
            alarm_cx=r.alarm_event_count, alarm_ds=r.n_alarm_events,
            healthy_cx=r.healthy_samples, healthy_ds=r.healthy_samples_ds,
            alarm_healthy_cx=r.alarm_healthy_samples, alarm_healthy_ds=r.alarm_healthy_ds))
cmp=pd.DataFrame(rows)
cmp['int_ok']=((cmp.truth_cx==cmp.truth_ds)&(cmp.hit_cx==cmp.hit_ds)&(cmp.fp_cx==cmp.fp_ds)&
               (cmp.alarm_cx==cmp.alarm_ds)&(cmp.healthy_cx==cmp.healthy_ds))
cmp.to_csv(os.path.join(R,'results','2026-09-15','protocol_v11_crosscheck_perfile.csv'),index=False,encoding='utf-8-sig')

print('== 整数计数与分母不一致的文件 ==')
bad=cmp[~cmp.int_ok]
print(bad[['method','file','hi' if False else 'hit_cx','hit_ds','fp_cx','fp_ds','alarm_cx','alarm_ds',
           'healthy_cx','healthy_ds','alarm_healthy_cx','alarm_healthy_ds']].to_string(index=False) if len(bad) else '全部一致')

print()
print('== 汇总（分子分母池化）==')
def dev(a,b):
    a,b=float(a),float(b)
    if a==0 and b==0: return 0.0
    if a==0 or b==0: return float('inf')
    return abs(a-b)/max(abs(a),abs(b))
out=[]
for m in ['F0','F2','F3']:
    g=cmp[cmp.method==m]
    t=dict(method=m)
    t['真值事件']=f"{g.truth_cx.sum()} / {g.truth_ds.sum()}"
    t['命中']=f"{g.hit_cx.sum()} / {g.hit_ds.sum()}"
    t['误报事件']=f"{g.fp_cx.sum()} / {g.fp_ds.sum()}"
    t['告警事件总数']=f"{g.alarm_cx.sum()} / {g.alarm_ds.sum()}"
    t['健康样本']=f"{g.healthy_cx.sum()} / {g.healthy_ds.sum()}"
    rec_cx=g.hit_cx.sum()/max(g.truth_cx.sum(),1); rec_ds=g.hit_ds.sum()/max(g.truth_ds.sum(),1)
    fph_cx=g.fp_cx.sum()/(g.healthy_cx.sum()/3600); fph_ds=g.fp_ds.sum()/(g.healthy_ds.sum()/3600)
    tia_cx=g.alarm_healthy_cx.sum()/g.healthy_cx.sum(); tia_ds=g.alarm_healthy_ds.sum()/g.healthy_ds.sum()
    t['召回 差']=f"{rec_cx:.3f} vs {rec_ds:.3f} = {dev(rec_cx,rec_ds)*100:.1f}%"
    t['误报/健康小时 差']=f"{fph_cx:.2f} vs {fph_ds:.2f} = {dev(fph_cx,fph_ds)*100:.1f}%"
    t['TIA-H 差']=f"{tia_cx:.3f} vs {tia_ds:.3f} = {dev(tia_cx,tia_ds)*100:.1f}%"
    t['判定']='通过' if max(dev(rec_cx,rec_ds),dev(fph_cx,fph_ds),dev(tia_cx,tia_ds))<=0.10 else '未通过'
    out.append(t)
S=pd.DataFrame(out)
print(S.to_string(index=False))
io.open(os.path.join(R,'results','2026-09-15','protocol_v11_crosscheck.md'),'w',encoding='utf-8').write(
 '# PROTOCOL_v1.1 盲跑交叉比对（DSH 侧执行）\n\n## 一、逐文件整数计数与分母\n\n'
 +('全部一致' if len(bad)==0 else bad.to_markdown(index=False))+'\n\n## 二、汇总（池化分子分母）\n\n'+S.to_markdown(index=False))
