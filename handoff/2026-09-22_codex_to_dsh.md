# 2026-09-22 Codex → DSH：批次 4 交接（Q14 → Q13 → Q16 → Q15 → Q17）

来源：Codex ｜ 任务单日期：2026-09-22 ｜ 实际执行日期：2026-09-21（按用户要求提前执行未来任务单）

## 完成情况

已严格按 Q14→Q13→Q16→Q15→Q17 顺序完成全部五项。新增脚本均从头实跑，滚动窗使用真实时间单位；未修改 `src/dsh/`、`src/lanmai/`、`results/*/dsh/`、`data/`、`PROJECT_STATE.md` 或 `tasks/codex_batch_queue.md`。成本参数和结果始终只标作占位值。

## 关键结论

1. **Q14 `lanmai` CLI：主体通过，发现一个新参数缺陷。** selftest 阶跃 5 个且全 P2，慢漂移 11 个且含 P1/P3；SKAB 分号识别和 `calibrate --channels` 白名单生效；BSM1 frozen 首报精确为第 40.28125 天；MetroPT-3 三段阈值 4.482/4.608/10.407，极差比 2.32，median/upper 自洽；`TSS_eff` 未被误认成时间列。但 `inspect --channels` 被忽略，根因是 `cli.py::_read()` 固定调用 `load_table(..., None)`，未把 inspect 的通道参数传入。按约束未改 `src/lanmai/`。
2. **Q13：初始无标签 q0.995 的 timely 崩塌复现，但“所有健康段都 0/4”不跨实现。** DSH 落盘 score 的初始 q0.995=13.1393，timely 从标签辅助 2/4 降为 0/4；Codex 自有链路也从 2/4 降为 0/4。DSH 五段阈值 5.782–22.357，极差比 3.87、误报 1–49、全 0/4；Codex 五段极差比 2.78、误报 16–305，W3/W4/W5 timely=3/4、4/4、4/4。因此应把“全 0/4、3.5–3.9 倍、1–44”限定为 DSH 当前链路，跨实现只冻结“标定段选择高度敏感”。2.3954 仍必须标为标签辅助 DET 工作点。
3. **Q16：四项方向复现，但 +62% 数字不成立。** Thickener/Dewatering 同时刻末点为 13.579→21.121 m³/d，即 +55.54%，干固体 3802.181→3802.181 kg/d 不变；理论 `28/18-1=55.56%` 也支持该值。真值失效第 109 天、frozen 首报 61.333、自适应 0 告警均复现。DSH 的 RUL 273.08/63.92/46.68 可由“首报先圆整为 61.33 + 96 点/天”精确复现；真实时间窗得到 269.25/63.30/46.67。决策层复现最优固定 30 天单台年占位成本 108220、RUL 驱动 81704.8、节省 24.50%、非计划失效 0。建议将 +62% 冻结值改为 +55.5%，并注明 RUL 窗口索引口径。
4. **Q15：主体结论复现，报告“45 组严格相等”应收窄。** 3D 下 ratio=76/83/96、single=51、union=127/134/147；全部组合检出 12/12、延迟中位 20.3 天。与门在 1D/3D 全为 51，但 5D 随 k_and 为 51/51/50/50/49；DSH 自身 CSV 也有 50/49。因此“几乎等于单点”成立，“全部 45 组恒等于 51”不成立。
5. **Q17：两条方向均复现。** 时间窗门禁挂 RUL 为 3/7；在线 RUL 仅 1/7 可算。基准轨迹在线 4.859 天、真值 7.104 天、误差 2.245 天。第 40 天轨迹的分布位置比 1.250487，属于门禁刀锋边缘；另两条挂 RUL 轨迹因告警前 5D 没有负向机理斜率而不报数。

## 产物

### 报告

- `results/2026-09-22/codex/lanmai_cli_audit.md`
- `results/2026-09-22/codex/ablation_regime_repro.md`
- `results/2026-09-22/codex/sludge_line_repro.md`
- `results/2026-09-22/codex/strategy_sensitivity_repro.md`
- `results/2026-09-22/codex/online_chain_repro.md`

### 复现脚本

- `src/codex/2026-09-22_01_ablation_regime_repro.py`
- `src/codex/2026-09-22_02_sludge_line_repro.py`
- `src/codex/2026-09-22_03_strategy_sensitivity_repro.py`
- `src/codex/2026-09-22_04_online_chain_repro.py`

### 机器可读明细

- `results/2026-09-22/codex/q13_ablation_regime_repro.csv`
- `results/2026-09-22/codex/q16_sludge_repro.json`
- `results/2026-09-22/codex/q16_sludge_line_repro.csv`
- `results/2026-09-22/codex/q16_sludge_decision_repro.csv`
- `results/2026-09-22/codex/q15_strategy_sensitivity.csv`
- `results/2026-09-22/codex/q17_online_chain.csv`
- Q14 的 `q14_*` 原始日志、baseline JSON 和 alarms CSV。

## 建议 DSH 下一步

1. 修复 `lanmai inspect --channels` 参数传递，并补一条 CLI 回归测试；
2. 将 Q13 的“无标签全 0/4”限定为当前 DSH 链路，不作跨实现规律；
3. 将污泥线湿泥饼增幅从 +62% 修正为同刻配对的约 +55.5%，并把 RUL 主结果改为时间窗或至少注明旧点索引口径；
4. 将策略敏感性正文“45 组恒等于 51”改成“49–51，几乎等于”；
5. 在线 RUL 保持“机理段未出现则不报数”，并单独记录第 40 天轨迹的 1.250487 刀锋边缘。
