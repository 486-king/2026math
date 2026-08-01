"""Canonical two-bomb full-window plan and its independent validation chain."""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy.optimize import minimize_scalar

from q2_common import MODEL_SCOPE, PARAMS, SmokePlan
from q2_continuous_certificate import (
    canonical_two_bomb_intervals,
    certify_continuous_window,
    event_intervals,
)
from q2_geometry import high_precision_uncovered_area, union_margin_at_time
from q2_reachability import enumerate_relative_headings


def canonical_two_bomb_plan() -> list[SmokePlan]:
    return [
        SmokePlan(
            smoke_id="minimum_resource_smoke_1",
            center_m=33.73703319,
            t_cmd_s=-7.88582566,
        ),
        SmokePlan(
            smoke_id="minimum_resource_smoke_2",
            center_m=161.83285766,
            t_cmd_s=2.94018905,
        ),
    ]


def _exact_interval_minimum(
    plan: list[SmokePlan],
    start_s: float,
    end_s: float,
) -> dict[str, Any]:
    if end_s - start_s <= 1e-12:
        time = start_s
        result = union_margin_at_time(time, plan)
        return {"time_s": time, **result.as_dict()}
    result = minimize_scalar(
        lambda time: union_margin_at_time(time, plan).minimum_squared_section_margin_m2,
        bounds=(start_s, end_s),
        method="bounded",
        options={"xatol": 1e-13, "maxiter": 1000},
    )
    candidates = [
        (start_s, union_margin_at_time(start_s, plan)),
        (float(result.x), union_margin_at_time(float(result.x), plan)),
        (end_s, union_margin_at_time(end_s, plan)),
    ]
    time, section = min(
        candidates,
        key=lambda row: row[1].minimum_squared_section_margin_m2,
    )
    return {"time_s": float(time), **section.as_dict()}


def exact_cross_section_diagnostic(
    plan: list[SmokePlan],
    intervals: list[Any],
    structural_events: dict[str, float],
    *,
    dense_count: int = 20001,
) -> dict[str, Any]:
    extrema = [
        _exact_interval_minimum(plan, interval.start_s, interval.end_s)
        for interval in intervals
    ]
    event_rows = [
        {
            "event": name,
            "time_s": time,
            **union_margin_at_time(time, plan).as_dict(),
        }
        for name, time in sorted(structural_events.items(), key=lambda row: row[1])
    ]
    times = np.linspace(0.0, PARAMS.detect_worst_upper_s, dense_count)
    margins = np.array(
        [
            union_margin_at_time(float(time), plan).minimum_squared_section_margin_m2
            for time in times
        ]
    )
    index = int(np.argmin(margins))
    candidates = extrema + event_rows + [
        {
            "time_s": float(times[index]),
            **union_margin_at_time(float(times[index]), plan).as_dict(),
        }
    ]
    minimum = min(
        candidates,
        key=lambda row: row["minimum_squared_section_margin_m2"],
    )
    return {
        "method": "exact_xi_candidates_plus_deterministic_dense_time_diagnostic",
        "time_scan_role": "independent_bug_detection_not_continuous_proof",
        "dense_time_point_count": dense_count,
        "interval_extrema": extrema,
        "event_checks": event_rows,
        "minimum_cross_section_margin_m2": minimum[
            "minimum_squared_section_margin_m2"
        ],
        "minimum_time_s": minimum["time_s"],
        "reference_margin_m2": 1463.887280249688,
        "reference_absolute_error_m2": abs(
            minimum["minimum_squared_section_margin_m2"] - 1463.887280249688
        ),
        "verified": (
            minimum["minimum_squared_section_margin_m2"] >= 0.0
            and abs(
                minimum["minimum_squared_section_margin_m2"] - 1463.887280249688
            )
            <= 1e-3
        ),
    }

