# C-MAPSS FD001 RUL 基线独立复核（Codex，2026-09-19）

## 结论

**复现成功**：三种学习模型的 RMSE、PHM08、MAE、提前预测占比相对 DSH 落盘值均不超过 10% 偏差门槛。

| model                     | category        |    RMSE |   dsh_RMSE | rmse_relative_deviation   |           PHM08 |       dsh_PHM08 | phm08_relative_deviation   |     MAE | early_fraction   | within_10pct_all_reported_metrics   |
|:--------------------------|:----------------|--------:|-----------:|:--------------------------|----------------:|----------------:|:---------------------------|--------:|:-----------------|:------------------------------------|
| gradient_boosting         | learned_model   | 15.6344 |      15.27 | 2.39%                     |   426.676       |   434           | 1.69%                      | 11.5752 | 46.00%           | True                                |
| random_forest             | learned_model   | 15.8499 |      15.36 | 3.19%                     |   466.124       |   464           | 0.46%                      | 12.1724 | 39.00%           | True                                |
| ridge                     | learned_model   | 16.8112 |      16.66 | 0.91%                     |   482.59        |   482           | 0.12%                      | 13.5624 | 48.00%           | True                                |
| constant_125              | trivial_control | 64.6153 |      64.62 | 0.01%                     |     1.50248e+06 |     1.50248e+06 | 0.00%                      | 51.62   | 11.00%           | True                                |
| constant_true_mean_oracle | trivial_control | 41.5556 |      41.56 | 0.01%                     | 12229.4         | 12229           | 0.00%                      | 36.7672 | 57.00%           | True                                |

## 独立实现口径

- 数据：`C:\Users\boyi\Desktop\BEWG_PdM\data\cmapss` 中 FD001，只读；训练/测试各 100 台，官方测试真值 100 条。
- 训练：逐周期样本，从 cycle=10 起，共 19,731 行；标签 `min(末周期-cycle, 125)`，均值 85.089250。
- 测试：每台测试单元只取最后一个可见周期做一次预测；评分使用 `RUL_FD001.txt` 的官方未截断真值。
- 特征：12 个退化敏感传感器；训练集均值/样本标准差标准化后，拼接末值、最近 10 周期均值、最近 10 周期样本标准差、最近至多 30 周期的含截距精确 OLS 斜率，共 48 维。所有窗口只使用当前及过去数据。
- 模型：GBR(300 trees, depth=3, learning_rate=0.05, seed=0)；RF(200 trees, max_features=0.8, seed=42)；StandardScaler + Ridge(alpha=10)。预测统一裁剪到 [0, 300]。
- `constant_true_mean_oracle` 使用测试真值均值，仅是不可部署的 oracle 难度对照，不能作为实际预测器。

## 偏差归因

- 未读取或复用 `src/dsh/` 实现；仅从 DSH 落盘指标文件取得比较目标，因此模型参数与特征细节是 Codex 独立选择。
- 数值不要求逐位相同；剩余偏差主要来自随机森林的特征子采样/随机种子，以及两套实现可能不同的树模型参数。所有学习模型的已报告指标均在 10% 内，结论方向一致。
- FD001 是单工况、单故障模式涡扇数据，不能直接外推为污水厂现场 RUL 精度。

## 可复现命令

```powershell
python src/codex/2026-09-19_01_rul_repro.py
```

输出：`results/2026-09-19/codex/rul_repro.csv` 与 `rul_repro.md`。

## 环境与数据指纹

- Python: `3.12.10`
- NumPy: `2.5.2`；pandas: `3.0.5`；scikit-learn: `1.9.1`
- `train_FD001.txt` SHA256: `963b5e22825b34d8b21c69e1aeb4af3e647050eb672ee8834ba4b5d91d2de0f8`
- `test_FD001.txt` SHA256: `3cda7109ce17bafb5443f2ac926cfcf88154b941b8c4cf95eb55d1ddd6f52851`
- `RUL_FD001.txt` SHA256: `a19c8ec94931949d0485bdc35118206e9c81c4547b422efb9cf86f4ceddbceca`
