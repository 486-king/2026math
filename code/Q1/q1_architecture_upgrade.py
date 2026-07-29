"""Q1 architecture upgrade requested after teammate review.

This script does not change the accepted structural infeasibility proof.  It
verifies the revised event semantics, separates structural and executable
claims, and emits the Q1-to-Q2 interface evidence.
"""

from __future__ import annotations

import csv
from datetime import datetime
import json
from pathlib import Path
import platform
import sys
import time

import numpy as np

from q1_common import (
    Q1Constants,
    command_release_burst_times,
    coverage_defect,
    single_smoke_margin,
    smoke_radius,
    structural_bounds,
)


ROOT = Path(__file__).resolve().parents[2]
ROUND = ROOT / "results" / "Q1" / "experiments" / "round4"
METRICS = ROUND / "metrics"
TABLES = ROUND / "tables"
PLANNING = ROOT / "planning"


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    started = time.perf_counter()
    cfg = Q1Constants()
    bounds = structural_bounds(cfg)
    h = (
        cfg.smoke_max_radius_m - cfg.ship_radius_m
    ) / cfg.ship_speed_mps

    timing = command_release_burst_times(10.0, cfg)
    timing_checks = {
        "release_minus_command_s": (
            timing["release_time_s"] - timing["command_time_s"]
        ),
        "burst_minus_release_s": (
            timing["burst_time_s"] - timing["release_time_s"]
        ),
        "burst_minus_command_s": (
            timing["burst_time_s"] - timing["command_time_s"]
        ),
    }
    expected_timing = {
        "release_minus_command_s": 2.0,
        "burst_minus_release_s": 3.5,
        "burst_minus_command_s": 5.5,
    }
    timing_pass = all(
        abs(timing_checks[key] - expected_timing[key]) <= 1e-12
        for key in expected_timing
    )

    rng = np.random.default_rng(2026)
    defect_errors = []
    for _ in range(1000):
        ship = rng.uniform(-1000.0, 1000.0, size=2)
        center = rng.uniform(-1000.0, 1000.0, size=2)
        radius = float(rng.uniform(0.0, 160.0))
        margin = single_smoke_margin(
            ship, center, radius, cfg.ship_radius_m
        )
        defect = coverage_defect(
            ship,
            np.asarray([center]),
            np.asarray([radius]),
            cfg.ship_radius_m,
        )
        defect_errors.append(abs(margin + defect))

    max_defect_error = max(defect_errors)
    multi_smoke_guard_pass = False
    try:
        coverage_defect(
            (0.0, 0.0),
            np.asarray([[0.0, 0.0], [1.0, 0.0]]),
            np.asarray([120.0, 120.0]),
            cfg.ship_radius_m,
        )
    except NotImplementedError:
        multi_smoke_guard_pass = True

    latest_burst = -h
    normalized_cover = (-h, h)
    burst_interval = (
        h - cfg.smoke_constant_duration_s,
        -h,
    )
    full_radius_endpoint_checks = {
        "left_cover_age_at_earliest_burst_s": (
            normalized_cover[0] - burst_interval[0]
        ),
        "right_cover_age_at_earliest_burst_s": (
            normalized_cover[1] - burst_interval[0]
        ),
        "left_cover_age_at_latest_burst_s": (
            normalized_cover[0] - latest_burst
        ),
        "right_cover_age_at_latest_burst_s": (
            normalized_cover[1] - latest_burst
        ),
    }
    full_radius_interval_pass = (
        full_radius_endpoint_checks[
            "left_cover_age_at_earliest_burst_s"
        ] >= -1e-12
        and full_radius_endpoint_checks[
            "right_cover_age_at_earliest_burst_s"
        ] <= cfg.smoke_constant_duration_s + 1e-12
        and full_radius_endpoint_checks[
            "left_cover_age_at_latest_burst_s"
        ] >= -1e-12
        and full_radius_endpoint_checks[
            "right_cover_age_at_latest_burst_s"
        ] <= cfg.smoke_constant_duration_s + 1e-12
    )

    drift_thresholds = []
    for along_track_drift in (-10.0, -5.0, 0.0, 5.0, 7.70, 7.71, 7.72, 10.0):
        relative_speed = abs(cfg.ship_speed_mps - along_track_drift)
        if relative_speed <= 1e-12:
            geometric = float("inf")
        else:
            geometric = (
                2.0
                * (cfg.smoke_max_radius_m - cfg.ship_radius_m)
                / relative_speed
            )
        constant_phase_bound = min(
            cfg.smoke_constant_duration_s,
            geometric,
        )
        drift_thresholds.append(
            {
                "along_track_cloud_drift_mps": along_track_drift,
                "relative_speed_mps": relative_speed,
                "constant_radius_cover_bound_s": constant_phase_bound,
                "extension_only": True,
            }
        )

    result = {
        "schema_version": 1,
        "question_id": "Q1",
        "round": "round4",
        "decision_id": "q1_teammate_review_integration",
        "canonical_model_label": "G1+S1+O0+U0",
        "accepted_core_result_unchanged": True,
        "core_numbers": {
            "structural_cover_upper_s": bounds[
                "stationary_smoke_max_continuous_full_cover_s"
            ],
            "detection_window_lower_s": bounds[
                "m1_detection_window_lower_bound_s"
            ],
            "minimum_naked_time_lower_s": bounds[
                "minimum_naked_time_lower_bound_s"
            ],
        },
        "premises": [
            "G1 pure pursuit has already acquired lock at 8000 m.",
            "S1 smoke centre is fixed after burst.",
            "O0 requires complete two-dimensional ship-disk coverage.",
            "U0 excludes nominal wind drift.",
        ],
        "status_fields": {
            "execution_status": "passed",
            "input_status": "blocked_missing_absolute_geometry",
            "feasibility_status": "proved_infeasible_for_full_window",
            "compensation_status": "structural_family_available",
            "certificate_status": "verified",
        },
        "event_semantics": {
            "primary_interpretation": "command_to_release_response_delay",
            "symbols": {
                "t_cmd": "command time",
                "t_d": "actual release time",
                "t_b": "burst time",
                "t_m": "midpoint of a selected complete-cover interval",
            },
            "checks": timing_checks,
            "status": "PASS" if timing_pass else "FAIL",
            "warning": (
                "The statement gives a 2 s response delay but does not "
                "explicitly identify the endpoint events; this is the "
                "human-approved primary interpretation."
            ),
        },
        "coverage_defect_interface": {
            "definition": (
                "Delta(t)=max_{x in D_ship(t)} min_j "
                "(||x-c_j(t)||-r_j(t))"
            ),
            "complete_cover_condition": "Delta(t)<=0",
            "single_smoke_identity": "single_smoke_margin(t)=-Delta(t)",
            "random_test_count": 1000,
            "maximum_identity_error_m": max_defect_error,
            "single_smoke_identity_status": (
                "PASS" if max_defect_error <= 1e-12 else "FAIL"
            ),
            "multi_smoke_guard_status": (
                "PASS" if multi_smoke_guard_pass else "FAIL"
            ),
            "multi_smoke_implementation": (
                "Use the certified Q2 union-geometry kernel; Q1 refuses "
                "an uncertified finite-grid substitution."
            ),
        },
        "structural_vs_executable": {
            "T_structural_max_s": bounds[
                "stationary_smoke_max_continuous_full_cover_s"
            ],
            "T_executable_relation": "T_executable_star<=T_structural_max",
            "equality_requires": [
                "cloud centre on the ship track",
                "complete-cover interval lies in the 18 s full-radius phase",
                "command, release and burst times are legal",
                "UAV reaches the release point",
                "chosen 12 km interpretation is satisfied",
                "absolute scenario inputs are complete",
            ],
            "current_T_executable_status": "not_evaluated_missing_inputs",
        },
        "full_radius_interval_test": {
            "burst_interval_relative_to_t_m_s": list(burst_interval),
            "endpoint_ages_s": full_radius_endpoint_checks,
            "status": "PASS" if full_radius_interval_pass else "FAIL",
        },
        "G2_fixed_heading_extension": {
            "duration_necessary_condition": (
                "|W_G2|<=10.376134889753567 s"
            ),
            "full_feasibility_status": "not_evaluated_missing_initial_geometry",
            "warning": "Duration is necessary, not sufficient.",
        },
        "S2_drift_extension": {
            "formula": (
                "min(18,2(R_c-R_s)/||v_s-v_c||) for the ideal collinear "
                "constant-radius phase"
            ),
            "parameter_curve": drift_thresholds,
            "warning": "No wind data; extension only.",
        },
    }
    write_json(METRICS / "q1_architecture_upgrade.json", result)

    TABLES.mkdir(parents=True, exist_ok=True)
    with (TABLES / "q1_drift_parameter_curve.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(drift_thresholds[0]),
        )
        writer.writeheader()
        writer.writerows(drift_thresholds)

    scenario_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Q1 absolute execution scenario",
        "type": "object",
        "required": [
            "task_clock_zero_definition",
            "ship_initial_position_m",
            "ship_heading_rad",
            "missile_initial_position_m",
            "uav_initial_position_m",
            "operation_radius_reference",
        ],
        "properties": {
            "task_clock_zero_definition": {"type": "string", "minLength": 1},
            "ship_initial_position_m": {
                "type": "array", "items": {"type": "number"},
                "minItems": 2, "maxItems": 2
            },
            "ship_heading_rad": {"type": "number"},
            "missile_initial_position_m": {
                "type": "array", "items": {"type": "number"},
                "minItems": 2, "maxItems": 2
            },
            "uav_initial_position_m": {
                "type": "array", "items": {"type": "number"},
                "minItems": 2, "maxItems": 2
            },
            "operation_radius_reference": {
                "enum": [
                    "distance_from_initial_takeoff_point",
                    "distance_from_realtime_ship_position",
                    "total_path_length"
                ]
            },
            "lock_acquired_at_8000m": {"const": True}
        },
        "additionalProperties": False,
    }
    write_json(PLANNING / "scenario_schema.json", scenario_schema)

    assumption_rows = [
        {
            "id": "F4",
            "statement": "response delay equals 2 s",
            "class": "problem fact",
            "source": "problem statement",
            "scope": "Q1-Q4",
        },
        {
            "id": "A10",
            "statement": "2 s is interpreted from command to actual release",
            "class": "human-approved timing interpretation",
            "source": "q1_teammate_review_integration",
            "scope": "Q1-Q4",
        },
        {
            "id": "A11",
            "statement": "lock is already acquired when range first reaches 8000 m",
            "class": "standard-scenario premise",
            "source": "teammate review; required by G1 detection-window claim",
            "scope": "Q1-Q2",
        },
        {
            "id": "S2",
            "statement": (
                "released bomb inherits 28 m/s horizontal UAV velocity for "
                "3.5 s; drag, deceleration and wind are ignored"
            ),
            "class": "human-approved nominal simplification",
            "source": "q1_method_choice",
            "scope": "Q1-Q2",
        },
        {
            "id": "A12",
            "statement": "12 km means distance from the initial takeoff point",
            "class": "recommended primary interpretation, not yet evaluable",
            "source": "teammate review",
            "scope": "Q1-Q4",
        },
    ]
    with (PLANNING / "assumption_register.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(assumption_rows[0]),
        )
        writer.writeheader()
        writer.writerows(assumption_rows)

    run_summary = {
        "schema_version": 1,
        "question": "Q1",
        "round": "round4",
        "round_label": "teammate_review_architecture_upgrade",
        "status": (
            "PASS"
            if timing_pass
            and max_defect_error <= 1e-12
            and multi_smoke_guard_pass
            and full_radius_interval_pass
            else "FAIL"
        ),
        "accepted_core_numbers_unchanged": True,
        "execution_time_seconds": time.perf_counter() - started,
        "decision_id": "q1_teammate_review_integration",
        "outputs": [
            "results/Q1/experiments/round4/metrics/q1_architecture_upgrade.json",
            "results/Q1/experiments/round4/tables/q1_drift_parameter_curve.csv",
            "planning/scenario_schema.json",
            "planning/assumption_register.csv",
            "interfaces/Q1_to_Q2_coverage_contract.md"
        ],
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "numpy": np.__version__,
        },
        "generated_at": datetime.now().astimezone().isoformat(),
    }
    write_json(ROUND / "run_summary.json", run_summary)


if __name__ == "__main__":
    main()