def validate_canonical_two_bomb_plan() -> dict[str, Any]:
    plan = canonical_two_bomb_plan()
    event_checks = []
    for smoke in plan:
        event_checks.append(
            {
                **smoke.as_event_record(),
                "release_relation_error_s": abs(
                    smoke.t_d_s - (smoke.t_cmd_s + PARAMS.command_to_release_delay_s)
                ),
                "burst_relation_error_s": abs(
                    smoke.t_b_s - (smoke.t_d_s + PARAMS.release_to_burst_delay_s)
                ),
            }
        )
    release_interval = plan[1].t_d_s - plan[0].t_d_s
    intervals, structural_events = canonical_two_bomb_intervals(
        plan,
        PARAMS.detect_worst_upper_s,
    )
    certificate = certify_continuous_window(
        plan,
        0.0,
        PARAMS.detect_worst_upper_s,
        canonical_intervals=intervals,
    )
    cross_section = exact_cross_section_diagnostic(
        plan,
        intervals,
        structural_events,
    )
    area_times = sorted(
        {
            0.0,
            PARAMS.detect_worst_upper_s,
            *structural_events.values(),
            cross_section["minimum_time_s"],
        }
    )
    area_rows = [
        high_precision_uncovered_area(time, plan)
        for time in area_times
        if 0.0 <= time <= PARAMS.detect_worst_upper_s
    ]
    maximum_area_upper = max(
        row["conservative_area_upper_bound_m2"] for row in area_rows
    )
    reachability = enumerate_relative_headings(plan)
    all_verified = (
        certificate["certificate_status"] == "verified"
        and certificate["canonical_box_count"] == 9
        and certificate["undecided_box_count"] == 0
        and certificate["failed_box_count"] == 0
        and certificate["gap_count"] == 0
        and cross_section["verified"]
        and all(row["verified_no_uncovered_area"] for row in area_rows)
        and release_interval >= PARAMS.minimum_release_interval_s
        and reachability["relative_transition_status"] == "feasible"
    )
    return {
        "scheme_id": "Q2_A_two_bomb_minimum_resource_full_worst_window",
        "formal_method_name_zh": MODEL_SCOPE["main_method_name_zh"],
        "model_scope": MODEL_SCOPE,
        "defence_window_s": [0.0, PARAMS.detect_worst_upper_s],
        "event_chain": event_checks,
        "release_interval_s": release_interval,
        "minimum_release_interval_verified": (
            release_interval >= PARAMS.minimum_release_interval_s
        ),
        "continuous_certificate": certificate,
        "structural_events": structural_events,
        "exact_cross_section_validation": cross_section,
        "high_precision_area_diagnostics": area_rows,
        "maximum_uncovered_area_upper_bound_m2": maximum_area_upper,
        "relative_reachability": reachability,
        "minimum_bomb_count": 2 if all_verified else None,
        "minimum_bomb_count_statement_zh": (
            "在允许锁定前预警部署的 G1/S1/O0/U0 共线相对模型中，"
            "完成 G1 最坏探测窗口全防御的最少弹药数为 2。"
            if all_verified
            else "not_established"
        ),
        "one_bomb_impossibility": {
            "single_smoke_upper_bound_s": PARAMS.single_smoke_max_duration_s,
            "worst_detection_window_s": PARAMS.detect_worst_upper_s,
            "strict_inequality_verified": (
                PARAMS.single_smoke_max_duration_s < PARAMS.detect_worst_upper_s
            ),
            "proof": "2(R_c-R_s)/V_s < (D_max-R_s)/(V_m-V_s)",
        },
        "execution_status": "completed" if all_verified else "failed",
        "input_status": "relative_model_complete_absolute_inputs_missing",
        "relative_feasibility_status": (
            "full_worst_window_feasible" if all_verified else "failed_validation"
        ),
        "absolute_execution_status": (
            "blocked_missing_uav_initial_state_and_base_reference"
        ),
        "certificate_status": "verified" if all_verified else "failed",
        "result_strength": "continuous_certificate_plus_independent_geometry",
        "pre_lock_dependency": "required",
        "global_optimality_status": (
            "minimum_bomb_count_proved_in_relative_collinear_model"
            if all_verified
            else "not_established"
        ),
    }


def broken_plan_gate() -> dict[str, Any]:
    original = canonical_two_bomb_plan()
    broken = [
        original[0],
        SmokePlan.from_burst(
            smoke_id="broken_delayed_smoke_2",
            center_m=original[1].center_m,
            t_b_s=original[1].t_b_s + 6.0,
        ),
    ]
    intervals = event_intervals(
        broken,
        0.0,
        PARAMS.detect_worst_upper_s,
        prefix="broken",
    )
    certificate = certify_continuous_window(
        broken,
        0.0,
        PARAMS.detect_worst_upper_s,
        canonical_intervals=intervals,
        maximum_depth=24,
    )
    times = np.linspace(0.0, PARAMS.detect_worst_upper_s, 20001)
    margins = np.array(
        [
            union_margin_at_time(float(time), broken).minimum_squared_section_margin_m2
            for time in times
        ]
    )
    index = int(np.argmin(margins))
    failure_time = float(times[index])
    area = high_precision_uncovered_area(failure_time, broken)
    failed = (
        certificate["certificate_status"] == "failed"
        and margins[index] < 0.0
        and area["conservative_area_upper_bound_m2"] > area["area_tolerance_m2"]
    )
    return {
        "counterexample": "second_burst_delayed_by_6_seconds",
        "first_failure_time_interval": certificate["first_failure_time_interval"],
        "minimum_margin_m2": float(margins[index]),
        "minimum_margin_time_s": failure_time,
        "uncovered_area_or_gap": area,
        "certificate_status": "failed" if failed else "false_positive_detected",
        "continuous_certificate": certificate,
        "exact_cross_section_failed": margins[index] < 0.0,
        "area_diagnostic_failed": (
            area["conservative_area_upper_bound_m2"] > area["area_tolerance_m2"]
        ),
        "false_positive_gate_passed": failed,
    }


def no_pre_lock_counterfactual() -> dict[str, Any]:
    return {
        "allow_pre_lock_mission": False,
        "constraint": "t_cmd,j >= 0",
        "derived_earliest_release_s": PARAMS.command_to_release_delay_s,
        "derived_earliest_burst_s": (
            PARAMS.command_to_release_delay_s + PARAMS.release_to_burst_delay_s
        ),
        "unavoidable_initial_naked_interval_s": [0.0, 5.5],
        "interval_right_open": True,
        "unavoidable_initial_naked_duration_s": 5.5,
        "full_window_feasible": False,
        "conclusion_zh": (
            "若所有任务只能在锁定时刻后下达，则事件延迟导致最初 5.5 s "
            "必然裸露，无法从 t=0 实现全窗口遮蔽。"
        ),
        "proof_type": "analytic_event_delay_certificate_independent_of_bomb_count",
    }
