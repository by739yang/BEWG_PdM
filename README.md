# 澜脉——面向污水厂关键设备的 AI 预测性维护系统

> 参赛：北控水务杯第九届中国国际生态环境创新大赛 · 创意转化组 · 命题方向 2-6
> 报名截止 2026-10-15 ｜ 纯软件、无实物 ｜ 团队项目

## 目录导航

    PROJECT_STATE.md                    唯一事实来源：比赛信息、红线、协议、冻结结论与待办
    协作约定.md                          多助手分工与产物规则
    tasks/                              按日期归档的任务单
    src/dsh/  src/codex/                两套独立实现
    results/YYYY-MM-DD/dsh/             DSH 产物
    results/YYYY-MM-DD/codex/           Codex 产物
    handoff/                            两个助手之间的口径确认与差异报告
    docs/PROTOCOL_v1.5.md               SKAB 当前冻结协议
    docs/metropt3_fault_windows.json    MetroPT-3 官方故障窗口
    logs/实验日志.md                     只追加的实验记录
    data/                               本地数据集，不进入版本库

## 当前状态（2026-09-16）

- SKAB 已按 `PROTOCOL_v1.5` 收口；冻结结果见 `PROJECT_STATE.md` 第 12 节。
- MetroPT-3 仍是探索性验证；迟到命中和健康时长分母正在冻结，未对齐数字不得用于 BP。
- 2026-09-17 的后续任务见 `tasks/2026-09-17_codex.md`。

## 环境安装

推荐 Python 3.12。仓库的 `requirements.txt` 记录了当前复现实验环境；其中 PyTorch 使用 CUDA 12.8 构建。

```powershell
cd C:\Users\boyi\Desktop\BEWG_PdM
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

当前验证环境：Python 3.12.10、torch 2.9.1+cu128（RTX 5060 Laptop）。如机器没有兼容的 NVIDIA 驱动，可先运行不依赖 Torch 的传统基线脚本。

## 关键复现入口

### SKAB 冻结协议独立实现

```powershell
python src/codex/2026-09-15_05_protocol_v11.py
python src/dsh/2026-09-15_16_protocol_v14.py
python src/dsh/2026-09-15_17_crosscheck_v14.py
```

协议和冻结结果分别见：

- `docs/PROTOCOL_v1.5.md`
- `results/2026-09-15/protocol_v14_crosscheck_final.md`

### MetroPT-3 Codex 探索性基线

```powershell
python src/codex/2026-09-16_00_fetch_metropt3.py
python src/codex/2026-09-16_01_metropt3_baseline.py
```

结果写入 `results/2026-09-16/codex/`。MetroPT-3 尚未冻结，不能只摘取单个最佳 DET 点对外宣传。

### 早期 DSH 方法对比

```powershell
python src/dsh/2026-09-15_05_main_comparison.py
python src/dsh/2026-09-15_06_conv_autoencoder.py
python src/dsh/2026-09-15_07_changepoint_fusion.py
```

这些早期结果保留作研究轨迹；对外数字以 `PROJECT_STATE.md` 第 12 节冻结区为准。

## 自动检查

GitHub Actions 的 `.github/workflows/python-syntax.yml` 会对 `src/` 下 Python 文件执行语法编译检查。涉及数据和 GPU 的完整实验仍需按上述命令在本地复现。

## 诚信声明

所有指标均由仓库内脚本可复现；仿真数据一律标注“仿真”；未使用任何他人项目素材；团队获奖记录系团队成果，如实注明。

## 开源说明

比赛评审期间本仓库保持私有。
