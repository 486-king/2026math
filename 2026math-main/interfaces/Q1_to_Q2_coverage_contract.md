# Q1 → Q2 覆盖接口合同

本文件只定义交接语义，不实现或暗示 Q2 的求解方法。

## 事件字段

- `t_cmd`：投弹命令时刻。
- `t_d`：实际释放时刻，满足 `t_d = t_cmd + 2`。
- `t_b`：起爆时刻，满足 `t_b = t_d + 3.5 = t_cmd + 5.5`。
- `t_m`：最大连续完整覆盖区间的中点，不是命令、释放或起爆事件。
- `drop_time`：仅可作为 `t_d` 的兼容别名，并必须附带说明 `deprecated legacy alias of release time t_d`。

## 覆盖缺陷

统一连续覆盖缺陷定义为：

`Delta(t) = max_{x in ship disk} min_j (||x-c_j|| - r_j(t))`。

判定合同为 `Delta(t) <= 0` 当且仅当舰船完整圆盘被烟幕圆盘并集覆盖。Q1 只有一团烟幕时使用精确退化式：

`Delta_single(t) = ||s(t)-c|| + R_s - r(t)`，

且 `single_smoke_margin(t) = -Delta_single(t)`。

## 明确边界

Q1 对多团烟幕输入必须抛出：

> Exact continuous multi-smoke union coverage belongs to Q2 and is intentionally not implemented in Q1.

多烟幕连续联合覆盖不属于 Q1。Q2 必须提供精确连续几何核，或提供具有严格误差证书、足以支持连续结论的几何核。禁止用 `n × T_structural_max` 推断联合覆盖时长；禁止把有限角度或有限时间网格当作连续覆盖证明；禁止把“每团烟幕单独不能完整覆盖”等同于烟幕并集不能完整覆盖。

Q1 交付事件语义、单烟幕精确闭式和拒绝策略，不创建 Q2 结果或业务代码。
