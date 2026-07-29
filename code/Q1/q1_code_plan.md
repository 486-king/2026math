# Q1 Python Code Plan — round1

## Purpose and scope

实现人类批准的 A（事件驱动连续时间可行性模型）与 B（解析 baseline），先回答 M1/S1 下严格全探测窗口遮蔽是否可行。若结构上已不可行，输出不可行证书、最大连续完整遮蔽上界和最小裸露时间下界；不伪造投放坐标。C 初始只记录触发器；round1 中 A 已给出不可行结论，满足建模手预先批准的触发条件，因此 round2 仅实现针对该结论的全局区间证书。

## Approval

- implementation target: Python
- round: `round1`
- approved decision: `q1_method_choice`
- main: `A`
- usable baseline: `B`
- dormant fallback: `C`
- seed: `2026`（当前确定性计算不依赖随机数）

## Input contract

### Statement constants

| Field | Value | Unit |
|---|---:|---|
| `ship_speed` | 7.71 | m/s |
| `ship_radius` | 80 | m |
| `missile_speed` | 320 | m/s |
| `detection_distance` | 8000 | m |
| `fov_half_angle` | 15 | deg |
| `uav_speed` | 28 | m/s |
| `uav_operation_radius` | 12000 | m |
| `response_delay` | 2 | s |
| `bomb_burst_delay` | 3.5 | s |
| `smoke_max_radius` | 120 | m |
| `smoke_constant_duration` | 18 | s |
| `smoke_decay_duration` | 5 | s |

### Optional real-scenario fields

`ship_initial_position_m`, `ship_heading_rad`, `missile_initial_position_m`, `missile_fixed_heading_rad`（仅 M2）、`uav_initial_position_m`、任务时钟定义。未提供时，程序只运行不依赖这些字段的严格结构证书。

缺失字段不得自动置零。真实坐标优化状态应返回 `blocked_missing_scenario_inputs`。

## Mathematical mapping

### Shared helpers

- `ship_position(t)=s0+V_s e_s t`
- M1: `m_dot=V_m(s-m)/||s-m||`
- M2: `m(t)=m0+V_m e_m t`
- Bomb S1: `c=p_drop+3.5 V_u e_drop`
- Smoke center: nominally fixed after burst; robustness parameter `v_drift=(0,0)`
- Smoke radius:
  - `120`, `0≤age≤18`
  - `120(23-age)/5`, `18<age≤23`
  - `0` otherwise
- Complete-cover margin: `g(t)=r(t)-R_s-||c-s(t)||`
- Detection: `D≤8000` and FOV offset `≤15°`

### A — event-driven main

1. For a supplied scenario, integrate M1 with event roots at detection entry and target contact.
2. For a candidate drop time/heading, derive drop point, burst point and burst time.
3. Form event intervals from detection boundaries, burst, `burst+18`, `burst+23`, and coverage-root candidates.
4. Check continuous cover by evaluating the analytic/end-point minimum on every piece and solving boundary roots.
5. Optimize strict feasibility first. If infeasible, maximize the longest connected interval with `g(t)≥0` inside the detection window.
6. Return feasibility, decision variables, minimum margin, longest cover, naked time and every violated constraint.

### B — analytic baseline

Derive scenario-independent bounds:

- Fixed cloud maximum complete-cover interval:
  `T_cover^B=2(R_c-R_s)/V_s`.
- M1 detection-window lower bound before contact with the ship disk:
  `T_detect^LB=(D_max-R_s)/(V_m+V_s)`.
- Strict feasibility necessary condition:
  `T_cover^B≥T_detect^LB`.
- Minimum naked-time lower bound:
  `T_naked^LB=max(0,T_detect^LB-T_cover^B)`.

Also report the co-moving cloud relaxation
`18+5(1-R_s/R_c)` only as a non-S1 robustness upper bound.

### Parametric best-placement relation

