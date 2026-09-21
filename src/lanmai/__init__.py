# -*- coding: utf-8 -*-
"""澜脉 lanmai —— 污水厂设备健康接入与标定工具（DSH，2026-09-21）
三段流程：inspect（数据体检）→ calibrate（基线标定）→ watch（分级告警）。"""
__version__ = '0.1.0'
from .core import load_table, state_series, topk_score, make_events
from .pipeline import inspect, calibrate, watch, selftest
