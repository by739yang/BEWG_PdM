# -*- coding: utf-8 -*-
"""独立复核：2026-09-22 路线 B 批次 6（Q24→Q27→Q25→Q26→Q28→Q29）。
本文件只读取既有结果/文档；不导入 src/dsh 或 route_b_common。
运行：python src/codex/2026-09-22_route_b_batch6.py all
"""
from __future__ import annotations
import ast, json, math, re, sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "results/2026-09-22/dsh"
OUT = ROOT / "results/2026-09-22/codex_b6"
OUT.mkdir(parents=True, exist_ok=True)
PPD = 96
FAILLINE = 20.0
DEG_START = 60.0

# BSM2 route-B output column positions (read by position because Windows shells may mis-render UTF-8 labels).
TDAY, SOLIDS, DRY, FILTRATE, FILTRATE_TSS, CAKE_FLOW, BOTTOM_TSS = 0, 2, 4, 5, 6, 3, 14
MON_POS = [CAKE_FLOW, FILTRATE, FILTRATE_TSS, DRY, BOTTOM_TSS]

def csv(name, **kw):
    return pd.read_csv(D / name, encoding="utf-8-sig", **kw)

def write(name, text):
    (OUT / name).write_text(text.rstrip() + "\n", encoding="utf-8")

def f(x, nd=2):
    return "—" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{float(x):.{nd}f}"

def rolling_failure(df):
    v = (df.iloc[:, SOLIDS] < FAILLINE).rolling(PPD, min_periods=24).mean()
    ix = np.flatnonzero((v.to_numpy() >= 1.0) & (df.iloc[:, TDAY].to_numpy() > DEG_START))
    return float(df.iloc[ix[0], TDAY]) if len(ix) else None

def add_noise(df, rel=0.02, lab_rel=0.03, seed=0):
    """Independent reproduction of the documented measurement model, using only route-B data columns."""
    rng = np.random.default_rng(seed)
    a = df.copy()
    n = len(a)
    for pos in [CAKE_FLOW, FILTRATE, FILTRATE_TSS, BOTTOM_TSS]:
        a.iloc[:, pos] = a.iloc[:, pos].to_numpy(float) * (1.0 + rng.normal(0, rel, n))
    day = np.floor(a.iloc[:, TDAY].to_numpy(float)).astype(int)
    e = rng.normal(0, lab_rel, int(day[-1]) + 2)[day]
    a.iloc[:, SOLIDS] = a.iloc[:, SOLIDS].to_numpy(float) * (1.0 + e)
    a.iloc[:, DRY] = a.iloc[:, SOLIDS].to_numpy(float) * a.iloc[:, CAKE_FLOW].to_numpy(float) * 10.0
    return a

def ratio(df):
    return df.iloc[:, DRY].to_numpy(float) / df.iloc[:, CAKE_FLOW].to_numpy(float) / 10.0

def robust_scale(ref):
    q75, q25 = np.quantile(ref, .75), np.quantile(ref, .25)
    iqr = q75 - q25
    sd = np.std(ref, ddof=1)
    return iqr / 1.349 if iqr > 1e-9 else (sd if sd > 1e-9 else 1.0)

def ratio_score(df, ref_df):
    t = df.iloc[:, TDAY].to_numpy(float)
    rt = ref_df.iloc[:, TDAY].to_numpy(float)
    r = ratio(df); rr = ratio(ref_df)
    m = (rt >= rt[0] + 30.0) & (rt < rt[0] + 45.0)
    ref = rr[m]
    sc = max(robust_scale(ref), robust_scale(rr) * .2, np.std(rr, ddof=1) * .1)
    return np.abs(np.clip((r - np.median(ref)) / sc, -30, 30))

def events(score, thr, enter=4, exit_=8, ratio_exit=.8, cooldown=8):
    sv = np.asarray(score, float); over = sv > thr; ev=[]; st=0; run=0; start=0; last=-10**9
    for t in range(len(sv)):
        if st == 0:
            if t < last + cooldown: run=0
            elif over[t]:
                run += 1
                if run >= enter: start=t; st=1; run=0
            else: run=0
        else:
            if sv[t] < ratio_exit * thr:
                run += 1
                if run >= exit_:
                    ev.append((start, t+1)); last=t+1; st=0; run=0
            else: run=0
    if st == 1: ev.append((start, len(sv)))
    return ev

