# -*- coding: utf-8 -*-
"""lanmai CLI 在三个真实/仿真数据集上的端到端演示（DSH，2026-09-21）
产物目录：results/2026-09-21/lanmai_demo/
用法：python src/dsh/2026-09-21_02_lanmai_demo.py"""
import os, io, json, gzip, subprocess, sys, numpy as np, pandas as pd
OUT='results/2026-09-21/lanmai_demo'; os.makedirs(OUT, exist_ok=True)
ENV=dict(os.environ, PYTHONPATH='src', PYTHONIOENCODING='utf-8')
def run(args, title):
    print('### '+title)
    p=subprocess.run([sys.executable,'-m','lanmai']+args, capture_output=True, text=True, encoding='utf-8', errors='replace', env=ENV)
    out=(p.stdout or '')+(p.stderr or '')
    print(out.encode('ascii','replace').decode().strip()[:900]); print()   # 控制台只打 ASCII 安全摘要，完整 UTF-8 见日志文件
    return out

# ---------- 0) 准备 MetroPT-3（真实数据，带工况列 state：stopped/unloaded/loaded） ----------
src='data/metropt3/metropt3.csv'
cols=['timestamp','TP2','TP3','H1','Oil_temperature','Motor_current','DV_eletric','Reservoirs']
d=pd.read_csv(src, usecols=cols, parse_dates=['timestamp']).set_index('timestamp')
m=d.resample('1min').agg({'TP2':'mean','TP3':'mean','H1':'mean','Oil_temperature':'mean','Motor_current':'mean','DV_eletric':'max','Reservoirs':'mean'})
st=np.where(m.Motor_current.fillna(0)<1.0,'stopped',np.where(m.DV_eletric.fillna(0)>=0.5,'loaded','unloaded'))
m['state']=st
mp=os.path.join(OUT,'metropt3_prepared.csv.gz')
with gzip.open(mp,'wt',encoding='utf-8',newline='') as f: m.to_csv(f)
print('已生成 %s（%d 行，含 state 工况列）\n' % (mp, len(m)))

LOG=[]
# ---------- 1) SKAB 真实水泵台架（1 Hz，不重采样） ----------
skab_free='data/SKAB-master/data/anomaly-free/anomaly-free.csv'
skab_fault='data/SKAB-master/data/other/10.csv'
CHS='Current,Pressure,Temperature,Accelerometer1RMS,Volume Flow RateRMS'
LOG.append(run(['inspect','--data',skab_free], 'SKAB 无故障记录：数据体检'))
LOG.append(run(['calibrate','--data',skab_free,'--channels',CHS,'--state','hour','--win-days','0.05',
                '--ref','0,0.3','--out',os.path.join(OUT,'skab_baseline.json')], 'SKAB：基线标定（按小时分层，自适应窗 72 分钟）'))
LOG.append(run(['watch','--data',skab_free,'--baseline',os.path.join(OUT,'skab_baseline.json'),
                '--out',os.path.join(OUT,'skab_alarms_healthy.csv'),'--warmup','10min'], 'SKAB：在无故障记录上告警（误报检查）'))
LOG.append(run(['watch','--data',skab_fault,'--baseline',os.path.join(OUT,'skab_baseline.json'),
                '--out',os.path.join(OUT,'skab_alarms_fault.csv'),'--warmup','0min'], 'SKAB：在含故障记录上告警（检出检查）'))

# ---------- 2) MetroPT-3 地铁空压机（真实数据，带工况列） ----------
LOG.append(run(['inspect','--data',mp], 'MetroPT-3：数据体检（含工况列）'))
LOG.append(run(['calibrate','--data',mp,'--channels','TP2,TP3,H1,Oil_temperature,Motor_current',
                '--out',os.path.join(OUT,'metropt3_baseline.json'),'--state','col','--state-col','state','--ref','0,0.23'],
               'MetroPT-3：基线标定（按运行工况分层）'))
LOG.append(run(['watch','--data',mp,'--baseline',os.path.join(OUT,'metropt3_baseline.json'),
                '--out',os.path.join(OUT,'metropt3_alarms.csv'),'--warmup','1D'], 'MetroPT-3：分级告警'))

# ---------- 3) BSM1 数字孪生：在健康轨迹上标定，在退化轨迹上告警 ----------
hb='results/2026-09-20/dsh/bsm1_120d_baseline.csv'; dg='results/2026-09-20/dsh/bsm1_120d_degraded.csv'
for f in (hb,dg):
    x=pd.read_csv(f); x['timestamp']=pd.to_datetime((x.t_day*86400).round().astype('int64'), unit='s')
    x.to_csv(os.path.join(OUT, os.path.basename(f).replace('.csv','_ts.csv')), index=False)
ch='SO3,SO4,SO5,SNH_eff,Ntot_eff,TSS_eff,sludge_h'
LOG.append(run(['calibrate','--data',os.path.join(OUT,'bsm1_120d_baseline_ts.csv'),'--channels',ch,
                '--out',os.path.join(OUT,'bsm1_baseline.json'),'--state','hour','--ref','0.25,0.375'],
               'BSM1：在健康轨迹第 30-45 天标定基线（按一天中的时段分层）'))
LOG.append(run(['watch','--data',os.path.join(OUT,'bsm1_120d_degraded_ts.csv'),'--baseline',os.path.join(OUT,'bsm1_baseline.json'),
                '--out',os.path.join(OUT,'bsm1_alarms.csv'),'--warmup','1D'], 'BSM1：在退化轨迹上分级告警'))
io.open(os.path.join(OUT,'cli_run_log.txt'),'w',encoding='utf-8').write(chr(10).join(['### '+str(i)+chr(10)+x for i,x in enumerate(LOG)]))
print('全部日志已写入', os.path.join(OUT,'cli_run_log.txt'))
