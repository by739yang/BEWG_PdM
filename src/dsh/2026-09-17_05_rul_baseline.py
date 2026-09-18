# -*- coding: utf-8 -*-
"""剩余寿命（RUL）基线 v1：C-MAPSS FD001（DSH，2026-09-17，接 Codex 任务）
两个基线：① 健康指数趋势外推  ② 梯度提升回归；指标：RMSE 与 NASA/PHM08 评分"""
import numpy as np, pandas as pd, os, json
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_squared_error
OUT='results/2026-09-17/dsh'; os.makedirs(OUT,exist_ok=True)
COLS=['unit','cycle']+['op%d'%i for i in range(1,4)]+['s%d'%i for i in range(1,22)]
SENS=['s2','s3','s4','s7','s8','s11','s12','s13','s15','s17','s20','s21']   # 文献常用退化敏感通道
CAP=125; WIN=10; TREND=30
tr=pd.read_csv('data/cmapss/train_FD001.txt',sep=r'\s+',header=None,names=COLS)
te=pd.read_csv('data/cmapss/test_FD001.txt',sep=r'\s+',header=None,names=COLS)
rul=pd.read_csv('data/cmapss/RUL_FD001.txt',header=None)[0].values
tr['RUL']=tr.groupby('unit')['cycle'].transform('max')-tr['cycle']
mu,sd=tr[SENS].mean(),tr[SENS].std().replace(0,1)
def z(df): return (df[SENS]-mu)/sd
tr_z=z(tr); te_z=z(te)
tr['HI']=tr_z.mean(1); te['HI']=te_z.mean(1)
# ---- 基线 1：健康指数趋势外推 ----
thr=tr.groupby('unit')['HI'].last().mean()
pred1=[]
for u,g in te.groupby('unit'):
    g=g.tail(TREND); k=np.polyfit(g['cycle'],g['HI'],1)
    slope=k[0]; cur=g['HI'].iloc[-1]; cyc=g['cycle'].iloc[-1]
    est=(thr-cur)/slope if abs(slope)>1e-6 else CAP
    pred1.append((u,max(0,min(300,est))))
pred1=pd.DataFrame(pred1,columns=['unit','pred']).sort_values('unit')['pred'].values
# ---- 基线 2：梯度提升回归（用最近窗口的统计量做特征）----
def build_all(df, zdf):
    rows=[]; keys=[]
    for u,g in df.groupby('unit'):
        zg=zdf.loc[g.index].reset_index(drop=True)
        for i in range(len(g)):
            if i < WIN: continue
            f={}
            for c in SENS:
                w=zg[c].iloc[:i+1]
                f[c+'_last']=w.iloc[-1]; f[c+'_mean']=w.tail(WIN).mean(); f[c+'_std']=w.tail(WIN).std()
                # 精确最小二乘斜率（等价卷积，向量化：用累计和替代逐点 polyfit）
                L=30; seg=w.tail(L).values
                if len(seg)>=L:
                    idx=np.arange(L); Sx=idx.sum(); Sxx=(idx*idx).sum()
                    Sy=seg.sum(); Sxy=(idx*seg).sum()
                    f[c+'_slope']=float((L*Sxy-Sx*Sy)/(L*Sxx-Sx*Sx))
                else: f[c+'_slope']=0.0
            rows.append(f); keys.append((u,i))
    return pd.DataFrame(rows), keys
Xall,keys=build_all(tr,tr_z)
ytr=np.minimum(tr['RUL'].values[[tr.index.get_loc(tr.index[k[0]*0]) if False else 0]],0)  # 占位，下一行覆盖
lbl_map={(u,i):min(int(max(tr[tr.unit==u]['cycle'])-tr[tr.unit==u]['cycle'].iloc[i]),CAP) for u,i in keys}
ytr=np.array([lbl_map[k] for k in keys])
Xte,keys_te=build_all(te,te_z)
last_idx={u:i for (u,i) in keys_te}
keep=[k for k in keys_te if k[1]==max(i for (uu,i) in keys_te if uu==k[0])]
Xte_final=Xte.loc[[keys_te.index(k) for k in keep]].reset_index(drop=True)
assert len(Xte_final)==te.unit.nunique(), (len(Xte_final), te.unit.nunique())
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
models={'梯度提升回归':GradientBoostingRegressor(random_state=0,n_estimators=300,max_depth=3,learning_rate=0.05),
        '随机森林':RandomForestRegressor(n_estimators=200,random_state=0,n_jobs=-1),
        '岭回归':make_pipeline(StandardScaler(),Ridge(alpha=10.0))}
preds={}
for nm,mdl in models.items():
    mdl.fit(Xall,ytr); preds[nm]=np.clip(mdl.predict(Xte_final),0,300)
pred2=preds['梯度提升回归']
def phm08(d):
    d=np.asarray(d); return float(np.sum(np.where(d<0,np.exp(-d/13)-1,np.exp(d/10)-1)))
rows=[]
model_rows=[('基线2 %s'%nm,p) for nm,p in preds.items()]
for name,pred in [('基线1 健康指数趋势外推',pred1)]+model_rows+[
                  ('对照 恒报 125',np.full(len(rul),125.0)),('对照 恒报真实均值',np.full(len(rul),rul.mean()))]:
    d=pred-rul
    rows.append(dict(模型=name,RMSE=round(float(np.sqrt(mean_squared_error(rul,pred))),2),
                     PHM08得分=round(phm08(d),0), 平均绝对误差=round(float(np.abs(d).mean()),2),
                     提前预测占比=round(float((d<0).mean()),2)))
R=pd.DataFrame(rows)
R.to_csv(os.path.join(OUT,'rul_baseline_metrics.csv'),index=False,encoding='utf-8-sig')
pd.DataFrame({'unit':sorted(te.unit.unique()),'true_RUL':rul,'pred_trend':pred1.round(1),'pred_gb':pred2.round(1)}).to_csv(
    os.path.join(OUT,'rul_baseline_per_unit.csv'),index=False,encoding='utf-8-sig')
json.dump(dict(dataset='C-MAPSS FD001', source='github.com/edwardzjl/CMAPSSData (NASA PCoE 镜像)',
   train_units=int(tr.unit.nunique()), test_units=int(te.unit.nunique()), cap=CAP, window=WIN,
   health_index_threshold=round(float(thr),3), results=R.to_dict('records')),
   open(os.path.join(OUT,'rul_baseline_summary.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
with open(os.path.join(OUT,'rul_baseline.md'),'w',encoding='utf-8') as f:
    f.write('# 剩余寿命基线 v1：C-MAPSS FD001（DSH）\n\n命令：python src/dsh/2026-09-17_05_rul_baseline.py\n\n')
    f.write('数据：100 台训练 / 100 台测试，训练标签按 125 周期分段线性截断，测试用官方 RUL_FD001 真值。\n\n')
    f.write(R.to_markdown(index=False)+'\n\n')
    f.write('评分：RMSE（越小越好）与 NASA/PHM08 评分（对"晚报"罚得更重）。对照行说明任务本身的难度。\n\n')
    f.write('## 局限\n1. 只做了 FD001（单工况、单故障模式），未做 FD002/003/004；\n'
            '2. 未做超参搜索与特征筛选；\n'
            '3. 未做单元级分组交叉验证（当前用全部训练单元训练、测试集评估，属标准协议）；\n'
            '4. 涡扇发动机与水泵/鼓风机的退化机理不同，不能直接外推。\n')
print(R.to_markdown(index=False))
