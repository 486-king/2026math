"""Continuous Q3 coverage, strict double coverage, area, and N-1 checks."""

from __future__ import annotations

import math
from itertools import combinations
from typing import Any, Callable, Sequence

import numpy as np
from scipy.optimize import brentq

from q3_q2_adapter import (
    PARAMS,
    T_WORST_S,
    SmokePlan,
    certify_continuous_window,
    high_precision_uncovered_area,
    smoke_plans,
    smoke_radius,
    union_margin_at_time,
)


NEGATIVE_SENTINEL = -1e12


def plan_from_records(records: Sequence[dict[str, Any]]) -> list[SmokePlan]:
    return smoke_plans(records)


def margin_at(t_s: float, plan: Sequence[SmokePlan]) -> float:
    value = union_margin_at_time(float(t_s), plan).minimum_squared_section_margin_m2
    return NEGATIVE_SENTINEL if value < -1e250 else float(value)


def structural_event_times(
    plan: Sequence[SmokePlan], start_s: float = 0.0, end_s: float = T_WORST_S
) -> list[float]:
    events = {float(start_s), float(end_s)}
    for smoke in plan:
        for value in (
            smoke.t_b_s,
            smoke.t_b_s + PARAMS.smoke_hold_s,
            smoke.t_b_s + PARAMS.smoke_lifetime_s,
        ):
            if start_s < value < end_s:
                events.add(float(value))
    return sorted(events)


def _root_isolated_nonnegative_intervals(
    function: Callable[[float], float],
    event_times: Sequence[float],
    *,
    probes_per_event_interval: int = 192,
    root_tolerance_s: float = 1e-11,
) -> dict[str, Any]:
    roots: list[float] = []
    unresolved = 0
    intervals: list[list[float]] = []
    for event_left, event_right in zip(event_times[:-1], event_times[1:]):
        width = event_right - event_left
        epsilon = min(1e-9, max(1e-13, width * 1e-10))
        left = event_left + (epsilon if event_left != event_times[0] else 0.0)
        right = event_right - (epsilon if event_right != event_times[-1] else 0.0)
        if right <= left:
            continue
        probes = np.linspace(left, right, probes_per_event_interval + 1)
        values = [float(function(float(value))) for value in probes]
        local_roots: list[float] = []
        for index in range(len(probes) - 1):
            x0, x1 = float(probes[index]), float(probes[index + 1])
            y0, y1 = values[index], values[index + 1]
            if not math.isfinite(y0) or not math.isfinite(y1):
                unresolved += 1
                continue
            if abs(y0) <= 1e-9:
                local_roots.append(x0)
            if y0 * y1 < 0.0:
                local_roots.append(
                    float(
                        brentq(
                            function,
                            x0,
                            x1,
                            xtol=root_tolerance_s,
                            rtol=1e-14,
                        )
                    )
                )
        if abs(values[-1]) <= 1e-9:
            local_roots.append(right)
        unique_roots: list[float] = []
        for root in sorted(local_roots):
            if not unique_roots or abs(root - unique_roots[-1]) > 1e-8:
                unique_roots.append(root)
        roots.extend(unique_roots)
        boundaries = [event_left, *unique_roots, event_right]
        for left_boundary, right_boundary in zip(boundaries[:-1], boundaries[1:]):
            if right_boundary - left_boundary <= 1e-12:
                continue
            midpoint = 0.5 * (left_boundary + right_boundary)
            if function(midpoint) >= 0.0:
                intervals.append([float(left_boundary), float(right_boundary)])
    merged: list[list[float]] = []
    for interval in sorted(intervals):
        if merged and interval[0] <= merged[-1][1] + 1e-8:
            merged[-1][1] = max(merged[-1][1], interval[1])
        else:
            merged.append(interval)
    return {
        "intervals": merged,
        "roots_s": sorted(
            {
                round(float(root), 12)
                for root in roots
                if event_times[0] < root < event_times[-1]
            }
        ),
        "root_count": len(
            {
                round(float(root), 12)
                for root in roots
                if event_times[0] < root < event_times[-1]
            }
        ),
        "unresolved_interval_count": unresolved,
        "event_times_s": [float(value) for value in event_times],
        "sampling_used_as_measure": False,
        "method": "physical_event_partition_and_brent_root_isolation",
    }


def coverage_intervals(
    plan: Sequence[SmokePlan],
    start_s: float = 0.0,
    end_s: float = T_WORST_S,
) -> dict[str, Any]:
    result = _root_isolated_nonnegative_intervals(
        lambda value: margin_at(value, plan),
        structural_event_times(plan, start_s, end_s),
    )
    durations = [right - left for left, right in result["intervals"]]
    result.update(
        {
            "total_full_coverage_duration_s": sum(durations),
            "longest_continuous_full_coverage_s": max(durations, default=0.0),
            "full_window_coverage": (
                len(result["intervals"]) == 1
                and result["intervals"][0][0] <= start_s + 1e-8
                and result["intervals"][0][1] >= end_s - 1e-8
            ),
        }
    )
    return result


