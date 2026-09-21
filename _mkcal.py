import io, os
NL=chr(10)
src=io.open('src/dsh/2026-09-21_05_ablation_two_regimes.py',encoding='utf-8').read().split(NL)
i=[k for k,l in enumerate(src) if l.startswith('# ---- 无标签标定期')][0]
pre=src[:i]
pre[1]='"""标定期敏感性：用多段健康期分别标定阈值（DSH，2026-09-21）'
pre[2]='补掉第 17.1 节的局限「标定期只覆盖 2 月初至首次故障前」：'
pre[3]='用 4 个官方故障窗之间的 5 段健康期（各留 12 小时余量）分别给 8 个变体标定 q0.995 阈值，'
pre[4]='看 timely / 误报 / 阈值本身对「选哪一段健康期」有多敏感。"""'
body = '''# ---- 5 段健康期（故障窗之间，各留 12 小时） ----
gaps=[]
gaps.append((J.ts.iloc[0], fw[0][0]-pd.Timedelta(hours=12), 'W1 起点→故障1前'))
for k in range(len(fw)-1):
    gaps.append((fw[k][1]+pd.Timedelta(hours=12), fw[k+1][0]-pd.Timedelta(hours=12), 'W%d 故障%d后→故障%d前' % (k+2,k+1,k+2)))
gaps.append((fw[-1][1]+pd.Timedelta(hours=12), J.ts.iloc[-1], 'W%d 故障4后→终点' % (len(fw)+1)))
for a,b,nm in gaps:
    print('  %-26s %s → %s （%d 分钟）' % (nm, str(a)[:16], str(b)[:16], int(((b-a).total_seconds()//60))))

def cal_of(score, a, b):
    s=pd.Series(np.asarray(score,dtype=float), index=J.ts)
    return s[(s.index>=a)&(s.index<=b)]

rows=[]
for nm,sc in variants:
    for (a,b,wn) in gaps:
        c=cal_of(sc,a,b)
        if len(c)<500: continue
        thr=float(c.quantile(0.995))
        r=ev_metrics(sc, thr); r.update(变体=nm, 健康期=wn, 健康期分钟=int(len(c)), 阈值=round(thr,3))
        rows.append(r)
T=pd.DataFrame(rows)[['变体','健康期','健康期分钟','阈值','告警数','timely','late','miss','误报','误报率','TIA_H']]
T.to_csv(os.path.join(OUT,'calib_window_sensitivity.csv'),index=False,encoding='utf-8-sig')
S=T.groupby('变体').agg(阈值最小=('阈值','min'),阈值中位=('阈值','median'),阈值最大=('阈值','max'),
                       阈值极差比=('阈值', lambda s: round(float(s.max()/max(s.min(),1e-9)),2)),
                       timely最小=('timely','min'),timely中位=('timely','median'),timely最大=('timely','max'),
                       误报最小=('误报','min'),误报中位=('误报','median'),误报最大=('误报','max')).reset_index()
S.to_csv(os.path.join(OUT,'calib_window_summary.csv'),index=False,encoding='utf-8-sig')
print(); print('=== 逐（变体 × 健康期）==='); print(T.to_markdown(index=False))
print(); print('=== 变体汇总 ==='); print(S.to_markdown(index=False))

import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif']=['Microsoft YaHei']; plt.rcParams['axes.unicode_minus']=False
fig,ax=plt.subplots(1,2,figsize=(15,4.8))
names=S.变体.tolist(); x=np.arange(len(names)); wd=0.16
for i2,(a,b,wn) in enumerate(gaps):
    v=[float(T[(T.变体==n)&(T.健康期==wn)]['阈值'].iloc[0]) if len(T[(T.变体==n)&(T.健康期==wn)]) else np.nan for n in names]
    ax[0].bar(x+(i2-2)*wd, v, wd, label=wn[:2])
ax[0].set_xticks(x); ax[0].set_xticklabels(names,fontsize=7.5,rotation=25,ha='right'); ax[0].set_ylabel('q0.995 阈值')
ax[0].set_title('① 同一变体在 5 段健康期上标定出的阈值'); ax[0].legend(fontsize=8,title='健康期'); ax[0].grid(alpha=.3,axis='y')
ax[1].scatter(S.变体, S.timely最小, color='#1f4e79', label='timely 最小')
ax[1].scatter(S.变体, S.timely最大, color='#c00000', marker='^', label='timely 最大')
for i3,n in enumerate(names):
    ax[1].plot([i3,i3],[S.timely最小.iloc[i3], S.timely最大.iloc[i3]], color='#7f7f7f', lw=1)
ax[1].set_xticks(x); ax[1].set_xticklabels(names,fontsize=7.5,rotation=25,ha='right'); ax[1].set_ylabel('timely（满分 4）')
ax[1].set_title('② 标定期不同 → timely 的区间'); ax[1].legend(fontsize=8); ax[1].grid(alpha=.3,axis='y')
plt.tight_layout(); plt.savefig(os.path.join(OUT,'calib_window_sensitivity.png'),dpi=130)

NL2=chr(10)+chr(10)
f=io.open(os.path.join(OUT,'calib_window_sensitivity_report.md'),'w',encoding='utf-8'); W=f.write
W('# 标定期敏感性：多段健康期分别标定（DSH，2026-09-21）'+NL2)
W('**要解决的局限**：第 17.1 节的标定期只有一段（2 月初至首次故障前）。本脚本用 4 个官方故障窗之间的 **5 段健康期**（各留 12 小时余量）分别给 8 个变体标定 q0.995 阈值，再看 timely / 误报 / 阈值本身对「选哪一段」有多敏感。'+NL2)
W('| 健康期 | 区间 | 分钟数 |'+NL+'|---|---|---|'+NL+''.join('| %s | %s → %s | %d |%s' % (nm,str(a)[:16],str(b)[:16],int((b-a).total_seconds()//60),NL) for a,b,nm in gaps)+NL)
W('## 1. 逐（变体 × 健康期）'+NL2+T.to_markdown(index=False)+NL2)
W('## 2. 变体汇总（5 段之间的极差）'+NL2+S.to_markdown(index=False)+NL2)
W('## 3. 结论'+NL2)
W('**① 阈值本身对健康期很敏感**：同一变体在 5 段上标定出的阈值极差比见汇总表「阈值极差比」列 —— 比值越大说明越依赖「你选了哪一段」。'+NL)
W('**② timely 与误报的区间见第 2 节**：若某变体的 timely 最小/最大跨越 0 与非 0，说明「该变体能不能命中」取决于标定期选择，而不是变体本身。'+NL)
W('**③ 工程对策**：现场标定不可能只用一段 —— 建议取**多段健康期的分位数上界**（保守，减少误报）或中位（折中），并在报告里写明「标定期选择对阈值的影响范围」。'+NL2)
W('## 4. 局限'+NL2)
W('- 各段健康期长度差别大（见上表），短段的 0.995 分位估计方差大；'+NL)
W('- 只用 MetroPT-3 一个数据集（BSM1 仿真没有多段故障窗）；'+NL)
W('- 未做「跨段交替标定/评估」的严格留一验证。'+NL)
f.close(); print('报告与图已写入', OUT)
'''
io.open('src/dsh/2026-09-21_07_calib_window_sensitivity.py','w',encoding='utf-8',newline=NL).write(NL.join(pre)+NL+body)
import ast; ast.parse(io.open('src/dsh/2026-09-21_07_calib_window_sensitivity.py',encoding='utf-8').read())
print('脚本已生成')
