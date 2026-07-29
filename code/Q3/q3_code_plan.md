# Q3 Code Plan

## Target and round

- Language: Python
- Round: `round1_formal_event_feasibility`
- Approved main: `Q3-A`
- Mandatory baseline: `Q3-B`
- Dormant fallback: `Q3-C`
- Decisions: `q3_method_choice`,
  `q3_parameterized_and_standardized_scenario`
- Seed: 2026

## Input contract

Formal standardized input:
`workspace/data_clean/q3_standardized_scenario.json`.
Every output must retain `SYNTHETIC_SCENARIO_ONLY`.

The parameterized model uses
`u_i(0)=(x_i,y_i)`, initial heading `psi_i`, availability `a_i`,
and `d_safe`. The task clock has `t=0` at G1 lock on the 8000 m boundary.

## Mandatory event-feasibility gate

For every UAV,

`t_cmd_i >= a_i`,
`t_d_i=t_cmd_i+2`,
`t_b_i=t_d_i+3.5`.

Therefore `min_i t_b_i >= min_i a_i+5.5`.
If the defense window begins at zero and no smoke exists before its burst,
full defense requires the necessary condition

`min_i a_i <= -5.5 s`.

When it fails, Q3-A and Q3-B must both stop before optimization and return:

- `execution_status=PASS`;
- `input_status=PASS`;
- `feasibility_status=FAIL`;
- `certificate_status=PASS`;
- a continuous naked-interval certificate;
- no Pareto front, representative solution, coordinates, N-1 metrics, or
  fabricated fallback result.

## Q3-A computation

1. Validate the scenario and event chain.
2. Apply the event-feasibility gate.
3. Only if the gate passes: generate reachable three-UAV candidates, enforce
   continuous multi-circle union coverage and continuous pairwise safety,
   construct the epsilon-constraint Pareto set, compute N-1 metrics, and compare
   knee/ideal-point/layered representative rules.
4. If the three representative rules disagree, stop for human judgment.

For the approved standardized scenario the event gate is expected to fail, so
step 3 is not executed and no optimization result may be invented.

## Q3-B computation

Use the same event gate before constructing front/middle/rear smoke duties and
the 3! assignment baseline. If the gate fails, return the same feasibility
status and record that the baseline cannot satisfy full-window defense.

## Continuous-validator regression

The existing Q2 positive-margin two-smoke schedule is used only as a
`VALIDATOR_REGRESSION_ONLY` recovery fixture. Run both:

- interval continuous-time certificate;
- independent disk-difference geometry check.

This verifies that the continuous union validator can accept a known feasible
multi-smoke case. It is not a Q3 formal candidate.

## Outputs

`results/Q3/experiments/round1/`

- `metrics/q3_event_infeasibility_certificate.json`
- `metrics/q3_standard_scenario_status.json`
- `metrics/q3_validator_recovery_test.json`
- `tables/q3_availability_sensitivity.csv`
- `tables/q3_method_comparison.csv`
- `figures/q3_event_timeline.png`
- `run_summary.json`

## Comparable A/B metrics

- full-window defense status;
- earliest possible burst time;
- guaranteed initial naked duration;
- necessary availability threshold;
- optimization/Pareto status;
- reason for non-evaluation of path, turn, N-1 and `d_safe` outputs.

## Risk and fallback handling

- The old 864-candidate and 127.73 m probe values are prohibited from round-1
  formal outputs.
- Q3-C remains absent.
- Infeasibility caused by command/release/burst timing does not activate Q3-C,
  because uncertainty modeling cannot remove a deterministic 5.5 s delay.

## Expected review checks

`syntax`, `input_contract`, `method_alignment`, `reproducibility`,
`output_contract`, `event_chain_certificate`,
`continuous_validator_regression`, `claim_calibration`.

## Round-2 prewarning adjustment

Decision `q3_result_adjust_pretask` expands the availability range to
`a_i in [-60,0] s` while keeping the defense window at `t=0`.

Round 2:

1. shifts the continuously certified Q2 two-smoke schedule to `[0,T_G1]`;
2. searches a third collinear smoke centre/burst for redundancy;
3. assigns the three standardized UAVs by all 3! permutations;
4. computes straight predeployment routes from `u_i(a_i)` to release points;
5. analytically inverts each route’s latest feasible availability time;
6. checks pairwise safety by exact minimum distance of piecewise-linear relative
   trajectories;
7. constructs Pareto fronts over coverage, N-1 degradation, path and turn;
8. validates reported candidates by continuous envelope minimization and an
   independent disk-difference geometry calculation.

Formal claim scope is the standardized scenario and canonical collinear
smoke-centre candidate family, not a two-dimensional global optimum.

## Round-3 selected P2 analysis

Human decision `q3_representative_choice_p2` selects `A-00217` as the formal
representative, retains `A-00017` for large-clearance/low-path use,
`A-00033` for minimum-warning use, and keeps Q3-B as the transparent baseline.

Round 3 must:

1. rebuild the three fixed P2 routes from states defined at each `a_i`;
2. report command, release, burst, release-point and smoke-centre events;
3. save complete sampled trajectories while computing minimum pair distance
   analytically over piecewise-linear relative trajectories;
4. integrate the G1 pure-pursuit window over `beta in [0,pi]` and verify that
   it never exceeds the already certified conservative window;
5. scan every initial coordinate one-at-a-time over `[-200,200] m`, every
   initial heading over `[-45,45] deg`, and run 2000 fixed-seed combined
   perturbations;
6. report the full nominal `d_safe` interval and perturbation retention curve;
7. recompute all three single-UAV failure intervals with transition roots
   refined by bisection rather than retaining round-2 grid approximations;
8. compare P2 with P1, P4 and Q3-B under the same refined metrics.

The predeclared fallback diagnostic is not a problem constant. It triggers a
P1 re-comparison when any bearing fails, combined execution falls below 95%,
fewer than 80% of combined cases retain half the nominal P2 clearance, or any
one-at-a-time boundary case cannot execute within the 60 s pre-task range.

Round-3 output remains `SYNTHETIC_SCENARIO_ONLY`. A false fallback diagnostic
does not itself constitute the human stability or package-signoff decision.
