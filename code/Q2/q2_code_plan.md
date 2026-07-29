# Q2 Python Code Plan — round1 pre-optimization validation

## Purpose and scope

本轮只执行建模手在 `q2_method_choice` 中要求的正式优化前最小验证实验，不求三弹最终最优解。

- 主方案 A：验证风险探针给出的两弹相对候选能否在**连续时间**内使舰船整个圆盘始终被烟幕并集覆盖。
- baseline B：计算独立单弹完整覆盖的 1/2/3 弹解析容量，并构造带正重叠的三弹保守方案。
- C：只记录触发条件，不生成任何 C 代码。

若 A 验证失败，只报告失败证据；不得调整判据或用网格结果替代连续证书。

## Approval

- implementation target: Python
- round: `round1`
- round label: `preoptimization_validation`
- approved objective scope: `q2_objective_scope` = O3
- approved method decision: `q2_method_choice`
- main: A
- usable baseline: B
- dormant fallback: C
- seed: 2026

## Input contract

### Q1/M1/S1 canonical constants

| Field | Value | Unit |
|---|---:|---|
| `ship_speed` | 7.71 | m/s |
| `ship_radius` | 80 | m |
| `smoke_max_radius` | 120 | m |
| `smoke_constant_duration` | 18 | s |
| `smoke_decay_duration` | 5 | s |
| `bomb_burst_delay` | 3.5 | s |
| `uav_speed` | 28 | m/s |
| `min_drop_interval` | 1 | s |
| `conservative_serial_response_interval` | 2 | s |
| `missile_speed` | 320 | m/s |
| `detection_distance` | 8000 | m |

### Two-bomb relative candidate to validate

This candidate is evidence from the Q2 risk probe, not a final result.

| Field | Value | Unit |
|---|---:|---|
| cloud centers along ship track | `[0, 128.09582447]` | m |
| relative burst times | `[-6.76157575, 4.06443896]` | s |
| target window start | `-4.37575009` | s |
| target window length | `(8000-80)/(320-7.71)` | s |

Time and position origins are arbitrary. Absolute first-drop feasibility is not tested because `u_0`, the base/reference point and the task-clock origin are absent.

## Mathematical validation

For collinear fixed cloud centers, write the ship center as `s(t)=V_s t` and a ship-relative horizontal coordinate as `ξ`.

The ship cross-section half-height is

`h_s(ξ)=sqrt(R_s²-ξ²)`.

Smoke `j` supplies

`h_j(ξ,t)=sqrt(r_j(t)²-(s(t)+ξ-c_j)²)`

where defined. Full joint cover is equivalent to

`max_j h_j(ξ,t) >= h_s(ξ)` for every `ξ∈[-R_s,R_s]`.

### Validator 1 — certified interval split

For two collinear clouds `c_1<c_2`, use one of these sufficient-and-exact spatial modes on each time box:

1. cloud 1 independently contains the ship disk;
2. cloud 2 independently contains the ship disk;
3. the ship disk is split at a horizontal coordinate `q`, its left part is contained in cloud 1 and right part in cloud 2.

When `a_1=s-c_1>0` and `a_2=s-c_2<0`,

`q_1=(r_1²-a_1²-R_s²)/(2a_1)`,

`q_2=(r_2²-a_2²-R_s²)/(2a_2)`.

A valid split exists iff

`q_2≤q_1`, `q_1≥-R_s`, and `q_2≤R_s`.

Use outward-rounded interval arithmetic over time boxes. Split at every burst, constant-phase end, decay end and denominator sign event. Recursively bisect any unresolved box. A PASS requires the entire requested window to be covered by certified boxes with no unresolved interval.

### Validator 2 — independent adaptive geometry

At a fixed time, partition `ξ∈[-R_s,R_s]` by:

- target endpoints;
- smoke support endpoints;
- equality points of smoke squared half-heights.

On each partition cell the active smoke is fixed and the squared-height slack is linear in `ξ`, so its minimum is at a cell endpoint. This gives an exact fixed-time spatial check, including the disk interior rather than only the circumference.

Across time:

- split at all smoke-radius phase events;
- minimize the exact fixed-time slack on every time phase with bounded scalar optimization and dense bracketing;
- independently compute a high-resolution geometric disk difference at every event, detected minimizer and neighboring times.

Validator 2 is an independent numerical cross-check. Validator 1 carries the continuous certificate.

## A computation steps

1. Load constants and the relative two-bomb candidate.
2. Verify both smoke-radius functions and event ordering.
3. Run validator 1 over the complete worst-case M1 window.
4. Run validator 2 and record its minimum slack time and all internal/boundary checks.
5. Calculate relative drop times `t_j^d=t_j^b-3.5`.
6. For the same inherited heading, calculate consecutive drop-point distance and UAV transition slack.
7. Check both 1 s and conservative 2 s inter-drop interpretations.
8. Return `blocked_missing_initial_state` for absolute first-drop and 12 km checks.

## B computation steps

1. Compute `T_1=2(R_c-R_s)/V_s`.
2. Report capacities `nT_1` for `n=1,2,3`.
3. Construct three-bomb chains at overlap `δ=0`, `0.5 s`, and `1 s`.
4. Compare each chain with the M1 lower and upper window bounds.
5. Verify exact interval union and transition reachability in relative coordinates.
6. Mark the result as a conservative feasible lower bound, never as the multi-smoke global upper bound.

## Comparable outputs

