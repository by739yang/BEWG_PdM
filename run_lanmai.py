# -*- coding: utf-8 -*-
"""澜脉 · 一键入口（不需要设置 PYTHONPATH）

用法（在仓库根目录，PowerShell / CMD 都行）：
  python run_lanmai.py serve --open
  python run_lanmai.py report --data results/2026-09-21/lanmai_demo/bsm1_120d_degraded_ts.csv \
      --baseline results/2026-09-21/lanmai_demo/bsm1_baseline.json --out demo/report_test.html --warmup 1D
  python run_lanmai.py selftest
说明：这个脚本只是把仓库里的 src/ 加进模块搜索路径，再调用 lanmai 的命令行入口；
      算法与产物与直接运行 python -m lanmai 完全一致（同一套代码）。
"""
import os, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, 'src')
if SRC not in sys.path:
    sys.path.insert(0, SRC)
os.chdir(ROOT)   # 让相对路径（results/...、demo/...）按仓库根解析

from lanmai.cli import main   # noqa: E402

if __name__ == '__main__':
    main(sys.argv[1:])
