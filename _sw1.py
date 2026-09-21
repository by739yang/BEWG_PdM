import io, os
NL=chr(10); p='src/dsh/2026-09-21_12_sludge_sweep.py'; t=io.open(p,encoding='utf-8').read()
def rep(a,b):
    global t
    assert a in t, a[:70]; t=t.replace(a,b,1)
# 解析真值：斜坡延长到 20% 的时刻（若最终低于 20%）；并记录"是否仍在下降"
rep("""    rows.append(dict(场景=tag, 最终含固率=ds_end, 斜坡天=ramp, 降解速率pp每天=round((DS0-ds_end)/ramp,3),""",
    """    ana=(None if ds_end>=FAIL else round(DEG_START+ramp*(DS0-FAIL)/(DS0-ds_end),2))
    rows.append(dict(场景=tag, 最终含固率=ds_end, 斜坡天=ramp, 降解速率pp每天=round((DS0-ds_end)/ramp,3),
                     解析到20%时刻=ana, 仿真期内失效=(fail is not None),""")
# RUL 误差对可用真值（仿真内失效优先，否则解析）
rep("""                     RUL估计=(None if rul is None else round(rul,2)),
                     RUL真值=(None if (fail is None or ff is None) else round(fail-ff,2)),
                     RUL误差=(None if (rul is None or fail is None or ff is None) else round(abs(rul-(fail-ff)),2)),""",
    """                     RUL估计=(None if rul is None else round(rul,2)),
                     RUL真值=(None if ff is None else round((fail if fail is not None else (ana if ana is not None else float('nan')))-ff,2) if (fail is not None or ana is not None) else None),
                     RUL误差=(None if (rul is None or ff is None or (fail is None and ana is None)) else
                              round(abs(rul-(((fail if fail is not None else ana))-ff)),2)),""")
io.open('_tmp_sw.py','w',encoding='utf-8',newline=NL).write(t); os.replace('_tmp_sw.py',p)
import ast; ast.parse(io.open(p,encoding='utf-8').read()); print('已补解析真值')
