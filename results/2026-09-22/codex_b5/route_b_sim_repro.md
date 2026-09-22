# Q18 路线 B 整厂仿真独立复核

本脚本从官方 `bsm2_python` 的 `BSM2Base`、官方动态进水和官方 Dewatering 独立运行 160 天；没有导入 DSH 路线 B 公共模块。退化注入是 Dewatering 的 `dw_par[0]` 从 28% 于第 60 天开始在 60 天内线性降到 18%。

## 结果

| official_package                                                                    |   days |   timestep_days |   steps |   healthy_seconds |   degraded_seconds |   nan_count |   truth_failure_day |   target_end |   healthy_late_cake_flow |   degraded_late_cake_flow |   late_flow_increase_pct |   healthy_end_solids |   degraded_end_solids | simplified_model                                                                                                              | caveat                                                                                              |
|:------------------------------------------------------------------------------------|-------:|----------------:|--------:|------------------:|-------------------:|------------:|--------------------:|-------------:|-------------------------:|--------------------------:|-------------------------:|---------------------:|----------------------:|:------------------------------------------------------------------------------------------------------------------------------|:----------------------------------------------------------------------------------------------------|
| C:\Users\boyi\AppData\Local\Programs\Python\Python312\Lib\site-packages\bsm2_python |    160 |       0.0104167 |   15359 |             69.72 |               60.3 |           0 |                 109 |           18 |                  9.54068 |                   14.8388 |                  55.5319 |                   28 |                    18 | ['official BSM2Base', 'official dynamic influent', 'official Dewatering', 'dw_par[0] ramps 28->18% from day 60 over 60 days'] | This is an idealized unit-model route-B simulation; it contains no blockage or dewatering dynamics. |

- 真值失效：第 **109.00 天**（泥饼含固率 <20% 连续 1 天）。
- 末期湿泥饼量（t≥150 天均值）相对健康：**+55.53%**。
- 全厂旁证：本独立循环同时记录滤液、消化进泥、气体/能耗等输出；这些是同一官方整厂状态的可测量旁证，不代表每个旁证都会对 Dewatering 退化敏感。
- 原始五通道检出不足的检测结论见 Q19；不能把该负结果外推为所有设备、所有工况的普遍定律。

## 模型简化和可复现边界

官方 BSM2Base 的这个闭环仍是理想单元：没有堵塞、滤布污染、执行器迟滞或额外脱水动力学；退化只作用于 `dw_par[0]`。因此 +55.53% 是本配置与本轨迹的仿真读数，不是现场泛化性能。
