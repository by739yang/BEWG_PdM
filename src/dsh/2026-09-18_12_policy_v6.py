# -*- coding: utf-8 -*-
"""决策层 v6（DSH）：正确的单窗会计口径
定义：紧急单元 = 观察窗结束时真值 RUL <= 提前期 H（即将失效）
代价：抓住紧急单元 = 计划更换成本；漏掉紧急单元 = 失效成本；动了非紧急单元 = 浪费其剩余寿命
策略：① 不动 ② 固定周期（运行满 iv 周期首次更换）③ 点估计 RUL ④ 分类式预警"""
import numpy as np, pandas as pd, os, json, time
from sklearn.ensemble import GradientBoostingRegressor, GradientBoostingClassifier
t0=time.time(); OUT='results/2026-09-18/dsh'
COLS=['unit','cycle']+['op%d'%i for i in range(1,4)]+['s%d'%i for i in range(1,22)]
SENS=['s2','s3','s4','s7','s8','s11','s12','s13','s15','s17','s20','s21']
CAP=125; W=10; W5=5; H=60
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
m=tr['cycle']>=W; Ftr=feat(tr)
X=Ftr.loc[m,[c for c in Ftr.columns if c not in ('unit','cycle')]].values
y=np.minimum(tr.loc[m,'RUL'].values,CAP)
gb=GradientBoostingRegressor(random_state=0,n_estimators=300,max_depth=3,learning_rate=0.05).fit(X,y)
Fte=feat(te); cols=[c for c in Fte.columns if c not in ('unit','cycle')]
Fte['pred']=np.clip(gb.predict(Fte[cols].values),0,600)
lastmap={u:r for u,r in zip(sorted(te.unit.unique()),te_rul)}
te2=te.assign(trueRUL_end=te['unit'].map(lastmap))
Fte=Fte.merge(te2[['unit','cycle','trueRUL_end']],on=['unit','cycle'],how='left')
Fte['trueRUL']=Fte['trueRUL_end']+(Fte.groupby('unit')['cycle'].transform('max')-Fte['cycle'])
UNITS={u:g.sort_values('cycle') for u,g in Fte.groupby('unit')}
urgent={u:bool(g['trueRUL_end'].iloc[0]<=H) for u,g in UNITS.items()}
print('紧急单元（真值 RUL<=%d）共 %d 台' % (H, sum(urgent.values())))
def evaluate(flagfn, C_fail=50000, C_plan=8000, C_waste=60):
    caught=missed=wasted=0; waste_cycles=0.0
    for u,g in UNITS.items():
        c=flagfn(g)
        if c is not None:
            row=g[g['cycle']==c].iloc[0]
            if urgent[u]: caught+=1
            else: wasted+=1; waste_cycles+=max(0.0,row['trueRUL'])
        else:
            if urgent[u]: missed+=1
    cost=caught*C_plan+missed*C_fail+wasted*(C_plan)+waste_cycles*C_waste
    recall=caught/max(sum(urgent.values()),1)
    return dict(抓住紧急=caught, 漏掉紧急=missed, 动用非紧急=wasted, 浪费周期=int(waste_cycles),
                紧急召回=round(recall,3), 总成本=int(cost), 单台成本=int(cost/100))
def ai_fn(lead): return lambda g:(float(g.loc[g['pred']<=lead,'cycle'].iloc[0]) if (g['pred']<=lead).any() else None)
def fx_fn(iv):
    def f(g):
        s=g[g['cycle']>=iv]; return float(s['cycle'].iloc[0]) if len(s) else None
    return f
clfs={}
for lead in [20,40,60]:
    c=GradientBoostingClassifier(random_state=0,n_estimators=200,max_depth=3,learning_rate=0.05)
    c.fit(X,(np.minimum(tr.loc[m,'RUL'].values,CAP)<lead).astype(int)); clfs[lead]=(c,lead)
PROB={ld:clfs[ld][0].predict_proba(Fte[cols].values)[:,1] for ld in clfs}
Fte['p20']=PROB[20]; Fte['p40']=PROB[40]; Fte['p60']=PROB[60]
UNITS={u:g.sort_values('cycle') for u,g in Fte.groupby('unit')}   # 概率列加入后重建
def cl_fn(col,q): return lambda g:(float(g.loc[g[col]>=q,'cycle'].iloc[0]) if (g[col]>=q).any() else None)
rows=[dict(策略='① 不动',参数='—',**evaluate(lambda g: None))]
for iv in [25,50,75,100,150]: rows.append(dict(策略='② 固定周期',参数='%d 周期'%iv,**evaluate(fx_fn(iv))))
for ld in [10,20,30,40,60]: rows.append(dict(策略='③ 点估计 RUL',参数='提前期 %d'%ld,**evaluate(ai_fn(ld))))
for col,ld in [('p20',20),('p40',40),('p60',60)]:
    for q in [0.2,0.5,0.8]: rows.append(dict(策略='④ 分类式预警',参数='P(RUL<%d)>=%.1f'%(ld,q),**evaluate(cl_fn(col,q))))
R=pd.DataFrame(rows)
R=R[['策略','参数','抓住紧急','漏掉紧急','动用非紧急','浪费周期','紧急召回','总成本','单台成本']]
R.to_csv(os.path.join(OUT,'decision_policy_v6.csv'),index=False,encoding='utf-8-sig')
print(R.to_string(index=False))
best=R.sort_values('总成本').iloc[0]
print()
print('最优：%s（%s）单台 %d；紧急召回 %.0f%%' % (best.策略,best.参数,best.单台成本,best.紧急召回*100))
json.dump(dict(紧急定义='观察窗末真值 RUL <= %d'%H, 紧急台数=int(sum(urgent.values())),
  成本参数=dict(失效=50000,计划=8000,浪费单价=60), 最优=best.to_dict(),
  说明='只有紧急单元必须被抓住；动非紧急单元按浪费其剩余寿命计代价'),
  open(os.path.join(OUT,'decision_policy_v6_summary.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
with open(os.path.join(OUT,'decision_policy_v6.md'),'w',encoding='utf-8') as f:
    f.write('# 决策层 v6：正确的单窗会计口径（DSH，2026-09-18）\n\n命令：python src/dsh/2026-09-18_12_policy_v6.py\n\n')
    f.write('紧急单元定义：观察窗结束时真值 RUL <= %d 周期，共 %d 台。\n\n' % (H,sum(urgent.values())))
    f.write(R.to_markdown(index=False)+'\n\n## 读法\n- 紧急召回 = 抓住的紧急单元 / 全部紧急单元；\n'
            '- 「动用非紧急」是按浪费剩余寿命计代价的误动作；\n'
            '- 成本参数为占位值，比例关系比绝对值可信。\n')
Fte[['unit','cycle','pred','p20','p40','p60','trueRUL','trueRUL_end']].to_csv(
    os.path.join(OUT,'decision_v6_predictions.csv.gz'),compression='gzip',index=False)
print('逐周期预测已落盘')
print('耗时 %.0fs' % (time.time()-t0))
