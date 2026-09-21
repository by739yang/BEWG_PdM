import io, os
NL=chr(10); p='src/dsh/2026-09-21_10_sludge_line_loop.py'; t=io.open(p,encoding='utf-8').read()
def rep(a,b):
    global t
    assert a in t, a[:70]; t=t.replace(a,b,1)
# 单位：TSS mg/L -> % w/v 除以 10000（28 万 mg/L = 28%）
rep("泥饼含固率=float(yc[13])/1000.0*100.0/10.0 if False else float(yc[13])/10.0)",
    "泥饼含固率=float(yc[13])/10000.0, 浓缩含固率=float(yt_u[13])/10000.0, 湿泥饼产量=float(yc[14]), 滤液量=float(yr[14])")
rep("OBS=['滤液TSS','滤液Q','干固体产率','上清液TSS','浓缩污泥TSS']",
    "OBS=['泥饼Q','滤液Q','滤液TSS','干固体产率','上清液TSS']   # 只用真实厂可测的间接量；泥饼含固率留给 RUL 作机理锚")
rep("print(chk[['t_day','浓缩污泥TSS','浓缩污泥Q','上清液TSS','泥饼TSS','泥饼Q','滤液TSS','滤液Q','干固体产率','泥饼含固率']].round(2).to_string(index=False))",
    "print(chk[['t_day','浓缩TSS' if '浓缩TSS' in chk.columns else '浓缩污泥TSS','泥饼Q','滤液Q','滤液TSS','干固体产率','泥饼含固率','浓缩含固率']].round(2).to_string(index=False))")
io.open('_tmp_sl.py','w',encoding='utf-8',newline=NL).write(t); os.replace('_tmp_sl.py',p)
import ast; ast.parse(io.open(p,encoding='utf-8').read()); print('已修单位与监测通道')
