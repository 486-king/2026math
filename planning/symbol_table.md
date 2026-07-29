# 全局符号表

所有角度在输入层可用度表示，进入计算后统一为弧度；二维向量默认属于 `R²`。没有数据来源的量明确标为“待提供”，不得赋零。

| 符号 | 名称 | 定义 | 类型 | 域/范围 | 单位 | 范围/Qx | 来源与备注 |
|---|---|---|---|---|---|---|---|
| `t` | 全局时间 | 统一任务时钟 | input/index | `t≥0` | s | all | `t=0` 的物理事件待定义 |
| `Oxy` | 水平坐标系 | 海面二维直角坐标系 | set | `R²` | m | all | x、y 正方向待给 |
| `s(t)` | 舰船中心位置 | 舰船等效圆盘中心 | state | `R²` | m | all | 初值 `s0` 待给 |
| `s0` | 舰船初始位置 | `s(0)` | input | `R²` | m | all | 缺失 |
| `e_s` | 舰船航向单位向量 | `||e_s||=1` | input | 单位圆 | 1 | all | 缺失 |
| `v_s` | 舰船速度向量 | `7.71 e_s` | parameter | `R²` | m/s | all | 15 kn 换算 |
| `V_s` | 舰船速率 | `15×0.514=7.71` | parameter | `7.71` | m/s | all | 题面 |
| `R_s` | 舰船等效探测半径 | 舰船圆盘半径 | parameter | `80` | m | all | 题面 |
| `S(t)` | 舰船探测圆盘 | `{x:||x-s(t)||≤R_s}` | set/function | 圆盘 | m² | all | 覆盖判据对象 |
| `m_k(t)` | 第 k 枚导弹位置 | 导弹中心轨迹 | state | `R²` | m | Q1,Q4 | 初值缺失 |
| `m_k^0` | 导弹初始位置 | `m_k(0)` | input | `R²` | m | Q1,Q4 | 缺失 |
| `e_{m,k}(t)` | 导弹速度/弹轴方向 | 视场参考候选方向 | state | 单位圆 | 1 | Q1,Q4 | 定义待确认 |
| `V_{m,k}` | 导弹速率 | 默认 320；Q4 可能不同 | input/parameter | `>0` | m/s | Q1,Q4 | 语义冲突待解 |
| `D_k(t)` | 弹舰距离 | `||s(t)-m_k(t)||` | intermediate | `≥0` | m | Q1,Q4 | 距离探测条件 |
| `D_max` | 最大成像探测距离 | 距离阈值 | parameter | `8000` | m | all | 题面 |
| `θ_k(t)` | 视线偏角 | 导弹参考方向与弹舰视线夹角 | intermediate | `[0,π]` | rad | Q1,Q4 | 参考方向待确认 |
| `β` | 视场半角 | 探测角阈值 | parameter | `π/12` | rad | all | 15° |
| `χ_k(t)` | 导弹可探测指示 | 距离与视场均满足为 1 | output/intermediate | `{0,1}` | 1 | Q1,Q4 | 观测窗口 |
| `W_k` | 第 k 枚导弹探测窗口 | `{t:χ_k(t)=1}` | set/output | 时间区间并集 | s | Q1,Q4 | 必须由轨迹得到 |
| `u_i(t)` | 第 i 架无人机位置 | 无人机轨迹 | decision/state | `R²` | m | all | 初值缺失 |
| `u_i^0` | 无人机初始/基地位置 | `u_i(0)` | input | `R²` | m | all | 缺失 |
| `v_{u,i}(t)` | 无人机速度向量 | 机动控制 | decision | `||v_{u,i}||≤28` | m/s | all | 题面给速率 28，能否变速待确认 |
| `V_u` | 无人机标称速率 | 飞行速度 | parameter | `28` | m/s | all | 题面 |
| `R_op` | 最大作战半径 | 相对基地的最大距离候选定义 | parameter | `12000` | m | all | 基准点待给 |
| `L_i` | 第 i 机航程/路径长 | `∫||v_{u,i}(t)||dt` | intermediate | `≥0` | m | Q2-Q4 | 能耗代理候选 |
| `E_i` | 第 i 机能耗 | 尚未给定的路径/机动函数 | output | `≥0` | energy unit | Q1-Q4 | 函数与单位缺失 |
| `n_i` | 第 i 机用弹数 | 投放弹数 | decision | `0..3` | bomb | Q2,Q4 | Q3 固定为 1 |
| `t^d_{ij}` | 第 i 机第 j 弹投放时刻 | 投弹事件时间 | decision | `≥0` | s | all | Q3 每机 j=1 |
| `p^d_{ij}` | 投放位置 | `u_i(t^d_{ij})` | output/decision | `R²` | m | all | 可达性约束 |
| `δ_resp` | 投弹响应延时 | 单次响应延时 | parameter | `2` | s | all | 计时口径待确认 |
| `Δ_d` | 同机最小投弹间隔 | 相邻投弹下界 | parameter | `1` | s | Q2,Q4 | 题面 |
| `τ_b` | 起爆延时 | 投放到起爆的固定时间 | parameter | `3.5` | s | all | 题面 |
| `t^b_{ij}` | 起爆时刻 | `t^d_{ij}+τ_b` | output | `≥3.5` | s | all | 若响应延时另计需注明 |
| `b_{ij}(t)` | 干扰弹位置 | 投放至起爆的惯性轨迹 | state | `R²` | m | all | Q1 人工决定采用 S1：继承投放瞬间水平速度 3.5 s |
| `c_{ij}(t)` | 烟幕中心 | 起爆后的烟幕中心轨迹 | state | `R²` | m | all | Q1/Q2 名义 S1 中固定；漂移仅作扩展参数 |
| `a_{ij}(t)` | 烟幕龄期 | `t-t^b_{ij}` | intermediate | `R` | s | all | 负值表示未起爆 |
| `r_{ij}(t)` | 烟幕半径 | 由龄期决定的分段函数 | function | `[0,120]` | m | all | 题面数值 |
| `R_c` | 最大烟幕半径 | `120` | parameter | `120` | m | all | 题面 |
| `T_c` | 恒定遮蔽时长 | `18` | parameter | `18` | s | all | 题面 |
| `T_f` | 线性衰减时长 | `5` | parameter | `5` | s | all | 题面 |
| `C_{ij}(t)` | 单个烟幕圆盘 | `{x:||x-c_{ij}(t)||≤r_{ij}(t)}` | set/function | 圆盘 | m² | all | 几何对象 |
| `C(t)` | 烟幕并集 | `∪_{i,j}C_{ij}(t)` | set/function | 平面子集 | m² | Q2-Q4 | 不能用面积和替代 |
| `g_{ij}(t)` | 单烟幕覆盖裕度 | `r_{ij}(t)-R_s-||c_{ij}(t)-s(t)||` | intermediate | `R` | m | all | `g≥0` 表示该烟幕独立全覆盖 |
| `G_∪(t)` | 多烟幕联合覆盖裕度 | `-max_{x∈S(t)} min_{i,j}(||x-c_{ij}(t)||-r_{ij}(t))` | intermediate/metric | `R` | m | Q2-Q3 | `G_∪≥0` 当且仅当烟幕并集完整覆盖舰船圆盘 |
| `z(t)` | 完整遮蔽指示 | `1[S(t)⊆C(t)]` | output | `{0,1}` | 1 | all | 多烟幕需并集判断 |
| `y_k(t)` | 第 k 威胁防御指示 | 探测时段是否遮蔽 | output | `{0,1}` | 1 | Q1,Q4 | 与 `χ_k` 联动 |
| `T_cov` | 最长连续有效遮蔽 | 最长连续 `z(t)=1` 区间长度 | objective/output | `≥0` | s | Q2,Q3 | 与总时长区分 |
| `G_min` | 最小覆盖裕度 | 探测窗口中几何裕度最小值 | metric | `R` | m | Q1-Q3 | 稳定性指标 |
| `O_time` | 相邻烟幕时间重叠 | 完整覆盖区间交叠长度 | metric | `≥0` | s | Q2,Q3 | 容错指标 |
| `ε_p` | 投放/云心位置误差界 | 鲁棒性探针中的位置扰动半径 | uncertainty parameter | `≥0` | m | Q2-Q3 | 非题面常数，必须标注探索范围 |
| `ε_t` | 投放/起爆时间误差界 | 鲁棒性探针中的事件时刻扰动 | uncertainty parameter | `≥0` | s | Q2-Q4 | 非题面常数，必须标注探索范围 |
| `d_safe` | 最小无人机安全间距 | 任意两机距离下界 | parameter | `>0` | m | Q3,Q4 | 缺失 |
| `A_union(t)` | 烟幕并集面积 | `area(C(t))` | metric | `≥0` | m² | Q3 | 仅次级指标 |
| `ρ_fail` | 单点失效容错率 | 任一机/弹失效后的防御保持比例 | metric | `[0,1]` | 1 | Q3 | 定义需情景化 |
| `K` | 导弹集合 | 所有来袭威胁索引 | set | finite | 1 | Q4 | 规模缺失 |
| `I` | 无人机集合 | Q4 为 `{1,…,5}` | set | finite | 1 | Q3,Q4 | Q3 为 3 |
| `J_i` | 第 i 机弹药集合 | Q4 至多 3 枚 | set | finite | 1 | Q2,Q4 | 资源上限 |
| `TTI_k` | 剩余打击时间 | 威胁到达舰船的预测时间 | input/intermediate | `>0` | s | Q4 | 需轨迹数据 |
| `α_k` | 来袭角 | 导弹入射相对方向 | input | angle | rad | Q4 | 定义待给 |
| `w_k` | 威胁权重/等级 | 可解释风险排序量 | intermediate | `[0,1]` 或等级 | 1 | Q4 | 不得无数据任意赋值 |
| `x_{ik}` | 无人机-威胁分配 | 第 i 机是否服务威胁 k | decision | `{0,1}` | 1 | Q4 | 可扩展到弹级 |
| `q_{ik}` | 分配弹数 | i 机给 k 威胁的弹数 | decision | `0..3` | bomb | Q4 | `Σ_k q_{ik}≤3` |
| `R_total` | 总未防御风险 | 威胁权重与失败指示的聚合 | objective | `≥0` | 1 | Q4 | 形式需与人类风险偏好一致 |

