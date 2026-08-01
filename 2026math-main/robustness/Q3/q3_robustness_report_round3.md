# Q3 鲁棒性与限制报告（round3）

状态：`SYNTHETIC_SCENARIO_ONLY`、`EXPLORATORY_STRESS_TEST`、`UNFROZEN`。

## 口径

- 固定 P2 与有限方案切换分开报告。
- 组合扰动只包含每个初始位置坐标 ±200 m、初始航向 ±45°。
- 可用时刻没有受支持的范围或分布，因此未纳入随机扰动；只报告精确阈值。
- 均匀独立采样是额外探索性设计，不是题面分布、真实作战概率或置信度。

## 结果

- 旧 Q3-B 方案：`Q3_B_LEGACY_REFERENCE_ONLY`，当前复验状态为 `failed_current_start_time_window`，不作为已验证比较候选。
- 当前可用基线：`Q3_B_RECONSTRUCTED_TRANSPARENT_BASELINE`，来源为 `reconstructed_from_Q2_conservative_three_interval_structure`；它与旧 Q3-B 不是同一方案。
- P1/P4 来自只读 Git 历史完整配置，并在当前模型中独立复验；对应标识为 `P1_LEGACY_REFERENCE_VERIFIED` 与 `P4_LEGACY_REFERENCE_VERIFIED`。
- 已验证合成候选池非支配集：搜索范围 `hybrid_fixed_core_and_structured_six_variable_multistart_search`，由固定核心候选 181 个、六变量候选 24 个、历史复验候选 2 个组成，总计 207 个。
- 非支配关系口径：`nondominated_within_verified_candidate_pool`；连续问题 Pareto 完备性：`not_proved`；不声明连续非凸问题的完整或全局 Pareto 前沿。
- 样本数：2000，固定种子：2026。
- 固定 P2 可执行样本：1970，执行率 0.985000。
- 固定 P2 失败样本：30。
- 有限方案切换执行率：1.000000。
- 最小样本机间距：0.233772035858 m。
- 固定 P2 在半名义 d_safe 下的无条件联合保留率：0.947500。
- 无条件联合比例表示“可执行且安全”的全部样本比例；条件安全比例只在可执行样本中评价安全距离，二者不可互换。
- 位置单因素案例：13，执行失败：0。
- 航向效应：`turn_proxy_only_under_instantaneous_heading_model`。
- 可用时刻分布：`blocked_missing_supported_range`。
- 旧 96.05% 与 0.2337720332 m 的状态：`not_directly_comparable_to_legacy_combined_test`。

## 限制

当前结果不包含真实三机初态、真实 d_safe、真实能耗、最小转弯半径、风漂或基地 12 km 绝对可达性。P2 的名义最小距离不是刚性鲁棒保证；方案切换后可行也不能表述成固定 P2 鲁棒。
