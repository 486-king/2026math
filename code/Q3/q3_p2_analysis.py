from __future__ import annotations

import itertools
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from q3_common import CONSTANTS, ROOT, load_scenario
from q3_pretask_optimizer import (
    TOL,
    WINDOW_END,
    WINDOW_START,
    candidate_from,
    continuous_and_independent_validation,
    make_route,
    route_state,
)

from q2_union_optimizer import Schedule, fixed_time_union_slack_sq


ROUND2_MAIN = (
    ROOT
    / "results"
    / "Q3"
    / "experiments"
    / "round2"
    / "metrics"
    / "q3_main_pareto.json"
)
ROUND2_BASELINE = (
    ROOT
    / "results"
    / "Q3"
    / "experiments"
    / "round2"
    / "metrics"
    / "q3_baseline.json"
)


def load_selected() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    main = json.loads(ROUND2_MAIN.read_text(encoding="utf-8"))
    baseline = json.loads(ROUND2_BASELINE.read_text(encoding="utf-8"))["candidate"]
    selected = main["representative_candidates"]["A-00217"]
    alternatives = {
        "P1_A-00017": main["representative_candidates"]["A-00017"],
        "P2_A-00217": selected,
        "P4_A-00033": main["minimum_lead_candidate"],
        "Q3-B_B-3": baseline,
    }
    return selected, alternatives


def detailed_minimum_pair_distance(
    routes: list[dict[str, Any]], end_time: float
) -> dict[str, Any]:
    best = {
        "distance_m": math.inf,
        "time_s": None,
        "uav_pair": None,
        "positions_m": None,
    }
    route_objects = [
        make_route(
            uav=int(row["uav"]),
            bomb=int(row["bomb"]),
            start=tuple(row["start"]),
            initial_heading=float(row["initial_heading"]),
            center_x=float(row["center"][0]),
            burst_time=float(row["burst_time"]),
        )
        for row in routes
    ]
    for r1, r2 in itertools.combinations(route_objects, 2):
        left = max(r1.latest_available_time, r2.latest_available_time)
        cuts = sorted(
            {
                left,
                end_time,
                *(
                    value
                    for value in (r1.release_time, r2.release_time)
                    if left <= value <= end_time
                ),
            }
        )
        for a, b in zip(cuts[:-1], cuts[1:]):
            p1, v1 = route_state(r1, a)
            p2, v2 = route_state(r2, a)
            rel = p1 - p2
            vel = v1 - v2
            candidates = [0.0, b - a]
            denom = float(np.dot(vel, vel))
            if denom > 1e-14:
                candidates.append(
                    min(max(-float(np.dot(rel, vel)) / denom, 0.0), b - a)
                )
            for dt in candidates:
                distance = float(np.linalg.norm(rel + vel * dt))
                if distance < best["distance_m"]:
                    t = a + dt
                    q1, _ = route_state(r1, t)
                    q2, _ = route_state(r2, t)
                    best = {
                        "distance_m": distance,
                        "time_s": float(t),
                        "uav_pair": [r1.uav + 1, r2.uav + 1],
                        "positions_m": [q1.tolist(), q2.tolist()],
                    }
    return best


def trajectory_rows(candidate: dict[str, Any], step_s: float = 0.25) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for route_row in candidate["routes"]:
        route = make_route(
            uav=int(route_row["uav"]),
            bomb=int(route_row["bomb"]),
            start=tuple(route_row["start"]),
            initial_heading=float(route_row["initial_heading"]),
            center_x=float(route_row["center"][0]),
            burst_time=float(route_row["burst_time"]),
        )
        times = set(
            np.arange(route.latest_available_time, WINDOW_END + step_s, step_s).tolist()
        )
        times.update(
            {
                route.latest_available_time,
                route.command_time,
                route.release_time,
                route.burst_time,
                0.0,
                WINDOW_END,
            }
        )
        for t in sorted(v for v in times if route.latest_available_time <= v <= WINDOW_END):
            position, velocity = route_state(route, float(t))
            if t < route.release_time - 1e-9:
                phase = "predeployment_to_release"
            elif abs(t - route.release_time) <= 1e-9:
                phase = "release"
            else:
                phase = "post_release_straight_flight"
            rows.append(
                {
                    "scenario_label": "SYNTHETIC_SCENARIO_ONLY",
                    "uav": route.uav + 1,
                    "time_s": float(t),
                    "x_m": float(position[0]),
                    "y_m": float(position[1]),
                    "vx_mps": float(velocity[0]),
                    "vy_mps": float(velocity[1]),
                    "phase": phase,
                }
            )
    return rows


