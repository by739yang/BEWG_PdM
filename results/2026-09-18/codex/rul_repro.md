# C-MAPSS FD001 RUL 流程修复复现（Codex，2026-09-18）

## 修复点

- 训练样本为逐周期样本，而不是每台单元最后一周期：跳过前 `9` 个周期后共 `19,731` 行。
- 训练标签为 `min(max_cycle - cycle, 125)`；测试评估使用官方 `RUL_FD001.txt` 未截断真值。
- 训练标签均值：`85.089250`；测试单元数：`100`。
- 特征为 12 个常用传感器在最近 10 周期的 last/mean/std 与 5-vs-10 周期趋势差；不把测试集可见的末周期位置特征混入模型。

## 结果

| model                            | category           |     RMSE |            PHM08 |     MAE |   train_rows |   train_label_mean |   test_prediction_mean |   test_units |   label_cap |
|:---------------------------------|:-------------------|---------:|-----------------:|--------:|-------------:|-------------------:|-----------------------:|-------------:|------------:|
| gradient_boosting                | learned_model      |  19.6484 |   1019.96        | 14.5511 |        19731 |            85.0893 |                78.2352 |          100 |         125 |
| random_forest                    | learned_model      |  21.3306 |   2243.42        | 15.4588 |        19731 |            85.0893 |                78.8088 |          100 |         125 |
| ridge                            | learned_model      |  21.5035 |   1190.37        | 16.969  |        19731 |            85.0893 |                78.9767 |          100 |         125 |
| constant_125                     | trivial_control    |  64.6153 |      1.50248e+06 | 51.62   |        19731 |            85.0893 |               125      |          100 |         125 |
| constant_true_mean_oracle        | trivial_control    |  41.5556 |  12229.4         | 36.7672 |        19731 |            85.0893 |                75.52   |          100 |         125 |
| constant_train_median_diagnostic | diagnostic_control |  47.2464 | 101157           | 37.42   |        19731 |            85.0893 |                98      |          100 |         125 |
| trend_extrapolation              | trivial_control    | 116.035  |      1.13307e+10 | 91.8578 |        19731 |            85.0893 |               130.014  |          100 |         125 |

## 与 DSH 参考的偏差判定

- `gradient_boosting`：Codex RMSE=19.648，DSH 参考=19.73，差=-0.082；通过（差异 ≤ 0.5 RMSE）。
- `random_forest`：Codex RMSE=21.331，DSH 参考=21.03，差=+0.301；通过（差异 ≤ 0.5 RMSE）。
- `ridge`：Codex RMSE=21.504，DSH 参考=21.49，差=+0.014；通过（差异 ≤ 0.5 RMSE）。

## 解释与限制

- `constant_true_mean_oracle` 使用测试真值均值，只作难度参考，不能作为可部署预测器。
- `constant_train_median_diagnostic` 专门用于检查训练标签/样本构造；它不代表正式模型。
- FD001 是单工况公开基准，不能直接声称污水厂设备现场 RUL 精度。
- 数据从用户缓存读取：`C:\Users\boyi\.cache\BEWG_PdM\cmapss`；本脚本未写入 `data/`。
