# 模型条件与假设登记

“题面条件”是原文事实；其余类型必须区分人工已确认口径与仍待确认候选。Q1 的 G1/S1 口径已由建模手通过 `q1_method_choice` 确认；Q2、Q3 按题意继承该名义口径，但没有把题面未给的绝对初始状态补成数值。

## A. 题目明确给出的条件

| ID | 条件 | 范围 | 来源 | 可检验性 |
|---|---|---|---|---|
| F1 | 全部建模在二维海面水平面内，忽略高度 | all | 题面 | 与三维现实偏差只能讨论，不能由现有数据检验 |
| F2 | 舰船匀速直线航行，速率 7.71 m/s，等效半径 80 m | all | 题面 | 轨迹初值补齐后可直接回代 |
| F3 | 无人机速率 28 m/s、作战半径 12000 m、单机载弹 3 枚 | all | 题面 | 路径可达性检查 |
| F4 | 投弹响应延时 2 s，同机相邻投弹至少 1 s | Q1,Q2,Q4 | 题面 | 计时口径仍需澄清 |
| F5 | 干扰弹起爆延时 3.5 s | all | 题面 | 事件时刻检查 |
| F6 | 烟幕最大半径 120 m，恒定 18 s，随后 5 s 线性衰减 | all | 题面 | 分段函数端点和量纲检查 |
| F7 | 导弹速率默认 320 m/s、探测距离 8000 m、视场半角 15° | all | 题面 | Q4“不同速度”产生冲突 |
| F8 | 舰船完整圆盘被覆盖才算有效；全探测窗口无裸露才成功 | all | 题面 | 连续时间几何验证 |
| F9 | 优先 100% 防御，其次弹药/能耗，再其次时长/稳定性 | all | 题面与用户指令 | 用词典序一致性检查 |

## B. 候选必要假设/规格

| ID | 陈述 | 暂定类型 | 建模需要 | 验证证据 | 违反影响 | 缓解/备用 | 人工状态 |
|---|---|---|---|---|---|---|---|
| N1 | 数值求解前必须给定舰船、导弹、无人机的统一 `t=0` 初始状态 | 必要候选 | 常微分轨迹和可达域没有初值无法确定 | 当前数据画像确认缺失 | 所有量化坐标和时刻不可辨识 | 仅做符号模型、区间界和条件性筛查 | 待确认/补数 |
| N2 | 必须明确导弹追踪律与视场参考方向 | 必要规格 | 决定导弹轨迹和探测窗口 | Q1 已按 G1 纯追踪建立 24.168–25.361 s 的距离窗口界 | 若改为 G2，窗口和 Q2/Q3 所需烟幕协同可能改变 | G2 只作条件性稳健性对照 | Q1 已确认；Q2/Q3 继承 |
| N3 | 必须明确干扰弹延时阶段和烟幕中心的水平运动 | 必要规格 | 决定云心相对舰船速度 | Q1 已确认 S1，并给出固定云心单弹上界 10.376 s | 改为漂移云心会改变 Q2/Q3 联合覆盖几何 | 漂移作为后续鲁棒性扩展参数 | Q1 已确认；Q2/Q3 继承 |
| N6 | Q2 的绝对投放坐标和首弹可达性需要无人机初始/基地位置及作战半径基准 | 必要规格 | 相对时序可参数化，但绝对航迹和 12 km 约束无法回代 | 当前附件无初始状态；Q2 探针仅验证相邻投放转移 | 不能声称得到唯一绝对坐标 | 输出相对舰船航迹的参数族与首弹可达条件 | 待补数据 |
| N4 | Q3/Q4 数值求解前必须给安全间距及作用阶段 | 必要候选 | 无法验证空域冲突 | 当前未给 | 协同方案可能不可执行 | 先输出参数化解，补值后筛选 | 待确认 |
| N5 | Q4 必须给每枚导弹的批次、初始状态、速度或默认规则 | 必要候选 | 威胁排序与时间窗调度的输入 | 当前没有数据表 | 任何量化优先级均属编造 | 仅做通用滚动调度合同和合成恢复测试 | 待确认/补数 |

