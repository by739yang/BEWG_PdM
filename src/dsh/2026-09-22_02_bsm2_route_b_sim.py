# -*- coding: utf-8 -*-
"""路线 B：BSM2 整厂 + 脱水机退化闭环（DSH，2026-09-22）
仿真循环在公共层 src/dsh/route_b_common.py 的 run_plant（官方整厂 BSM2Base，退化注入官方 Dewatering 的 dw_par[0]），
本脚本只负责落盘与摘要。真值失效 = 泥饼含固率 < 20% 持续 1 天（与路线 A 同口径）。
用法：python src/dsh/2026-09-22_02_bsm2_route_b_sim.py degraded|healthy
产物：results/2026-09-22/dsh/bsm2_route_b_<tag>.csv.gz / .json
"""
import os, sys, io, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import route_b_common as R

OUT = R.DIR
DAYS = 160.0
DEG = 60.0


def main(tag):
    df = R.run_plant(deg_start=None if tag == 'healthy' else DEG, days=DAYS)
    if not os.path.isdir(OUT):
        os.makedirs(OUT)
    df.to_csv(os.path.join(OUT, 'bsm2_route_b_%s.csv.gz' % tag), index=False, compression='gzip')
    s0 = df[(df.t_day >= 45) & (df.t_day < 60)]
    info = dict(标签=tag, 天数=DAYS, 退化起始=(None if tag == 'healthy' else DEG), 斜坡天=R.RAMP,
                步数=int(df.attrs['步数']), 用时秒=df.attrs['用时秒'],
                秒每天=round(float(df.attrs['用时秒']) / DAYS, 3), NaN数=int(df.isna().sum().sum()),
                退化前泥饼含固率=round(float(s0['泥饼含固率'].mean()), 3),
                末期泥饼含固率=round(float(df['泥饼含固率'].iloc[-1]), 3),
                末期泥饼流量=round(float(df['泥饼流量'].iloc[-1]), 3),
                退化前泥饼流量=round(float(s0['泥饼流量'].mean()), 3),
                末期沼气CH4=round(float(df['沼气CH4'].iloc[-1]), 2),
                退化前沼气CH4=round(float(s0['沼气CH4'].mean()), 2))
    json.dump(info, io.open(os.path.join(OUT, 'bsm2_route_b_%s.json' % tag), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(json.dumps(info, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    if len(sys.argv) > 1:
        main(sys.argv[1])
    else:
        for tag in ('degraded', 'healthy'):
            main(tag)