## 冲突与统一

- “导弹速度”统一使用 `V_{m,k}`；只有在确认所有导弹同速时才设为 320。
- “烟幕寿命”不等同于“舰船完整覆盖时长”；前者由 `T_c+T_f` 描述，后者由 `z(t)` 或 `g(t)` 描述。
- “覆盖范围”统一分为烟幕并集面积 `A_union` 与核心完整遮蔽指示 `z(t)`，两者不得互换。
- Q1 的单烟幕关系、Q2/Q3 的并集覆盖以及 Q4 的服务时窗使用同一全局时间 `t` 和同一舰船圆盘 `S(t)`。
## Q1 teammate-review canonical symbol upgrade (2026-07-29)

The following entries supersede ambiguous Q1 uses while preserving all
previous numerical values.

| Symbol | Plain name | Definition | Type | Domain/range | Unit | Scope | Source / conflict resolution |
|---|---|---|---|---|---|---|---|
| `G1` | Pure-pursuit guidance | Missile speed has constant magnitude and points to the ship centre | model label | nominal | 1 | Q1-Q3 | Renamed from M1 to avoid collision with numbered modules |
| `G2` | Fixed-heading guidance | Missile follows a supplied fixed heading | model label | extension | 1 | Q1-Q3 | Renamed from M2; duration test is necessary only |
| `O0` | Complete-disk coverage | Full 2-D ship disk must be inside the smoke union | model label | nominal | 1 | all | Problem success criterion |
| `U0` | Nominal deterministic profile | No nominal wind drift | model label | nominal | 1 | Q1-Q3 | Human decision |
| `t_cmd` | Bomb command time | Time at which the UAV receives/issues the drop command | decision/event | task clock | s | all | New canonical symbol |
| `t_d` | Actual release time | `t_d=t_cmd+2` under the selected timing interpretation | decision/event | task clock | s | all | Replaces ambiguous “drop/response” wording |
| `t_b` | Burst time | `t_b=t_d+3.5=t_cmd+5.5` | output/event | task clock | s | all | Same physical event as before |
| `t_m` | Cover-interval midpoint | Midpoint of a selected single-smoke complete-cover interval | decision/intermediate | detection window | s | Q1 | Replaces the old Q1 use of `t_c`; `t_c` is no longer used for this meaning |
| `Delta(t)` | Unified coverage defect | `max_{x in S(t)} min_j(||x-c_j(t)||-r_j(t))` | function/metric | real | m | Q1-Q3 | Complete coverage iff `Delta<=0`; Q1 single-smoke `g=-Delta` |
| `T_structural_max` | Structural capacity upper bound | Maximum permitted by ship/smoke geometry before reachability | output | nonnegative | s | Q1-Q2 | `10.376134889753567` under fixed single smoke |
| `T_executable_star` | Executable scenario optimum | Best duration after event, reachability and radius constraints | output | `[0,T_structural_max]` | s | Q1 | Not evaluable until absolute scenario inputs are supplied |