| Metric | A | B |
|---|---|---|
| full worst-M1-window cover | certified boolean | duration-feasibility boolean |
| bombs used | 2 candidate | minimum within conservative chain |
| continuous covered duration | s | s |
| no-gap certificate | interval boxes | analytic interval union |
| geometry margin/slack | interval lower bound + independent minimum | single-cloud margin/overlap |
| relative UAV transition slack | m and s | m and s |
| absolute first-drop status | blocked/available | blocked/available |
| robustness evidence | validation neighborhood only | overlap sensitivity |
| runtime | s | s |

## Acceptance criteria

A may be called “validated for the relative M1/S1 scenario” only when all hold:

1. Validator 1 certifies every point of the entire `25.3610426206 s` window.
2. There are zero unresolved time boxes and zero certified time gaps.
3. Validator 2 returns nonnegative minimum spatial slack and no internal or boundary uncovered point.
4. The two validators agree on feasibility and event ordering.
5. Independent high-resolution disk-difference checks return no material uncovered area at all critical times.
6. Relative UAV transition distance and both inter-drop timing interpretations pass.

Even after PASS, the result must remain parameterized and carry the warning that absolute first-drop/12 km feasibility is blocked.

## Failure handling

- Candidate fails but both validators agree: save the counterexample time/point; remain with method A and do not activate C automatically.
- Validators disagree: record the disagreement and trigger C eligibility; do not announce feasibility.
- Validator 1 cannot terminate within the box/time budget: trigger C eligibility.
- B must still run and provide the conservative comparison even when A fails.

## Output contract

```text
results/Q2/experiments/round1/
├── metrics/
│   ├── q2_continuous_validation.json
│   └── q2_baseline_metrics.json
├── tables/
│   ├── q2_critical_times.csv
│   └── q2_method_comparison.csv
├── figures/
│   └── q2_validation_margin_diagnostic.png
└── run_summary.json
```

The figure is Type 1 diagnostic evidence, not a paper figure.

## Required run-summary warnings

- relative coordinates only;
- no absolute UAV initial state or operation-radius reference;
- no nominal wind drift;
- two-bomb validation is not the three-bomb capacity optimum;
- C was not implemented.

## Dependencies and expected runtime

- Python 3.13
- NumPy, SciPy, Shapely, Matplotlib
- fixed seed 2026
- expected runtime below 2 minutes

## Downstream named review checks

- `syntax`
- `input_contract`
- `method_alignment`
- `reproducibility`
- `output_contract`
- `continuous_geometry_certificate`
- `boundary_and_interior_coverage`
- `independent_validator_agreement`
- `raw_data_protection`

# Round 2 formal optimization addendum

Round 1 satisfied the human-mandated minimum validation experiment, so round 2
is authorized to optimize method A and retain method B as the mandatory
baseline. Method C remains unimplemented.

## Round 2 questions

1. What is the minimum number of bombs needed to cover the complete worst-case
   M1 detection window?
2. What continuous-cover durations are attainable with one, two and three
   bombs?
3. How much of the reported improvement over B comes from true spatial union
   coverage rather than independent single-cloud interval chaining?

## Optimization domain and claim boundary

- The relative ship track is the x-axis and the ship centre is
  `s(t)=7.71t`.
- Smoke centres are fixed after burst, as required by S1.
- The capacity search uses the canonical collinear family. Translation in
  space and time is normalized away.
- One-bomb capacity is analytic.
- The two-bomb collinear frontier is reduced to a one-dimensional bridge
  tangency equation and independently checked in continuous time.
- The three-bomb value is a reproducible multi-start numerical search result
  followed by exact fixed-time cross-section checks and adaptive
  continuous-time validation. Unless a matching upper bound is proved, it must
  be called the **best verified collinear capacity**, not the global optimum.
- Absolute first-drop position and the 12 km operational-radius check remain
  blocked because the problem data do not specify a UAV initial state,
  reference base or absolute task clock.

## Exact fixed-time union geometry

For ship-relative horizontal coordinate `xi in [-Rs,Rs]`, smoke `j` covers the
ship cross-section when

`L_j(xi,t)=r_j(t)^2-Rs^2-(s(t)-c_j)^2-2(s(t)-c_j)xi >= 0`.

At fixed time each `L_j` is affine in `xi`. Therefore
`min_xi max_j L_j` is attained at a ship-disk endpoint or at a pairwise
intersection of two affine functions. Evaluating this finite set checks the
entire disk interior and boundary exactly up to floating-point rounding.

## Round 2 acceptance rules

- The two-bomb minimum-resource M1 plan is accepted only by reference to the
  already-passed round-1 continuous interval certificate and independent
  geometry validator.
- A capacity candidate must have one connected covered component, no detected
  internal gap, and nonnegative exact fixed-time margin at all reported
  critical points.
- Adaptive phase minimization and a much finer independent scan must agree.
- A boundary optimum with near-zero margin is labelled boundary-sensitive.
- B is rerun and compared using the same units and M1 upper-window target.
- C is triggered only by the human-approved conditions; merely finding a
  boundary-sensitive capacity optimum does not silently implement C.

## Round 2 outputs

```text
results/Q2/experiments/round2/
├── metrics/
│   ├── q2_two_bomb_minimum_resource_plan.json
│   └── q2_capacity_frontier.json
├── tables/
│   ├── q2_capacity_frontier.csv
│   └── q2_verified_schedules.csv
├── figures/
│   └── q2_capacity_frontier.png
└── run_summary.json
```

Required review additions:

- `capacity_claim_calibration`
- `exact_cross_section_geometry`
- `continuous_time_gap_check`
- `baseline_comparison`
