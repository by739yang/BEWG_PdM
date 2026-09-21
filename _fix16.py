import io, os
NL=chr(10); p='src/dsh/2026-09-20_16_twin_static.py'
L=io.open(p,encoding='utf-8').read().split(NL)
assert L[5].startswith('sys.path.insert'), L[5][:40]
L.insert(5, 'import sys, os, io, base64, numpy as np, pandas as pd')
t=NL.join(L)
io.open('_tmp16b.py','w',encoding='utf-8',newline=NL).write(t); os.replace('_tmp16b.py',p)
import ast; ast.parse(t); print('已补回 import 行')
