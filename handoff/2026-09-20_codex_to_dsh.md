# 2026-09-20 Codex → DSH：批次 2 交接（Q3 / Q5 / Q4 / Q2 / Q6 / Q7）

来源：Codex ｜ 日期：2026-09-20

## 完成情况

已按 `tasks/2026-09-20_codex.md` 的顺序完成全部六项。脚本通过 `py_compile` 并已从头重跑；未修改 `src/dsh/`、`results/*/dsh/`、`data/`、`PROJECT_STATE.md` 或 `tasks/codex_batch_queue.md`。

## 关键结论

1. **Q3 静态审计：有条件通过。** `pipeline.py` 的 `THR=2.395` 来自官方故障标签辅助的 DET 工作点选择，却被写成“标定期 0.995 分位”；冻结 0.995 阈值实际为 13.139。同一故障窗用于选点和汇报，不能称独立前瞻验证。固定“空气泄漏”是接口占位，50,000/8,000/60 是成本占位，RUL 事后门禁包含事件结束信息。
2. **Q5：严格一致。** Codex 行的 2/4、555、0.3459、36.4%、-8.5 分钟均与主 JSON 一致。
3. **Q4：两条方向均复现。** 简化随机森林中 raw 宏 F1 E3→E4 为 0.390→0.550，selective 为 0.381→0.522；跨转速 selective 0.951，高于 full 0.709。
4. **Q2：精确复现。** 主策略 20/20 行和敏感性 15/15 格的整数、最优参数、成本、赢家均一致；AI 赢 12/15。成本参数仍只可作为占位会计。
5. **Q6：两条指定强结论未跨实现复现。** 自有 walk-forward 链路中 V0/V1/V2/V3 的告警为 557/233/582/593，timely 为 2/2/2/1。因此“无工况=0 告警”“去派生=timely 归零”应收窄为 DSH 当前链路/阈值下的观察；max 聚合导致召回下降、误报上升的方向成立。详细简化项和反例证据见报告。
6. **Q7：参考域与工况泛化方向成立。** 健康 0–10 天参考 75 告警、30–45 天参考 0；退化轨迹 0–10 天参考 80 告警，退化后 30–45 天参考仅 1 个且参考窗后 0。刀锋边缘总越限数是 6→8（差 2），最长连续长度是 3→4（差 1并跨过事件门槛）；“只差一个采样点”只应修饰最长连续长度。WinB/WinC 健康 SO3<0.5 分别占 25.7%/60.3%，绝对阈值会把健康工况误定义为失效。

## 产物

- `results/2026-09-20/codex/pipeline_audit.md`
- `results/2026-09-20/codex/self_consistency.md`
- `src/codex/2026-09-20_01_diag_repro.py`
- `results/2026-09-20/codex/diag_repro.csv`
- `results/2026-09-20/codex/diag_repro.md`
- `src/codex/2026-09-20_02_decision_v6_repro.py`
- `results/2026-09-20/codex/decision_v6_repro.csv`
- `results/2026-09-20/codex/decision_v6_repro.md`
- `src/codex/2026-09-20_03_ablation_repro.py`
- `results/2026-09-20/codex/ablation_repro.csv`
- `results/2026-09-20/codex/ablation_repro.md`
- `src/codex/2026-09-20_04_dual_baseline_repro.py`
- `results/2026-09-20/codex/dual_baseline_repro.md`
- `results/2026-09-20/codex/dual_baseline_reference_checks.csv`
- `results/2026-09-20/codex/dual_baseline_edge_check.csv`
- `results/2026-09-20/codex/dual_baseline_operating_windows.csv`

## 建议 DSH 下一步

优先修正整链阈值来源文案；Q6 增加“共同阈值”和“各变体重新标定阈值”两套口径后再冻结强结论；Q7 将刀锋边缘表述改成“最长连续越限 3→4”，并将 SO3 失效阈值改为按工况健康基线标定的相对幅度或条件分位数。
