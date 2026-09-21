import io, os
NL=chr(10)
# core.py：窗口自适应（DatetimeIndex 用时间窗；整数索引按采样率折算点数）
p='src/lanmai/core.py'; t=io.open(p,encoding='utf-8').read()
a="DEF_THR_Q = 0.999"
b=("DEF_THR_Q = 0.999"+NL+NL+
"def points_per_day(index):"+NL+
"    if isinstance(index, pd.DatetimeIndex) and len(index) > 2:"+NL+
"        dt = np.median(np.diff(index.values).astype('timedelta64[s]').astype(float))"+NL+
"        if np.isfinite(dt) and dt > 0: return 86400.0 / dt"+NL+
"    return 1440.0"+NL+NL+
"def window_of(index, days, min_points=8):"+NL+
"    \"\"\"时间窗：DatetimeIndex 直接用 Timedelta；整数索引按采样率折算成点数（避免把时间窗当点数）。\"\"\"\""+NL+
"    if isinstance(index, pd.DatetimeIndex):"+NL+
"        return pd.Timedelta(days=days)"+NL+
"    return max(min_points, int(round(points_per_day(index) * days)))")
assert a in t; t=t.replace(a,b,1)
a2="        W = pd.Timedelta(days=win_days)"
b2="        W = window_of(x.index, win_days)"
assert a2 in t; t=t.replace(a2,b2,1)
io.open('_tmp_core.py','w',encoding='utf-8',newline=NL).write(t); os.replace('_tmp_core.py',p)

# pipeline.py：比值窗同样自适应 + 自检数据用 DatetimeIndex
p='src/lanmai/pipeline.py'; t=io.open(p,encoding='utf-8').read()
a3="from .core import (DEF_EVENT, DEF_ADAPT, DEF_THR_Q, load_table, state_series, scale_floor,"
b3="from .core import (DEF_EVENT, DEF_ADAPT, DEF_THR_Q, window_of, load_table, state_series, scale_floor,"
assert a3 in t; t=t.replace(a3,b3,1)
a4="    win = pd.Timedelta(days=base['ratio']['window_days'])"
b4="    win = window_of(sf.index, base['ratio']['window_days'])"
assert a4 in t; t=t.replace(a4,b4,1)
a5="    df = pd.DataFrame({'chA': base, 'chB': base * .5, 'chC': base * 1.2})"
b5="    df = pd.DataFrame({'chA': base, 'chB': base * .5, 'chC': base * 1.2}, index=idx)"
assert a5 in t; t=t.replace(a5,b5,1)
io.open('_tmp_pipe.py','w',encoding='utf-8',newline=NL).write(t); os.replace('_tmp_pipe.py',p)
import ast
for f in ['src/lanmai/core.py','src/lanmai/pipeline.py']: ast.parse(io.open(f,encoding='utf-8').read())
print('已修：窗口自适应 + 自检索引')
