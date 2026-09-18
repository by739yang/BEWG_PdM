# 2026-09-17 Codex → DSH：MetroPT-3 掩码与 DET v2、C-MAPSS RUL 独立复核

来源：Codex ｜ 任务日期：2026-09-17 ｜ 完成复核：2026-09-18

## 一、已完成产物

脚本：

- `src/codex/2026-09-17_02_metropt3_masks_det.py`
- `src/codex/2026-09-17_00_fetch_cmapss.py`
- `src/codex/2026-09-17_01_rul_baseline.py`

可复现命令：

```powershell
cd C:\Users\boyi\Desktop\BEWG_PdM
python src/codex/2026-09-17_02_metropt3_masks_det.py
python src/codex/2026-09-17_00_fetch_cmapss.py
python src/codex/2026-09-17_01_rul_baseline.py
```

产物均落在 `results/2026-09-17/codex/`，且本轮未修改 `src/dsh/`、`results/*/dsh/` 或 `data/`。

## 二、逐分钟掩码字段与整数

导出文件：

- `results/2026-09-17/codex/metropt3_masks_codex.npz`
- `results/2026-09-17/codex/metropt3_masks_codex.csv.gz`
- `results/2026-09-17/codex/metropt3_mask_counts_codex.json`

CSV/NPZ 的核心字段为：

- `in_eval_domain`
- `score_finite`
- `stable_state`
- `running_state`
- `in_fault_window`
- `in_quarantine`

另保留 `in_eval_domain_A`、`in_eval_domain_B`、`timestamp`，CSV 中还保留 `state`、`score` 便于逐分钟定位。

时间轴共 252,720 个分钟桶。`in_eval_domain` 兼容字段取 Codex 的 B 域；A/B 域均单独保留。

### Codex A 域

A 域定义为自官方首故障窗 `2020-04-18 00:00` 起：

|计数项|Codex|
|---|---:|
|eval_domain|159,515|
|score_finite|113,790|
|stable_state|138,983|
|running_state|65,677|
|in_fault_window|4,960|
|in_quarantine|121,421|
|healthy_all_stable（域内、finite、stable、非故障）|108,854|
|healthy_running|50,912|

### Codex B 域

B 域定义为 A 域再排除四段固定标定窗：

|计数项|Codex|
|---|---:|
|eval_domain|132,088|
|score_finite|113,790|
|stable_state|115,087|
|running_state|56,410|
|in_fault_window|4,960|
|in_quarantine|121,421|
|healthy_all_stable（域内、finite、stable、非故障）|108,854|
|healthy_running|50,912|

### 与 DSH 数字的对照

DSH 提供的目标整数为：

- A：`159,515 / 132,963 / 64,352`
- B：`132,088 / 109,203 / 54,426`

其中域分钟已经完全一致。Codex 与 DSH 的健康分钟仍未完全对齐：

- B `healthy_all_stable`：Codex `108,854`，DSH `109,203`，差 `-349` 分钟。
- B `healthy_running`：Codex `50,912`，DSH `54,426`，差 `-3,514` 分钟。
- A `healthy_all_stable`：Codex `108,854`，DSH `132,963`，差 `-24,109` 分钟。
- A `healthy_running`：Codex `50,912`，DSH `64,352`，差 `-13,440` 分钟。

差异定位：

1. Codex 的 `score_finite` 只在 Codex walk-forward 实际产生分数的分钟为真；A/B 内均为 `113,790`。DSH 导出的对应字段在其 NPZ 中为全时间轴有限，因此 A/B 分别多出 `45,725` / `18,298` 个“有限分数”分钟。两边的 `score_finite` 语义尚未一致。
2. 在 B 域，Codex 的健康 all-stable 比 DSH 少 349 分钟，说明在把有限分数语义统一后，仍有 stable/切换定义差异；running 差异更大，主要集中在运行状态判定。
3. Codex 的 `in_quarantine` 是按原 Codex 在线逻辑重建的“阻止基线更新”状态，不参与健康分母剔除；B 域计数为 `121,421`。该数字较大，冻结前建议按分钟逐项审计触发与延长规则。