## C. 候选简化假设

| ID | 陈述 | 暂定类型 | 适用方案 | 可检验方法 | 违反影响 | 缓解/备用 | 人工状态 |
|---|---|---|---|---|---|---|---|
| S1 | 烟幕中心在起爆后固定于海面坐标 | 人工确认的名义简化 | Q1–Q3 的确定性基线 | `q1_method_choice`；漂移探针另存 | 非零漂移会改变联合覆盖时长 | 使用给定漂移速度重算相对运动 | 已确认用于 Q1；Q2/Q3 继承 |
| S2 | 干扰弹投放后继承无人机投放瞬间水平速度并匀速飞行 3.5 s | 人工确认的名义简化 | Q1–Q3 | `q1_method_choice`；水平位移为 98 m | 直接改变所有投放点 | 若题面补充弹道则替换并重跑 | 已确认用于 Q1；Q2/Q3 继承 |
| S3 | 导弹采用瞬时纯追踪，速度方向始终指向舰船中心 | 人工确认的名义模型 | Q1–Q3 | `q1_method_choice` 与 Q1 全局证书 | G2 可能缩短视场探测窗口 | G2 固定航向作为非阻塞对照 | 已确认用于 Q1；Q2/Q3 继承 |
| S4 | 无人机能耗与路径长度成正比，固定投弹成本另计 | 简化候选 | Q1–Q4 次级目标 | 若有油耗/电耗曲线则拟合 | 可能低估急转弯和加速成本 | 用路径长、转向总变差双指标或真实功率模型 | 待确认 |
| S5 | 烟幕光学效果采用二值几何覆盖，不叠加浓度 | 简化候选/题意贴近 | all | 对照题面“完全覆盖即失效” | 无法表达重叠增厚，只能表达冗余 | 若给光学厚度规律，升级为浓度叠加 | 待确认 |
| S6 | Q3 将正常完整防御设为硬约束，再对覆盖裕度、失效容错、总航程和总转向量输出 Pareto 集 | 人工确认的目标结构 | Q3 | 检查是否牺牲首要防御目标且前沿无隐藏权重 | 与任意加权和相比保留真实取舍 | 在前沿内用膝点、理想点距离或分层筛选代表解 | `q3_objective_safety_energy_scope` 已确认 |
| S7 | Q4 采用事件触发滚动重算，已执行动作冻结 | 简化候选 | Q4 | 合成事件流恢复与计算时限探针 | 重算周期不当可能抖动或过时 | 设置最小冻结窗和应急规则 | 待确认 |

## D. 可由数据检验与暂时不可验证的假设

- 可检验：轨迹是否近似匀速直线、烟幕半径分段规律、风漂移速度、能耗与路径关系、导弹速度是否一致、调度扰动稳定性。
- 当前不可检验：二维忽略高度是否足够、光学遮蔽二值化是否准确、烟幕重叠是否有浓度增益，因为没有观测数据或物理附件。
- 参数可辨识性：给定常数本身不需估计；初始状态、追踪律、风漂移、能耗函数和安全距离不是“可从现有数据估计”的未知参数，而是缺失规格。把它们交给优化器同时拟合会产生多解和参数耦合。

## 决策关联

Q1 的 G1/S1 运动口径来自人工 `q1_method_choice`，本表只忠实转录，不把其扩写成已由数据验证的事实。2 s 响应延时现按命令到实际释放解释；1 s 约束用于同机相邻实际释放。Q2 已有人类 O3/A 选择。Q3 已有人类 O2/D1/E3 framing 决策，但仍待 A/B/C 方法选择。
## Q1 teammate-review assumption update (2026-07-29)

