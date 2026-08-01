# Q4 rolling finite-template scheduler

Run from the repository root:

```powershell
$env:OMP_NUM_THREADS='1'
$env:OPENBLAS_NUM_THREADS='1'
$env:MKL_NUM_THREADS='1'
$env:NUMEXPR_NUM_THREADS='1'
python code/Q4/q4_run.py
```

Q4-A is a rolling-horizon lexicographic MILP over a finite, revalidated
template and UAV-state-flow network. Q4-B is the feasibility-filtered greedy
baseline and takes over only when A has no feasible incumbent.

All concrete inputs and outputs are `SYNTHETIC_SCENARIO_ONLY`, `UNFROZEN`, and
`RECONSTRUCTED_SYNTHETIC_SCENARIO`. The work-guide summary is reference-only
and is excluded from candidate generation, objectives, constraints, solver
acceptance, and test pass conditions. No continuous-space or
all-possible-template global optimum is claimed.

The accepted scenario identity is `Q4_S2_RECONSTRUCTED_SYNTHETIC`, with
`legacy_identity_claimed=false`. Q4 is at G4 for modelling handoff only:
numerical freezing, final paper-number use, and final assembly remain
unauthorized.

Representative endpoints use
`lexicographic_defence_then_path_then_turn_then_change`. P1 and P2 are separate
comparison groups, so no cross-group champion is claimed. `P1_L_RECONSTRUCTED`
and `P2_L_RECONSTRUCTED` are the selected representatives.
`P1_T_RECONSTRUCTED` remains a numerically equivalent verified alternative;
`P2_T_RECONSTRUCTED` remains the lower-turn verified alternative. Total path
contains service and transition distance and is prioritized as the more direct
resource proxy. Turn is only a manoeuvre-complexity proxy because minimum turn
radius, turn time, and true turn energy are not modelled.