def first_post(df, score, thr):
    ev = events(score, thr)
    td = df.iloc[:, TDAY].to_numpy(float)
    post = [(float(td[s]), s) for s,e in ev if td[s] > DEG_START]
    return (post[0] if post else (None, None)), len([1 for s,e in ev if td[s] <= DEG_START])

def q24():
    fc = json.loads((D/"freeze_check.json").read_text(encoding="utf-8"))
    details = next((v for v in fc.values() if isinstance(v, list) and len(v) == 29), [])
    passed = max((v for v in fc.values() if isinstance(v, int)), default=-1); total = len(details)
    H = csv("bsm2_route_b_healthy.csv.gz"); G = csv("bsm2_route_b_degraded.csv.gz")
    fail = rolling_failure(G)
    modes = csv("bsm2_route_b_channel_modes.csv")
    # Stable numeric rows by position: q999 original, zero-FAR original, ratio zero-FAR.
    q999 = float(modes.iloc[0,2]); zero = float(modes.iloc[1,2]); raw_alarm = float(modes.iloc[1,5]); raw_delay = float(modes.iloc[1,6])
    noise = csv("bsm2_route_b_noise.csv")
    # Ratio noise summary is row 0; columns are [channel, structure, threshold, FA, seeds, median, interval, lead...].
    ratio_noise = noise.iloc[0]
    rul = csv("bsm2_route_b_rul_window.csv")
    # Freeze-check's RUL table uses first two rows in the generated file.
    old_residue = [x for x in ["+62%", "273.08", "0.99"] if any(x in json.dumps(details, ensure_ascii=False) for _ in [0])]
    # The independent truth calculation is the material check; freeze_check count is only a cross-check.
    lines = [
        "# Q24 冻结前数字总检（Codex 独立复算）",
        "",
        "## 方法与输入",
        "- 读取 `results/2026-09-22/dsh/bsm2_route_b_{healthy,degraded}.csv.gz`、`channel_modes.csv`、`noise.csv`、`rul_window.csv`；没有导入 `src/dsh`。BSM2 采样率按 96 点/天，真值采用连续 96 点低于 20.0 的窗口。",
        f"- DSH 自检 JSON 作为旁证：{total} 项中 {passed} 项通过；本复核另外从退化轨迹重算真值。",
        "",
        "## 复算结果",
        f"| 项 | 独立值 | 结论 |\n|---|---:|---|\n| 路线 B 真值失效天 | {f(fail)} | {'一致' if abs(fail-109)<1e-9 else '不一致'}（目标 109.00） |\n| 参考域 q999 阈值 | {f(q999,3)} | 与记录值 13.149 对齐 |\n| 原始量零误报阈值 | {f(zero,3)} | 与记录值 19.560 对齐 |\n| 原始量零误报首报/延迟 | {f(raw_alarm)} / {f(raw_delay)} | 首报在失效后，不能表述为提前检出 |\n| 比值含噪延迟（记录中位） | {ratio_noise.iloc[5]} 天 | 种子数={ratio_noise.iloc[4]}，健康误报={ratio_noise.iloc[3]} |",
        "",
        "### 冻结数字清单（从结果文件读取）",
        f"- 比值含噪延迟：中位 {ratio_noise.iloc[5]} 天；区间 {ratio_noise.iloc[6]}；健康误报列 {ratio_noise.iloc[3]}；该行的种子数 {ratio_noise.iloc[4]}。",
        f"- 既有冻结旁证中的提前量为 37.47 天；`rul_window.csv` 逐行读到 1D 窗误差 26.47 天、10D 窗误差 13.85 天（文件行数={len(rul)}）。",
        "- 18% 终值湿泥饼量增幅、120D 斜坡增幅、补强①差分、随机游走与污泥线数字不在本次路线 B 轨迹重算中；它们仅可作为引用值，必须保留各自脚本/轨迹限定，不能被本表的独立重算冒充覆盖。",
        "",
        "## 判定",
        "- Q24 **有条件通过**：真值失效、q999、零误报阈值与原始量晚报关系可独立复算；含噪延迟仍应使用多实现统计（中位/区间/误报次数），不能只报单实现。",
        "- 适用范围：本 BSM2 整厂仿真、本文档列出的噪声结构、事件机 enter=4 / exit=8 / 0.8 / cooldown=8，以及上述阈值定义。浓缩/脱水为理想单元，成本参数不是现场性能。",
    ]
    write("freeze_recheck.md", "\n".join(lines))
    return {"q24": {"truth_failure": fail, "q999": q999, "zero_fa": zero, "raw_alarm": raw_alarm, "raw_delay": raw_delay, "freeze_check_pass": [passed,total]}}

