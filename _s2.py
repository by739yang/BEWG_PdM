# -*- coding: utf-8 -*-
import io
p='PROJECT_STATE.md'; s=io.open(p,encoding='utf-8').read()
old="- 统一协议（所有方法必须一致）：逐文件因果自适应标准化（120s 滑窗 + 相对离散度下限）→ 滑窗特征 → 标定期取该文件 [120s, 40%] 段 → 阈值按 0.5% 误报率标定 → 1 分钟块判决。禁止用故障标签训练或调参。"
new=("- 【已废弃 2026-09-16】以下为 v1 时代的旧描述，仅作历史记录，请勿再使用：\n"
     "  逐文件因果自适应标准化（120s 滑窗 + 相对离散度下限）→ 滑窗特征 → 标定期取该文件 [120s, 40%] 段 → 阈值按 0.5% 误报率标定 → 1 分钟块判决。\n"
     "- 【当前生效】SKAB 一律按 docs/PROTOCOL_v1.5.md 执行（标定期固定 360 s、事件化判决、四项成组指标、覆盖率三字段、严格整数判据）。\n"
     "- MetroPT-3 另立协议，不得套用 SKAB 口径。")
assert old in s, 'sec5 not found'
s=s.replace(old,new)
o2='- 冻结值（主阈值 0.995，33 个真值事件，8390 健康样本）：'
n2=('- 覆盖率字段：raw_truth_events=34、evaluable_truth_events=33、boundary_truncated_exclusions=1'
    '（other/2.csv 原始区间 [104,488)，评估自 480 起仅余 8 秒）。对外必须写成「33 个可评估事件」，'
    '不得简写成「原始数据只有 33 个事件」；换标定窗后必须重报这三个数。\n'
    '- 冻结值（主阈值 0.995，33 个可评估事件，8390 健康样本）：')
assert o2 in s, 'sec12 not found'
s=s.replace(o2,n2)
io.open(p,'w',encoding='utf-8').write(s)
print('state patched')
