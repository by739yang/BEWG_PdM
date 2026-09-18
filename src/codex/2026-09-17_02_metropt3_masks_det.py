#!/usr/bin/env python3
"""Export Codex MetroPT-3 minute masks and recompute DET with timely/late/miss."""
from __future__ import annotations
import argparse, importlib.util, json, sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'src/codex/2026-09-16_01_metropt3_baseline.py'
DEFAULT_CSV=ROOT/'data/metropt3/metropt3.csv'
DEFAULT_OUT=ROOT/'results/2026-09-17/codex'
FIRST_FAULT=pd.Timestamp('2020-04-18 00:00:00')
LATE=pd.Timedelta(minutes=60)

def load_base():
    spec=importlib.util.spec_from_file_location('metro_base', BASE)
    mod=importlib.util.module_from_spec(spec); sys.modules[spec.name]=mod; spec.loader.exec_module(mod); return mod

def read_csv(path, base):
    use=['timestamp',*base.ANALOG,*base.CONTROL]
    dtype={c:'float32' for c in base.ANALOG+base.CONTROL}
    df=pd.read_csv(path,usecols=use,dtype=dtype)
    df['timestamp']=pd.to_datetime(df['timestamp'],format='%Y-%m-%d %H:%M:%S')
    return df.sort_values('timestamp',kind='stable').reset_index(drop=True)

def fault_mask(index, failures):
    out=np.zeros(len(index),bool)
    for _,a,b,_ in failures: out |= (index>=a)&(index<=b)
    return out

def calibration_mask(index, specs):
    out=np.zeros(len(index),bool)
    for _,_,a,b,_ in specs: out |= (index>=a)&(index<b)
    return out

def quarantine_mask(scored, base):
    # Reconstruct the online quarantine state independently of accepted_update.
    out=np.zeros(len(scored),bool); until=pd.Timestamp.min; dur=pd.Timedelta(hours=base.QUARANTINE_HOURS)
    for i,(t,row) in enumerate(scored.iterrows()):
        s=row['score']; ok=bool(row['stable']) and np.isfinite(s)
        if ok and s>=base.QUARANTINE_THRESHOLD:
            until=max(until,t+dur); out[i]=True
        elif t<until:
            out[i]=True
    return out

def classify(scored, alarms, failures):
    rows=[]; timely_alarm=set(); late_alarm=set(); timely_delays=[]; late_delays=[]
    for eid,g0,g1,fault in failures:
        timely=[(i,a,b) for i,(a,b) in enumerate(alarms) if g0-LATE<=a<=g0+LATE]
        late=[(i,a,b) for i,(a,b) in enumerate(alarms) if g0+LATE<a<=g1]
        if timely:
            i,a,b=min(timely,key=lambda x:x[1]); status='timely'; timely_alarm.add(i); timely_delays.append((a-g0).total_seconds()/60)
        elif late:
            i,a,b=min(late,key=lambda x:x[1]); status='late'; late_alarm.add(i); late_delays.append((a-g0).total_seconds()/60)
        else:
            i=None;a=b=None;status='miss'
        rows.append({'event_id':eid,'truth_start':g0,'truth_end':g1,'status':status,
                     'alarm_start':a,'alarm_end':b,'delay_minutes':np.nan if a is None else (a-g0).total_seconds()/60})
    return rows,timely_alarm,late_alarm,timely_delays,late_delays