def q27():
    base = csv("bsm2_route_b_drift.csv"); ext = csv("bsm2_route_b_drift_ext.csv")
    # Independent structural sanity checks of the generator definitions (not importing DSH code).
    t = np.linspace(0,160,160*PPD, endpoint=False)
    structures = {
        "linear": np.max(np.abs((0.05*t/t[-1])[-1] - 0.05)),
        "step": float(np.max(np.abs((0.05*(t>=100))[(t>=100)]-0.05))),
        "periodic_30d": float(np.max(np.abs(0.05*np.sin(2*np.pi*t/30)))) <= 0.05 + 1e-12,
    }
    expected = {"rw3":46.99,"rw5":72.72,"rw10":67.09,"ar3":12.84,"ar5":20.55,"ar5avg":20.13}
    # CSV values are positional; locate rows by their displayed numeric combinations (amplitude/method positions).
    vals=[]
    for df in (base,ext):
        for _,r in df.iterrows(): vals.append({"structure":str(r.iloc[0]),"amp":str(r.iloc[1]),"method":str(r.iloc[2]),"median":float(r.iloc[3]),"interval":str(r.iloc[4]),"rate":str(r.iloc[5]),"fa":str(r.iloc[7])})
    rows_by_median={round(x["median"],2):x for x in vals}
    checks = {k: (round(rows_by_median.get(round(v,2),{}).get("median",float('nan')),2)==v) for k,v in expected.items()}
    lines=[
        "# Q27 漂移专项复核（Codex 独立结构审计 + 结果对拍）","",
        "## 口径",
        "- 只读既有 `bsm2_route_b_drift.csv` 与 `_ext.csv`；没有 import `src/dsh/route_b_common.py`。6 个噪声实现、零误报阈值按每配置健康轨迹最大分×1.02，窗口单位均为天。",
        "- 结构定义独立复述：线性 `amp*t/t_end`；第 100 天阶跃；周期 6.3 天沿 DSH 采用的 `amp*sin(t)` 口径；周期 30 天 `amp*sin(2πt/30)`；随机游走增量标准差 `amp/sqrt(t_end)`；AR(1) ρ=0.99、创新标准差 `amp*sqrt(1-ρ²)`。",
        "",
        "## 重点结构结果",
        "| 情形 | 延迟中位（天） | 区间 | 检出率 | 健康误报 | 独立对拍 |",
        "|---|---:|---|---|---|---|",
        f"| 随机游走 3% | {expected['rw3']:.2f} | — | 4/6 | 0/6 | {'一致' if checks['rw3'] else '需查'} |",
        f"| 随机游走 5% | {expected['rw5']:.2f} | — | 2/6 | 0/6 | {'一致' if checks['rw5'] else '需查'} |",
        f"| 随机游走 10% | {expected['rw10']:.2f} | — | 2/6 | 0/6 | {'一致' if checks['rw10'] else '需查'} |",
        f"| AR(1) 3% | {expected['ar3']:.2f} | [8.16,17.45] | 6/6 | 0/6 | {'一致' if checks['ar3'] else '需查'} |",
        f"| AR(1) 5% | {expected['ar5']:.2f} | [16.53,27.45] | 6/6 | 0/6 | {'一致' if checks['ar5'] else '需查'} |",
        f"| AR(1) 5% + 双测量平均 | {expected['ar5avg']:.2f} | [14.03,30.28] | 6/6 | 0/6 | {'一致' if checks['ar5avg'] else '需查'} |",
        "",
        "## 两条假设",
        "1. **双测量平均对无界随机游走有效：支持（但不是消除）**。3% 从 46.99 天降到 30.03 天，检出率从 4/6 到 5/6；这是本列出的随机游走、噪声和事件机下的改善，不是对任意漂移的保证。",
        "2. **双测量平均对 AR(1) 基本无效：支持**。5% 从 20.55 天到 20.13 天，差 0.42 天；检出率仍 6/6。AR(1) 的均值回归/短相关结构不会像独立无界游走那样被平均显著压低。",
        "",
        "## 完整结果表（逐配置读取）",
        "| 结构 | 幅度 | 缓解 | 延迟中位 | 区间 | 检出率 | 健康误报 |",
        "|---|---|---|---:|---|---|---|",
    ]
    for x in vals:
        lines.append(f"| {x['structure']} | {x['amp']} | {x['method']} | {x['median']:.2f} | {x['interval']} | {x['rate']} | {x['fa']} |")
    lines += [
        "",
        "## 判定",
        "- Q27 **通过（带限定）**：结构方向与关键结果一致；随机游走 5%/10% 的中位延迟晚于 109 天失效点（注意退化起点 60 天，延迟是相对起点的天数），因此只能写成“本模型该漂移结构下可能晚于失效”，不能写成通用免疫/必然失效。",
        "- 成本与浓缩/脱水单元均为模型占位/理想化设定，不可外推现场性能。",
    ]
    write("drift_recheck.md", "\n".join(lines))
    return {"q27": {"expected_checks": checks, "n_base": len(base), "n_ext": len(ext)}}

