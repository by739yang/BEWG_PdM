# Q4：CWRU 诊断结论独立复核

## 最小独立实现

- 输入：`data/cwru/*.npz` 的驱动端 `DE` 信号；假定采样率 48 kHz。
- 切窗：4096 点、步长 2048；固定随机种子 20260920。
- 特征：9 个时域幅值/形状特征、频谱质心/带宽/熵、12 个 0–12 kHz 频带能量，共 24 维。
- 分类器：300 棵随机森林，`max_features=sqrt`、类别平衡。
- 防止 Normal 同段泄漏：E3 将 Normal 前/后 50% 分给训练/测试；E4 按前 2/3 与后 1/3 分割；E5 使用不同记录 Normal/N1750。
- 三种归一化：`raw`=绝对幅值+log 频带能量；`selective`=保留幅值，仅将频带能量除以总能量；`full`=每条记录先做全信号 z-score。

## 实测结果

| normalization   | experiment   | split           | model        |   train_windows |   test_windows |   accuracy |   macro_f1 |
|:----------------|:-------------|:----------------|:-------------|----------------:|---------------:|-----------:|-----------:|
| raw             | E3           | 7mil→14mil      | RandomForest |             827 |            825 |      0.435 |      0.39  |
| raw             | E4           | 7+14mil→21mil   | RandomForest |            1575 |            788 |      0.539 |      0.55  |
| raw             | E5           | 1730rpm→1750rpm | RandomForest |            2364 |            943 |      0.937 |      0.937 |
| selective       | E3           | 7mil→14mil      | RandomForest |             827 |            825 |      0.433 |      0.381 |
| selective       | E4           | 7+14mil→21mil   | RandomForest |            1575 |            788 |      0.508 |      0.522 |
| selective       | E5           | 1730rpm→1750rpm | RandomForest |            2364 |            943 |      0.951 |      0.951 |
| full            | E3           | 7mil→14mil      | RandomForest |             827 |            825 |      0.425 |      0.401 |
| full            | E4           | 7+14mil→21mil   | RandomForest |            1575 |            788 |      0.147 |      0.3   |
| full            | E5           | 1730rpm→1750rpm | RandomForest |            2364 |            943 |      0.77  |      0.709 |

## 两条结论

1. **多尺寸训练方向复现成功。** raw：E3 0.390 → E4 0.550；selective：E3 0.381 → E4 0.522。在本简化特征下，7+14mil 训练到 21mil 的宏 F1 高于仅 7mil 训练到 14mil。
2. **归一化要挑对象的方向复现成功。** 跨转速 E5：selective=0.951，full=0.709；E4：selective=0.522，full=0.300。全记录 z-score 会抹除有诊断价值的绝对幅值。

## 与 DSH 数字的关系及限制

本实现只要求方向复核，窗口、特征和 Normal 切分均与 DSH 不同，因此不声称复现 DSH 的具体 0.625/0.550。E5 的 raw/selective 得到 1.000，说明这些记录在该特征空间中很容易分开，也可能含记录级工况签名；该完美结果不得外推为真实跨厂泛化性能。每类只有少数记录，窗口不是独立设备样本。

机器可读明细：`diag_repro.csv`。
