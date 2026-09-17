# -*- coding: utf-8 -*-
"""C-MAPSS（NASA 涡扇发动机退化）数据获取：从 GitHub 镜像分块下载（代理单连接约 4MB 上限）"""
import os, urllib.request, urllib.parse, hashlib
BASE='https://raw.githubusercontent.com/edwardzjl/CMAPSSData/master/'
OUT='data/cmapss'; os.makedirs(OUT,exist_ok=True)
FILES=['train_FD001.txt','test_FD001.txt','RUL_FD001.txt','readme.txt']
CH=3_500_000
for name in FILES:
    dst=os.path.join(OUT,name)
    if os.path.exists(dst) and os.path.getsize(dst)>1000:
        print('已有', name, os.path.getsize(dst)); continue
    url=BASE+urllib.parse.quote(name); off=0
    with open(dst,'wb') as f:
        while True:
            req=urllib.request.Request(url, headers={'User-Agent':'dsh','Range':f'bytes={off}-{off+CH-1}'})
            try:
                with urllib.request.urlopen(req, timeout=90) as r: data=r.read()
            except Exception as e:
                print(name,'err',off,e); break
            if not data: break
            f.write(data); off+=len(data)
            if len(data)<CH: break
    sz=os.path.getsize(dst) if os.path.exists(dst) else 0
    h=hashlib.sha256(open(dst,'rb').read()).hexdigest()[:12] if sz else '-'
    print('%-18s %8.2f MB  sha256:%s' % (name, sz/1048576, h))
