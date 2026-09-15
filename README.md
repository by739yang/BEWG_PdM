# BEWG_PdM —— 面向污水厂关键设备的 AI 预测性维护系统

> 参赛：北控水务杯第九届中国国际生态环境创新大赛 · 创意转化组 · 命题方向 2-6
> 报名截止 2026-10-15 ｜ 纯软件、无实物 ｜ 团队项目

## 目录导航（按日期归档）
    PROJECT_STATE.md              唯一事实来源：比赛信息、红线、数据协议、结论、待办
    协作约定.md                    多助手分工与产物规则
    tasks/                        每天的任务单    tasks/2026-09-15_codex.md
    src/dsh/  src/codex/          每天的脚本      src/dsh/2026-09-15_05_main_comparison.py
    results/2026-09-15/dsh/       当天结果表/图
    results/2026-09-15/codex/     第二助手的产物（skab_repro / review_dsh / metropt3_audit）
    handoff/                      两个助手之间的对话（YYYY-MM-DD_<谁>_to_<谁>.md）
    docs/PROTOCOL_v1.md           冻结的评测协议（未冻结前数字禁止对外）
    docs/01_项目速览.md          给王家兴看的一页纸（人话版）
    docs/02_倒排工期到10-07.md    里程碑与材料准备倒排
    logs/实验日志.md               追加式实验记录
    data/                         数据集（不进版本库，见 data/README.md）

## 当天工作怎么找
打开 results/日期/ 就能看到当天两个助手各自产出了什么。

## 复现
    cd C:\Users\boyi\Desktop\BEWG_PdM
    python src/dsh/2026-09-15_05_main_comparison.py
    python src/dsh/2026-09-15_06_conv_autoencoder.py
    python src/dsh/2026-09-15_07_changepoint_fusion.py

## 环境
Python 3.12 ｜ torch 2.9.1+cu128（RTX 5060 Laptop）｜ pandas / scikit-learn / scipy / matplotlib

## 诚信声明
所有指标均由仓库内脚本可复现；仿真数据一律标注"仿真"；未使用任何他人项目素材；团队获奖记录系团队成果，如实注明。

## 开源说明
比赛评审期间本仓库保持私有。
