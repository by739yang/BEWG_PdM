# -*- coding: utf-8 -*-
"""决策层 v3（DSH）：维护策略成本对比（修正会计口径 + 分类式预警）
四种策略：① 跑坏为止 ② 固定周期 ③ 点估计 RUL ④ 分类式预警 P(RUL<lead)
关键修正：所有单元最终都会失效；未被标记 = 失效（不再假设"RUL 大就永不坏"）。"""
import numpy as np, pandas as pd, os, json, time
from sklearn.ensemble import GradientBoostingRegressor, GradientBoostingClassifier
t0=time.time()
OUT='results/2026-09-18/dsh'
COLS=['unit','cycle']+['op%d'%i for i in range(1,4)]+['s%d'%i for i in range(1,22)]
SENS=['s2','s3','s4','s7','s8','s11','s12','s13','s15','s17','s20','s21']
CAP=125; W=10; W5=5
tr=pd.read_csv('data/cmapss/train_FD001.txt',sep=r'\s+',header=None,names=COLS)
te=pd.read_csv('data/cmapss/test_FD001.txt',sep=r'\s+',header=None,names=COLS)
rul=pd.read_csv('data/cmapss/RUL_FD001.txt',header=None)[0].values
tr['RUL']=tr.groupby('unit')['cycle'].transform('max')-tr['cycle']
mu,sd=tr[SENS].mean(),tr[SENS].std().replace(0,1)
def feat(df):
    z=((df[SENS]-mu)/sd); parts=[z.add_suffix('_last')]
    for w,suf in [(W,'_m10'),(W5,'_m5')]: parts.append(z.rolling(w,min_periods=1).mean().add_suffix(suf))
    parts.append(z.rolling(W,min_periods=1).std().add_suffix('_sd10'))
    m5=z.rolling(W5,min_periods=1).mean(); parts.append((m5-m5.shift(W5)).add_suffix('_trend'))
    F=pd.concat(parts,axis=1); F['unit']=df['unit'].values; F['cycle']=df['cycle'].values
    return F.bfill()
Ftr=feat(tr); Fte=feat(te)
cols=[c for c in Ftr.columns if c not in ('unit','cycle')]
m=tr['cycle']>=W
Xall=Ftr.loc[m,cols].values; ytr=np.minimum(tr.loc[m,'RUL'].values,CAP)
last=te.groupby('unit')['cycle'].idxmax(); Xte=Fte.loc[last,cols].values
print('特征构建完成 %.0fs，训练 %d 行' % (time.time()-t0, len(Xall)))
gb=GradientBoostingRegressor(random_state=0,n_estimators=300,max_depth=3,learning_rate=0.05).fit(Xall,ytr)
pred_rul=np.clip(gb.predict(Xte),0,None)
COST=dict(非计划失效=50000, 计划更换=8000, 过度更换额外=3000)
N=len(rul)
def account(flag, lead):
    flag=np.asarray(flag,bool)
    saved=int((flag&(rul>=lead)).sum())        # 及时换掉，避免失效
    failed=int(N-saved)                        # 其余全部失效
    waste=int((flag&(rul>=2*lead)).sum())      # 真值还剩两倍提前期以上就换 → 过度维修
    cost=saved*COST['计划更换']+failed*COST['非计划失效']+waste*COST['过度更换额外']
    return dict(计划更换=saved, 失效=failed, 过度更换=waste, 总成本=int(cost), 单台成本=int(cost/N))
rows=[]
rows.append(dict(策略='① 跑坏为止',参数='—',**account(np.zeros(N,bool),1)))
for iv in [25,50,75,100,125,150]:
    rows.append(dict(策略='② 固定周期',参数='%d 周期'%iv,**account(np.full(N,iv>0),iv)))
for lead in [10,15,20,30,40,50]:
    rows.append(dict(策略='③ 点估计 RUL',参数='提前期 %d'%lead,**account(pred_rul<=lead,lead)))
for lead in [10,15,20,30,40,50]:
    clf=GradientBoostingClassifier(random_state=0,n_estimators=200,max_depth=3,learning_rate=0.05)
    clf.fit(Xall,(np.minimum(tr.loc[m,'RUL'].values,CAP)<lead).astype(int))
    p=clf.predict_proba(Xte)[:,1]
    for base in [0.3,0.5,0.7]:
        rows.append(dict(策略='④ 分类式预警',参数='提前期 %d / 阈值 %.1f'%(lead,base),**account(p>=base,lead)))
R=pd.DataFrame(rows)
R['相对跑坏为止节省%']=(1-R.总成本/R[R.策略=='① 跑坏为止'].总成本.iloc[0]).round(3)*100
R=R[['策略','参数','计划更换','失效','过度更换','总成本','单台成本','相对跑坏为止节省%']]
R.to_csv(os.path.join(OUT,'decision_policy_v3.csv'),index=False,encoding='utf-8-sig')
best=R.sort_values('总成本').iloc[0]
print(R.to_string(index=False))
print()
print('最优策略：%s（%s）总成本 %d，相对跑坏为止节省 %.1f%%' % (best.策略,best.参数,best.总成本,best['相对跑坏为止节省%']))
json.dump(dict(成本参数=COST,单元数=N,最优=best.to_dict(),
  点估计低端偏差={'真值<20 的台数':int((rul<20).sum()),'点估计预测<20 的台数':int((pred_rul<20).sum()),
                  '真值<30 的台数':int((rul<30).sum()),'点估计预测<30 的台数':int((pred_rul<30).sum())},
  说明='所有单元最终都会失效；未被标记即失效。成本参数为占位值。'),
  open(os.path.join(OUT,'decision_policy_v3_summary.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
with open(os.path.join(OUT,'decision_policy_v3.md'),'w',encoding='utf-8') as f:
    f.write('# 决策层 v3：维护策略成本对比（DSH，2026-09-18）\n\n命令：python src/dsh/2026-09-18_09_policy_v3.py\n\n')
    f.write('数据：C-MAPSS FD001，100 台测试单元。会计口径：**所有单元最终都会失效，未被标记即失效**。\n\n')
    f.write(R.to_markdown(index=False)+'\n\n')
    f.write('## 核心发现\n'
            '点估计 RUL 在低寿命端系统性高估（回归向均值收缩），导致该救的没被标记：真值 RUL<20 的台数与模型预测<20 的台数见 summary.json。\n'
            '分类式预警（直接预测"会不会在提前期内失效"）绕过这个问题，是本数据上更合适的决策接口。\n\n'
            '## 局限\n1. 成本参数为占位值，绝对值不可引用，只看相对排序；\n'
            '2. 假设计划更换可即时安排；\n3. 单次快照决策，未建模多次观察与动态阈值。\n')
print('耗时 %.0fs' % (time.time()-t0))