| ID | Statement | Scope/source | Modeling need | Validation/evidence | Impact if violated | Mitigation | Decision |
|---|---|---|---|---|---|---|---|
| A10 | Interpret the statement’s 2 s response delay as command-to-actual-release: `t_d=t_cmd+2` | Q1-Q4; statement gives 2 s, endpoint meaning comes from teammate-review integration | Makes command, release and burst events schedulable without mixing symbols | `results/Q1/experiments/round4/metrics/q1_architecture_upgrade.json` event-chain test | All absolute command times shift; inter-release constraints could be misapplied | Keep interpretation field explicit and rerun if organizers clarify | `q1_teammate_review_integration` |
| A11 | In the standard G1 scenario the missile has already acquired lock when range reaches 8000 m | Q1-Q3; premise needed by the teammate review | Makes the full 8000 m-to-contact interval an active detection window under pure pursuit | G1 line-of-sight offset is zero after lock | Detection-window lower bound may not describe the whole active window | Recompute distance-and-FOV activation if initial lock is not assumed | `q1_teammate_review_integration` |
| A12 | The 98 m inertial displacement assumes the released bomb keeps the UAV’s instantaneous horizontal velocity for 3.5 s and ignores drag, horizontal deceleration and wind | Q1-Q2; earlier `q1_method_choice`, now stated explicitly | Maps release point to burst centre | `28*3.5=98 m`; synthetic identity checks | Release point and reachability change | Replace by `integral v_b(t)dt` when a trajectory law is supplied | `q1_method_choice`; clarified by teammate review |
| A13 | Primary 12 km interpretation is distance from the initial takeoff point, not total path length | Q1-Q4; teammate recommendation | Needed for an eventual reachability check | Not evaluable because the reference point is missing | Executable solution may change | Report `blocked_missing_absolute_geometry`; retain total-path interpretation as sensitivity | `q1_teammate_review_integration` |

The structural single-smoke infeasibility certificate does not depend on A10,
A12 or A13. It does depend on A11 when the lower bound is described as an
active detection-window lower bound rather than a pure closing-time bound.

## Q3 人工确认的建模口径（2026-07-29）

| ID | 陈述 | 范围/来源 | 类型 | 验证方法 | 违反影响 | 缓解/备用 | 决策 |
|---|---|---|---|---|---|---|---|
| Q3-A1 | 正常三机完整防御是硬约束，覆盖裕度、失效容错、总航程和总转向量生成 Pareto 前沿 | Q3/O2 | 人工确认的目标结构 | 检查所有 Pareto 候选均先通过连续完整防御 | 任意加权可能以能耗收益补偿防御失败 | 硬约束筛选后再做非支配比较 | `q3_objective_safety_energy_scope` |
| Q3-A2 | `d_safe` 是参数而非自拟常数 | Q3/D1 | 人工确认的必要规格处理 | 输出可行域、最大允许值和方案切换阈值 | 固定虚构值会改变航迹与 Pareto 前沿 | 补真实值后从参数前沿读取/重跑 | `q3_objective_safety_energy_scope` |
| Q3-A3 | 总航程与总转向量分开报告，不构造 `E=L+lambda*Theta` | Q3/E3 | 人工确认的指标结构 | 检查结果表中两列独立、无隐藏权重 | 无依据 `lambda` 会主观改变代表解 | 获得真实能耗函数后再升级 | `q3_objective_safety_energy_scope` |
| Q3-A4 | 任意单机失效是鲁棒性检验，不是当前硬约束 | Q3/补充要求 | 人工确认的容错口径 | 三个留一情景逐一连续回代 | 强制 N-1 可能使名义可行域不必要地为空 | 有 N-1 完整解时单列；否则报告最优降级 | `q3_objective_safety_energy_scope` |
| Q3-S1 | 无真实能耗模型时，总转向量仅为机动复杂度指标 | Q3 | 简化假设 | 与航程分列并明确单位 rad | 不能解释为真实电量/燃油消耗 | 获得功率或转弯损耗数据后替换 | `q3_objective_safety_energy_scope` |
| Q3-S2 | 未给最小转弯半径时，主模型使用分段直线可机动航迹 | Q3/A-B | 待正式方法选择后采用的简化候选 | 连续避碰、速度和转向量回代 | 可能低估急转弯不可执行性 | 把最小转弯半径作为后续参数或切换鲁棒/运动学扩展 | 尚未进行 A/B/C 方法选择 |

