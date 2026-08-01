# Q4 robustness and final technical audit report

Scope: **SYNTHETIC_SCENARIO_ONLY · UNFROZEN · RECONSTRUCTED_SYNTHETIC_SCENARIO**.

The nine-scenario matrix was rebuilt transparently because no complete Q4-S2 input or implementation exists in reachable Git history. Work-guide numbers were not used in template generation, candidate generation, objectives, constraints, acceptance, or test conditions.

## Independent technical audit

- Canonical shared-action audit: `56/56` PASS.
- Independent five-UAV schedule replay: `22/22` PASS.
- Candidate conservation: `302 raw instances -> 441 role assignments -> 373 admitted + 68 rejected`.
- Network-node conservation: `675 candidate + 45 source + 45 sink = 765 total`.
- Lexicographic replay: `143/143` PASS; later-stage lock violations: `0`.
- All four reconstructed L/T endpoints are retained. Human-selected representatives: `P1_L_RECONSTRUCTED, P2_L_RECONSTRUCTED`.
- P1 and P2 are separate comparison groups and were not ranked against each other.
- Selection rule: defence lexicography first, then total path, turn proxy and plan changes.
- P1-L is selected from a numerically equivalent pair by the authorized L/stable-id tie break.
- P2-L is selected because it reduces total path by 71.65123806256133 m; P2-T remains the lower-turn alternative.
- Representative selection status: `human_selected_from_verified_reconstructed_endpoints`.
- Straight-segment operating-radius certificates use convexity of distance to the base: the maximum on each segment occurs at an endpoint.
- Pairwise UAV safety is recomputed by analytic minimisation of relative affine trajectories over every overlapping segment interval.

## Threshold evidence

- Lead-time values tested: 40.0, 45.0, 47.5, 50.0, 55.0, 60.0 s.
- Observed transition intervals: none in tested grid.
- Commitment values tested: 0, 5, 8, 12 and 20 s.
- Commitment conclusion: `no_change_observed_within_tested_range`.
- Wall-clock solver limits are environment-dependent and excluded from the deterministic core hash set.
- The deterministic forced-no-incumbent case triggered Q4-B and the takeover plan passed the same hard validation.

## Evidence limits

- No real missile-batch table, five-UAV state, d_safe, home reference, or uncertainty distribution was supplied.
- Q3 is an unfrozen dependency accepted only at the exact recorded hashes.
- The MILP proves lexicographic optimality only within the current finite verified template-route network.
- Finite critical-shift and role-assignment sampling is not a completeness proof for continuous time or all possible templates.
- Instantaneous heading changes are a path/turn proxy; minimum turning radius and full flight dynamics are not modeled.
- No real success probability, real deployment claim, continuous global optimum, or current frozen result is asserted.