Conflict resolution: `t_c` must not denote both a command time and a
cover-interval midpoint. New and revised Q1/Q2 artifacts use `t_cmd` and `t_m`
respectively.

## Q3 Pareto、参数化安全与失效指标（2026-07-29）

以下符号由人工决策 `q3_objective_safety_energy_scope` 确认，供 Q3 方法卡、
代码计划、实验结果和论文统一使用。

| 符号 | 名称 | 定义 | 类型 | 域/范围 | 单位 | 范围/Qx | 来源与备注 |
|---|---|---|---|---|---|---|---|
| `Delta_all(t)` | 正常三机覆盖缺陷 | `max_{x in S(t)} min_i(||x-c_i(t)||-r_i(t))` | function/metric | real | m | Q3 | `Delta_all<=0` 为完整覆盖硬约束 |
| `Delta_-i(t)` | 单机失效覆盖缺陷 | 移除第 `i` 机及其烟幕后计算的覆盖缺陷 | function/metric | real | m | Q3 | 三个确定性失效情景 |
| `M_min` | 正常最小覆盖裕度 | `min_{t in W_G1}[-Delta_all(t)]` | objective/metric | real | m | Q3 | 越大越稳健 |
| `rho_-1` | 单机失效全窗口成功率 | 三个单机失效情景中仍完整防御的比例 | objective/metric | `{0,1/3,2/3,1}` | 1 | Q3 | 不作为当前硬约束 |
| `T_-1^min` | 最差失效连续遮蔽 | 三个失效情景最长连续遮蔽时长的最小值 | objective/metric | `[0,|W_G1|]` | s | Q3 | 无 N-1 完整解时用于降级排序 |
| `eta_2` | 双重覆盖时间比例 | 任意一机失效后仍完整覆盖的时刻占 `W_G1` 比例 | objective/metric | `[0,1]` | 1 | Q3 | 等价于每个时刻均可承受任一单机失效的时间比例 |
| `L_total` | 三机总航程 | `sum_i L_i` | objective/metric | `>=0` | m | Q3 | 与转向量分开最小化 |
| `Theta_i` | 第 i 机总转向量 | 航向角轨迹的总变差 | intermediate/metric | `>=0` | rad | Q3 | 不是能耗 |
| `Theta_total` | 三机总转向量 | `sum_i Theta_i` | objective/metric | `>=0` | rad | Q3 | 不与航程加权合成 |
| `P_Q3(d_safe)` | Q3 参数化 Pareto 集 | 给定安全距离下满足正常完整防御的非支配方案集 | output/set | finite/continuous set | 1 | Q3 | O2 人工选择 |
| `d_safe^max` | 最大允许安全距离 | 仍存在正常完整防御可执行方案的 `d_safe` 上确界 | output | `>=0` | m | Q3 | 缺真实初态时不得给正式数值 |
| `a_i` | 第 i 机任务可用时刻 | 第 i 机最早可接收投弹指令的任务时钟时刻 | input/parameter | real | s | Q3 | 标准场景为 0；敏感性范围 0–3 |
| `a_crit` | 预任务必要阈值 | 在窗口从 0 开始时满足 `min_i(a_i)<=-5.5` 的临界值 | derived threshold | `-5.5` | s | Q3 | 仅为完整防御必要条件，不是充分条件 |

