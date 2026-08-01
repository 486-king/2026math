"""Physically coupled sensitivity thresholds for the three formal Q2 plans."""

from __future__ import annotations

from typing import Any, Callable, Sequence

import numpy as np
from scipy.optimize import brentq, minimize_scalar

from q2_common import PARAMS, SmokePlan
from q2_geometry import union_margin_at_time
from q2_reachability import enumerate_relative_headings


def plan_from_event_records(records: Sequence[dict[str, Any]]) -> list[SmokePlan]:
    return [
        SmokePlan(
            smoke_id=str(record["smoke_id"]),
            center_m=float(record["center_m"]),
            t_cmd_s=float(record["t_cmd_s"]),
        )
        for record in records
    ]


def minimum_margin_over_window(
    plan: Sequence[SmokePlan],
    start_s: float,
    end_s: float,
    *,
    ship_speed_mps: float = PARAMS.ship_speed_mps,
    max_radius_m: float = PARAMS.smoke_max_radius_m,
    longitudinal_drift_mps: float = 0.0,
    point_count: int = 1201,
) -> tuple[float, float]:
    events = {float(start_s), float(end_s)}
    for smoke in plan:
        for event in (
            smoke.t_b_s,
            smoke.t_b_s + PARAMS.smoke_hold_s,
            smoke.t_b_s + PARAMS.smoke_lifetime_s,
        ):
            if start_s < event < end_s:
                events.add(float(event))
    times = np.unique(
        np.concatenate(
            (
                np.linspace(start_s, end_s, point_count),
                np.array(sorted(events)),
            )
        )
    )

    def margin(time_value: float) -> float:
        return union_margin_at_time(
            time_value,
            plan,
            ship_speed_mps=ship_speed_mps,
            max_radius_m=max_radius_m,
            longitudinal_drift_mps=longitudinal_drift_mps,
        ).minimum_squared_section_margin_m2

    values = np.array([margin(float(time_value)) for time_value in times])
    candidates = [(float(times[int(np.argmin(values))]), float(np.min(values)))]
    local_indices = np.flatnonzero(
        (values[1:-1] <= values[:-2]) & (values[1:-1] <= values[2:])
    ) + 1
    for index in local_indices:
        result = minimize_scalar(
            margin,
            bounds=(float(times[index - 1]), float(times[index + 1])),
            method="bounded",
            options={"xatol": 1e-11, "maxiter": 300},
        )
        candidates.append((float(result.x), float(result.fun)))
    return min(candidates, key=lambda row: row[1])


