# Q1 队友审查意见合入报告

## 1. 修订后的准确状态

Q1 不再笼统标记为“全部完成”，而分成三层：

1. **已完成且证书成立**：`G1+S1+O0+U0` 条件下，单弹覆盖完整探测窗口严格不可行。
2. **已建立**：最大连续完整遮蔽的参数化补偿族，结构上界为
   `10.376134889753567 s`。
3. **尚受输入阻塞**：缺少绝对舰船、导弹、无人机初态、统一任务时钟和
   12 km 参考点，无法给出场景化唯一代表坐标与
   `T_executable_star`。

程序分别报告：

- `execution_status=passed`
- `input_status=blocked_missing_absolute_geometry`
- `feasibility_status=proved_infeasible_for_full_window`
- `compensation_status=structural_family_available`
- `certificate_status=verified`

## 2. 保留不变的核心证明

单固定烟幕完整覆盖舰船圆盘需要舰船中心满足

`||s(t)-c|| <= R_c-R_s = 40 m`。

因此固定云心的结构上界为

`T_structural_max=2(R_c-R_s)/V_s=10.376134889753567 s`。

在 `G1` 纯追踪且导弹在 8000 m 处已经锁定的标准场景中，视轴偏差为
0，探测窗口下界为

`T_detect_lower=(8000-80)/(320+7.71)=24.167709255134113 s`。

所以

`T_naked_lower >= 13.791574365380546 s > 0`，

单弹全窗口防御严格不可行。A 事件模型、B 解析界和 C 向外舍入区间证书
结论一致。

## 3. 已正式合入的改进

### 3.1 模型标签

- `G1`：纯追踪导弹，替代旧称 M1。
- `G2`：固定航向对照，替代旧称 M2。
- `S1`：起爆后固定云心。
- `S2`：云心漂移扩展。
- `O0`：二维完整舰船圆盘覆盖。
- `U0`：名义确定性、无风漂。

### 3.2 三类时刻

题面给出 2 s 响应常数，但没有明示其事件端点。按本轮人工授权采用主解释：

- `t_cmd`：命令时刻；
- `t_d=t_cmd+2`：实际释放时刻；
- `t_b=t_d+3.5=t_cmd+5.5`：起爆时刻。

原 Q1 使用 `t_c` 表示覆盖中点会与 command 冲突，现统一改为 `t_m`。

### 3.3 98 m 位移的正确地位

`c=p_d+98e_u` 不是题面直接给出的事实，而是 S1 名义简化：

释放后干扰弹在 3.5 s 内继承无人机瞬时水平速度，忽略空气阻力、水平
减速和风漂。通用替换接口为

`c=p_d+integral_[t_d,t_b] v_b(t)dt`。

### 3.4 统一覆盖缺陷

定义

`Delta(t)=max_[x in D_s(t)] min_j(||x-c_j(t)||-r_j(t))`。

`Delta(t)<=0` 当且仅当烟幕并集完整覆盖舰船圆盘。

单烟幕时：

`Delta(t)=||s(t)-c||+R_s-r(t)`，

所以旧裕度 `g(t)=-Delta(t)`。1000 组随机退化测试的最大恒等误差为
`4.55e-13 m`。

Q1 代码会拒绝用未经证明的有限网格计算多烟幕缺陷；Q2 使用专门的连续
联合几何核。

### 3.5 结构上界与可执行最优

必须区分：

- `T_structural_max=10.376134889753567 s`
- `T_executable_star<=T_structural_max`

只有云心位于舰船航迹、覆盖段处于 18 s 满半径阶段、三类时刻合法、
无人机按时到达释放点、12 km 解释满足且绝对输入完整时才可能取等号。

### 3.6 G2 与 S2 的边界

G2 中 `|W_G2|<=10.3761 s` 只是必要条件，不是完整可行性。

S2 应使用舰船—云心相对速度。对于理想共线、只讨论满半径阶段的表达：

`T_full_radius <= min(18,2(R_c-R_s)/||v_s-v_c||)`。

若要计算包含 5 s 衰减阶段的总覆盖时长，必须运行事件模型。题面没有风场
数据，所以只能输出参数曲线，不能写“实际风下结论”。

## 4. 条件性采纳或暂不合入的建议

- 12 km 主解释暂按“相对初始起飞点的最大距离”，但参考点缺失，程序仍
  返回 blocked；总航程解释保留作敏感性对照。
- 双坐标系作为论文解释和后续接口保留；当前没有绝对初态，不生成虚构的
  绝对轨迹图。
- 二阶覆盖缺陷与 N-1 单点失效属于 Q3 的韧性指标，不塞入 Q1 主求解。
- 时空 Lipschitz 网格证书不替代 Q1 的解析和区间证书；Q2 已采用更直接的
  连续联合几何验证。
- 视线投影 `O1` 会改变题目“完整圆盘覆盖”的成功判据，只能作扩展模型。

## 5. 参数化补偿族的新写法

令实际探测窗口为 `W=[t_in,t_out]`，

`h=(R_c-R_s)/V_s=5.188067444876784 s`。

选择

`t_m in [t_in+h,t_out-h]`，

令云心 `c*=s(t_m)`，则最大完整覆盖段为

`[t_m-h,t_m+h]`。

要使整个覆盖段位于 18 s 满半径阶段，起爆时刻满足

`t_b in [t_m+h-18,t_m-h]`。

继而

- `t_d=t_b-3.5`
- `t_cmd=t_b-5.5`
- `p_d=c*-98e_u`

绝对可执行性必须由 `planning/scenario_schema.json` 的真实输入筛选。

## 6. Q1 到 Q2 的正式交接

Q1 提供单烟幕结构上界、事件链、参数化动作和覆盖缺陷定义。Q2 必须检查

`D_s(t) subseteq union_j D_j(t)`，

既允许时序接力，也允许空间互补。禁止把
`10.3761 s × 弹数` 当成多烟幕联合覆盖上界。

正式合同见 `interfaces/Q1_to_Q2_coverage_contract.md`。

## 7. 新增证据

- `results/Q1/experiments/round4/metrics/q1_architecture_upgrade.json`
- `results/Q1/experiments/round4/run_summary.json`
- `planning/assumption_register.csv`
- `planning/scenario_schema.json`
- `interfaces/Q1_to_Q2_coverage_contract.md`

