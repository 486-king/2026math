"""One-click production entry point for Q1.

The production runner intentionally has no pytest or tests-directory dependency.
Formal tests are executed separately before release and summarized in
code/Q1/reviews/q1_final_validation.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from q1_outputs import finalize_production_run, generate_core_outputs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate and validate all Q1 production artifacts.")
    parser.add_argument("--all", action="store_true", help="Generate all Q1 production artifacts.")
    parser.add_argument("--scenario", type=Path, help="Optional complete scenario JSON.")
    return parser.parse_args()


def main() -> int:
<<<<<<< HEAD
    np.random.seed(SEED)
    cfg = Q1Constants()
    errors = validate_constants(cfg)
    if errors:
        raise ValueError("; ".join(errors))

    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    METRIC_DIR.mkdir(parents=True, exist_ok=True)

    boundary_checks = {
        "radius_age_0_m": smoke_radius(0.0, cfg),
        "radius_age_18_m": smoke_radius(18.0, cfg),
        "radius_age_23_m": smoke_radius(23.0, cfg),
        "radius_age_23_plus_m": smoke_radius(23.0 + 1e-9, cfg),
    }
    expected = {
        "radius_age_0_m": 120.0,
        "radius_age_18_m": 120.0,
        "radius_age_23_m": 0.0,
        "radius_age_23_plus_m": 0.0,
    }
    if any(abs(boundary_checks[k] - expected[k]) > 1e-7 for k in expected):
        raise AssertionError(f"smoke boundary check failed: {boundary_checks}")

    start_a = time.perf_counter()
    main_result = structural_main_result(cfg)
    runtime_a = time.perf_counter() - start_a
    main_result["runtime_seconds"] = runtime_a

    start_b = time.perf_counter()
    baseline_result = run_baseline(cfg)
    runtime_b = time.perf_counter() - start_b
    baseline_result["runtime_seconds"] = runtime_b

    comparable_keys = [
        "strict_full_window_feasible",
        "maximum_continuous_full_cover_seconds",
    ]
    exact_agreement = all(
        main_result[key] == baseline_result[key] for key in comparable_keys
    )
    bound_difference = abs(
        float(main_result["detection_window_seconds"]["lower_bound"])
        - float(baseline_result["detection_window_seconds"]["lower_bound"])
    )
    naked_difference = abs(
        float(main_result["minimum_naked_seconds"]["lower_bound"])
        - float(baseline_result["minimum_naked_seconds"]["lower_bound"])
    )
    agreement_tolerance = 1e-9
    comparison_pass = (
        exact_agreement
        and bound_difference <= agreement_tolerance
        and naked_difference <= agreement_tolerance
    )

    fallback_observed = (
        (not bool(main_result["strict_full_window_feasible"]))
        or (not comparison_pass)
    )
    metrics = {
        "schema_version": 1,
        "question_id": "Q1",
        "round": "round1",
        "constants": cfg.to_dict(),
        "main": main_result,
        "baseline": baseline_result,
        "comparison": {
            "exact_agreement_on_core_outputs": exact_agreement,
            "detection_lower_bound_difference_s": bound_difference,
            "naked_lower_bound_difference_s": naked_difference,
            "tolerance": agreement_tolerance,
            "status": "PASS" if comparison_pass else "FAIL",
        },
        "boundary_checks": boundary_checks,
        "g2_robustness_reference": {
            "status": "blocked_missing_fixed_heading_and_initial_state",
            "feasibility_change_condition": (
                "G2 can pass the duration necessary condition only if the "
                "distance-and-FOV window is no longer than the fixed-smoke "
                "complete-cover upper bound; this is not sufficient."
            ),
            "threshold_seconds": main_result[
                "maximum_continuous_full_cover_seconds"
            ],
        },
        "fallback_trigger": {
            "fallback_id": "C",
            "observed": fallback_observed,
            "evidence": (
                "A returned strict infeasibility, which is a human-approved C trigger"
                if not bool(main_result["strict_full_window_feasible"])
                else (
                    "A/B structural outputs disagree"
                    if not comparison_pass
                    else "No trigger observed"
                )
            ),
        },
    }

    metrics_path = METRIC_DIR / "q1_structural_metrics.json"
    write_json(metrics_path, metrics)

    table_path = TABLE_DIR / "q1_feasibility_bounds.csv"
    with table_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "quantity",
                "value",
                "unit",
                "interpretation",
            ],
        )
        writer.writeheader()
        writer.writerows(
            [
                {
                    "quantity": "stationary_smoke_max_full_cover",
                    "value": main_result[
                        "maximum_continuous_full_cover_seconds"
                    ],
                    "unit": "s",
                    "interpretation": "rigorous upper bound under S1",
                },
                {
                    "quantity": "g1_detection_window_lower_bound",
                    "value": main_result["detection_window_seconds"][
                        "lower_bound"
                    ],
                    "unit": "s",
                    "interpretation": (
                        "shortest possible G1 detection window from an "
                        "already-acquired 8000 m lock to ship-disk contact"
                    ),
                },
                {
                    "quantity": "minimum_naked_time_lower_bound",
                    "value": main_result["minimum_naked_seconds"]["lower_bound"],
                    "unit": "s",
                    "interpretation": "strict lower bound before UAV reachability",
                },
                {
                    "quantity": "inherited_bomb_displacement",
                    "value": cfg.uav_speed_mps * cfg.bomb_burst_delay_s,
                    "unit": "m",
                    "interpretation": "S1 burst point minus drop point",
                },
            ]
        )

    method_common = {
        "input_files": [
            "planning/session_config.json",
            "methods/Q1/q1_decisions.jsonl",
            "code/Q1/q1_code_plan.md",
        ],
        "output_files": [
            str(metrics_path.relative_to(ROOT)).replace("\\", "/"),
            str(table_path.relative_to(ROOT)).replace("\\", "/"),
        ],
        "figure_files": [],
        "warnings": [
            "Scenario initial states are absent; no unique coordinate/time claim is produced.",
            "G2 is retained as a robustness reference but cannot run without fixed heading and initial state.",
        ],
        "errors": [],
    }
    run_summary = {
        "schema_version": 1,
        "question": "Q1",
        "round": "round1",
        "implementation_target": "python",
        "random_seed": SEED,
        "approved_decision_id": "q1_method_choice",
        "methods": [
            {
                "method_id": "A",
                "role": "main_candidate",
                "script": "code/Q1/q1_event_model.py",
                "status": "success",
                "execution_time_seconds": runtime_a,
                **method_common,
                "metrics_summary": {
                    "strict_full_window_feasible": main_result[
                        "strict_full_window_feasible"
                    ],
                    "maximum_continuous_full_cover_seconds": main_result[
                        "maximum_continuous_full_cover_seconds"
                    ],
                    "minimum_naked_seconds_lower_bound": main_result[
                        "minimum_naked_seconds"
                    ]["lower_bound"],
                    "coordinate_solution_status": main_result[
                        "coordinate_solution_status"
                    ],
                },
            },
            {
                "method_id": "B",
                "role": "usable_baseline",
                "script": "code/Q1/q1_analytic_baseline.py",
                "status": "success",
                "execution_time_seconds": runtime_b,
                **method_common,
                "metrics_summary": {
                    "strict_full_window_feasible": baseline_result[
                        "strict_full_window_feasible"
                    ],
                    "maximum_continuous_full_cover_seconds": baseline_result[
                        "maximum_continuous_full_cover_seconds"
                    ],
                    "minimum_naked_seconds_lower_bound": baseline_result[
                        "minimum_naked_seconds"
                    ]["lower_bound"],
                    "coordinate_solution_status": baseline_result[
                        "coordinate_solution_status"
                    ],
                },
            },
        ],
        "comparison": metrics["comparison"],
        "output_degeneracy": {
            "strict_feasible_set_empty_under_G1_S1_O0_U0_duration_bound": True,
            "unique_coordinate_identifiable": False,
            "interpretation": "A structural infeasibility result, not a numerical failure.",
        },
        "fallback_trigger": metrics["fallback_trigger"],
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "pandas": pd.__version__,
        },
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(),
    }
    write_json(ROUND_DIR / "run_summary.json", run_summary)
    print(json.dumps(run_summary, ensure_ascii=False, indent=2))
    return 0 if comparison_pass else 2
=======
    args = parse_args()
    try:
        context = generate_core_outputs(args.scenario)
        result = finalize_production_run(context)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"Q1 production run failed: {exc}", file=sys.stderr)
        return 1
>>>>>>> 05b4caca0369d310133e03bd82ba235ad075b5d3


if __name__ == "__main__":
    raise SystemExit(main())
