"""Continuous analytic pairwise safety certificate for piecewise-linear paths."""

from __future__ import annotations

from itertools import combinations
from typing import Any, Sequence

import numpy as np

from q3_q2_adapter import T_WORST_S
from q3_trajectory import position_at


def certify_pair(
    first: dict[str, Any],
    second: dict[str, Any],
    d_safe_m: float = 0.0,
    end_s: float = T_WORST_S,
) -> dict[str, Any]:
    start = max(float(first["t_start_s"]), float(second["t_start_s"]))
    if start > end_s:
        raise ValueError("The pair has no common trajectory interval.")
    p1 = position_at(first, start)
    p2 = position_at(second, start)
    v1 = 28.0 * np.asarray(first["unit_heading"], dtype=float)
    v2 = 28.0 * np.asarray(second["unit_heading"], dtype=float)
    relative_position = p1 - p2
    relative_velocity = v1 - v2
    vv = float(relative_velocity @ relative_velocity)
    duration = float(end_s) - start
    stationary_offset = (
        0.0
        if vv == 0.0
        else -float(relative_position @ relative_velocity) / vv
    )
    clipped_offset = min(duration, max(0.0, stationary_offset))
    t_star = start + clipped_offset
    pos1 = position_at(first, t_star)
    pos2 = position_at(second, t_star)
    distance = float(np.linalg.norm(pos1 - pos2))
    margin = distance - float(d_safe_m)
    return {
        "uav_pair": [int(first["uav_id"]), int(second["uav_id"])],
        "minimum_pairwise_distance_m": distance,
        "minimum_distance_time_s": t_star,
        "uav_i_position_m": pos1.tolist(),
        "uav_k_position_m": pos2.tolist(),
        "relative_velocity_mps": relative_velocity.tolist(),
        "trajectory_segment": [start, float(end_s)],
        "candidate_times_s": sorted({start, float(end_s), t_star}),
        "relative_velocity_zero": vv == 0.0,
        "safety_distance_m": float(d_safe_m),
        "safety_margin_m": margin,
        "certificate_status": "verified" if margin >= -1e-10 else "failed",
        "time_grid_used": False,
        "method": "analytic_quadratic_distance_stationary_point",
    }


def certify_plan_safety(
    plans: Sequence[dict[str, Any]],
    d_safe_m: float = 0.0,
    end_s: float = T_WORST_S,
) -> dict[str, Any]:
    if len(plans) != 3:
        raise ValueError("Q3 safety requires exactly three UAV plans.")
    pairs = [
        certify_pair(plans[i], plans[j], d_safe_m=d_safe_m, end_s=end_s)
        for i, j in combinations(range(3), 2)
    ]
    worst = min(
        pairs,
        key=lambda item: (
            item["minimum_pairwise_distance_m"],
            item["uav_pair"],
        ),
    )
    status = (
        "verified"
        if all(item["certificate_status"] == "verified" for item in pairs)
        else "failed"
    )
    return {
        "minimum_pairwise_distance_m": worst["minimum_pairwise_distance_m"],
        "nominal_fixed_plan_maximum_d_safe_m": worst[
            "minimum_pairwise_distance_m"
        ],
        "minimum_distance_time_s": worst["minimum_distance_time_s"],
        "uav_pair": worst["uav_pair"],
        "uav_i_position_m": worst["uav_i_position_m"],
        "uav_k_position_m": worst["uav_k_position_m"],
        "pair_certificates": pairs,
        "safety_distance_m": float(d_safe_m),
        "safety_margin_m": worst["minimum_pairwise_distance_m"] - float(d_safe_m),
        "certificate_status": status,
        "time_grid_used": False,
        "robust_safe_distance_guarantee": False,
    }
