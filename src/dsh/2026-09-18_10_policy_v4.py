# -*- coding: utf-8 -*-
"""决策层 v4（DSH）：时序维护策略仿真（修正单快照假象）
逐周期决策：每周期用模型预测 RUL，<= 提前期则计划更换；跑到真失效则付失效代价；
过度更换按浪费的剩余寿命计额外代价。对照：跑坏为止 / 固定周期。"""
import numpy as np, pandas as pd, os, json, time
from sklearn.ensemble import GradientBoostingRegressor
t0=time.time(); OUT='results/2026-09-18/dsh'
COLS=['unit','cycle']+['op%d'%i for i in range(1,4)]+['s%d'%i for i in range(1,22)]
SENS=['s2','s3','s4','s7','s8','s11','s12','s13','s15','s17','s20','s21']
CAP=125; W=10; W5=5
tr=pd.read_csv('data/cmapss/train_FD001.txt',sep=r'\s+',header=None,names=COLS)
te=pd.read_csv('data/cmapss/test_FD001.txt',sep=r'\s+',header=None,names=COLS)
te_rul=pd.read_csv('data/cmapss/RUL_FD001.txt',header=None)[0].values
tr['RUL']=tr.groupby('unit')['cycle'].transform('max')-tr['cycle']
mu,sd=tr[SENS].mean(),tr[SENS].std().replace(0,1)
def feat(df):
    z=((df[SENS]-mu)/sd); parts=[z.add_suffix('_last')]
    for w,suf in [(W,'_m10'),(W5,'_m5')]: parts.append(z.rolling(w,min_periods=1).mean().add_suffix(suf))
    parts.append(z.rolling(W,min_periods=1).std().add_suffix('_sd10'))
    m5=z.rolling(W5,min_periods=1).mean(); parts.append((m5-m5.shift(W5)).add_suffix('_trend'))
    F=pd.concat(parts,axis=1); F['unit']=df['unit'].values; F['cycle']=df['cycle'].values
    return F.bfill()
Ftr=feat(tr); m=tr['cycle']>=W
X= Ftr.loc[m,[c for c in Ftr.columns if c not in ('unit','cycle')]].values
y= np.minimum(tr.loc[m,'RUL'].values,CAP)
gb=GradientBoostingRegressor(random_state=0,n_estimators=300,max_depth=3,learning_rate=0.05).fit(X,y)
Fte=feat(te); Xte=Fte[[c for c in Fte.columns if c not in ('unit','cycle')]].values
pred=np.clip(gb.predict(Xte),0,600); Fte['pred']=pred
# 真值 RUL（逐周期）：测试单元最后周期真值已知 -> 向前累加
te=te.copy(); te['trueRUL']=te['unit'].map({u:r for u,r in zip(sorted(te.unit.unique()),te_rul)})
te['trueRUL']=te['trueRUL']+ (te.groupby('unit')['cycle'].transform('max')-te['cycle'])
Fte['trueRUL']=te['trueRUL'].values
PR=dict(失效=50000, 计划更换=8000, 每剩余周期浪费=60)   # 占位值
def sim_ai(lead, min_gap=0):
    """逐周期：pred<=lead 就计划更换；否则继续跑；跑到底仍未更换且真值耗尽 -> 失效"""
    cost=0.0; planned=0; failed=0; waste_cycles=0
    for u,g in Fte.groupby('unit'):
        g=g.sort_values('cycle'); done=False
        for _,r in g.iterrows():
            if r['pred']<=lead:
                cost+=PR['计划更换']; planned+=1
                waste_cycles+=max(0.0,r['trueRUL']-lead); done=True; break
        if not done:
            last=g.iloc[-1]
            if last['trueRUL']<=0: cost+=PR['失效']; failed+=1
            else:
                cost+=PR['失效']; failed+=1      # 跑到观察窗结束仍未维护 -> 记为失效
    cost+=waste_cycles*PR['每剩余周期浪费']
    return dict(策略='AI 预测性维护',参数='提前期 %d'%lead,计划更换=planned,失效=failed,
                浪费周期=int(waste_cycles),总成本=int(cost),单台成本=int(cost/100))
def sim_fixed(iv, tol=3):
    """每 iv 周期做一次计划更换（近似：在 cycle % iv 接近 0 时更换）"""
    cost=0.0; planned=0; failed=0; waste=0
    for u,g in Fte.groupby('unit'):
        g=g.sort_values('cycle'); cyc=g['cycle'].values; rulv=g['trueRUL'].values
        idx=np.where((cyc % iv)<=tol)[0]
        if len(idx)>0:
            i=idx[0]; planned+=1; cost+=PR['计划更换']; waste+=max(0.0,rulv[i]); 
        else:
            failed+=1; cost+=PR['失效']
    cost+=waste*PR['每剩余周期浪费']
    return dict(策略='固定周期',参数='每 %d 周期'%iv,计划更换=planned,失效=failed,
                浪费周期=int(waste),总成本=int(cost),单台成本=int(cost/100))
rows=[dict(策略='跑坏为止',参数='—',计划更换=0,失效=100,浪费周期=0,总成本=100*PR['失效'],单台成本=PR['失效'])]
for iv in [25,40,50,75,100,125]: rows.append(sim_fixed(iv))
for lead in [10,15,20,25,30,40]: rows.append(sim_ai(lead))
R=pd.DataFrame(rows); R['节省%']=(1-R.总成本/R.总成本.iloc[0]).round(3)*100
R.to_csv(os.path.join(OUT,'decision_policy_v4.csv'),index=False,encoding='utf-8-sig')
print(R.to_string(index=False))
best=R.sort_values('总成本').iloc[0]; ai=R[R.策略=='AI 预测性维护'].sort_values('总成本').iloc[0]
fx=R[R.策略=='固定周期'].sort_values('总成本').iloc[0]
print()
print('最优：%s(%s) 单台 %d；AI 最优 单台 %d；固定周期最优 单台 %d' % (best.策略,best.参数,best.单台成本,ai.单台成本,fx.单台成本))
json.dump(dict(成本参数=PR,最优=best.to_dict(),AI最优=ai.to_dict(),固定周期最优=fx.to_dict(),
  口径='逐周期时序仿真：pred<=提前期则计划更换并停止；未更换则该单元记为失效；过度更换按浪费的剩余周期计代价'),
  open(os.path.join(OUT,'decision_policy_v4_summary.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
with open(os.path.join(OUT,'decision_policy_v4.md'),'w',encoding='utf-8') as f:
    f.write('# 决策层 v4：时序维护策略仿真（DSH，2026-09-18）\n\n命令：python src/dsh/2026-09-18_10_policy_v4.py\n\n')
    f.write('口径：逐周期判断，pred RUL <= 提前期即计划更换；未更换的单元记失效；过度更换按浪费剩余周期×单价计代价。\n\n')
    f.write(R.to_markdown(index=False)+'\n\n## 局限\n1. 成本参数为占位值；\n'
            '2. 更换后未继续建模（单次更换即结束），适合作为首次维护决策的对比；\n'
            '3. 提前期未与备件/人员提前期联动。\n')
print('耗时 %.0fs' % (time.time()-t0))