因此 MetroPT-3 仍不应冻结；下一步应先逐分钟对比 `score_finite`、`stable_state`、`running_state` 的 XOR 集合，再统一定义。

## 三、DET v2（timely / late / miss）

产物：

- `results/2026-09-17/codex/metropt3_det_v2.csv`
- `results/2026-09-17/codex/metropt3_det_v2.md`

判据：

- `timely`：告警起点落在 `[g0-60min, g0+60min]`，计主召回；
- `late`：没有 timely，且告警起点落在 `(g0+60min, g1]`，单列；
- 其余为 `miss`。

Codex 主阈值为原 Codex 基线的 `threshold=6.0`：

- timely `2`
- late `0`
- miss `2`
- 主召回 `50% (2/4)`
- 健康分钟 `185,263`，健康小时 `3,087.7167`
- 误报事件 `1,004`
- 误报事件 / 健康小时 `0.325159`
- TIA-H `0.271770`
- timely 延迟中位数 `-12.5 min`

DET 扫描最佳点（按最高 timely recall、再按最低误报率排序）为 `threshold=30`：

- timely `3/4`，即 `75%`
- late `0`
- miss `1`
- 误报事件 / 健康小时 `0.039188`
- TIA-H `0.041249`
- timely 延迟中位数 `19 min`

所以 Codex 原先的 75% 点仍然是 timely 命中，并不是靠 late 命中；但主阈值下仍为 `2/4`。Codex DET 的健康分母沿用原 walk-forward 评分域 `185,263`，不等同于共同 A/B 掩码中的 `healthy_all_stable`，这里不应直接和 DSH 的 A/B 分母混报。

## 四、C-MAPSS FD001 RUL 独立基线

数据获取脚本只写用户缓存：

`C:\Users\boyi\.cache\BEWG_PdM\cmapss`

没有写入仓库 `data/`。manifest：

`results/2026-09-17/codex/cmapss_fetch_manifest.json`

数据规模：100 台训练发动机、20,631 个训练周期、100 台测试发动机。训练标签使用 `min(max_cycle-cycle, 125)`。

正式基线结果：

|模型|RMSE|PHM08|MAE|
|---|---:|---:|---:|
|Ridge|73.157|242031.922|61.289|
|Gradient Boosting（Huber）|84.449|519294.637|73.277|

另有透明对照 `constant_train_median`：RMSE `49.820`、PHM08 `166570.543`，不计入两个正式基线。该对照优于当前两个学习模型，说明这版特征/训练设置仍不够强，不能拿 Ridge/GB 结果包装成现场精度。

产物：

- `results/2026-09-17/codex/rul_baseline.csv`
- `results/2026-09-17/codex/rul_baseline_per_unit.csv`
- `results/2026-09-17/codex/rul_baseline.md`

C-MAPSS 只能证明 RUL 训练—测试—评分链路可复现。迁移到水泵/鼓风机时，需要将发动机周期换成运行小时/启停次数/负荷积分，引入振动、温度、电流、压力、流量等工况条件特征，并处理维护后的状态重置与右删失，不能直接外推精度。

## 五、当前结论与下一步

1. 三项任务的 Codex 脚本和主要产物均已落盘；掩码域分钟已与 DSH 完全一致。
2. DET 新判据下，Codex 主阈值为 `2/4 timely`，扫描最佳为 `3/4 timely`，late 均为 `0`。
3. MetroPT-3 健康分钟尚未冻结；优先逐分钟对齐 score finite、stable、running，再决定是否重算共同分母。
4. C-MAPSS Codex 结果明显弱于 DSH 结果，且常数中位数对照更好；应作为“独立实现未复现、特征仍需改进”的结果保留，不应强行贴合 DSH 数字。
