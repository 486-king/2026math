"""Q3 straight-line deployment geometry and event-chain validation."""

from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np

from q3_q2_adapter import PARAMS, T_WORST_S


def wrap_to_pi(angle_rad: float) -> float:
    return (float(angle_rad) + math.pi) % (2.0 * math.pi) - math.pi


def validate_event_chain(record: dict[str, Any], tolerance_s: float = 1e-9) -> dict[str, Any]:
    t_cmd = float(record["t_cmd_s"])
    t_d = float(record["t_d_s"])
    t_b = float(record["t_b_s"])
    errors: list[dict[str, Any]] = []
    release_error = t_d - (t_cmd + PARAMS.command_to_release_delay_s)
    burst_error = t_b - (t_d + PARAMS.release_to_burst_delay_s)
    if abs(release_error) > tolerance_s:
        errors.append({"field": "t_d_s", "error_s": release_error})
    if abs(burst_error) > tolerance_s:
        errors.append({"field": "t_b_s", "error_s": burst_error})
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "t_cmd_s": t_cmd,
        "t_d_s": t_d,
        "t_b_s": t_b,
        "pre_lock_mission": min(t_cmd, t_d, t_b) < 0.0,
        "burst_before_lock": t_b < 0.0,
        "negative_times_clipped": False,
    }


def derive_uav_plan(
    uav_state: dict[str, Any],
    smoke_center_m: float,
    t_b_s: float,
    *,
    smoke_id: str | None = None,
) -> dict[str, Any]:
    q = np.asarray(uav_state["position_m"], dtype=float)
    center = np.asarray([float(smoke_center_m), 0.0], dtype=float)
    displacement = center - q
    center_distance = float(np.linalg.norm(displacement))
    if center_distance <= PARAMS.inertial_displacement_m:
        return {
            "uav_id": int(uav_state["uav_id"]),
            "smoke_id": smoke_id or str(uav_state["uav_id"]),
            "execution_status": "infeasible_center_distance_not_greater_than_98m",
            "center_distance_m": center_distance,
        }
    heading = displacement / center_distance
    release_point = center - PARAMS.inertial_displacement_m * heading
    path_length = center_distance - PARAMS.inertial_displacement_m
    t_d = float(t_b_s) - PARAMS.release_to_burst_delay_s
    t_cmd = t_d - PARAMS.command_to_release_delay_s
    start_time = t_d - path_length / PARAMS.uav_speed_mps
    theta = math.atan2(float(heading[1]), float(heading[0]))
    initial_heading = float(uav_state["initial_heading_rad"])
    turn = abs(wrap_to_pi(theta - initial_heading))
    event = validate_event_chain(
        {"t_cmd_s": t_cmd, "t_d_s": t_d, "t_b_s": float(t_b_s)}
    )
    window_ok = -60.0 <= start_time <= 0.0
    return {
        "uav_id": int(uav_state["uav_id"]),
        "smoke_id": smoke_id or str(uav_state["uav_id"]),
        "execution_status": "feasible" if window_ok else "failed_start_time_window",
        "staging_position_m": q.tolist(),
        "initial_heading_rad": initial_heading,
        "smoke_center_m": float(smoke_center_m),
        "smoke_center_xy_m": center.tolist(),
        "unit_heading": heading.tolist(),
        "release_point_m": release_point.tolist(),
        "inertial_displacement_m": PARAMS.inertial_displacement_m,
        "deployment_path_length_m": path_length,
        "pre_release_path_length_m": path_length,
        "t_start_s": start_time,
        "t_cmd_s": t_cmd,
        "t_d_s": t_d,
        "t_b_s": float(t_b_s),
        "turn_proxy_rad": turn,
        "event_chain": event,
        "post_release_uav_motion": "continues_same_straight_velocity_through_T_worst",
        "trajectory_end_s": T_WORST_S,
        "operating_radius_status": "blocked_missing_base_reference",
    }


def position_at(plan: dict[str, Any], t_s: float) -> np.ndarray:
    if plan["execution_status"] not in {"feasible", "failed_start_time_window"}:
        raise ValueError("A geometric UAV plan is required.")
    start = float(plan["t_start_s"])
    if float(t_s) < start - 1e-12:
        raise ValueError("Trajectory is undefined before the UAV availability time.")
    q = np.asarray(plan["staging_position_m"], dtype=float)
    heading = np.asarray(plan["unit_heading"], dtype=float)
    return q + PARAMS.uav_speed_mps * (float(t_s) - start) * heading


def derive_plan_set(
    scenario: dict[str, Any],
    smoke_records: Sequence[dict[str, Any]],
    assignment: Sequence[int] = (0, 1, 2),
) -> dict[str, Any]:
    states = scenario["uav_staging_states"]
    if sorted(int(value) for value in assignment) != [0, 1, 2]:
        raise ValueError("assignment must be a permutation of [0,1,2].")
    plans: list[dict[str, Any]] = []
    for uav_index, smoke_index in enumerate(assignment):
        smoke = smoke_records[smoke_index]
        plans.append(
            derive_uav_plan(
                states[uav_index],
                float(smoke["smoke_center_m"]),
                float(smoke["t_b_s"]),
                smoke_id=str(smoke.get("smoke_id", smoke_index + 1)),
            )
        )
    feasible = all(plan["execution_status"] == "feasible" for plan in plans)
    return {
        "assignment_uav_to_smoke_index": [int(value) for value in assignment],
        "uav_plans": plans,
        "execution_status": "feasible" if feasible else "failed",
        "common_warning_lead_s": (
            -min(float(plan["t_start_s"]) for plan in plans if "t_start_s" in plan)
        ),
        "total_deployment_path_length_m": sum(
            float(plan.get("deployment_path_length_m", 0.0)) for plan in plans
        ),
        "total_pre_release_path_length_m": sum(
            float(plan.get("pre_release_path_length_m", 0.0)) for plan in plans
        ),
        "total_turn_proxy_rad": sum(
            float(plan.get("turn_proxy_rad", 0.0)) for plan in plans
        ),
    }
