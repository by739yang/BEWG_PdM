#!/usr/bin/env python3
"""Fetch C-MAPSS FD001 into the user cache (never writes repository data/)."""
from __future__ import annotations
import argparse, hashlib, json, os, urllib.request
from pathlib import Path
BASE='https://raw.githubusercontent.com/edwardzjl/CMAPSSData/master/'
FILES=('train_FD001.txt','test_FD001.txt','RUL_FD001.txt','readme.txt')
ROOT=Path(__file__).resolve().parents[2]
DEFAULT_CACHE=Path(os.environ.get('BEWG_PDM_CACHE_DIR',Path.home()/'.cache'/'BEWG_PdM'))/'cmapss'
DEFAULT_OUT=ROOT/'results/2026-09-17/codex'
def sha256(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''): h.update(b)
 return h.hexdigest()
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--cache-dir',type=Path,default=DEFAULT_CACHE); ap.add_argument('--output-dir',type=Path,default=DEFAULT_OUT); a=ap.parse_args()
 a.cache_dir.mkdir(parents=True,exist_ok=True); a.output_dir.mkdir(parents=True,exist_ok=True); manifest=[]
 for name in FILES:
  dst=a.cache_dir/name; url=BASE+name
  if not dst.exists() or dst.stat().st_size<10:
   tmp=dst.with_suffix(dst.suffix+'.part'); req=urllib.request.Request(url,headers={'User-Agent':'BEWG-PdM-Codex/1.0'})
   with urllib.request.urlopen(req,timeout=120) as r, tmp.open('wb') as f:
    while True:
     b=r.read(1<<20)
     if not b: break
     f.write(b)
   tmp.replace(dst)
  manifest.append({'file':name,'bytes':dst.stat().st_size,'sha256':sha256(dst),'url':url})
 (a.output_dir/'cmapss_fetch_manifest.json').write_text(json.dumps({'cache_dir':str(a.cache_dir.resolve()),'files':manifest},indent=2),encoding='utf-8')
 print(json.dumps(manifest,indent=2))
if __name__=='__main__': raise SystemExit(main())