def bisection_root(schedule: Schedule, left: float, right: float) -> float:
    fl = fixed_time_union_slack_sq(left, schedule)[0]
    fr = fixed_time_union_slack_sq(right, schedule)[0]
    for _ in range(70):
        mid = 0.5 * (left + right)
        fm = fixed_time_union_slack_sq(mid, schedule)[0]
        if abs(fm) <= 1e-11 or right - left <= 1e-10:
            return float(mid)
        if (fl >= 0) == (fm >= 0):
            left, fl = mid, fm
        else:
            right, fr = mid, fm
    return float(0.5 * (left + right))


def coverage_intervals(schedule: Schedule) -> list[list[float]]:
    events = {WINDOW_START, WINDOW_END}
    for burst in schedule.burst_times_s:
        for value in (burst, burst + 18.0, burst + 23.0):
            if WINDOW_START <= value <= WINDOW_END:
                events.add(float(value))
    dense = np.linspace(WINDOW_START, WINDOW_END, 30001)
    points = sorted(events.union(dense.tolist()))
    flags = [fixed_time_union_slack_sq(t, schedule)[0] >= -TOL for t in points]
    roots: list[float] = []
    for i in range(len(points) - 1):
        if flags[i] != flags[i + 1]:
            roots.append(bisection_root(schedule, points[i], points[i + 1]))
    cuts = sorted({WINDOW_START, WINDOW_END, *events, *roots})
    intervals: list[list[float]] = []
    for left, right in zip(cuts[:-1], cuts[1:]):
        mid = 0.5 * (left + right)
        if fixed_time_union_slack_sq(mid, schedule)[0] >= -TOL:
            if intervals and abs(intervals[-1][1] - left) <= 1e-7:
                intervals[-1][1] = float(right)
            else:
                intervals.append([float(left), float(right)])
    return intervals