def certify_normal_coverage(
    records: Sequence[dict[str, Any]],
    *,
    analytic_start_zero: bool = False,
    analytic_internal_terminal_times: Sequence[float] = (),
) -> dict[str, Any]:
    plan = plan_from_records(records)
    certificate = certify_continuous_window(
        plan,
        0.0,
        T_WORST_S,
        analytic_start_zero=analytic_start_zero,
        analytic_internal_terminal_times=analytic_internal_terminal_times,
    )
    interval_result = coverage_intervals(plan)
    certificate["interval_cross_check"] = interval_result
    certificate["independent_interval_method_agreement"] = (
        certificate["certificate_status"] == "verified"
        and interval_result["full_window_coverage"]
        and interval_result["unresolved_interval_count"] == 0
    )
    if not certificate["independent_interval_method_agreement"]:
        certificate["certificate_status"] = "failed"
    return certificate


def area_diagnostic(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    plan = plan_from_records(records)
    events = structural_event_times(plan)
    times = {0.0, T_WORST_S}
    for left, right in zip(events[:-1], events[1:]):
        times.add(0.5 * (left + right))
    margin_candidates = [
        (margin_at(value, plan), value) for value in sorted(times)
    ]
    worst_time = min(margin_candidates)[1]
    times.add(worst_time)
    interval_result = coverage_intervals(plan)
    cursor = 0.0
    for left, right in interval_result["intervals"]:
        if left > cursor + 1e-8:
            times.add(0.5 * (cursor + left))
        cursor = max(cursor, right)
    if cursor < T_WORST_S - 1e-8:
        times.add(0.5 * (cursor + T_WORST_S))
    diagnostics = [
        high_precision_uncovered_area(
            value,
            plan,
            precision_digits=60,
            repeat_precision_digits=120,
            area_tolerance_m2=1e-30,
        )
        for value in sorted(times)
    ]
    return {
        "method": "independent_decimal_vertical_cross_section_diagnostic",
        "continuous_certificate_is_primary_proof": True,
        "diagnostic_times_s": sorted(times),
        "continuous_root_isolation_intervals": interval_result["intervals"],
        "diagnostics": diagnostics,
        "maximum_raw_uncovered_area_m2": max(
            item["raw_uncovered_area_m2"] for item in diagnostics
        ),
        "maximum_conservative_area_upper_bound_m2": max(
            item["conservative_area_upper_bound_m2"] for item in diagnostics
        ),
        "maximum_precision_doubling_difference_m2": max(
            item["precision_doubling_difference_m2"] for item in diagnostics
        ),
        "area_tolerance_m2": 1e-30,
        "integration_precision_digits": 60,
        "repeated_precision_digits": 120,
        "clipping_applied": False,
        "negative_value_clamped": False,
        "diagnostic_status": (
            "no_uncovered_area_detected_above_tolerance"
            if all(item["verified_no_uncovered_area"] for item in diagnostics)
            else "positive_uncovered_area_detected"
        ),
    }


def _second_envelope_margin(t_s: float, plan: Sequence[SmokePlan]) -> float:
    ship = PARAMS.ship_speed_mps * float(t_s)
    lines: list[tuple[float, float]] = []
    for smoke in plan:
        radius = smoke_radius(t_s, smoke.t_b_s)
        if radius <= 0.0:
            continue
        distance = ship - smoke.center_m
        intercept = radius * radius - PARAMS.ship_radius_m**2 - distance**2
        slope = -2.0 * distance
        lines.append((intercept, slope))
    if len(lines) < 2:
        return NEGATIVE_SENTINEL
    candidates = [-PARAMS.ship_radius_m, PARAMS.ship_radius_m]
    for first, second in combinations(lines, 2):
        denominator = first[1] - second[1]
        if abs(denominator) > 1e-12:
            xi = (second[0] - first[0]) / denominator
            if -PARAMS.ship_radius_m <= xi <= PARAMS.ship_radius_m:
                candidates.append(float(xi))
    values: list[float] = []
    for xi in candidates:
        ordered = sorted(
            (intercept + slope * xi for intercept, slope in lines),
            reverse=True,
        )
        values.append(float(ordered[1]))
    return min(values)


def strict_double_coverage(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    plan = plan_from_records(records)
    if len(plan) != 3:
        raise ValueError("Strict Q3 double coverage requires three smokes.")
    pair_plans = [
        [smoke for index, smoke in enumerate(plan) if index != removed]
        for removed in range(3)
    ]

    def leave_one_margin(t_s: float) -> float:
        return min(margin_at(t_s, pair) for pair in pair_plans)

    events = structural_event_times(plan)
    isolated = _root_isolated_nonnegative_intervals(leave_one_margin, events)
    duration = sum(right - left for left, right in isolated["intervals"])
    check_times = {0.0, T_WORST_S, *isolated["roots_s"]}
    for left, right in zip(events[:-1], events[1:]):
        check_times.add(0.5 * (left + right))
    method_differences = [
        abs(leave_one_margin(value) - _second_envelope_margin(value, plan))
        for value in sorted(check_times)
        if abs(leave_one_margin(value)) < 1e11
    ]
    agreement = max(method_differences, default=0.0) <= 1e-6
    double_fraction = duration / T_WORST_S
    return {
        "definition": (
            "every point of the ship disk is covered by at least two smoke disks; "
            "equivalently every leave-one-smoke union covers the full ship disk"
        ),
        "double_coverage_intervals": isolated["intervals"],
        "double_coverage_duration_s": duration,
        "double_coverage_fraction": double_fraction,
        "double_coverage_percent": 100.0 * double_fraction,
        "root_count": isolated["root_count"],
        "unresolved_interval_count": isolated["unresolved_interval_count"],
        "method_agreement": agreement,
        "independent_method": "second_largest_L_j_envelope",
        "maximum_method_margin_difference_m2": max(method_differences, default=0.0),
        "sampling_used_as_time_measure": False,
        "result_status": "verified" if agreement and not isolated["unresolved_interval_count"] else "failed",
    }


def n_minus_one(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    full_plan = plan_from_records(records)
    cases: list[dict[str, Any]] = []
    for removed in range(3):
        remaining = [
            smoke for index, smoke in enumerate(full_plan) if index != removed
        ]
        intervals = coverage_intervals(remaining)
        failure_intervals: list[list[float]] = []
        cursor = 0.0
        for left, right in intervals["intervals"]:
            if left > cursor + 1e-8:
                failure_intervals.append([cursor, left])
            cursor = max(cursor, right)
        if cursor < T_WORST_S - 1e-8:
            failure_intervals.append([cursor, T_WORST_S])
        critical_times = {
            0.0,
            T_WORST_S,
            *(0.5 * (left + right) for left, right in failure_intervals),
        }
        margins = [(margin_at(value, remaining), value) for value in critical_times]
        minimum_margin, worst_time = min(margins)
        remaining_double = _root_isolated_nonnegative_intervals(
            lambda value: _second_envelope_margin(value, remaining),
            structural_event_times(remaining),
        )
        double_duration = sum(
            right - left for left, right in remaining_double["intervals"]
        )
        remaining_double_fraction = double_duration / T_WORST_S
        cases.append(
            {
                "failed_uav_id": removed + 1,
                "full_window_coverage": intervals["full_window_coverage"],
                "certificate_status": (
                    "verified"
                    if intervals["unresolved_interval_count"] == 0
                    else "failed"
                ),
                "first_failure_time_s": (
                    failure_intervals[0][0] if failure_intervals else None
                ),
                "failure_intervals": failure_intervals,
                "longest_continuous_full_coverage_s": intervals[
                    "longest_continuous_full_coverage_s"
                ],
                "total_full_coverage_duration_s": intervals[
                    "total_full_coverage_duration_s"
                ],
                "minimum_coverage_margin_m2": minimum_margin,
                "remaining_double_coverage_fraction": (
                    remaining_double_fraction
                ),
                "remaining_double_coverage_percent": 100.0
                * remaining_double_fraction,
                "worst_time_s": worst_time,
                "remaining_smoke_ids": [smoke.smoke_id for smoke in remaining],
            }
        )
    successes = [case for case in cases if case["full_window_coverage"]]
    success_fraction = len(successes) / 3.0
    return {
        "failure_cases": cases,
        "full_window_success_count": len(successes),
        "full_window_success_fraction": success_fraction,
        "full_window_success_percent": 100.0 * success_fraction,
        "successful_failed_uav_ids": [case["failed_uav_id"] for case in successes],
        "failed_failed_uav_ids": [
            case["failed_uav_id"]
            for case in cases
            if not case["full_window_coverage"]
        ],
        "worst_failure_continuous_coverage_s": min(
            case["longest_continuous_full_coverage_s"] for case in cases
        ),
        "fixed_plan_no_reoptimization": True,
        "N_minus_1_is_hard_constraint": False,
        "structural_feasibility_claimed": False,
    }
