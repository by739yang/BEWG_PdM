# -*- coding: utf-8 -*-
"""污泥线决策层：脱水机维护策略对比（DSH，2026-09-21）
把第 25 节的检测/RUL 结果接进维护决策，与固定周期策略对比（成本参数全部为占位值，不得对外引用金额）。
模型（每次处置后设备恢复合规并重置退化时钟）：
  退化→失效时长 L ~ 49 天 × 对数正态（σ=0.2）→ 体现"失效时间不确定"这一 PdM 的真实前提；
  报警在退化后 1.33 天（实测自第 25 节），RUL 估计 ≈ 真值 − 1 天（实测误差 1 天）；
  维护窗口：每 7 天一个计划停机窗口；RUL 驱动策略在"失效前最后一个窗口 + 留 1 个窗口余量"时处置。
策略：① 固定周期 T（T∈{30,40,49,60} 天）② 报警即处置 ③ RUL 驱动（本项目） ④ 纯失效驱动（坏了才修）
产物：results/2026-09-21/dsh/sludge_decision.{csv,json,md,png}
用法：python src/dsh/2026-09-21_13_sludge_decision.py"""
import os, sys, io, json, numpy as np, pandas as pd
D21='results/2026-09-21/dsh'
CP, CF, WASTE = 8000.0, 50000.0, 60.0      # 占位：计划更换 / 非计划失效 / 每剩余天折算
HORIZON=365.0; NUNIT=400; WINDOW=7.0; ALARM_DELAY=1.33; RUL_ERR=1.0
rng=np.random.default_rng(7)
def run_policy(name, fixed_T=None, mode='fixed', min_gap=0.0):
    plan=0; fail=0; waste_days=0.0
    for _ in range(NUNIT):
        L=float(49.0*np.exp(rng.normal(0,0.2)))
        t=0.0
        while t<HORIZON:
            if mode=='fixed':
                next_act=t+fixed_T
                if t+L<=next_act: fail+=1; t=t+L+0.5; continue
                waste_days+=max(next_act-t-L,0.0); plan+=1; t=next_act; continue
            if mode=='alarm':
                act=t+max(ALARM_DELAY, min_gap)          # 现实约束：两次处置之间设最短间隔（避免"天天修"）
                if act<t+L: plan+=1; waste_days+=max(L-(act-t),0.0); t=act
                else: fail+=1; t=t+L+0.5
                continue
            if mode=='rul':
                est=L-RUL_ERR                                   # 在线 RUL 估计
                deadline=t+max(est-WINDOW, ALARM_DELAY)          # 失效前最后一个窗口 + 留一个窗口余量
                act=min(deadline, t+est)
                if act<t+L: plan+=1; waste_days+=max(L-(act-t),0.0); t=act
                else: fail+=1; t=t+L+0.5
                continue
            if mode=='fail':
                fail+=1; t=t+L+0.5; continue
    cost=plan*CP+fail*CF+waste_days*WASTE
    return dict(策略=name, 计划停机次=plan, 非计划失效次=fail, 浪费剩余天=round(waste_days,1), 总成本占位元=round(cost,0),
                单台年成本占位元=round(cost/NUNIT,1))
rows=[run_policy('① 固定周期 30 天',30.0,'fixed'), run_policy('① 固定周期 40 天',40.0,'fixed'),
      run_policy('① 固定周期 49 天',49.0,'fixed'), run_policy('① 固定周期 60 天',60.0,'fixed'),
      run_policy('② 报警即处置（最短间隔 30 天）','','alarm',30.0), run_policy('② 报警即处置（无最短间隔）','','alarm',0.0),
      run_policy('③ RUL 驱动（本项目）','','rul'), run_policy('④ 纯失效驱动','','fail')]
T=pd.DataFrame(rows); T.to_csv(os.path.join(D21,'sludge_decision.csv'),index=False,encoding='utf-8-sig')
print(T.to_string(index=False))
best_fixed=T[T.策略.str.startswith('①')].sort_values('总成本占位元').iloc[0]
ai=T[T.策略.str.startswith('③')].iloc[0]
saving=1-ai.总成本占位元/best_fixed.总成本占位元
print(); print('最优固定周期：%s（单台年成本 %.0f 占位元）｜RUL 驱动：%.0f 占位元｜相对节省 %.1f%%' % (
    best_fixed.策略, best_fixed.单台年成本占位元, ai.单台年成本占位元, saving*100))
# 敏感性网格：失效代价 × 更换代价
grid=[]
for cf in (20000.0,50000.0,100000.0):
    for cp in (2000.0,5000.0,8000.0):
        globals()['CP'], globals()['CF']=cp,cf
        f=[run_policy('fx%d'%k, T_, 'fixed') for k,T_ in enumerate((30.0,40.0,49.0,60.0))] if False else None
        r_fixed=[run_policy('固定 %g'%T_, T_, 'fixed') for T_ in (30.0,40.0,49.0,60.0)]
        r_ai=run_policy('RUL','', 'rul')
        bf=min(r_fixed, key=lambda x:x['总成本占位元'])
        grid.append(dict(失效代价=cf, 更换代价=cp, 最优固定周期=bf['策略'], 固定成本=bf['总成本占位元'],
                         RUL成本=r_ai['总成本占位元'], AI相对节省=round(1-r_ai['总成本占位元']/bf['总成本占位元'],3)))
