# -*- coding: utf-8 -*-
"""从 GitHub 镜像分块下载 CWRU 轴承数据（代理单连接约 4MB 上限，故按 3.5MB 分块）"""
import json, os, urllib.request, urllib.parse
BASE='https://raw.githubusercontent.com/srigas/CWRU_Bearing_NumPy/main/'
OUT='data/cwru'; os.makedirs(OUT,exist_ok=True)
def tree():
    req=urllib.request.Request('https://api.github.com/repos/srigas/CWRU_Bearing_NumPy/git/trees/main?recursive=1',headers={'User-Agent':'dsh'})
    with urllib.request.urlopen(req,timeout=30) as r: return json.load(r)
t=tree()
paths=[x['path'] for x in t['tree'] if x['type']=='blob' and x['path'].endswith('.npz')]
norm=['Data/1730 RPM/1730_Normal.npz']
print('Normal 候选:', norm[:3])
targets=[('Normal',norm[0]),('IR_7','Data/1730 RPM/1730_IR_7_DE48.npz'),
         ('OR6_7','Data/1730 RPM/1730_OR@6_7_DE48.npz'),('B_7','Data/1730 RPM/1730_B_7_DE48.npz'),
         ('IR_14','Data/1730 RPM/1730_IR_14_DE48.npz'),('OR6_14','Data/1730 RPM/1730_OR@6_14_DE48.npz'),
         ('B_14','Data/1730 RPM/1730_B_14_DE48.npz'),
         ('N1750','Data/1750 RPM/1750_Normal.npz'),('IR_7_1750','Data/1750 RPM/1750_IR_7_DE48.npz'),
         ('OR6_7_1750','Data/1750 RPM/1750_OR@6_7_DE48.npz'),('B_7_1750','Data/1750 RPM/1750_B_7_DE48.npz')]
CH=3_500_000
for label,p in targets:
    url=BASE+urllib.parse.quote(p)
    dst=os.path.join(OUT,label+'.npz')
    if os.path.exists(dst) and os.path.getsize(dst)>3_000_000: print('已有',dst); continue
    with open(dst,'wb') as f:
        off=0
        while True:
            req=urllib.request.Request(url, headers={'User-Agent':'dsh','Range':f'bytes={off}-{off+CH-1}'})
            try:
                with urllib.request.urlopen(req,timeout=90) as r: data=r.read()
            except Exception as e:
                print(label,'chunk err',off,e); break
            if not data: break
            f.write(data); off+=len(data)
            if len(data)<CH: break
    print('%s -> %s  %.2f MB' % (label,dst,os.path.getsize(dst)/1048576))
