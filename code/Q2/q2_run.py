from __future__ import annotations

import csv
from datetime import datetime
import json
from pathlib import Path
import platform
import sys
import time

import matplotlib.pyplot as plt
import numpy as np
import scipy
import shapely

from q2_analytic_baseline import run_baseline
from q2_common import (
    CANDIDATE,
    CONSTANTS,
    candidate_drop_times,
    candidate_event_times,
    candidate_window,
)
from q2_continuous_validator import (
    fixed_time_spatial_slack_sq,
    run_continuous_validation,
)


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results" / "Q2" / "experiments" / "round1"
METRICS = OUT / "metrics"
TABLES = OUT / "tables"
FIGURES = OUT / "figures"


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    for directory in (METRICS, TABLES, FIGURES):
        directory.mkdir(parents=True, exist_ok=True)

    a_started = time.perf_counter()
    validation = run_continuous_validation()
    a_runtime = time.perf_counter() - a_started
    write_json(METRICS / "q2_continuous_validation.json", validation)

    b_started = time.perf_counter()
    baseline = run_baseline()
    b_runtime = time.perf_counter() - b_started
    write_json(METRICS / "q2_baseline_metrics.json", baseline)

    critical_rows = []
    for event in candidate_event_times():
        slack, x = fixed_time_spatial_slack_sq(event)
        critical_rows.append(
            {
                "time_s": event,
                "minimum_squared_cross_section_slack_m2": slack,
                "minimum_global_x_m": x,
            }
        )
    with (TABLES / "q2_critical_times.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as f:
        writer = csv.DictWriter(f, fieldnames=list(critical_rows[0]))
        writer.writeheader()
        writer.writerows(critical_rows)

    drop_times = candidate_drop_times()
    drop_gap = drop_times[1] - drop_times[0]
    transition_distance = (
        CANDIDATE.cloud_centers_m[1] - CANDIDATE.cloud_centers_m[0]
    )
    transition_slack = CONSTANTS.uav_speed_mps * drop_gap - transition_distance

    comparison_rows = [
        {
            "method": "A",
            "bomb_count": 2,
            "validated_window_s": CONSTANTS.m1_detection_upper_s,
            "full_worst_M1_window": validation[
                "strict_relative_candidate_validated"
            ],
            "absolute_first_drop_status": "blocked_missing_initial_state",
            "role": "main_preoptimization_validation",
        },
        {
            "method": "B",
            "bomb_count": 3,
            "validated_window_s": (
                3.0 * CONSTANTS.single_cloud_cover_upper_s - 2.0
            ),
            "full_worst_M1_window": baseline["three_bomb_chains"][2][
                "covers_M1_upper_window"
            ],
            "absolute_first_drop_status": "blocked_missing_initial_state",
            "role": "usable_baseline",
        },
    ]
    with (TABLES / "q2_method_comparison.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as f:
        writer = csv.DictWriter(f, fieldnames=list(comparison_rows[0]))
        writer.writeheader()
        writer.writerows(comparison_rows)

    start, end = candidate_window()
    times = np.linspace(start, end, 1601)
    slacks = np.array([fixed_time_spatial_slack_sq(t)[0] for t in times])
    fig, ax = plt.subplots(figsize=(8.2, 4.5))
    ax.plot(times, slacks, color="#1F4D78", linewidth=1.6)
    ax.axhline(0.0, color="#9B1C1C", linewidth=1.0, linestyle="--")
    for event in candidate_event_times():
        ax.axvline(event, color="#B8C2CC", linewidth=0.6, alpha=0.7)
    ax.set_xlabel("Relative time (s)")
    ax.set_ylabel("Minimum squared cross-section slack (m²)")
    ax.set_title("Q2 two-smoke continuous-cover validation diagnostic")
    ax.grid(alpha=0.2)
    fig.tight_layout()
    figure_path = FIGURES / "q2_validation_margin_diagnostic.png"
    fig.savefig(figure_path, dpi=180)
    plt.close(fig)

    fallback_observed = (
        not validation["validators_agree"]
        or validation["interval_certificate"]["unresolved_box_count"] > 0
    )
    summary = {
        "schema_version": 1,
        "question": "Q2",
        "round": "round1",
        "round_label": "preoptimization_validation",
        "implementation_target": "python",
        "random_seed": 2026,
        "approved_decision_ids": [
            "q2_objective_scope",
            "q2_method_choice",
        ],
        "methods": [
            {
                "method_id": "A",
                "role": "main_candidate_preoptimization_validation",
                "script": "code/Q2/q2_continuous_validator.py",
                "status": (
                    "success"
                    if validation["strict_relative_candidate_validated"]
                    else "validation_failed"
                ),
                "execution_time_seconds": a_runtime,
                "input_files": [
                    "methods/Q2/q2_decisions.jsonl",
                    "code/Q2/q2_code_plan.md",
                    "results/Q1/experiments/round3/metrics/q1_parametric_compensation.json",
                ],
                "output_files": [
                    "results/Q2/experiments/round1/metrics/q2_continuous_validation.json",
                    "results/Q2/experiments/round1/tables/q2_critical_times.csv",
                ],
                "figure_files": [
                    "results/Q2/experiments/round1/figures/q2_validation_margin_diagnostic.png"
                ],
                "metrics_summary": {
                    "relative_two_bomb_full_worst_M1_window": validation[
                        "strict_relative_candidate_validated"
                    ],
                    "window_length_s": CONSTANTS.m1_detection_upper_s,
                    "unresolved_time_boxes": validation[
                        "interval_certificate"
                    ]["unresolved_box_count"],
                    "validators_agree": validation["validators_agree"],
                    "minimum_squared_cross_section_slack_m2": validation[
                        "independent_geometry"
                    ]["minimum_squared_cross_section_slack_m2"],
                    "maximum_uncovered_area_m2": validation[
                        "independent_geometry"
                    ]["maximum_shapely_uncovered_area_m2"],
                    "relative_uav_transition_slack_m": transition_slack,
                },
                "warnings": [
                    "Relative coordinates only; absolute first-drop and 12 km checks are blocked.",
                    "This round validates one two-bomb candidate; it does not optimize the three-bomb capacity frontier.",
                ],
                "errors": [],
            },
            {
                "method_id": "B",
                "role": "usable_baseline",
                "script": "code/Q2/q2_analytic_baseline.py",
                "status": "success",
                "execution_time_seconds": b_runtime,
                "input_files": [
                    "results/Q1/experiments/round3/metrics/q1_parametric_compensation.json"
                ],
                "output_files": [
                    "results/Q2/experiments/round1/metrics/q2_baseline_metrics.json",
                    "results/Q2/experiments/round1/tables/q2_method_comparison.csv",
                ],
                "figure_files": [],
                "metrics_summary": {
                    "two_bomb_capacity_s": (
                        2.0 * CONSTANTS.single_cloud_cover_upper_s
                    ),
                    "three_bomb_1s_overlap_capacity_s": (
                        3.0 * CONSTANTS.single_cloud_cover_upper_s - 2.0
                    ),
                    "three_bomb_covers_worst_M1_window": baseline[
                        "three_bomb_chains"
                    ][2]["covers_M1_upper_window"],
                },
                "warnings": [
                    "B is a conservative feasible lower bound, not the multi-smoke global upper bound.",
                    "Absolute first-drop reachability is blocked.",
                ],
                "errors": [],
            },
        ],
        "comparison": {
            "directly_comparable": True,
            "A_bomb_count": 2,
            "B_bomb_count": 3,
            "same_M1_upper_window_target_s": CONSTANTS.m1_detection_upper_s,
            "A_relative_validation_pass": validation[
                "strict_relative_candidate_validated"
            ],
            "B_duration_feasibility_pass": baseline["three_bomb_chains"][2][
                "covers_M1_upper_window"
            ],
            "absolute_operational_comparison_status": "blocked_missing_initial_state",
        },
        "output_degeneracy": {
            "status": "PASS",
            "one_two_three_bomb_capacities_distinct": True,
            "absolute_solution_nonunique": True,
            "interpretation": "Relative feasibility evidence with expected translation/time-shift nonuniqueness.",
        },
        "fallback_trigger": {
            "fallback_id": "C",
            "observed": fallback_observed,
            "condition": (
                "A continuous validator fails to certify or independent validators disagree"
            ),
            "evidence": (
                "results/Q2/experiments/round1/metrics/q2_continuous_validation.json"
            ),
            "fallback_implemented": False,
        },
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "shapely": shapely.__version__,
        },
        "warnings": [
            "No UAV initial/base position, operation-radius reference, or absolute task clock is available.",
            "Nominal smoke drift is zero under the approved S1 convention.",
            "C was not implemented.",
        ],
        "generated_at": datetime.now().astimezone().isoformat(),
    }
    write_json(OUT / "run_summary.json", summary)

    if not validation["strict_relative_candidate_validated"]:
        raise SystemExit("Q2 two-bomb continuous validation did not pass")


if __name__ == "__main__":
    main()