冲突处理：

- Q3 的“冗余”不再用含义模糊的单一 `rho_fail`；正式输出拆成
  `rho_-1`、`T_-1^min` 和 `eta_2`。
- `L_total` 与 `Theta_total` 是两个独立 Pareto 目标，不定义无依据的
  `E=L+lambda*Theta`。
- Q3 的投弹事件沿用 `t_cmd`、`t_d`、`t_b`，旧表中的
  `t^d_{ij}` 仅按“实际释放时刻”读取。

## Q3-R2 锁定前预任务时间符号（2026-07-29）

| 符号 | 名称 | 定义 | 类型 | 范围 | 单位 | 备注 |
|---|---|---|---|---|---|---|
| `u_i(a_i)` | 预任务开始状态 | 第 `i` 架无人机在自身可用时刻的位置，等于输入 `u_{i,0}` | input/state | `R^2` | m | 不再把 `u_{i,0}` 无条件解释为 `u_i(0)` |
| `psi_i(a_i)` | 预任务开始航向 | 第 `i` 架无人机在自身可用时刻的航向，等于输入 `psi_{i,0}` | input/state | `[0,2pi)` | rad | 从 `a_i` 开始模拟预部署 |
| `T_lead^latest` | 最晚可用无人机提前量 | `-max_i a_i` | output/metric | `[0,60]` | s | 严格按建模手给出的公式；表示三机中最晚开始者的提前量 |
| `T_lead^common` | 全部所选航路共同提前量 | `-min_i a_i` | output/metric | `[0,60]` | s | 使所有所选航路均可执行所需的统一预警提前量 |

说明：`T_lead^latest` 与 `T_lead^common` 不是同一个指标。若某架无人机可在
`t=0` 才开始而其余无人机已预部署，则前者可为 0，但这不表示系统无需预警。
因此实际部署可行性以逐机阈值 `a_i` 和 `T_lead^common` 为主，同时保留
`T_lead^latest` 以忠实回应原定义。