def _allowed_interval(
    nominal: float,
    lower_bound: float,
    upper_bound: float,
    evaluator: Callable[[float], float],
    *,
    sample_count: int = 31,
) -> dict[str, Any]:
    nominal_margin = evaluator(nominal)
    feasibility_tolerance_m2 = 1e-7

    def find_side(bound: float) -> dict[str, Any]:
        values = np.linspace(nominal, bound, sample_count)
        previous_x = float(values[0])
        previous_y = nominal_margin
        for value in values[1:]:
            current_x = float(value)
            current_y = evaluator(current_x)
            if (
                previous_y >= 0.0
                and current_y < -feasibility_tolerance_m2
            ):
                root_value = brentq(
                    evaluator,
                    min(previous_x, current_x),
                    max(previous_x, current_x),
                    xtol=1e-10,
                )
                return {
                    "threshold": float(root_value),
                    "threshold_status": "failure_threshold_isolated",
                    "failure_found": True,
                    "scan_censored": False,
                    "tested_limit": float(bound),
                    "tested_limit_margin_m2": float(evaluator(bound)),
                }
            if (
                abs(previous_y) <= feasibility_tolerance_m2
                and current_y < -feasibility_tolerance_m2
            ):
                return {
                    "threshold": float(previous_x),
                    "threshold_status": "nominal_boundary_threshold",
                    "failure_found": True,
                    "scan_censored": False,
                    "tested_limit": float(bound),
                    "tested_limit_margin_m2": float(evaluator(bound)),
                }
            previous_x, previous_y = current_x, current_y
        tested_margin = float(evaluator(bound))
        return {
            "threshold": None,
            "threshold_status": "no_failure_observed_within_scan",
            "failure_found": False,
            "scan_censored": tested_margin >= -feasibility_tolerance_m2,
            "tested_limit": float(bound),
            "tested_limit_margin_m2": tested_margin,
        }

    lower = find_side(lower_bound)
    upper = find_side(upper_bound)
    return {
        "nominal_value": nominal,
        "nominal_minimum_margin_m2": nominal_margin,
        "exploratory": True,
        "search_lower_bound": lower_bound,
        "search_upper_bound": upper_bound,
        "failure_found_lower_direction": lower["failure_found"],
        "failure_found_upper_direction": upper["failure_found"],
        "threshold_lower": lower["threshold"],
        "threshold_upper": upper["threshold"],
        "threshold_status_lower": lower["threshold_status"],
        "threshold_status_upper": upper["threshold_status"],
        "scan_censored_lower": lower["scan_censored"],
        "scan_censored_upper": upper["scan_censored"],
        "tested_lower_limit": lower["tested_limit"],
        "tested_upper_limit": upper["tested_limit"],
        "tested_lower_limit_margin_m2": lower["tested_limit_margin_m2"],
        "tested_upper_limit_margin_m2": upper["tested_limit_margin_m2"],
        "feasibility_tolerance_m2": feasibility_tolerance_m2,
        "verified_feasible_region": {
            "lower": {
                "value": (
                    lower["threshold"]
                    if lower["threshold"] is not None
                    else lower_bound
                ),
                "meaning": (
                    "isolated_failure_threshold"
                    if lower["threshold"] is not None
                    else "tested_feasible_limit_not_true_threshold"
                ),
            },
            "upper": {
                "value": (
                    upper["threshold"]
                    if upper["threshold"] is not None
                    else upper_bound
                ),
                "meaning": (
                    "isolated_failure_threshold"
                    if upper["threshold"] is not None
                    else "tested_feasible_limit_not_true_threshold"
                ),
            },
        },
        "scan_range_source": "exploratory_programmer_range_not_problem_condition",
    }


def _physically_coupled_delay_plan(
    plan: Sequence[SmokePlan],
    heading_signs: Sequence[int],
    new_delay_s: float,
) -> tuple[list[SmokePlan], list[dict[str, float]]]:
    perturbed: list[SmokePlan] = []
    couplings = []
    for smoke, sign in zip(plan, heading_signs):
        fixed_release_time = smoke.t_d_s
        fixed_release_position = (
            smoke.center_m
            - PARAMS.uav_speed_mps
            * PARAMS.release_to_burst_delay_s
            * sign
        )
        new_burst = fixed_release_time + float(new_delay_s)
        new_center = (
            fixed_release_position
            + PARAMS.uav_speed_mps * float(new_delay_s) * sign
        )
        perturbed.append(
            SmokePlan.from_burst(
                smoke_id=smoke.smoke_id,
                center_m=new_center,
                t_b_s=new_burst,
            )
        )
        couplings.append(
            {
                "fixed_release_time_s": fixed_release_time,
                "fixed_release_position_m": fixed_release_position,
                "release_heading_sign": int(sign),
                "new_burst_time_s": new_burst,
                "new_center_m": new_center,
            }
        )
    return perturbed, couplings


