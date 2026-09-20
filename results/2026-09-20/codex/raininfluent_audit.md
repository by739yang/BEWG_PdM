# Q9：`raininfluent.csv` 数据坑独立审计（Codex，2026-09-20）

## 结论

- **Q 列单位量级问题：确认。** 按 `bsm2_python` 随包文件的读法（首行跳过，时间列之后的第 15 个变量，即原数组第 16 列 / 0-based 列 15）核对，首个数据点为 dry `21474.0`、rain `21.474`，恰差 `1000.0` 倍。两文件 Q 列均值分别为 dry `18444.07520476545`、rain `21.304404477611943`；因为雨天序列自身形状不同，两个均值之比为约 `865.73`，不能把“逐点统一恰差 1000 倍”误写成“均值恰差 1000 倍”。rain 乘 1000 后均值为 `21304.40447761194`，与 dry 同属约 `2e4 m³/d` 量级。
- **NaN 数量：与 DSH 注释不一致。** 实测不是 1 个，而是 **3 个**，全部位于 Q 列（原数组 0-based 列 15；1-based 第 16 列）。跳过首行后的数据行 0-based 索引为 `996, 998, 999`；若把文件首行计作第 1 行，物理 CSV 行号为 `998, 1000, 1001`。因此“Q 列第 996 行 1 个 NaN”只说中了首次出现位置（按 0-based 数据行计），漏掉后两个 NaN。
- **未修正短跑：确认会报 splitter 负流量错误。** 为排除随包时间列首点 `0.01` 与模型步长 `1/96` 不完全一致造成的无关初始化错误，仅像生产脚本一样重建规则时间轴；Q 值和 3 个 NaN 均保持原样。`stabilize()` 成功（日志为 `Stabilized after 76647 iterations`），随后在 `step i=996`、即首个 Q NaN 所在数据行报错。故错误由未处理的 Q 缺失触发；“Q 小 1000 倍会让水力为负”的表述不够精确：本次可复现实验中，真正触发异常的是第一个 NaN。

## 数据与定位

包位置：

```text
C:\Users\boyi\AppData\Local\Programs\Python\Python312\Lib\site-packages\bsm2_python
```

读取口径：

```python
np.genfromtxt(path, delimiter=',', skip_header=1).astype(float)
```

| 文件 | 数组形状 | Q 第 0 行 | Q `nanmean` | NaN 总数 |
|---|---:|---:|---:|---:|
| `dryinfluent.csv` | 1343 × 22 | 21474.0 | 18444.07520476545 | 0 |
| `raininfluent.csv` | 1343 × 22 | 21.474 | 21.304404477611943 | 3 |

`raininfluent.csv` 的全部 NaN 坐标（`np.argwhere`，0-based）：

```text
[[996, 15], [998, 15], [999, 15]]
```

## 未修正数据实跑

关键构造与生产脚本一致，只重建时间轴，不修 Q、不插值：

```python
raw = np.genfromtxt(rain_path, delimiter=',', skip_header=1).astype(float)
vin = raw[:, 1:]
data_in = np.column_stack([np.arange(len(vin)) * (1/96), vin])
o = bsm2_python.BSM1OL(
    data_in=data_in,
    timestep=1/96,
    endtime=float(data_in[-1, 0]),
    evaltime=1,
)
o.stabilize()
for i in range(len(vin)):
    o.step(i)
```

实测首次异常：

```text
stabilize True
ERROR phase=step i=996 csv_data_row_0based=996
csv_line_1based_including_header=998 t=10.375000000
ValueError: Negative flow in splitter output 1 with split ratio <object type:float64>.
```

栈顶位置：

```text
bsm2_python\bsm1_base.py:228 -> self.splitter.output(...)
bsm2_python\bsm2\helpers_bsm2.py:127 -> raise ValueError(err)
```

## 审计判断

1. DSH 对 **Q 单位少 1000 倍**的判断成立，至少首点精确验证为 1000 倍，整体量级也由乘 1000 后恢复合理。
2. DSH 对 **NaN 个数**的记录不成立：随包当前文件实有 3 个，而非 1 个。
3. 未修正输入确会在首个 NaN 对应的第 996 步报 splitter 负流量错误；当前证据把直接触发因素定位为 NaN，而不是仅凭 Q 的 `1/1000` 量级。
4. DSH 现有 `load()` 会遍历所有列并插值，因此虽然注释少记了两个 NaN，实际实现仍会把 3 个都补齐；属于**文档/审计记录错误，不是当前插值代码漏修**。
