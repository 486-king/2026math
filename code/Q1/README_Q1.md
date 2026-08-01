# 舰船烟幕遮蔽干扰优化：问题一编程实现

## 任务范围

本工程只完成问题一的编程手工作：固定单烟幕的 G1 纯追踪、S1 起爆后云心固定、O0 舰船完整圆盘覆盖、U0 名义无风漂模型；建立连续事件、解析和向外舍入三重证书；输出最大连续遮蔽补偿族；提供场景输入与可达性检查接口。

本工程不包含 Q2 多烟幕联合覆盖、Q3 多机协同、Q4 多目标调度，不撰写论文正文，也不把有限网格当作连续覆盖证明。

## 数学前提与核心区分

在导弹于 8000 m 处已经锁定的标准 G1 场景中，固定单烟幕结构上界为 `10.376134889753567 s`，探测窗口下界为 `24.167709255134113 s`。因此全窗口持续完整遮蔽在结构上不可行，但最大连续遮蔽补偿族仍存在。

`T_structural_max` 是固定单烟幕结构上界；`T_executable_star` 是真实绝对场景中经过命令、航程、释放点、12 km 等约束筛选后的可执行最优值。没有真实场景输入时，两者不得相等。

## 四类状态

- `execution_status`：程序是否正常完成。
- `input_status`：真实场景输入是否完整或因缺失/歧义而阻塞。
- `feasibility_status`：结构或执行层的数学可行性。
- `certificate_status`：证书已验证、条件成立、失败或未评估。

缺少真实场景时，预期状态为：程序完成、输入阻塞、全窗口结构不可行证书成立、可执行最优未评估。`blocked_missing_scenario` 不是代码失败。

## 安装与运行

选择带有 NumPy、SciPy、pandas和 Matplotlib 的 Python 3.12+：

```powershell
<PYTHON> -m pip install -r code/Q1/requirements-q1.txt
<PYTHON> code/Q1/q1_run.py --all
```

单独运行各证书或交付模块：

```powershell
<PYTHON> code/Q1/q1_interval_certificate.py
<PYTHON> code/Q1/q1_parametric_compensation.py
<PYTHON> code/Q1/q1_robustness.py
<PYTHON> code/Q1/q1_architecture_upgrade.py
```

发布前正式测试已经执行，测试源码按交付策略删除。摘要保存在
`code/Q1/reviews/q1_final_validation.json`；生产入口不调用 pytest，也不依赖 `tests/`。

## 结果位置

- 四轮指标：`results/Q1/experiments/round1` 至 `round4`。
- 图表和底层数据：`results/Q1/figures`、`results/Q1/plot_data`。
- 生产运行摘要：`results/Q1/q1_run_summary.json`。
- 鲁棒性：`robustness/Q1/q1_robustness_summary.json`。
- 最终清单：`results/Q1/q1_final_manifest.json`。

## 提供未来真实场景

复制 `planning/scenario_schema.json` 的字段结构，新建一个独立 JSON（不要修改 schema），填写舰船、导弹、无人机的绝对初始位置和航向、任务时钟零点、最早命令时刻，并明确启用 8000 m 锁定与 12 km 解释。然后运行：

```powershell
<PYTHON> code/Q1/q1_run.py --scenario <SCENARIO_JSON>
```

题面当前没有这些绝对初态，也没有给出释放瞬间方向 `e_u`。云心与释放点满足 `p_d = c - 98 e_u`，因此本工程输出参数关系，不输出虚构的唯一绝对坐标。

## Q1 → Q2 边界

接口合同位于 `interfaces/Q1_to_Q2_coverage_contract.md`。Q1 只提供 `t_cmd`、`t_d`、`t_b`、`t_m` 语义、`Delta` 定义和单烟幕精确退化式；多烟幕输入被明确拒绝。禁止用烟幕数量乘以单烟幕结构上界，也禁止有限网格伪装连续证明。

## 清理规则

`q1_run.py --all` 删除本次运行产生的 `__pycache__`、`.pytest_cache`、`.pyc`
和 Matplotlib 临时缓存，随后生成 manifest。两份原始 Word 只保留在本地，不提交
Git；生产程序在仓库中缺少 Word 时使用已验证哈希记录，不伪造文档内容。不得创建
调试脚本、重复结果或 Q2/Q3/Q4 业务目录。
