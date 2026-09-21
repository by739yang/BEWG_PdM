# Q14：`lanmai` CLI 独立复核

- 任务单日期：2026-09-22
- 实际执行日期：2026-09-21（按用户要求提前执行未来任务单）
- 约束：只读 `src/lanmai/` 与输入数据，未修改工具源码或 `data/`。
- 环境：在项目根目录设置 `PYTHONPATH=src` 后运行 `python -m lanmai ...`。

## ① 内置 selftest

命令：

```powershell
$env:PYTHONPATH='src'
python -m lanmai selftest | Tee-Object results/2026-09-22/codex/q14_selftest.txt
```

**通过。** 阶跃产生 5 个告警，等级 `{2: 5}`，全部为 P2；慢漂移产生 11 个告警，等级 `{2: 6, 1: 4, 3: 1}`，同时出现 P1 与 P3。Windows 控制台中文因编码显示为乱码，但数字与分级可读取。

## ② SKAB 分号文件、白名单与 watch

显式白名单：

```text
Accelerometer1RMS,Accelerometer2RMS,Current,Pressure,Temperature,Thermocouple,Voltage,Volume Flow RateRMS
```

复现命令（输入为 SKAB 无故障分号文件）：

```powershell
python -m lanmai inspect data/SKAB-master/data/anomaly-free/anomaly-free.csv --channels 'Accelerometer1RMS,Accelerometer2RMS,Current,Pressure,Temperature,Thermocouple,Voltage,Volume Flow RateRMS'
python -m lanmai calibrate data/SKAB-master/data/anomaly-free/anomaly-free.csv --channels 'Accelerometer1RMS,Accelerometer2RMS,Current,Pressure,Temperature,Thermocouple,Voltage,Volume Flow RateRMS' --state hour --ref '0,0.3' --output results/2026-09-22/codex/q14_skab_baseline.json
python -m lanmai watch data/SKAB-master/data/anomaly-free/anomaly-free.csv --baseline results/2026-09-22/codex/q14_skab_baseline.json --output results/2026-09-22/codex/q14_skab_alarms.csv
```

**分号自动识别通过，`calibrate` 白名单通过。** 工具读到 9405 行、1 秒中位采样间隔、8 个通道；baseline JSON 的 `channels` 与上述白名单一致。实测阈值为 3.583；watch 得到 5 个告警（P2=3、P3=2、P1=0）。这与手册旧示例的 3.560/3 个告警略有差异，本报告保留当前版本、当前 8 通道显式白名单下的实测值。

另发现一个独立缺陷：**`inspect --channels` 参数被忽略**。`src/lanmai/cli.py` 的 `cmd_inspect` 经 `_read()` 固定以 `load_table(..., None)` 读取，所以上述 inspect 命令虽传了白名单，输出列数并不受它约束；相同参数在 `calibrate` 中有效。此缺陷不影响本项对分号识别与 calibrate 白名单的判定，且按约束未修改 `src/lanmai/`。

## ③ BSM1 冻结通道首报

使用健康轨迹第 30–45 天标定，并在退化轨迹上 watch；显式排除零方差 `kla_sum`，采用手册基线的 7 个过程通道：

```text
SO3,SO4,SO5,SNH_eff,Ntot_eff,TSS_eff,sludge_h
```

关键参数：

```text
--state hour --ref 0.25,0.375 --warmup 20D
```

**通过。** 标定窗为 `1970-01-31 00:00:00` 至 `1970-02-14 23:45:00`，1440 行，阈值 20.807574（CLI 显示 20.808）。watch 共 6 个告警（P1=3、P3=3）。所有事件中的最早 ratio 告警在第 26.80 天左右，但验收项要求的**冻结通道首报**为 `1970-02-10 06:45:00`，相对 `1970-01-01 00:00:00` 为 **40.28125 天（40.28 天）**，与研究链路口径一致。

## ④ MetroPT-3 三段标定与阈值策略

命令核心参数：

```text
--channels TP2,TP3,H1,Oil_temperature,Motor_current
--state col --state-col state
--ref 0,0.23
--ref-segments 0,0.08;0.09,0.17;0.26,0.34
--thr-policy median   # 另跑 upper
```

三段独立阈值实测为 4.482、4.608、10.407，因此：

- 最小值：4.482
- 中位数：4.608
- 最大值：10.407
- 极差比：10.407 / 4.482 = **2.32**
- `median` 输出阈值：4.608
- `upper` 输出阈值：10.407

**通过。** JSON/控制台中的范围统计与策略输出自洽。与手册旧值 4.418 / 4.528 / 10.431、2.36 倍略有差异，属于当前运行实测差异，不回填旧数字。

## ⑤ `TSS_eff` 时间列边界

命令：

```powershell
python -m lanmai inspect results/2026-09-21/lanmai_demo/bsm1_120d_degraded_ts.csv --channels TSS_eff
```

**时间列识别通过。** 尽管 `TSS_eff` 位于真实 `timestamp` 列之前，工具仍识别起点 `1970-01-01 00:00:00`、终点 `1970-04-30 23:45:00`、中位采样间隔 900 秒；`TSS_eff` 未被误判为时间列。

但该命令同时再次暴露 `inspect --channels` 被忽略：输出仍列出 9 个数值列，而不是只列 `TSS_eff`。这是参数传递缺陷，不是时间列误判。

## 总结

| 验收项 | 判定 | 实测证据 |
|---|---|---|
| selftest 阶跃/慢漂移 | 通过 | 阶跃 5 个全 P2；慢漂移 11 个且含 P1/P3 |
| SKAB 分号与白名单 | 通过（附缺陷） | 9405 行、1 s、8 通道；calibrate 白名单生效；inspect 白名单被忽略 |
| BSM1 frozen 首报 | 通过 | 40.28125 天，即 40.28 天 |
| 多段阈值范围/策略 | 通过 | 4.482 / 4.608 / 10.407，极差比 2.32；median/upper 自洽 |
| `TSS_eff` 不作时间列 | 通过 | 时间范围与 900 s 采样间隔正确 |

原始控制台、JSON 与告警 CSV 均保存在本目录的 `q14_*` 文件中。