def analyse_plan_robustness(
    scheme_id: str,
    plan: Sequence[SmokePlan],
    horizon_s: float,
    *,
    change_window_with_ship_speed: bool,
) -> dict[str, Any]:
    reachability = enumerate_relative_headings(plan)
    signs = reachability["selected_heading_combination"]["release_heading_signs"]

    def ship_speed_metric(speed: float) -> float:
        end = (
            (PARAMS.detection_distance_m - PARAMS.ship_radius_m)
            / (PARAMS.missile_speed_mps - speed)
            if change_window_with_ship_speed
            else horizon_s
        )
        return minimum_margin_over_window(
            plan,
            0.0,
            end,
            ship_speed_mps=speed,
        )[1]

    def radius_metric(radius: float) -> float:
        return minimum_margin_over_window(
            plan,
            0.0,
            horizon_s,
            max_radius_m=radius,
        )[1]

    def delay_metric(delay: float) -> float:
        coupled_plan, _ = _physically_coupled_delay_plan(plan, signs, delay)
        return minimum_margin_over_window(
            coupled_plan,
            0.0,
            horizon_s,
        )[1]

    def drift_metric(drift: float) -> float:
        return minimum_margin_over_window(
            plan,
            0.0,
            horizon_s,
            longitudinal_drift_mps=drift,
        )[1]

    delay_example, coupling = _physically_coupled_delay_plan(
        plan,
        signs,
        PARAMS.release_to_burst_delay_s,
    )
    del delay_example
    return {
        "scheme_id": scheme_id,
        "horizon_s": horizon_s,
        "ship_speed": {
            **_allowed_interval(
                PARAMS.ship_speed_mps,
                6.0,
                9.0,
                ship_speed_metric,
            ),
            "physical_coupling": (
                "ship trajectory and G1 worst window both change"
                if change_window_with_ship_speed
                else "ship trajectory changes on the fixed capacity horizon"
            ),
        },
        "smoke_max_radius": _allowed_interval(
            PARAMS.smoke_max_radius_m,
            100.0,
            140.0,
            radius_metric,
        ),
        "burst_delay": {
            **_allowed_interval(
                PARAMS.release_to_burst_delay_s,
                2.5,
                4.5,
                delay_metric,
            ),
            "physical_coupling": (
                "t_d, p_d, and release heading fixed; t_b=t_d+tau and "
                "c=p_d+28*tau*heading_sign"
            ),
            "nominal_coupling_records": coupling,
            "timing_only_diagnostic_used_as_main_result": False,
        },
        "longitudinal_drift": {
            **_allowed_interval(
                0.0,
                -2.0,
                2.0,
                drift_metric,
            ),
            "scope": "collinear_longitudinal_extension",
        },
        "lateral_drift": {
            "status": "not_evaluated_outside_collinear_scope",
            "collinear_certificate_used": False,
        },
    }


def robustness_summary(
    minimum_resource_plan: Sequence[SmokePlan],
    two_frontier_plan: Sequence[SmokePlan],
    two_frontier_horizon_s: float,
    three_frontier_plan: Sequence[SmokePlan],
    three_frontier_horizon_s: float,
) -> dict[str, Any]:
    return {
        "nominal_drift_model": "U0_no_wind_drift",
        "uncertainty_distribution": "not_provided",
        "result_type": (
            "one_sided_failure_thresholds_and_two_sided_allowed_intervals"
        ),
        "plans": [
            analyse_plan_robustness(
                "Q2_A_two_bomb_minimum_resource_full_worst_window",
                minimum_resource_plan,
                PARAMS.detect_worst_upper_s,
                change_window_with_ship_speed=True,
            ),
            analyse_plan_robustness(
                "Q2_A_two_bomb_best_verified_collinear_solution",
                two_frontier_plan,
                two_frontier_horizon_s,
                change_window_with_ship_speed=False,
            ),
            analyse_plan_robustness(
                "Q2_A_three_bomb_best_verified_collinear_reference",
                three_frontier_plan,
                three_frontier_horizon_s,
                change_window_with_ship_speed=False,
            ),
        ],
        "physical_consistency_checks": {
            "ship_speed_updates_window_for_minimum_resource_plan": True,
            "radius_updates_geometry_and_bridge_capacity": True,
            "burst_delay_updates_time_and_center": True,
            "lateral_drift_does_not_reuse_collinear_certificate": True,
        },
    }