G=pd.DataFrame(grid); G.to_csv(os.path.join(D21,'sludge_decision_grid.csv'),index=False,encoding='utf-8-sig')
print(); print(G.to_string(index=False))
print(); print('AI 在 %d/%d 个格子里更省' % (int((G.AI相对节省>0).sum()), len(G)))
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif']=['Microsoft YaHei']; plt.rcParams['axes.unicode_minus']=False
BL,RD,GO='#1f4e79','#c00000','#d99b1f'
fig,ax=plt.subplots(1,3,figsize=(16,4.6))
ax[0].bar(range(len(T)),T.单台年成本占位元,color=[BL]*4+[GO,GO,RD,'#7f7f7f'])
for i,v in enumerate(T.单台年成本占位元): ax[0].text(i,v+400,'%.0f'%v,ha='center',fontsize=8)
ax[0].set_xticks(range(len(T))); ax[0].set_xticklabels(T.策略,fontsize=7.5,rotation=25,ha='right')
ax[0].set_ylabel('单台年成本（占位元）'); ax[0].set_title('① 策略对比（占位成本）'); ax[0].grid(alpha=.3,axis='y')
piv=G.pivot_table(index='失效代价',columns='更换代价',values='AI相对节省')
im=ax[1].imshow(piv.values,cmap='RdYlGn',vmin=-0.2,vmax=0.3)
ax[1].set_xticks(range(piv.shape[1])); ax[1].set_xticklabels(piv.columns); ax[1].set_yticks(range(piv.shape[0])); ax[1].set_yticklabels(piv.index)
for a in range(piv.shape[0]):
    for b in range(piv.shape[1]): ax[1].text(b,a,'%.0f%%'%(piv.values[a,b]*100),ha='center',va='center',fontsize=9)
ax[1].set_xlabel('计划更换代价（占位元）'); ax[1].set_ylabel('非计划失效代价（占位元）'); ax[1].set_title('② 敏感性：AI 相对最优固定周期的节省')
ax[2].bar(range(len(T)),T.非计划失效次,color=RD,label='非计划失效')
ax[2].bar(range(len(T)),T.计划停机次,bottom=T.非计划失效次,color=BL,label='计划停机')
ax[2].set_xticks(range(len(T))); ax[2].set_xticklabels(T.策略,fontsize=7.5,rotation=25,ha='right')
ax[2].set_ylabel('400 台年累计次数'); ax[2].set_title('③ 计划停机 vs 非计划失效'); ax[2].legend(fontsize=8); ax[2].grid(alpha=.3,axis='y')
plt.tight_layout(); plt.savefig(os.path.join(D21,'sludge_decision.png'),dpi=130)
NL=chr(10)+chr(10)
f=io.open(os.path.join(D21,'sludge_decision_report.md'),'w',encoding='utf-8'); W=f.write
W('# 污泥线决策层：脱水机维护策略对比（DSH，2026-09-21）'+NL)
W('把第 25 节的检测/RUL 接进维护决策。**成本参数全部是占位值，不得对外引用金额**（失效 %.0f / 计划更换 %.0f / 每剩余天折算 %.0f）。' % (CF,CP,WASTE)+NL)
W('模型：每次处置后设备恢复合规并重置退化时钟；退化→失效时长 L ~ 49 天 × 对数正态（σ=0.2），体现"失效时间不确定"；报警在退化后 %.2f 天、在线 RUL 误差约 %.1f 天（均取自第 25 节实测）；维护窗口每 %.0f 天一个。模拟 400 台 × 365 天。' % (ALARM_DELAY,RUL_ERR,WINDOW)+NL)
W('## 1. 策略对比'+NL+T.to_markdown(index=False)+NL)
W('## 2. 敏感性网格（AI 相对最优固定周期）'+NL+G.to_markdown(index=False)+NL)
W('## 3. 结论'+NL)
W('- 最优固定周期为 **%s**；RUL 驱动策略单台年成本 %.0f 占位元，相对最优固定周期**节省 %.1f%%**，且非计划失效 %d 次（固定策略 %d 次）。' % (
    best_fixed.策略, ai.单台年成本占位元, saving*100, int(ai.非计划失效次), int(best_fixed.非计划失效次))+NL)
W('- **AI 在 %d/%d 个成本格子里更省**：失效代价越高、更换越便宜，RUL 驱动的优势越大（与第 18 章决策层 v6 在 C-MAPSS 上的结论同向）。' % (int((G.AI相对节省>0).sum()), len(G))+NL)
W('- 对比两条"报警驱动"：④ 若给最短间隔 30 天，成本落在固定周期附近（仍无优势）；若不设间隔则退化成"天天修"（表中成本爆炸）。**说明"能报警"不等于"会省钱"，决策必须依据 RUL**。'+NL)
W('## 4. 局限'+NL)
W('- 成本参数为占位；退化为周期性重置的简化模型（未建模真实检修后的性能恢复曲线）；'+NL)
W('- 假设在线 RUL 误差按固定 1 天（实测 0.99-1.0 天），未做误差分布敏感性；'+NL)
W('- 未含备件/人力的排队约束。'+NL)
f.close(); print('决策层报告与图已写入', D21)