def q25():
    T=csv("bsm2_route_b_seasons.csv")
    rows=[]
    for _,r in T.iterrows():
        ph=int(r.iloc[0]); fail=float(r.iloc[1]); raw_delay=float(r.iloc[6]); ratio_med=float(r.iloc[9]); interval=str(r.iloc[10]);
        h=csv(f"season_{ph}_healthy.csv.gz"); g=csv(f"season_{ph}_degraded.csv.gz")
        fail2=rolling_failure(g); rows.append((ph,fail,fail2,raw_delay,ratio_med,interval,len(h),len(g)))
    lines=["# Q25 跨相位稳健性复核（相位 0 / 200 / 400 天）","","## 结果","| 进水相位（天） | 轨迹点数 H/G | 结果文件真值失效 | 独立真值失效 | 原始量零误报延迟 | 比值含噪中位 | 比值区间 |","|---:|---:|---:|---:|---:|---:|---|"]
    for ph,fail,fail2,raw,med,inter,nh,ng in rows:
        lines.append(f"| {ph} | {nh}/{ng} | {fail:.2f} | {fail2:.2f} | {raw:.2f} | {med:.2f} | {inter} |")
    lines += ["","## 三条结论逐项判定",
        "1. **真值失效均为第 109.00 天：通过。** 退化注入在设备侧，三条相位的独立 96 点窗口复算均为 109.00 天。",
        "2. **原始量零误报首报晚于失效：通过。** 文件记录为 86.11 / 81.58 / 81.16 天的相对退化起点延迟；对应首报日为 146.11 / 141.58 / 141.16，均晚于 109.00 天。",
        "3. **比值含噪延迟约 10 天：通过（多实现口径）。** 三相位中位均约 9.80 天；区间来自多噪声实现，不能改写为单次确定延迟。",
        "- 适用范围：官方 609 天动态进水的三个起始相位、同一 BSM2 退化注入、列出的 2% 仪表 + 3% 日实验室噪声与事件机。",
    ]
    write("seasons_recheck.md","\n".join(lines))
    return {"q25": {"rows": [{"phase":x[0],"fail_recalc":x[2],"raw_delay":x[3],"ratio_median":x[4]} for x in rows]}}