def evaluate_v2(scored, threshold, base):
    alarms=base.eventize(scored,threshold)
    ev,tset,lset,td,ld=classify(scored,alarms,base.FAILURES)
    eligible=scored['stable'].to_numpy(bool)&np.isfinite(scored['score'].to_numpy(float))
    fault=fault_mask(scored.index,base.FAILURES); healthy=eligible&~fault
    alarm_mask=np.zeros(len(scored),bool)
    for a,b in alarms: alarm_mask|=(scored.index>=a)&(scored.index<b)
    false=sum(i not in (tset|lset) for i in range(len(alarms)))
    hm=int(healthy.sum()); ham=int((healthy&alarm_mask).sum())
    timely=sum(r['status']=='timely' for r in ev); late=sum(r['status']=='late' for r in ev); miss=len(ev)-timely-late
    return {'threshold':threshold,'truth_events':len(ev),'timely_events':timely,'late_events':late,'miss_events':miss,
            'timely_recall':timely/len(ev),'alarm_events':len(alarms),'false_alarm_events':false,
            'healthy_minutes':hm,'healthy_hours':hm/60,'false_alarm_events_per_healthy_hour':false/(hm/60) if hm else np.nan,
            'healthy_alarm_minutes':ham,'TIA_H':ham/hm if hm else np.nan,
            'median_timely_delay_minutes':float(np.median(td)) if td else np.nan,
            'median_late_delay_minutes':float(np.median(ld)) if ld else np.nan},ev

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--csv',type=Path,default=DEFAULT_CSV); ap.add_argument('--output-dir',type=Path,default=DEFAULT_OUT)
    a=ap.parse_args(); a.output_dir.mkdir(parents=True,exist_ok=True); base=load_base()
    raw=read_csv(a.csv,base); minutes=base.make_minute_features(raw); scored,audits=base.walk_forward(minutes)
    idx=minutes.index; aligned=scored.reindex(idx)
    in_a=(idx>=FIRST_FAULT); in_cal=calibration_mask(idx,base.EPOCH_SPECS); in_b=in_a&~in_cal
    finite=np.isfinite(aligned['score'].to_numpy(float)); stable=minutes['stable'].to_numpy(bool); running=stable&(minutes['state'].to_numpy()!=0)
    fault=fault_mask(idx,base.FAILURES); q=np.zeros(len(idx),bool); q[np.isin(idx,scored.index)]=quarantine_mask(scored,base)
    # Required generic field is Codex's actual walk-forward evaluation domain (B); A retained for reconciliation.
    frame=pd.DataFrame({'timestamp':idx,'in_eval_domain':in_b,'in_eval_domain_A':in_a,'in_eval_domain_B':in_b,
        'score_finite':finite,'stable_state':stable,'running_state':running,'in_fault_window':fault,'in_quarantine':q,
        'state':minutes['state'].to_numpy(np.int8),'score':aligned['score'].to_numpy(float)})
    frame.to_csv(a.output_dir/'metropt3_masks_codex.csv.gz',index=False,compression='gzip',encoding='utf-8')
    np.savez_compressed(a.output_dir/'metropt3_masks_codex.npz',timestamp=idx.to_numpy('datetime64[m]'),
        in_eval_domain=in_b,in_eval_domain_A=in_a,in_eval_domain_B=in_b,score_finite=finite,stable_state=stable,
        running_state=running,in_fault_window=fault,in_quarantine=q)
    def counts(domain):
        healthy=domain&finite&stable&~fault; run=healthy&running
        return {'eval_domain':int(domain.sum()),'score_finite':int((domain&finite).sum()),'stable_state':int((domain&stable).sum()),
          'running_state':int((domain&running).sum()),'in_fault_window':int((domain&fault).sum()),'in_quarantine':int((domain&q).sum()),
          'healthy_all_stable':int(healthy.sum()),'healthy_running':int(run.sum())}
    summary={'A':counts(in_a),'B':counts(in_b),'calibration_minutes_in_A':int((in_a&in_cal).sum()),'rows':len(frame)}
    (a.output_dir/'metropt3_mask_counts_codex.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    thresholds=sorted(set([base.PRIMARY_THRESHOLD,*np.arange(2,15.01,.5),18.,22.,30.]))
    det=[]; primary_ev=None
    for th in thresholds:
        m,ev=evaluate_v2(scored,float(th),base); det.append(m)
        if th==base.PRIMARY_THRESHOLD: primary_ev=ev
    det=pd.DataFrame(det).sort_values('threshold'); det.to_csv(a.output_dir/'metropt3_det_v2.csv',index=False,encoding='utf-8-sig')
    primary=det.loc[np.isclose(det.threshold,base.PRIMARY_THRESHOLD)].iloc[0]; best=det.sort_values(['timely_recall','false_alarm_events_per_healthy_hour'],ascending=[False,True]).iloc[0]
    lines=['# MetroPT-3 Codex DET v2（timely / late / miss）','',f'- 主阈值：{base.PRIMARY_THRESHOLD:g}',
      f"- 主阈值：timely {int(primary.timely_events)} / late {int(primary.late_events)} / miss {int(primary.miss_events)}；主召回 {primary.timely_recall:.1%}。",
      f"- DET 最大主召回：{best.timely_recall:.1%}（{int(best.timely_events)}/4），threshold={best.threshold:g}；late={int(best.late_events)}，miss={int(best.miss_events)}。",
      f"- 该点误报/健康小时={best.false_alarm_events_per_healthy_hour:.6f}，TIA-H={best.TIA_H:.6f}。",'',
      '判据：timely 起点在 `[g0-60min, g0+60min]`；若无 timely 而起点在 `(g0+60min, g1]` 则 late；其余 miss。late 不计主召回。','',
      '## 主阈值逐事件','', '|事件|状态|告警起点|延迟(min)|','|---|---|---|---:|']
    for r in primary_ev: lines.append(f"|{r['event_id']}|{r['status']}|{'' if r['alarm_start'] is None else r['alarm_start']}|{'' if not np.isfinite(r['delay_minutes']) else r['delay_minutes']}|")
    lines += ['', '## 掩码整数','', '```json',json.dumps(summary,ensure_ascii=False,indent=2),'```','',
      '注意：A 是自首个官方故障窗起的观测分钟；B 是 A 再排除四段固定标定窗。健康计数还要求 score finite、stable 且不在故障窗。']
    (a.output_dir/'metropt3_det_v2.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'mask_counts':summary,'primary':primary.to_dict(),'best':best.to_dict()},ensure_ascii=False,indent=2,default=str))
if __name__=='__main__': raise SystemExit(main())

