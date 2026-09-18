# 2026-09-18 codex_to_dsh —— RUL 修复完成；MetroPT-3 冻结分母与自有模型统一事件机复评

来源：Codex ｜ 时间：2026-09-18

## 一、RUL 流程修复

复现命令：

```powershell
python src/codex/2026-09-18_01_rul_fix.py
```

产物：

- `results/2026-09-18/codex/rul_repro.csv`
- `results/2026-09-18/codex/rul_repro.md`
- `results/2026-09-18/codex/rul_repro_per_unit.csv`

结果：训练改为逐周期样本（cycle ≥ 10），共 19,731 行；训练标签均值 85.089250；测试使用官方未截断 RUL。GBR/RF/Ridge RMSE = 19.648450 / 21.330567 / 21.503505；相对 DSH 参考 19.73 / 21.03 / 21.49 的差异分别为 -0.082 / +0.301 / +0.014，均通过 ≤0.5 RMSE 的复核标准。

## 二、MetroPT-3 冻结分母复算

复现命令：

```powershell
python src/codex/2026-09-18_02_metropt3_frozen.py
```

产物：

- `results/2026-09-18/codex/metropt3_metrics_frozen.csv`
- `results/2026-09-18/codex/metropt3_metrics_frozen.md`
- `results/2026-09-18/codex/metropt3_metrics_frozen_events.csv`

冻结交集分母严格为 healthy_all_stable=96,270 分钟、healthy_running=43,136 分钟。当前 Codex 主阈值 6.0 的统一事件机结果为：557 次告警；timely/late/miss=2/0/2；误报 555；误报率 0.345902 次/全稳定小时、0.771977 次/running 小时；TIA-H=36.3602%/46.0636%。DET 表含 30 个阈值点。

## 三、诊断模块 BP 边界

产物：`results/2026-09-18/codex/diagnosis_boundary.md`

结论：宏 F1=1.000 只能放在“诊断模块原型的公开基准链路/同记录时间切分能力验证”部分；不能写成现场部署准确率、跨记录/跨转速/跨故障尺寸泛化能力或污水厂设备实际效果。

## 四、补充任务：自有分数流 + 统一事件机

复现命令：

```powershell
python src/codex/2026-09-16_01_metropt3_baseline.py
python src/codex/2026-09-18_04_metropt3_ownmodel_unified.py
```

产物：

- `src/codex/2026-09-18_04_metropt3_ownmodel_unified.py`
- `results/2026-09-18/codex/metropt3_ownmodel_unified.csv`
- `results/2026-09-18/codex/metropt3_ownmodel_unified.md`
- `results/2026-09-18/codex/metropt3_ownmodel_unified_events.csv`
- `results/2026-09-18/codex/metropt3_ownmodel_unified_primary.json`

主阈值 6.0 逐故障延迟：F2=-11 分钟、F3=-6 分钟；F1/F4 miss。延迟中位数 -8.5 分钟。30 点 DET 与所有请求字段均已落盘。脚本还对主工作点用 `src/codex/2026-09-16_01_metropt3_baseline.py` 的参考事件机做了逐事件一致性校验。

与 DSH 模型并列时，请保留 DSH 的冻结结果（阈值 2.395：205/2/1/1/201/0.1253/11.6%）作为 DSH 行；Codex 自有模型阈值 6.0 的行如上。阈值数值本身不能直接横比，剩余差异归因于模型分数流。

## 五、日志与边界

已在 `logs/实验日志.md` 追加本次五段式记录。没有修改 `src/dsh/`、`results/*/dsh/`，没有写入 `data/`。MetroPT-3 仍只有 4 个粗粒度真值故障窗，所有 DET/延迟数字仅作探索性证据；RUL 仅为 C-MAPSS FD001 单工况单故障模式。

## 需要 DSH 做什么

请读取本文件指向的 Codex 产物，将 `metropt3_ownmodel_unified.csv/.md` 与 DSH 冻结结果并列；如要写入 BP，继续等待协议冻结后的双方共同表述，不把 Codex 主阈值 6.0 与 DSH 阈值 2.395 直接当作同一工作点。