def failure_details(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    centers = candidate["centers_m"]
    bursts = candidate["burst_times_s"]
    assignment = candidate["assignment"]
    for failed_uav in range(3):
        failed_bomb = assignment[failed_uav]
        keep = [j for j in range(3) if j != failed_bomb]
        schedule = Schedule(
            tuple(centers[j] for j in keep),
            tuple(bursts[j] for j in keep),
            f"P2_failure_UAV{failed_uav + 1}",
        )
        intervals = coverage_intervals(schedule)
        durations = [right - left for left, right in intervals]
        covered = sum(durations)
        rows.append(
            {
                "scenario_label": "SYNTHETIC_SCENARIO_ONLY",
                "failed_uav": failed_uav + 1,
                "failed_smoke_index": failed_bomb + 1,
                "remaining_smoke_indices": [j + 1 for j in keep],
                "coverage_intervals_s": intervals,
                "full_window_success": bool(
                    len(intervals) == 1
                    and intervals[0][0] <= WINDOW_START + 1e-7
                    and intervals[0][1] >= WINDOW_END - 1e-7
                ),
                "longest_continuous_cover_s": max(durations, default=0.0),
                "total_covered_time_s": covered,
                "covered_time_ratio": covered / (WINDOW_END - WINDOW_START),
            }
        )
    return rows


def interval_intersection_measure(
    interval_groups: list[list[list[float]]],
) -> float:
    current = [[WINDOW_START, WINDOW_END]]
    for group in interval_groups:
        updated: list[list[float]] = []
        for left_a, right_a in current:
            for left_b, right_b in group:
                left = max(left_a, left_b)
                right = min(right_a, right_b)
                if right > left:
                    updated.append([left, right])
        current = updated
    return float(sum(right - left for left, right in current))


def exact_failure_metrics(candidate: dict[str, Any]) -> dict[str, Any]:
    details = failure_details(candidate)
    return {
        "details": details,
        "n_minus_one_success_rate": float(
            np.mean([row["full_window_success"] for row in details])
        ),
        "worst_failure_continuous_cover_s": float(
            min(row["longest_continuous_cover_s"] for row in details)
        ),
        "double_cover_time_ratio": interval_intersection_measure(
            [row["coverage_intervals_s"] for row in details]
        )
        / (WINDOW_END - WINDOW_START),
    }


def pure_pursuit_window(beta: float, dt: float = 0.002) -> float:
    missile_speed = CONSTANTS.missile_speed_mps
    ship_speed = CONSTANTS.ship_speed_mps
    target = CONSTANTS.ship_radius_m
    r = CONSTANTS.lock_distance_m * np.array([math.cos(beta), math.sin(beta)])
    t = 0.0

    def derivative(value: np.ndarray) -> np.ndarray:
        return -missile_speed * value / np.linalg.norm(value) - np.array(
            [ship_speed, 0.0]
        )

    while np.linalg.norm(r) > target and t < 40.0:
        prior = r.copy()
        prior_norm = float(np.linalg.norm(prior))
        k1 = derivative(r)
        k2 = derivative(r + 0.5 * dt * k1)
        k3 = derivative(r + 0.5 * dt * k2)
        k4 = derivative(r + dt * k3)
        r = r + dt * (k1 + 2 * k2 + 2 * k3 + k4) / 6.0
        new_norm = float(np.linalg.norm(r))
        if new_norm <= target:
            fraction = (prior_norm - target) / max(prior_norm - new_norm, 1e-15)
            return float(t + dt * fraction)
        t += dt
    raise RuntimeError("pure-pursuit integration failed to reach the ship disk")


def bearing_sensitivity(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for beta in np.linspace(0.0, math.pi, 37):
        duration = pure_pursuit_window(float(beta))
        rows.append(
            {
                "scenario_label": "SYNTHETIC_SCENARIO_ONLY",
                "beta_rad": float(beta),
                "beta_deg": float(math.degrees(beta)),
                "g1_detection_window_s": duration,
                "p2_validated_window_s": WINDOW_END,
                "complete_defense": bool(duration <= WINDOW_END + 2e-4),
            }
        )
    return rows


def rebuild_candidate(
    template: dict[str, Any],
    starts: list[tuple[float, float]],
    headings: list[float],
) -> dict[str, Any] | None:
    geometry = {
        key: template[key]
        for key in (
            "normal_full_defense",
            "normal_min_slack_sq_m2",
            "n_minus_one_success_rate",
            "worst_failure_continuous_cover_s",
            "double_cover_time_ratio",
            "failure_rows",
        )
    }
    try:
        return candidate_from(
            template["candidate_id"],
            tuple(template["centers_m"]),
            tuple(template["burst_times_s"]),
            tuple(template["assignment"]),
            starts,
            headings,
            geometry,
        )
    except ValueError:
        return None


def compact_sensitivity(
    row_id: str,
    candidate: dict[str, Any] | None,
    perturbation: dict[str, Any],
) -> dict[str, Any]:
    return {
        "scenario_label": "SYNTHETIC_SCENARIO_ONLY",
        "case_id": row_id,
        **perturbation,
        "route_constructible": candidate is not None,
        "lead_within_60s": bool(
            candidate is not None and candidate["lead_required_s"] <= 60.0 + 1e-9
        ),
        "common_warning_lead_s": None
        if candidate is None
        else candidate["lead_required_s"],
        "minimum_pair_distance_m": None
        if candidate is None
        else candidate["d_safe_max_m"],
        "total_path_length_m": None
        if candidate is None
        else candidate["total_path_length_m"],
        "total_turn_angle_rad": None
        if candidate is None
        else candidate["total_turn_angle_rad"],
    }


def position_and_heading_sensitivity(
    template: dict[str, Any], scenario: dict[str, Any]
) -> dict[str, Any]:
    starts0 = [tuple(map(float, p)) for p in scenario["uav_initial_positions_m"]]
    headings0 = [float(x) for x in scenario["uav_initial_headings_rad"]]
    position_rows = []
    offsets = np.linspace(-200.0, 200.0, 9)
    for uav in range(3):
        for axis in range(2):
            for offset in offsets:
                starts = [tuple(p) for p in starts0]
                point = list(starts[uav])
                point[axis] += float(offset)
                starts[uav] = tuple(point)
                rebuilt = rebuild_candidate(template, starts, headings0)
                position_rows.append(
                    compact_sensitivity(
                        f"POS_U{uav + 1}_{'XY'[axis]}_{offset:+.0f}",
                        rebuilt,
                        {
                            "uav": uav + 1,
                            "axis": "xy"[axis],
                            "offset_m": float(offset),
                        },
                    )
                )

    heading_rows = []
    for uav in range(3):
        for offset_deg in np.linspace(-45.0, 45.0, 7):
            headings = list(headings0)
            headings[uav] += math.radians(float(offset_deg))
            rebuilt = rebuild_candidate(template, starts0, headings)
            heading_rows.append(
                compact_sensitivity(
                    f"HDG_U{uav + 1}_{offset_deg:+.0f}",
                    rebuilt,
                    {"uav": uav + 1, "heading_offset_deg": float(offset_deg)},
                )
            )

    rng = np.random.default_rng(2026)
    combined_rows = []
    for index in range(2000):
        position_offsets = rng.uniform(-200.0, 200.0, size=(3, 2))
        heading_offsets_deg = rng.uniform(-45.0, 45.0, size=3)
        starts = [
            (
                starts0[i][0] + float(position_offsets[i, 0]),
                starts0[i][1] + float(position_offsets[i, 1]),
            )
            for i in range(3)
        ]
        headings = [
            headings0[i] + math.radians(float(heading_offsets_deg[i]))
            for i in range(3)
        ]
        rebuilt = rebuild_candidate(template, starts, headings)
        combined_rows.append(
            compact_sensitivity(
                f"MC_{index + 1:04d}",
                rebuilt,
                {
                    "position_offsets_m": position_offsets.tolist(),
                    "heading_offsets_deg": heading_offsets_deg.tolist(),
                },
            )
        )
    return {
        "position_one_at_a_time": position_rows,
        "heading_one_at_a_time": heading_rows,
        "combined": combined_rows,
    }


def sensitivity_summary(
    selected: dict[str, Any],
    bearing_rows: list[dict[str, Any]],
    sensitivity: dict[str, Any],
) -> dict[str, Any]:
    combined = sensitivity["combined"]
    nominal_clearance = float(selected["d_safe_max_m"])
    executable = [
        row
        for row in combined
        if row["route_constructible"] and row["lead_within_60s"]
    ]
    clearance_values = np.array(
        [row["minimum_pair_distance_m"] for row in executable], dtype=float
    )
    execution_rate = len(executable) / len(combined)
    half_margin_rate = float(np.mean(clearance_values >= 0.5 * nominal_clearance))
    bearing_rate = float(np.mean([row["complete_defense"] for row in bearing_rows]))
    oat_rows = (
        sensitivity["position_one_at_a_time"]
        + sensitivity["heading_one_at_a_time"]
    )
    oat_all_executable = all(
        row["route_constructible"] and row["lead_within_60s"] for row in oat_rows
    )
    narrow_trigger = (
        bearing_rate < 1.0 - 1e-12
        or execution_rate < 0.95
        or half_margin_rate < 0.80
        or not oat_all_executable
    )
    return {
        "scenario_label": "SYNTHETIC_SCENARIO_ONLY",
        "predeclared_diagnostic_rule": {
            "bearing_success_rate_min": 1.0,
            "combined_execution_rate_min": 0.95,
            "combined_half_nominal_clearance_retention_rate_min": 0.80,
            "all_one_at_a_time_boundaries_must_execute": True,
            "role": "fallback diagnostic only; not a problem constant",
        },
        "bearing_success_rate": bearing_rate,
        "combined_execution_rate": execution_rate,
        "combined_half_nominal_clearance_retention_rate": half_margin_rate,
        "all_one_at_a_time_cases_execute": oat_all_executable,
        "combined_minimum_pair_distance_quantiles_m": {
            "min": float(np.min(clearance_values)),
            "p05": float(np.quantile(clearance_values, 0.05)),
            "p25": float(np.quantile(clearance_values, 0.25)),
            "median": float(np.quantile(clearance_values, 0.50)),
            "p75": float(np.quantile(clearance_values, 0.75)),
            "p95": float(np.quantile(clearance_values, 0.95)),
            "max": float(np.max(clearance_values)),
        },
        "combined_common_lead_quantiles_s": {
            "min": float(np.min([row["common_warning_lead_s"] for row in executable])),
            "median": float(
                np.median([row["common_warning_lead_s"] for row in executable])
            ),
            "p95": float(
                np.quantile(
                    [row["common_warning_lead_s"] for row in executable], 0.95
                )
            ),
            "max": float(np.max([row["common_warning_lead_s"] for row in executable])),
        },
        "narrow_initial_or_bearing_range_triggered": narrow_trigger,
        "fallback_p1_recomparison_required": narrow_trigger,
    }


def build_analysis() -> dict[str, Any]:
    scenario = load_scenario()
    selected, alternatives = load_selected()
    routes = selected["routes"]
    min_distance = detailed_minimum_pair_distance(routes, WINDOW_END)
    validation = continuous_and_independent_validation(selected)
    selected_failure = exact_failure_metrics(selected)
    failures = selected_failure["details"]
    bearings = bearing_sensitivity(selected)
    perturbations = position_and_heading_sensitivity(selected, scenario)
    summary = sensitivity_summary(selected, bearings, perturbations)
    events = []
    for route in routes:
        events.append(
            {
                "scenario_label": "SYNTHETIC_SCENARIO_ONLY",
                "uav": route["uav"] + 1,
                "initial_position_m": route["start"],
                "initial_heading_rad": route["initial_heading"],
                "available_time_s": route["latest_available_time"],
                "command_time_s": route["command_time"],
                "release_time_s": route["release_time"],
                "burst_time_s": route["burst_time"],
                "release_point_m": route["release_point"],
                "smoke_center_m": route["center"],
                "path_length_m": route["path_length"],
                "turn_angle_rad": route["turn_angle"],
            }
        )
    comparisons = []
    for label, row in alternatives.items():
        exact_failure = exact_failure_metrics(row)
        comparisons.append(
            {
                "scenario_label": "SYNTHETIC_SCENARIO_ONLY",
                "plan": label,
                "common_warning_lead_s": row["lead_required_s"],
                "user_defined_latest_uav_warning_lead_s": row[
                    "user_defined_latest_uav_warning_lead_s"
                ],
                "d_safe_max_m": row["d_safe_max_m"],
                "n_minus_one_success_rate": exact_failure[
                    "n_minus_one_success_rate"
                ],
                "worst_failure_continuous_cover_s": exact_failure[
                    "worst_failure_continuous_cover_s"
                ],
                "double_cover_time_ratio": exact_failure[
                    "double_cover_time_ratio"
                ],
                "total_path_length_m": row["total_path_length_m"],
                "total_turn_angle_rad": row["total_turn_angle_rad"],
            }
        )
    return {
        "scenario": scenario,
        "selected": selected,
        "events": events,
        "trajectory_rows": trajectory_rows(selected),
        "minimum_pair_distance": min_distance,
        "continuous_validation": validation,
        "failure_details": failures,
        "selected_exact_failure_metrics": {
            key: value
            for key, value in selected_failure.items()
            if key != "details"
        },
        "bearing_rows": bearings,
        "perturbations": perturbations,
        "sensitivity_summary": summary,
        "comparison": comparisons,
        "nominal_safety_distance_feasible_interval_m": [
            0.0,
            selected["d_safe_max_m"],
        ],
    }
