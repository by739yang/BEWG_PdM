# -*- coding: utf-8 -*-
"""决策层 v5（DSH）：维护策略 + 成本参数敏感性网格
修正：固定周期改为"运行满 iv 周期后首次更换"；AI 策略为"pred<=提前期即更换"。
敏感性：失效代价与更换代价之比决定策略优劣——这正是需要企业数据标定的量。"""
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
m=tr['cycle']>=W
X=Ftr=feat(tr); X=X.loc[m,[c for c in X.columns if c not in ('unit','cycle')]].values
y=np.minimum(tr.loc[m,'RUL'].values,CAP)
gb=GradientBoostingRegressor(random_state=0,n_estimators=300,max_depth=3,learning_rate=0.05).fit(X,y)
Fte=feat(te); cols=[c for c in Fte.columns if c not in ('unit','cycle')]
Fte['pred']=np.clip(gb.predict(Fte[cols].values),0,600)
lastmap={u:r for u,r in zip(sorted(te.unit.unique()),te_rul)}
Fte=Fte.merge(te[['unit','cycle']].assign(trueRUL=te['unit'].map(lastmap)+ (te.groupby('unit')['cycle'].transform('max')-te['cycle'])),on=['unit','cycle'],how='left')
UNITS={u:g.sort_values('cycle') for u,g in Fte.groupby('unit')}
def cost_of(act_fn, C_fail, C_plan, C_waste):
    """act_fn(g, C)= 要更换的周期；None 表示不更换（失效）"""
    total=0.0; planned=0; failed=0; waste=0.0
    for u,g in UNITS.items():
        c=act_fn(g)
        if c is None: total+=C_fail; failed+=1
        else:
            row=g[g['cycle']==c].iloc[0]
            total+=C_plan; planned+=1; waste+=max(0.0,row['trueRUL'])
    total+=waste*C_waste
    return dict(计划更换=planned,失效=failed,浪费周期=int(waste),总成本=int(total),单台成本=int(total/100))
def ai_fn(lead):
    return lambda g: (float(g.loc[g['pred']<=lead,'cycle'].iloc[0]) if (g['pred']<=lead).any() else None)
def fx_fn(iv):
    def f(g):
        s=g[g['cycle']>=iv]
        return float(s['cycle'].iloc[0]) if len(s) else None
    return f
BASE=dict(失效=50000,计划=8000,浪费=60)
rows=[]
for lead in [10,20,30,40,60]: rows.append(dict(策略='AI 预测',参数='提前期 %d'%lead, **cost_of(ai_fn(lead),**{'C_fail':BASE['失效'],'C_plan':BASE['计划'],'C_waste':BASE['浪费']})))
for iv in [25,50,75,100,150]: rows.append(dict(策略='固定周期',参数='%d 周期'%iv, **cost_of(fx_fn(iv),**{'C_fail':BASE['失效'],'C_plan':BASE['计划'],'C_waste':BASE['浪费']})))
row_rtf=dict(策略='跑坏为止',参数='—',计划更换=0,失效=100,浪费周期=0,总成本=100*BASE['失效'],单台成本=BASE['失效'])
R=pd.DataFrame([row_rtf]+rows); R['节省%']=(1-R.总成本/R.总成本.iloc[0]).round(3)*100
R.to_csv(os.path.join(OUT,'decision_policy_v5.csv'),index=False,encoding='utf-8-sig')
print('=== 基准参数（失效 5 万 / 更换 8 千 / 浪费 60 元每周期）===')
print(R.to_string(index=False))
# 敏感性网格
grid=[]
for cf in [20000,50000,100000,150000]:
    for cw in [20,60,120]:
        res={}
        res['跑坏为止']=cost_of(lambda g: None, cf, BASE['计划'], cw)['单台成本']
        res['固定周期最优']=min(cost_of(fx_fn(iv), cf, BASE['计划'], cw)['单台成本'] for iv in [25,50,75,100,150])
        res['AI 最优']=min(cost_of(ai_fn(ld), cf, BASE['计划'], cw)['单台成本'] for ld in [10,20,30,40,60])
        best=min(res,key=res.get)
        grid.append(dict(失效代价=cf,浪费单价=cw,跑坏为止=res['跑坏为止'],固定周期最优=res['固定周期最优'],
                          AI最优=res['AI 最优'],最优策略=best,
                          AI相对固定周期节省=round((res['固定周期最优']-res['AI 最优'])/res['固定周期最优'],3)))
G=pd.DataFrame(grid); G.to_csv(os.path.join(OUT,'decision_sensitivity_grid.csv'),index=False,encoding='utf-8-sig')
print()
print('=== 敏感性网格（AI 最优 vs 固定周期最优）===')
print(G.to_string(index=False))
json.dump(dict(基准参数=BASE,基准表=R.to_dict('records'),网格=G.to_dict('records'),
  结论='策略优劣由 失效代价/更换代价 之比决定；参数为占位值，必须用企业数据标定后才能引用金额'),
  open(os.path.join(OUT,'decision_policy_v5_summary.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
print('耗时 %.0fs' % (time.time()-t0))
