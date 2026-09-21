import io, os
NL=chr(10); p='src/dsh/2026-09-21_10_sludge_line_loop.py'
L=io.open(p,encoding='utf-8').read().split(NL)
i=[k for k,l in enumerate(L) if 'return dict(' in l][0]
print('修复前:'); print(NL.join(L[i:i+4]))
cur=' '.join(L[i:i+4])
if not cur.rstrip().endswith(')'):
    L[i+2]=L[i+2].rstrip()+')' if L[i+2].strip() else L[i+1].rstrip()+')'
    if not L[i+1].rstrip().endswith(')'): L[i+1]=L[i+1].rstrip()+')'
t=NL.join(L)
io.open('_tmp_sl2.py','w',encoding='utf-8',newline=NL).write(t); os.replace('_tmp_sl2.py',p)
import ast; ast.parse(t); print('已修复 dict 括号')
