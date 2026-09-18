# -*- coding: utf-8 -*-
"""决策层 v2（DSH）：用已验证的 C-MAPSS RUL 模型做维护策略对比
三个策略：① 跑坏为止 ② 固定周期更换 ③ AI 预测性维护（预测 RUL <= 提前期则计划更换）
成本参数为占位值，必须用企业数据标定；本脚本给结构与敏感性。"""
import numpy as np, pandas as pd, os, json
OUT='results/2026-09-18/dsh'
P=pd.read_csv('results/2026-09-17/dsh/rul_baseline_per_unit.csv')
print('逐单元预测列：', list(P.columns))
pred_col=[c for c in P.columns if c.startswith('pred_') and 'trend' not in c][0]
true=P['true_RUL'].values; pred=np.clip(P[pred_col].values,0,None)
print('使用预测列 %s ｜ 真值均值 %.1f ｜ 预测均值 %.1f' % (pred_col, true.mean(), pred.mean()))
COST=dict(非计划停机损失=50000, 计划更换成本=8000, 提前更换额外损失=3000)   # 占位值
N=len(true)
def simulate(lead):
    """AI 策略：预测 RUL <= lead 时安排计划更换（假设能在 lead 周期内完成）"""
    planned=(pred<=lead)
    prevented=int(((true>=lead)&planned).sum())      # 真值够、预测也报警 → 成功预防
    missed=int(((true<lead)&(~planned)).sum())       # 真值不够、没报警 → 跑到坏
    extra=int(((true>=lead*2)&planned).sum())        # 真值还剩很多就换 → 过度维修
    cost=prevented*COST['计划更换成本']+missed*COST['非计划停机损失']+extra*COST['提前更换额外损失']
    return dict(策略='AI 预测性维护', 提前期=lead, 计划更换=prevented, 未预防失效=missed,
                过度维修=extra, 总成本=cost, 单单元成本=round(cost/N,0))
def fixed(interval):
    planned=(true>interval)   # 固定周期：到了周期还剩寿命就计划换；否则跑到坏
    cost=planned.sum()*COST['计划更换成本']+(~planned).sum()*COST['非计划停机损失']
    return dict(策略='固定周期更换', 提前期=interval, 计划更换=int(planned.sum()),
                未预防失效=int((~planned).sum()), 过度维修=int(planned.sum()),
                总成本=cost, 单单元成本=round(cost/N,0))
rows=[dict(策略='跑坏为止', 提前期=None, 计划更换=0, 未预防失效=N, 过度维修=0,
           总成本=N*COST['非计划停机损失'], 单单元成本=COST['非计划停机损失'])]
for iv in [50,75,100,125,150,200]: rows.append(fixed(iv))
for lead in [5,10,15,20,30,40,50]: rows.append(simulate(lead))
R=pd.DataFrame(rows)
R.to_csv(os.path.join(OUT,'decision_policy_compare.csv'),index=False,encoding='utf-8-sig')
best_ai=R[R.策略=='AI 预测性维护'].sort_values('总成本').iloc[0]
best_fx=R[R.策略=='固定周期更换'].sort_values('总成本').iloc[0]
rtf=R[R.策略=='跑坏为止'].iloc[0]
summary=dict(单元数=N, 成本参数=COST,
    最优AI=best_ai.to_dict(), 最优固定周期=best_fx.to_dict(), 跑坏为止=rtf.to_dict(),
    相对跑坏为止节省=(rtf.总成本-best_ai.总成本)/rtf.总成本,
    相对最优固定周期节省=(best_fx.总成本-best_ai.总成本)/best_fx.总成本,
    说明='成本参数为占位值；AI 策略假设被发现后有足够时间完成计划更换，且不含预测误差造成的二次代价')
json.dump(summary,open(os.path.join(OUT,'decision_policy_summary.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2,default=str)
with open(os.path.join(OUT,'decision_policy.md'),'w',encoding='utf-8') as f:
    f.write('# 决策层 v2：维护策略成本对比（DSH，2026-09-18）\n\n命令：python src/dsh/2026-09-18_08_policy_compare.py\n\n')
    f.write('数据：C-MAPSS FD001 的 100 台测试单元，RUL 用已验证的梯度提升模型预测（RMSE 19.73）。\n\n')
    f.write(R.to_markdown(index=False)+'\n\n')
    f.write('## 怎么读\n- 「未预防失效」是跑到坏的台数，「过度维修」是还剩很多寿命就换的台数；\n'
            '- AI 策略的提前期是唯一可调参数，本表把 5~50 周期都扫了一遍；\n'
            '- **成本参数全是占位值**，比例关系比绝对值更可信；换企业真实参数后结论方向通常不变，幅度会变。\n\n')
    f.write('## 局限\n1. 未计入预测误差的二次代价（预测偏高导致漏修）；\n'
            '2. 假设计划更换可即时安排，未建模备件与人员约束；\n'
            '3. 涡扇发动机的失效成本结构与水泵不同，参数不可直接搬用。\n')
print(R.to_markdown(index=False))
print()
print('相对跑坏为止节省 %.1f%%；相对最优固定周期节省 %.1f%%' % (summary['相对跑坏为止节省']*100, summary['相对最优固定周期节省']*100))
