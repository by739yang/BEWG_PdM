import io, os
NL=chr(10)
src=io.open('src/dsh/2026-09-19_03_ablation_robustness.py',encoding='utf-8').read().split(NL)
pre=src[:87]   # 1..87 行：数据、估计器、z_table、打分、事件机
pre[2]='"""检测模块消融 —— 两套公平阈值口径重跑（DSH，2026-09-21）'
pre[3]='背景：原口径让所有变体共用硬编码阈值 2.395，Codex Q6/Q11 指出这不公平（各变体分数尺度不同）。'
pre[4]='本脚本复用同一套估计/事件机/命中判据，只改阈值来源，跑三套口径：'
pre[5]='  ① 各自重新标定 q0.995（各变体用自己的无标签标定期分数）'
pre[6]='  ② 共用同一阈值（用 V0 基线自标定的绝对值，无标签）'
pre[7]='  ③ 原口径：硬编码 2.395（保留作对照）"""'
body = '''# ---- 变体分数（与 2026-09-19 版完全相同） ----
variants=[]
Z0=z_table('wf',allc,True); v0=score_top3(Z0).reindex(J.ts).values
variants.append(('V0 基线（walk-forward + 工况条件化 + top3-RMS）', v0))
variants.append(('V1 聚合改 max|z|（单信号）', score_max(Z0).reindex(J.ts).values))
Zs=z_table('static',allc,False); variants.append(('V2 静态标准化（全期一次估计）', score_top3(Zs).reindex(J.ts).values))
Zn=z_table('wf',allc,False); variants.append(('V3 不做工况条件化', score_top3(Zn).reindex(J.ts).values))
Zr=z_table('wf',RAW,True); variants.append(('V4 去掉派生特征', score_top3(Zr).reindex(J.ts).values))
rng=np.random.default_rng(0)
for frac,tag in [(0.10,'V5 随机缺失 10% 分钟'),(0.30,'V6 随机缺失 30% 分钟')]:
    s_=np.asarray(v0,dtype=float).copy(); idx=rng.choice(len(s_),int(len(s_)*frac),replace=False); s_[idx]=0.0
    variants.append((tag,s_))
Zs2=z_table('static',allc,False).copy(); Zs2['Oil_temperature']=0.0
variants.append(('V7 温度通道卡死（该列置零）', score_top3(Zs2).reindex(J.ts).values))

# ---- 无标签标定期：与冻结脚本一致（首个故障窗前 12 小时、再去掉前 12 小时） ----
def cal_series(score):
    s=pd.Series(np.asarray(score,dtype=float), index=J.ts)
    return s.loc[:str(fw[0][0]-pd.Timedelta(hours=12))].iloc[12*60:]

thr_own={nm: float(cal_series(sc).quantile(0.995)) for nm,sc in variants}
thr_shared=thr_own[variants[0][0]]
print('V0 自标定阈值 = %.3f（共用口径用它）｜原硬编码 = 2.395' % thr_shared)

REGIMES=[('各自重新标定 q0.995',None),('共用同一阈值（V0 自标定）',thr_shared),('原口径：硬编码 2.395',2.395)]
rows=[]
for nm,sc in variants:
    for rname,fixed in REGIMES:
        thr=thr_own[nm] if fixed is None else fixed
        r=ev_metrics(sc, thr); r.update(变体=nm, 口径=rname, 阈值=round(float(thr),3)); rows.append(r)
T=pd.DataFrame(rows)[['变体','口径','阈值','告警数','timely','late','miss','误报','误报率','TIA_H']]
T.to_csv(os.path.join(OUT,'ablation_two_regimes.csv'),index=False,encoding='utf-8-sig')
pv_t=T.pivot_table(index='变体',columns='口径',values='timely')
pv_f=T.pivot_table(index='变体',columns='口径',values='误报')
pv_thr=T.pivot_table(index='变体',columns='口径',values='阈值')
print(); print('=== timely 召回（同一变体在三种口径下）==='); print(pv_t.to_markdown())
print(); print('=== 误报事件数 ===');  print(pv_f.to_markdown())
print(); print('=== 各变体自标定阈值 vs 共用阈值 ==='); print(pv_thr.to_markdown())

# ---- 三条结论的判定 ----
def g(nm,regime,col):
    s=T[(T.变体==nm)&(T.口径==regime)][col]
    return None if not len(s) else s.iloc[0]
CLAIMS=[('V3 不做工况条件化','不做工况条件化 → timely 归零'),
        ('V4 去掉派生特征','去掉派生特征 → timely 归零'),
        ('V1 聚合改 max|z|（单信号）','max|z| 聚合 → 召回更差、误报更高')]
V=[]
for nm,claim in CLAIMS:
    rec=dict(变体=nm, 结论=claim)
    for rname,_ in REGIMES:
        rec[rname+'_timely']=g(nm,rname,'timely'); rec[rname+'_误报']=g(nm,rname,'误报')
    V.append(rec)
Vv=pd.DataFrame(V); Vv.to_csv(os.path.join(OUT,'ablation_two_regimes_verdicts.csv'),index=False,encoding='utf-8-sig')
print(); print(Vv.to_markdown(index=False))

import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif']=['Microsoft YaHei']; plt.rcParams['axes.unicode_minus']=False
BL,RD,GO='#1f4e79','#c00000','#d99b1f'
fig,ax=plt.subplots(1,2,figsize=(15,5))
names=pv_t.index.tolist(); x=np.arange(len(names)); wd=0.26
for i,(rname,_) in enumerate(REGIMES):
    ax[0].bar(x+(i-1)*wd, pv_t[rname].values, wd, label=rname)
    ax[1].bar(x+(i-1)*wd, pv_f[rname].values, wd, label=rname)
for a,t in [(ax[0],'timely 命中官方故障数（满分 4）'),(ax[1],'误报事件数（越低越好）')]:
    a.set_xticks(x); a.set_xticklabels(names,fontsize=7.5,rotation=25,ha='right'); a.set_title(t); a.grid(alpha=.3,axis='y'); a.legend(fontsize=8)
plt.tight_layout(); plt.savefig(os.path.join(OUT,'ablation_two_regimes.png'),dpi=130)

NL2=chr(10)+chr(10)
f=io.open(os.path.join(OUT,'ablation_two_regimes_report.md'),'w',encoding='utf-8'); W=f.write
W('# 检测消融：两套公平阈值口径重跑（DSH，2026-09-21）'+NL2)
W('**为什么要重跑**：原消融（2026-09-19）让所有变体共用硬编码阈值 2.395，而各变体分数的尺度不同 —— Codex 在 Q6 用自有链路给出反例，Q11 又在它自己的链路上跑了两套口径。本脚本在**本项目链路**上补做同样的两套口径。'+NL2)
W('**口径定义**：'+NL)
W('- 无标签标定期与冻结脚本一致：首个官方故障窗之前 12 小时，再去掉前 12 小时的预热；'+NL)
W('- ① 各自重新标定：每个变体用自己标定期的 0.995 分位作为阈值；'+NL)
W('- ② 共用同一阈值：用 V0 基线自标定的阈值（%.3f）应用到所有变体；' % thr_shared+NL)
W('- ③ 原口径：硬编码 2.395（保留作对照）。事件机（5/10/0.8x/30）与三态命中判据不变。'+NL2)
W('## 1. timely 召回'+NL2+pv_t.to_markdown()+NL2)
W('## 2. 误报事件数'+NL2+pv_f.to_markdown()+NL2)
W('## 3. 各变体自标定阈值'+NL2+pv_thr.to_markdown()+NL2)
W('## 4. 三条结论的判定'+NL2+Vv.to_markdown(index=False)+NL2)
W('**读法**：同一条结论在三种口径下若 timely/误报的方向一致，才可写进材料；只要有一种口径下方向反转，就必须收窄为「在本链路的具体口径下观察到」。'+NL2)
W('## 5. 局限'+NL2)
W('- 标定期只有 2 月初到首次故障前这一段（无标签、但也不覆盖全部工况）；'+NL)
W('- 官方故障窗仅 4 个，timely 每变化 1 个就是 25%；'+NL)
W('- V5/V6/V7 是对基线分数的扰动/替换，不是完整重训。'+NL)
f.close(); print('报告与图已写入', OUT)
'''
io.open('src/dsh/2026-09-21_05_ablation_two_regimes.py','w',encoding='utf-8',newline=NL).write(NL.join(pre)+NL+body)
import ast; ast.parse(io.open('src/dsh/2026-09-21_05_ablation_two_regimes.py',encoding='utf-8').read())
print('新脚本已生成')