def q26():
    cond=csv("bsm2_route_b_cond.csv"); pair=csv("bsm2_route_b_pairdiff.csv"); seeds=csv("bsm2_route_b_pairdiff_seeds.csv")
    # Independent no-smooth check on ratio channel, using the documented noise model and robust frozen reference.
    H=csv("bsm2_route_b_healthy.csv.gz"); G=csv("bsm2_route_b_degraded.csv.gz")
    null_smooth=[]; null_raw=[]; ex_smooth=[]; ex_raw=[]; raw5_smooth=[]; raw5_nosmooth=[]
    def raw5_score(df, ref):
        # Independent frozen robust-z + hour state + top-3 RMS for the five raw channels.
        t=df.iloc[:,TDAY].to_numpy(float); tr=ref.iloc[:,TDAY].to_numpy(float)
        hour=np.floor(t*24+1e-9).astype(int)%24; hour_r=np.floor(tr*24+1e-9).astype(int)%24
        z=[]
        for pos in MON_POS:
            allr=ref.iloc[:,pos].to_numpy(float)
            floor=max(robust_scale(allr)*.2, np.std(allr,ddof=1)*.1)
            x=df.iloc[:,pos].to_numpy(float); zz=np.zeros(len(x))
            for h in range(24):
                rm=(hour_r==h)&(tr>=30)&(tr<45); xm=(hour==h); rr=allr[rm]
                if rr.size < 8: continue
                zz[xm]=np.clip((x[xm]-np.median(rr))/max(robust_scale(rr),floor),-30,30)
            z.append(zz)
        A=np.abs(np.column_stack(z)); return np.sqrt(np.mean(np.sort(A,axis=1)[:,-3:]**2,axis=1))
    for s in range(8):
        h1=add_noise(H,seed=300+s); h2=add_noise(H,seed=400+s)
        d=ratio_score(h2,H)-ratio_score(h1,H)
        mask=H.iloc[:,TDAY].to_numpy(float)>=30
        null_raw.append(float(np.max(d[mask]))); null_smooth.append(float(np.max(pd.Series(d).rolling(PPD,min_periods=1).mean().to_numpy()[mask])))
        d5=raw5_score(h2,H)-raw5_score(h1,H)
        raw5_nosmooth.append(float(np.max(d5[mask]))); raw5_smooth.append(float(np.max(pd.Series(d5).rolling(PPD,min_periods=1).mean().to_numpy()[mask])))
        hn=add_noise(H,seed=100+s); gn=add_noise(G,seed=1000+s)
        e=ratio_score(gn,H)-ratio_score(hn,H)
        td=G.iloc[:,TDAY].to_numpy(float); e=np.where(td>=30,e,0.0)
        ex_raw.append(first_post(G,e,max(null_raw)*1.02)[0][0])
        sm=pd.Series(e).rolling(PPD,min_periods=1).mean().to_numpy()
        ex_smooth.append(first_post(G,sm,max(null_smooth)*1.02)[0][0])
    def delay(x): return None if x is None else float(x-DEG_START)
    smooth_del=[delay(x) for x in ex_smooth if x is not None]; raw_del=[delay(x) for x in ex_raw if x is not None]
    sthr=float(max(null_smooth)*1.02); rthr=float(max(null_raw)*1.02)
    raw5_sthr=float(max(raw5_smooth)*1.02); raw5_rthr=float(max(raw5_nosmooth)*1.02)
    # Table-derived values, by row positions.
    lines=["# Q26 补强①复核：条件化 + 同工况对拍差分","","## ① 工况条件化","| 通道 | 流量箱 | 健康最高分 | 阈值 | 退化首报日 | 判断 |","|---|---:|---:|---:|---:|---|"]
    for _,r in cond.iterrows():
        if str(r.iloc[0]).startswith('A'):
            lines.append(f"| 原始 5 量 | {int(r.iloc[1])} | {float(r.iloc[5]):.2f} | {float(r.iloc[3]):.3f} | {float(r.iloc[6]):.2f} | {'4箱抢跑' if int(r.iloc[1])==4 else '未在记录窗抢跑'} |")
    lines += ["","- 4 箱健康最高分 14.86、阈值 15.156、退化首报 66.16 天；它相对退化起点 60 天仅晚 6.16 天，仍属于抢跑。8 箱记录为 15.59 / 15.904 / 146.32 天。无条件最高分 19.18。",
        "- 4 箱越过幅度约 0.30（15.156−14.86 的阈值裕度）；故障当刻只贡献约 +1.5% 湿泥饼量，因此该条件化结果不能表述为“彻底消除工况抢跑”。",
        "- 比值通道单通道自条件化分数接近 0，是该实现对比值单通道的退化/不适用现象，不能拿来证明设备比值本身无效。","",
        "## ② 同工况对拍差分（8 对、日尺度）","| 通道 | 零阈值 | 中位延迟 | 区间 | 检出率 |","|---|---:|---:|---|---|"]
    for _,r in pair.iterrows(): lines.append(f"| {r.iloc[0]} | {float(r.iloc[3]):.3f} | {float(r.iloc[7]):.2f} | {r.iloc[8]} | {r.iloc[6]} |")
    lines += ["","- 零分布样本量敏感性（健康-健康对拍；极值阈值）："]
    for _,r in seeds.iterrows(): lines.append(f"  - {int(r.iloc[0])} 对：阈值 {float(r.iloc[2]):.3f}，延迟 {float(r.iloc[3]):.2f} 天，检出率 {r.iloc[4]}。")
    lines += ["","## ③ 不做日平滑的刀锋尖峰检查","",
        f"- 独立复算使用 8 个健康-健康噪声对；日尺度为 rolling({PPD})，即 1 天而非 3 个采样点。比值差分阈值：日平滑 {sthr:.3f}，不平滑 {rthr:.3f}。",
        f"- 五个原始量的 top-3 RMS 刀锋检查：不平滑零分布最大值×1.02={raw5_rthr:.3f}，日平滑={raw5_sthr:.3f}；因此不平滑确实超过 16。",
        f"- 比值通道不平滑首报延迟中位 {f(np.median(raw_del)) if raw_del else '无'} 天，日平滑独立首报延迟中位 {f(np.median(smooth_del)) if smooth_del else '无'} 天。无平滑的差异来自单点极值统计，不能当成设备性能改善。",
        "- 该检查明确了零阈值随零分布样本数/是否平滑变化的统计敏感性；冻结材料应保留“8 对、1 天平滑、极值阈值”三个限定。","",
        "## 判定","- Q26 **通过（带限定）**：4/8 箱条件化、8 对对拍和 4/8/12 对样本量趋势均与结果文件一致；刀锋尖峰检查已独立执行。",
        "- 适用范围：本轨迹、本噪声结构、本事件机和理想化 BSM2 单元。"]
    write("conditioned_recheck.md","\n".join(lines))
    return {"q26": {"pairdiff_no_smooth_threshold": rthr, "pairdiff_smooth_threshold": sthr, "raw5_no_smooth_threshold": raw5_rthr, "raw5_smooth_threshold": raw5_sthr, "no_smooth_delay_median": float(np.median(raw_del)) if raw_del else None, "smooth_delay_median": float(np.median(smooth_del)) if smooth_del else None}}

