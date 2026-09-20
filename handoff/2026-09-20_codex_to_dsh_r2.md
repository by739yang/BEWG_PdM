# 2026-09-20 Codex → DSH：批次 3 交接（Q9 / Q10 / Q12 / Q8 / Q11）

来源：Codex ｜ 日期：2026-09-20

## 完成情况

已严格按 `tasks/2026-09-20_codex_batch3.md` 的顺序完成 Q9 → Q10 → Q12 → Q8 → Q11。Q8、Q11 脚本均通过 `py_compile` 并从头重跑；Q8 CSV 为 24 行（12 场景 × 2 窗口模式），Q11 CSV 为 8 行（4 变体 × 2 阈值口径）。最终未修改 `src/dsh/`、`results/*/dsh/`、`data/`、`PROJECT_STATE.md` 或 `tasks/codex_batch_queue.md`。

## 关键结论

### Q9：raininfluent 数据坑

1. Q 列首点 dry/rain 为 `21474.0 / 21.474`，恰差 1000 倍；Q 均值为 `18444.07520476545 / 21.304404477611943`。
2. 随包 `raininfluent.csv` 实有 **3 个 NaN**，不是 DSH 注释中的 1 个；0-based 坐标为 `[996,15]、[998,15]、[999,15]`。
3. 不修 Q、不插值，仅重建规则时间轴后，`stabilize()` 成功并在 `step i=996` 报 `ValueError: Negative flow in splitter output 1...`。直接触发因素是首个 Q NaN。DSH 当前遍历全列插值的实现会补齐 3 个，问题在注释/审计记录而非插值漏修。

### Q10：P1–P5 修正审计

- P1、P2、P4、P5：**已生效**。
- P3：**部分生效**。源码运行输出完整写明门禁是 retrospective、使用告警后数据且不可在线；但落盘 Markdown/JSON 只保留“事后”，没有持久化“使用未来数据 / 不可用于在线决策”。
- 独立只读复算：阈值 `2.395` 与 `2.3954` 均为 205 个事件、201 个误报；分数流 MD5 前 12 位为 `ade8c0e00922`。

### Q12：全量复现

- 实跑 `python run_all.py --full` 返回码 0，**18/18 阶段通过**。
- 内部总耗时 `229.3 s`，外层墙钟 `229.328 s`；DSH 日志为 `225.2 s`，差 1.8%。
- MetroPT-3：timely 2、误报 201、FP/h 0.1253、TIA-H 11.6%、主阈值 13.1393，全部一致。
- C-MAPSS GBR：RMSE 15.27、PHM08 434.0，一致。
- BSM1：29 个 CSV、211,438 行、列数合计 274；29/29 形状和 SHA-256 均不变。4 个分析汇总 CSV 只刷新 mtime。全量运行产生的两个 DSH 耗时字段差异已留证后恢复，最终禁止路径无修改。

### Q8：比值判据/组合策略重大口径错误

1. BSM1 CSV 实测为 **96 点/天**，真实 5 天窗应为 `5×96=480` 点。DSH 两个脚本使用 `rolling(5*1440)=7200` 点，在该数据上实际是 **75 天窗口**：
   - `src/dsh/2026-09-20_13_ratio_rule.py:31`
   - `src/dsh/2026-09-20_14_alarm_strategy.py:32`
2. `legacy_7200_samples` 兼容模式精确复现 DSH 的 ratio base 与关键延迟，证明“健康零越限 + 长延迟”来自 75 天累计平滑，而不是 5 天判据。
3. 真实 5 天主结果：k=1.3 健康越限占比为 `0.514–0.948`，0/12 场景为零；健康单点/P1 事件为 `47/46`，仅降 2.1%；单点/比值/P1 检出为 `6/12、12/12、6/12`。两者均检出的 6 场中，比值更晚 0、更早 6，但这些首越限也存在于健康运行，是非特异漂移。慢漂移 P1 检出 1/4，并非 0/4。
4. DSH `alarm_strategy.py:57-61` 的健康单点/P1事件还未应用文字声明的第 45–120 天统一评估窗。
5. 因此 Q8 三条方向在“真实 5 天 + 统一评估窗”下均未完整复现。不得再把已发布 7200 点结果称为“5 天滚动判据”，应修为基于 `t_day` 的时间窗或 480 点后重跑冻结。

### Q11：消融两套公平阈值口径

| 变体 | 共享阈值 6：事件 / timely / FP | 各自健康 q0.995：阈值 / 事件 / timely / FP |
|---|---:|---:|
| V0 工况化+派生+top3 | 557 / 2 / 555 | 24.072 / 110 / 2 / 108 |
| V1 无工况条件化 | 233 / 2 / 231 | 41.509 / 61 / 3 / 58 |
| V2 去派生特征 | 582 / 2 / 580 | 22.420 / 111 / 2 / 109 |
| V3 max 聚合 | 593 / 1 / 592 | 33.504 / 108 / 2 / 106 |

每个变体的健康标定分数为 31,564 个。明确判定：

- “无工况条件化 = 0 告警”：**两套口径均不成立**。
- “去派生特征 = timely 归零”：**两套口径均不成立**。
- “max 聚合召回更差”只在共享阈值下成立；各自标定后 V3 与 V0 都是 timely=2。

## 可复现命令

```powershell
python -m py_compile src/codex/2026-09-20_05_ratio_rule_repro.py
python -m py_compile src/codex/2026-09-20_06_ablation_two_regimes.py
python src/codex/2026-09-20_05_ratio_rule_repro.py
python src/codex/2026-09-20_06_ablation_two_regimes.py
python run_all.py --full
```

## 产物

- `results/2026-09-20/codex/raininfluent_audit.md`
- `results/2026-09-20/codex/pipeline_fix_audit.md`
- `results/2026-09-20/codex/full_repro_audit.md`
- `results/2026-09-20/codex/full_repro_raw_log.txt`
- `src/codex/2026-09-20_05_ratio_rule_repro.py`
- `results/2026-09-20/codex/ratio_rule_repro.csv`
- `results/2026-09-20/codex/ratio_rule_repro.md`
- `src/codex/2026-09-20_06_ablation_two_regimes.py`
- `results/2026-09-20/codex/ablation_two_regimes.csv`
- `results/2026-09-20/codex/ablation_two_regimes.md`

## 需要 DSH 做什么

优先修正并重跑 Q8：把滚动窗从 7200 点改为基于 `t_day` 的 5 天或 480 点，同时统一健康事件的第 45–120 天评估窗；撤回/改写“5 天零误报、显著更晚、与门 77→26 且慢漂移 4/4 全漏”的冻结表述。其次把 Q9 的 NaN 记录改为 3 个，把 Q10/P3 的“使用告警后数据、不可在线”写入 Markdown 和 JSON。Q11 两条强结论应收窄为 DSH 特定实现/阈值下的观察，不应冻结为跨实现规律。

产物落盘：`results/2026-09-20/codex/`、`src/codex/`；本交接文件：`handoff/2026-09-20_codex_to_dsh_r2.md`。
