# -*- coding: utf-8 -*-
"""决策层：成本参数敏感性网格（v6 会计口径）——回答"什么数据最该向企业要"
结论形态：AI 策略占优 当且仅当 失效代价/计划更换代价 之比超过某阈值。"""
import pandas as pd, numpy as np, json, os
OUT='results/2026-09-18/dsh'
F=pd.read_csv(os.path.join(OUT,'decision_v6_predictions.csv.gz'))
H=60
UNITS={u:g.sort_values('cycle') for u,g in F.groupby('unit')}
urgent={u:bool(g['trueRUL_end'].iloc[0]<=H) for u,g in UNITS.items()}
NURG=sum(urgent.values())
def costs(flagfn, cf, cp, cw):
    caught=missed=wasted=0; wc=0.0
    for u,g in UNITS.items():
        c=flagfn(g)
        if c is not None:
            if urgent[u]: caught+=1
            else:
                wasted+=1; wc+=float(g.loc[g['cycle']==c,'trueRUL'].iloc[0])
        elif urgent[u]: missed+=1
    return caught*0+missed*cf + (caught+wasted)*cp + wc*cw
def ai(lead): return lambda g:(float(g.loc[g['pred']<=lead,'cycle'].iloc[0]) if (g['pred']<=lead).any() else None)
def clf(col,q): return lambda g:(float(g.loc[g[col]>=q,'cycle'].iloc[0]) if (g[col]>=q).any() else None)
def fx(iv):
    def f(g):
        s=g[g['cycle']>=iv]; return float(s['cycle'].iloc[0]) if len(s) else None
    return f
AI=[('RUL<=%d'%ld, ai(ld)) for ld in [20,30,40,60]]+[('P20>=%.1f'%q, clf('p20',q)) for q in [0.2,0.5]]+[('P40>=%.1f'%q, clf('p40',q)) for q in [0.2,0.5,0.8]]+[('P60>=%.1f'%q, clf('p60',q)) for q in [0.5,0.8]]
FX=[('%d 周期'%iv, fx(iv)) for iv in [50,75,100,125,150]]
rows=[]
for cf in [20000,35000,50000,80000,120000]:
    for cp in [4000,8000,16000]:
        for cw in [60]:
            base=NURG*cf
            best_ai=min((costs(fn,cf,cp,cw),name) for name,fn in AI)
            best_fx=min((costs(fn,cf,cp,cw),name) for name,fn in FX)
            win='AI' if best_ai[0]<best_fx[0] else '固定周期'
            rows.append(dict(失效代价=cf,更换代价=cp,浪费单价=cw,比值=round(cf/cp,1),
                不动成本=int(base),最优AI成本=int(best_ai[0]),最优AI参数=best_ai[1],
                最优固定周期成本=int(best_fx[0]),最优固定参数=best_fx[1],
                获胜方=win, AI相对固定节省=round((best_fx[0]-best_ai[0])/best_fx[0],3)))
G=pd.DataFrame(rows)
G.to_csv(os.path.join(OUT,'decision_sensitivity_v6.csv'),index=False,encoding='utf-8-sig')
print(G.to_string(index=False))
sw=G[G.获胜方=='AI'].比值.min() if (G.获胜方=='AI').any() else None
print()
print('AI 占优的比值(失效/更换)下限：', sw if sw is not None else '在本网格内 AI 从未占优')
print('固定周期占优的比值上限：', G[G.获胜方=='固定周期'].比值.max() if (G.获胜方=='固定周期').any() else '—')
json.dump(dict(网格=G.to_dict('records'), AI占优比值下限=sw,
  说明='AI 策略与固定周期策略的成本差由 失效代价/更换代价 之比驱动；该比值是必须向企业要的标定数据'),
  open(os.path.join(OUT,'decision_sensitivity_v6_summary.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