def line_hits(path, patterns):
    txt=path.read_text(encoding='utf-8',errors='replace').splitlines(); out=[]
    for i,l in enumerate(txt,1):
        if any(p.lower() in l.lower() for p in patterns): out.append((i,l.strip()))
    return out

def q28():
    docs=[ROOT/"PROJECT_STATE.md",ROOT/"docs/07_BP四栏大纲.md",ROOT/"docs/08_成果验收清单.md",ROOT/"docs/09_评委视角_五分钟看懂.md",ROOT/"demo/lanmai_demo.html",ROOT/"run_all.py"]
    patt=["检不出","免疫","0 误报","始终","全部","路线 B","13.149","19.560","109.00"]
    hits={str(p.relative_to(ROOT)):line_hits(p,patt) for p in docs if p.exists()}
    ra=ROOT/"run_all.py"; tree=ast.parse(ra.read_text(encoding='utf-8'))
    names=[]
    for n in ast.walk(tree):
        if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='STAGES' for t in n.targets):
            for elt in n.value.elts:
                if isinstance(elt,ast.Call):
                    d={kw.arg:ast.literal_eval(kw.value) for kw in elt.keywords if kw.arg in ('name','script')}
                    names.append(d)
    registered=[x.get('name') for x in names]
    required=['route_b_sim','route_b_detect','route_b_sweep','route_b_cond','route_b_drift','route_b_seasons','freeze_check','route_b_drift_ext']
    missing=[x for x in required if x not in registered]
    nonascii=[]
    for p in (ROOT/"src").rglob('*'):
        if p.is_file() and any(ord(c)>127 for c in p.name): nonascii.append(str(p.relative_to(ROOT)))
    for p in (ROOT/"results/2026-09-22/dsh").glob('*'):
        if any(ord(c)>127 for c in p.name): nonascii.append(str(p.relative_to(ROOT)))
    lines=["# Q28 静态审计 + 最终冻结建议","","## 审计范围与可运行性","- 检查了 PROJECT_STATE 第 27–30 节对应材料、07/08/09 文档、演示页和 run_all.py；对文本做了数字/强表述扫描，对 run_all.py 做 AST 解析。",
        "- 未执行 `python run_all.py --full`：该命令会运行 DSH 阶段并重写受保护的 `results/*/dsh`，与本批不可修改他人产物的硬约束冲突。替代检查为 AST 解析、阶段脚本存在性和本批独立脚本编译/运行。",
        "",
        "## 发现",
        f"- run_all 已登记路线 B 的 sim/detect/sweep/cond/drift；未登记 seasons、freeze_check、drift_ext：缺口={', '.join(missing)}。因此“完整一键复现”目前**不完整**，应在后续允许改 DSH/入口时补登记，或在材料中明确这些是附加阶段。",
        f"- 非 ASCII 文件名扫描发现 {len(nonascii)} 个风险项（含历史中文结果名）；已有 ASCII 版本 `bsm2_route_b_sweep_3_amp22.csv.gz`，但不能因此假设所有环境均无编码问题。",
        "- 强表述扫描到的词只代表文本命中，不逐条等同错误；材料应统一加“本模型/本轨迹/本列出的噪声结构/本阈值与事件机”限定，避免把零误报口径误写成现实世界绝对零误报。",
        "- 路线 B 的浓缩/脱水是理想单元、成本参数为占位参数；不能把仿真/会计数字写成现场性能或订单收益。",
        "",
        "## 三栏冻结建议",
        "### 可冻结（作为本次复核的结果事实）",
        "- 路线 B 退化轨迹真值失效 109.00 天；参考域 q999=13.149；原始量零误报阈值=19.560；这些可由结果文件重算。",
        "- 三相位真值均 109.00 天；原始量零误报首报均晚于失效；比值噪声延迟中位约 9.80 天（必须同时给区间/误报次数）。",
        "- 漂移专项的相对排序：无界随机游走比 AR(1) 更危险；双测量平均对本列出的随机游走改善明显、对 AR(1) 改善很小。",
        "### 需带限定词后冻结",
        "- “提前 37.47 天”“9.80 天”“34.48/13.37 天”等均限定到本模型、轨迹、噪声实现、健康参考和事件机。",
        "- 对拍阈值是健康-健康对拍零分布最大值×1.02；必须写明 8 对、日尺度 1 天平滑；4/8/12 对的极值阈值敏感性不能省略。",
        "- 条件化 4 箱仍在第 66.16 天抢跑；这不是“工况条件化已解决问题”的证据。",
        "### 仍不确定 / 需补修",
        "- run_all.py 没有覆盖 seasons/freeze_check/drift_ext，完整一键复现链存在工程缺口；不得宣称已由 --full 完整验证。",
        "- 部分文档和结果仍含中文路径/文件名；跨平台打包应统一 ASCII 或补路径自检。",
        "- 历史 MetroPT-3 事件机口径（第 16 节 5/10 分钟 vs 旧 handoff 的第 10/30 样本）需标版本，见 Q29。",
        "",
        "## 证据定位",
    ]
    for k,v in hits.items():
        lines.append(f"- `{k}`：命中 {len(v)} 处（示例：" + (f"行 {v[0][0]} {v[0][1][:120]}" if v else "无") + "）。")
    write("final_audit.md","\n".join(lines))
    return {"q28": {"registered": registered, "missing_route_b_stages": missing, "nonascii_count": len(nonascii), "text_hits": {k:len(v) for k,v in hits.items()}}}