Q3 继续继承 A10（命令到释放 2 s）、A11（G1 在 8000 m 已锁定）和
A12（S1 的 98 m 惯性位移）。烟幕叠加只按几何并集与失效冗余解释，
没有光学浓度数据时不引入浓度增益。

## Q3 标准化场景与事件可行性更新（2026-07-29）

| ID | 陈述 | 范围/来源 | 类型 | 验证方法 | 影响 | 决策 |
|---|---|---|---|---|---|---|
| Q3-A5 | `t=0` 为 G1 在 8000 m 完成锁定，三机标准场景可用时刻均为 0 | Q3 标准场景 | 人工确认的场景定义 | `q3_parameterized_and_standardized_scenario` | 防御窗口与任务响应同时开始 | `q3_parameterized_and_standardized_scenario` |
| Q3-A6 | 标准场景坐标、航向和扫描范围只作 `SYNTHETIC_SCENARIO_ONLY` | Q3 | 人工确认的证据层级 | 检查所有输出标签 | 禁止冒充题目真实部署 | `q3_parameterized_and_standardized_scenario` |
| Q3-D1 | 在 A10 与 Q3-A5 下，首团烟幕最早于 5.5 s 出现，因此 `[0,5.5)` 必然裸露 | Q3-A/Q3-B | 由已确认条件推导 | 事件链代码、解析回代和重复运行 | 正常完整防御硬约束不可行，Pareto 可行集为空 | `results/Q3/experiments/round1/metrics/q3_event_infeasibility_certificate.json` |
| Q3-D2 | `min_i(a_i)<=-5.5 s` 是消除该事件阻塞的必要条件 | Q3 参数化结论 | 推导结果 | 极限与边界检查 | 通过该条件后仍需可达、连续覆盖与安全验证 | 同上 |

## Q3-R2 锁定前预任务更新（2026-07-29）

| ID | 陈述 | 范围/来源 | 类型 | 验证方法 | 影响/限制 | 决策 |
|---|---|---|---|---|---|---|
| Q3-A7 | 允许 `a_i in [-60,0] s`，且初态定义为 `u_i(a_i)=u_{i,0}`、`psi_i(a_i)=psi_{i,0}` | Q3-R2 | 人工确认的正式口径 | 从 `a_i` 连续模拟至锁定时刻，再模拟防御窗口 | 原 round1 的 `a_i>=0` 不可行证书仅保留为无预警对照 | `q3_result_adjust_pretask` |
| Q3-A8 | 防御考核窗口仍从 `t=0` 开始；首团用于覆盖 `t=0` 时原则上 `t_b<=0`，若要求仍处于最大半径阶段则 `-18<=t_b<=0` | Q3-R2 | 人工确认的事件约束 | 检查命令、释放、起爆和半径相位 | 不允许把预任务误写成缩短防御窗口 | `q3_result_adjust_pretask` |
| Q3-D3 | `5.5 s` 仅是补偿命令响应与起爆延迟的理论下界，不包含飞抵释放点的时间 | Q3-R2 | 解析必要条件 | 与优化反演的逐机可用时刻比较 | 不能把 `a_i<=-5.5 s` 称为充分条件 | `q3_result_adjust_pretask` |
| Q3-S3 | 当前正式搜索限定为可复核的共线烟幕中心候选族 | Q3-A round2 | 计算简化 | 连续时间包络证书与独立圆盘差验证 | 数值是标准化场景候选族结果，不是完整二维全局最优 | 扩展二维搜索前保持明确限定 |

标准化场景的坐标仍必须标记 `SYNTHETIC_SCENARIO_ONLY`。来袭方位、初始坐标、
初始航向与可用时刻的完整参数化结论，需要在相应维度真正重优化后才能形成；
不能从单一标准场景外推。
