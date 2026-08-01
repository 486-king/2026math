# Q3 production implementation

This directory implements the accepted Q3-A main method and mandatory Q3-B
comparison for the `SYNTHETIC_SCENARIO_ONLY`, `UNFROZEN` standard scenario.

Run:

```powershell
python code/Q3/q3_run_round3.py --all
```

The model scope is a two-dimensional straight UAV deployment model with
collinear smoke centers, G1 worst-window coverage, S1 fixed post-burst smoke
centers, O0 full-ship-disk coverage, and U0 nominal no drift. Continuous
coverage reuses the committed Q2 exact cross-section and time-certificate
implementation. Pairwise UAV safety is minimized analytically on each relative
linear segment; no time grid is used for the safety certificate.

P2 is a human-selected fixed reference plan that is independently reconstructed.
Its reference values are loaded only after the derived quantities are computed
and never control objectives, constraints, candidate acceptance, or continuous
certificates.

The repository-wide history audit recovered the complete historical P1
`A-00017` and P4 `A-00033` configurations from commit
`36b874664ad9b814e5768c7c6c1e008f01374a54`. They pass the current event,
deployment, continuous-coverage, continuous-safety, strict-double-coverage,
and N-1 calculations and are therefore named
`P1_LEGACY_REFERENCE_VERIFIED` and `P4_LEGACY_REFERENCE_VERIFIED`.

The same history audit recovered the old Q3-B `B-3` configuration. It does
not pass the current deployment gate because UAV 3 requires
`t_start=2.895126922364277 s`, outside the allowed `[-60,0] s` interval.
It is kept separately as `Q3_B_LEGACY_REFERENCE_ONLY` and is never ranked as
a verified candidate. The current usable baseline is
`Q3_B_RECONSTRUCTED_TRANSPARENT_BASELINE`, derived from the Q2 conservative
three-interval structure. Its safety, path, and turn metrics differ from the
legacy reference because the responsibility assignment is different. It is
not an exact reproduction of the old Q3-B, and this distinction does not
change any P2 verification result.

The verified candidate-pool audit combines 181 candidates whose normal three-smoke coverage
is inherited only from the canonical two-smoke core, 24 deterministic genuine
six-variable multistart results covering all `3!` assignments, and the two
independently verified historical P1/P4 plans. Every other metric—including
event/deployment feasibility, continuous safety, strict double coverage,
N-1, warning, path, and turn—is recomputed per candidate. The resulting
output is a **Verified nondominated synthetic candidate set**. Its formal scope
is `hybrid_fixed_core_and_structured_six_variable_multistart_search`, and its
non-dominance relation is
`nondominated_within_verified_candidate_pool`. Continuous-problem Pareto
completeness is `not_proved`: the finite 207-candidate pool contains 181
fixed-core candidates, 24 full six-variable candidates, and two independently
revalidated historical candidates. No completeness or global Pareto-front
claim is made for the continuous non-convex problem.

`d_safe` remains a parameter. The safety table and figure report three
different quantities: execution rate, unconditional joint executable-and-safe
retention, and safety retention conditional on executability. The last two
must not be interchanged. Combined position/heading tests are finite
exploratory synthetic stress tests, not real probabilities. Availability-time
distributions, real UAV initial states, real energy, turn radius, wind drift,
and absolute 12 km base reachability remain unavailable.

The available runtime is Python 3.12.13 / NumPy 2.3.5 rather than the work
guide's Python 3.13 / NumPy 2.4.4. Compatibility is verified only in the
available environment; byte-identical repeated runs do not constitute a rerun
under the guide-specified versions.

Production execution does not call pytest or require the deleted development
tests. It never creates `frozen_numbers.json`, enables paper writing, or enters
Q4.