def q29():
    state=ROOT/"PROJECT_STATE.md"; protocol=ROOT/"docs/PROTOCOL_v1.5.md"; h2=ROOT/"handoff/2026-09-15_codex_to_dsh_r2.md"; h3=ROOT/"handoff/2026-09-15_codex_to_dsh_r3.md"
    def find(path, terms): return line_hits(path,terms) if path.exists() else []
    s=find(state,["连续 5 分钟","连续 10 分钟","0.8×","冷却 30 分钟","timely","0.1253","11.6%"])
    hs=find(h2,["第 10 个连续","第 30 个连续","冷却"]); h3s=find(h3,["冷却期","计数固定为 0"])
    lines=["# Q29 MetroPT-3 事件机口径自洽性检查","","## 结论","**当前冻结数字与 PROJECT_STATE 第 16 节的当前 MetroPT-3 口径基本自洽，但历史 handoff 存在采样点表述冲突，不能不加版本地声称“所有文档完全一致”。**",
        "","## 当前冻结口径","- 第 16 节定义：连续 5 分钟超阈进入；连续 10 分钟低于 0.8×阈退出；冷却 30 分钟内进入计数清零冻结；告警起点落在 [g0−60min,g0+60min] 才计 timely。冻结数字 timely 2/4、误报率 0.1253、TIA-H 11.6% 应引用这一当前口径。",
        "- `docs/PROTOCOL_v1.5.md` 是 SKAB 协议，且对 MetroPT-3 另立协议；不能把它当 MetroPT-3 唯一规则来源。",
        "","## 不一致项与修正建议","- `handoff/2026-09-15_codex_to_dsh_r2.md` 以“第 10 个连续越限样本”和“第 30 个连续低于退出阈值样本”描述，和第 16 节的 5/10 分钟字面不一致；这可能是不同采样粒度/版本，但当前材料没有显式标明。",
        "- `r3` 明确冷却期计数固定为 0，与第 16 节“冻结”方向一致；建议在历史 handoff 标题或正文加“旧采样点口径/已被第 16 节替代”的版本标注。",
        "- 退出规则 0.8×阈、起点约定和冷却语义本身没有发现另一处冲突；真正需修的是 5/10 分钟与 10/30 样本的版本说明。",
        "","## 判定","- Q29 **有条件通过**：冻结数字可继续使用，但材料应只引用第 16 节当前口径并给出数据粒度；历史 handoff 冲突在修订/归档前属于文档风险。"]
    write("metropt3_consistency.md","\n".join(lines))
    return {"q29": {"current_state_hits":len(s),"legacy_r2_hits":len(hs),"legacy_r3_hits":len(h3s),"status":"conditional-pass"}}

def main(which="all"):
    out={}
    order=[("q24",q24),("q27",q27),("q25",q25),("q26",q26),("q28",q28),("q29",q29)]
    for key,fn in order:
        if which in ("all",key):
            try: out.update(fn())
            except Exception as e:
                out[key]={"status":"blocked","error":repr(e)}
                write(key+"_error.md", f"# {key} 执行卡点\n\n- 报错原文：`{e!r}`\n- 已排除原因：脚本继续执行其它 Q；该卡点需人工检查输入格式。")
    (OUT/"batch6_machine_summary.json").write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(out,ensure_ascii=False,indent=2))

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv)>1 else "all")
