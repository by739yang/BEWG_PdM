#!/usr/bin/env python3
"""Independent C-MAPSS FD001 RUL baselines: Ridge and Gradient Boosting."""
from __future__ import annotations
import argparse, json, os
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT=Path(__file__).resolve().parents[2]
DEFAULT_CACHE=Path(os.environ.get('BEWG_PDM_CACHE_DIR',Path.home()/'.cache'/'BEWG_PdM'))/'cmapss'
DEFAULT_OUT=ROOT/'results/2026-09-17/codex'
COLS=['unit','cycle',*[f'op{i}' for i in range(1,4)],*[f's{i}' for i in range(1,22)]]
SENSORS=['s2','s3','s4','s7','s8','s9','s11','s12','s13','s14','s15','s17','s20','s21']
CAP=125

def read_data(cache):
 tr=pd.read_csv(cache/'train_FD001.txt',sep=r'\s+',header=None,names=COLS)
 te=pd.read_csv(cache/'test_FD001.txt',sep=r'\s+',header=None,names=COLS)
 truth=pd.read_csv(cache/'RUL_FD001.txt',sep=r'\s+',header=None,names=['RUL'])['RUL'].to_numpy(float)
 if len(tr.columns)!=26 or len(tr)==0 or te['unit'].nunique()!=len(truth): raise RuntimeError('invalid FD001 files')
 return tr,te,truth

def add_features(df, mean, std):
 z=(df[SENSORS]-mean)/std
 out=pd.DataFrame(index=df.index)
 max_cycle=df.groupby('unit')['cycle'].transform('max')
 out['cycle']=df['cycle']; out['cycle_fraction_observed']=df['cycle']/max_cycle
 for c in SENSORS:
  s=z[c]; g=s.groupby(df['unit'],sort=False)
  out[c]=s
  out[c+'_mean10']=g.transform(lambda x:x.rolling(10,min_periods=1).mean())
  out[c+'_std10']=g.transform(lambda x:x.rolling(10,min_periods=2).std()).fillna(0)
  out[c+'_delta5']=s-g.shift(5).fillna(s)
 return out.astype('float32')

def phm08(y,p):
 d=np.asarray(p)-np.asarray(y)
 return float(np.where(d<0,np.exp(-d/13)-1,np.exp(d/10)-1).sum())
def metrics(y,p):
 return {'RMSE':float(np.sqrt(np.mean((np.asarray(p)-np.asarray(y))**2))),'PHM08':phm08(y,p),'MAE':float(np.mean(np.abs(np.asarray(p)-np.asarray(y))))}

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--cache-dir',type=Path,default=DEFAULT_CACHE); ap.add_argument('--output-dir',type=Path,default=DEFAULT_OUT); a=ap.parse_args(); a.output_dir.mkdir(parents=True,exist_ok=True)
 tr,te,truth=read_data(a.cache_dir)
 max_train=tr.groupby('unit')['cycle'].transform('max'); y=np.minimum(max_train-tr['cycle'],CAP).to_numpy(float)
 mu=tr[SENSORS].mean(); sd=tr[SENSORS].std().replace(0,1)
 Xtr=add_features(tr,mu,sd); Xte=add_features(te,mu,sd)
 last=te.groupby('unit',sort=True).tail(1).index; Xend=Xte.loc[last]
 models={'ridge':make_pipeline(StandardScaler(),Ridge(alpha=10.0)),
         'gradient_boosting':GradientBoostingRegressor(n_estimators=250,max_depth=2,learning_rate=.04,loss='huber',random_state=20260917)}
 rows=[]; per=pd.DataFrame({'unit':np.arange(1,len(truth)+1),'true_RUL':truth})
 for name,m in models.items():
  m.fit(Xtr,y); pred=np.clip(m.predict(Xend),0,300); per[name+'_pred_RUL']=pred
  rows.append({'model':name,**metrics(truth,pred),'train_rows':len(Xtr),'test_units':len(truth),'rul_cap':CAP})
 # Transparent non-learning comparator, not counted among the two requested models.
 naive=np.full_like(truth,np.median(y)); rows.append({'model':'constant_train_median',**metrics(truth,naive),'train_rows':len(Xtr),'test_units':len(truth),'rul_cap':CAP})
 pd.DataFrame(rows).to_csv(a.output_dir/'rul_baseline.csv',index=False,encoding='utf-8-sig'); per.to_csv(a.output_dir/'rul_baseline_per_unit.csv',index=False,encoding='utf-8-sig')
 best=min(rows[:2],key=lambda r:r['RMSE'])
 report=['# C-MAPSS FD001 剩余寿命基线（Codex 独立实现）','', '## 数据与任务','',
 f'- 训练：{tr.unit.nunique()} 台发动机、{len(tr):,} 个周期；测试：{te.unit.nunique()} 台发动机，在每台最后观测周期预测剩余寿命。',
 f'- 训练 RUL 使用 `min(max_cycle-cycle, {CAP})` 截断；测试真值来自 `RUL_FD001.txt`。数据只存用户缓存 `{a.cache_dir.resolve()}`，未写入仓库 `data/`。','',
 '## 方法','', '- Ridge：标准化后的线性回归，用作低复杂度基线。','- Gradient Boosting：Huber 损失树提升，用作非线性基线。',
 '- 输入包含观测周期、14 个常用退化传感器的标准化当前值、10 周期滚动均值/标准差与 5 周期变化。标准化参数仅由训练集计算。','',
 '## 指标','', '|模型|RMSE|PHM08|MAE|','|---|---:|---:|---:|']
 for r in rows: report.append(f"|{r['model']}|{r['RMSE']:.3f}|{r['PHM08']:.3f}|{r['MAE']:.3f}|")
 report += ['',f"两种正式基线中，按 RMSE 最好的是 **{best['model']}**：RMSE={best['RMSE']:.3f}，PHM08={best['PHM08']:.3f}。",'',
 '## PHM08 定义','', '误差 `d=预测RUL-真实RUL`；`d<0` 使用 `exp(-d/13)-1`，`d>=0` 使用 `exp(d/10)-1` 后对 100 台求和，因此晚报（高估寿命）惩罚更重。','',
 '## 迁移到水泵/鼓风机时必须改变','',
 '1. 发动机“周期”要替换为累计运行小时、启停次数、负荷积分等设备年龄轴，停机日不能当作退化周期。',
 '2. 传感器需换成振动、温度、电流、压力、流量等，并按工况/维护 epoch 做归一化；C-MAPSS 的稳态单工况假设不能硬套。',
 '3. 真实水务设备通常只有维修记录或右删失数据，需要生存分析、删失损失及维护后状态重置，而不是假设每台都运行到失效。',
 '4. 需按设备留出、按时间回测并给不确定区间；本结果仅证明 RUL 训练—测试—评分链路可复现。','',
 '## 局限','', '- FD001 是仿真、单故障模式、单工况数据；测试只有 100 台。','- 特征与超参数没有独立外部验证，不能据此宣称水泵现场精度。','- PHM08 是总分，受样本数影响，只能在同一测试集上比较。']
 (a.output_dir/'rul_baseline.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
 print(json.dumps(rows,ensure_ascii=False,indent=2))
if __name__=='__main__': raise SystemExit(main())