For any selected coverage interval midpoint `t_c`, the best fixed cloud center lies on the ship path:
`c=s(t_c)`. The complete-cover interval is
`[t_c-(R_c-R_s)/V_s, t_c+(R_c-R_s)/V_s]`
while the smoke radius remains maximal. A valid S1 drop must satisfy
`p_drop=c-3.5 V_u e_drop`, `t_drop=t_b-3.5`, response and operation-radius constraints. Without `u0` and the task clock this remains a parameterized family, not a unique coordinate.

## Directly comparable outputs

Both A and B must report:

- `strict_full_window_feasible`
- `detection_window_seconds` or its rigorous bound
- `maximum_continuous_full_cover_seconds`
- `minimum_naked_seconds` or its rigorous bound
- `minimum_cover_margin_m`
- `assumptions_used`
- `missing_inputs`
- `runtime_seconds`

Agreement requirements:

- A structural certificate and B analytic bounds must agree within `1e-9` on closed-form quantities.
- A may improve a scenario-specific feasible placement, but may not exceed the analytic stationary-cloud upper bound.

## Risk monitors

- Detect any automatic defaulting of missing initial states.
- Verify M1 range-rate bound `-(V_m+V_s)≤D_dot≤-(V_m-V_s)`.
- Verify smoke radius at ages 0, 18 and 23.
- Verify no time-grid-only feasibility claim.
- Report non-uniqueness when scenario symmetry or missing coordinates leave a family of optima.
- Evaluate M2 only when a fixed heading is supplied; otherwise report its data requirement.

## Fallback C trigger

Set `observed=true` if:

1. A gives an infeasibility conclusion;
2. A and B materially disagree;
3. the optimum is on the feasible boundary and independent checks cannot verify it reliably.

C remains unimplemented in round1. Because condition 1 fired, round2 implements only:

- outward-rounded upper bound for any fixed-cloud complete-cover interval;
- outward-rounded lower bound for the M1 detection window;
- positive separation certificate between those intervals;
- no general-purpose branch-and-bound machinery.

## Files

```text
code/Q1/q1_common.py
code/Q1/q1_event_model.py
code/Q1/q1_analytic_baseline.py
code/Q1/q1_run.py
results/Q1/experiments/round1/
├── tables/q1_feasibility_bounds.csv
├── metrics/q1_structural_metrics.json
└── run_summary.json
```

No figure is required for the structural run. A later supplied scenario may add a diagnostic trajectory figure.

## Expected environment and runtime

- Python 3.13
- NumPy, SciPy, pandas
- structural run: below 2 s
- scenario integration/optimization: target below 30 s for one supplied case

## Expected named review checks

- `syntax`: all scripts import and execute.
- `input_contract`: missing scenario inputs block coordinate claims.
- `method_alignment`: A is event-driven M1/S1; B uses the approved analytic bounds.
- `reproducibility`: deterministic outputs, seed recorded.
- `output_contract`: required metrics and `run_summary.json` exist and agree.

## Round 4 teammate-review architecture upgrade

This round preserves the accepted G1/S1 structural infeasibility numbers and
changes only the interfaces and claim discipline.

- Canonical label: `G1+S1+O0+U0`.
- `t_cmd` is command time, `t_d=t_cmd+2` is actual release, and
  `t_b=t_d+3.5`; the command-to-release meaning of the 2 s statement constant
  is a human-approved interpretation, not an unqualified problem fact.
- The old coverage-midpoint symbol `t_c` is renamed `t_m`.
- Q1 exposes the exact single-smoke identity
  `single_smoke_margin=-coverage_defect`.
- The Q1 common function refuses multi-smoke evaluation rather than using an
  uncertified finite grid; Q2 supplies the certified union-geometry kernel.
- Structural capacity and executable optimum are separate output fields.
- Execution, input, feasibility and certificate states are separate.
- G2 duration is only a necessary condition; S2 drift uses relative velocity
  and remains an extension without wind data.

Added checks:

- command/release/burst event-chain identities;
- 1000-case exact single-smoke defect degeneration;
- full-radius burst-interval endpoints;
- explicit guard against uncertified multi-smoke evaluation;
- scenario schema with no defaulted absolute geometry;
- Q1-to-Q2 interface contract.
