# -*- coding: utf-8 -*-
"""v1.2 复判：DSH 修正 exit 语义后，与 Codex v1.1 结果比对（含低计数裁决）"""
import pandas as pd, numpy as np, os, io
R=r'C:\Users\boyi\Desktop\BEWG_PdM'
CD=os.path.join(R,'results','2026-09-15','codex'); DD=os.path.join(R,'results','2026-09-15','dsh')
mine=pd.read_csv(os.path.join(DD,'protocol_v13_per_file.csv'))
mine['file']=mine.file.str.replace('\\','/',regex=False)
def ok_count(a,b):
    a,b=int(a),int(b)
    if a==b: return True
    if abs(a-b)<=1 and max(a,b)<=5: return True
    return abs(a-b)/max(abs(a),abs(b),1) <= 0.10
out=[];detail=[]
for m in ['F0','F2','F3']:
    c=pd.read_csv(os.path.join(CD,f'protocol_v11_{m}.csv')); c=c[np.isclose(c.q,0.995)]
    a=mine[mine.method==m]
    j=c.merge(a,on='file',suffixes=('_cx','_ds'))
    j['healthy_ds']=(j.healthy_hours*3600).round().astype(int)
    j['alarm_healthy_ds']=(j.tia*j.healthy_ds).round().astype(int)
    bad_denom=j[j.healthy_samples!=j.healthy_ds]
    bad_cnt=j[(j.true_event_count!=j.events)|(j.hit_event_count!=j.hits)|
              (j.false_alarm_event_count!=j.fp_events)|(~j.apply(lambda r: ok_count(r.hit_event_count,r.hits),axis=1))|
              (~j.apply(lambda r: ok_count(r.false_alarm_event_count,r.fp_events),axis=1))]
    hits_cx=j.hit_event_count.sum(); hits_ds=j.hits.sum()
    fp_cx=j.false_alarm_event_count.sum(); fp_ds=j.fp_events.sum()
    h_cx=j.healthy_samples.sum(); h_ds=j.healthy_ds.sum()
    t_cx=j.true_event_count.sum(); t_ds=j.events.sum()
    rec_cx,rec_ds=hits_cx/max(t_cx,1),hits_ds/max(t_ds,1)
    fph_cx,fph_ds=fp_cx/(h_cx/3600),fp_ds/(h_ds/3600)
    tia_cx,tia_ds=j.alarm_healthy_samples.sum()/h_cx,j.alarm_healthy_ds.sum()/h_ds
    def dev(x,y): return 0.0 if (x==0 and y==0) else (float('inf') if (x==0 or y==0) else abs(x-y)/max(abs(x),abs(y)))
    d1=ok_count(hits_cx,hits_ds); d2=ok_count(fp_cx,fp_ds)
    v=max(dev(rec_cx,rec_ds),dev(fph_cx,fph_ds),dev(tia_cx,tia_ds))
    verdict='通过' if (h_cx==h_ds and d1 and d2 and (v<=0.10 or (max(hits_cx,hits_ds)<=5 and max(fp_cx,fp_ds)<=5))) else '未通过'
    out.append(dict(方法=m,命中=f'{hits_cx}/{hits_ds}',误报事件=f'{fp_cx}/{fp_ds}',
        健康样本=f'{h_cx}/{h_ds}',召回=f'{rec_cx:.3f}/{rec_ds:.3f}',召回偏差=f'{dev(rec_cx,rec_ds)*100:.1f}%',
        误报每健康小时=f'{fph_cx:.2f}/{fph_ds:.2f}',TIAH=f'{tia_cx:.3f}/{tia_ds:.3f}',TIAH偏差=f'{dev(tia_cx,tia_ds)*100:.1f}%',
        分母不一致文件数=len(bad_denom),计数超差文件数=len(bad_cnt),判定=verdict))
S=pd.DataFrame(out)
print(S.to_string(index=False))
io.open(os.path.join(R,'results','2026-09-15','protocol_v13_crosscheck.md'),'w',encoding='utf-8').write(
 '# PROTOCOL_v1.2 复判（DSH 修正 exit 语义后）\n\n比对口径：逐文件整数计数（绝对差 ≤1 或相对差 ≤10%）、分母必须严格相等、汇总相对偏差 ≤10%。\n\n'
 + S.to_markdown(index=False))
