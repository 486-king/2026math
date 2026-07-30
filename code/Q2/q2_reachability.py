"""Relative UAV transition checks without inventing an absolute start state."""

from __future__ import annotations

import itertools
from typing import Any, Sequence

from q2_common import PARAMS, SmokePlan


def enumerate_relative_headings(plan: Sequence[SmokePlan]) -> dict[str, Any]:
    if not plan:
        raise ValueError("A nonempty plan is required.")
    ordered = sorted(plan, key=lambda smoke: (smoke.t_d_s, smoke.smoke_id))
    candidates: list[dict[str, Any]] = []
    for signs in itertools.product((-1, 1), repeat=len(ordered)):
        release_positions = [
            smoke.center_m - PARAMS.inertial_displacement_m * sign
            for smoke, sign in zip(ordered, signs)
        ]
        transitions = []
        feasible = True
        slacks = []
        for index in range(len(ordered) - 1):
            release_interval = ordered[index + 1].t_d_s - ordered[index].t_d_s
            transition_distance = abs(
                release_positions[index + 1] - release_positions[index]
            )
            available = PARAMS.uav_speed_mps * release_interval
            slack = available - transition_distance
            slacks.append(slack)
            interval_ok = release_interval >= PARAMS.minimum_release_interval_s
            transition_ok = slack >= -1e-10
            feasible = feasible and interval_ok and transition_ok
            transitions.append(
                {
                    "from_smoke_id": ordered[index].smoke_id,
                    "to_smoke_id": ordered[index + 1].smoke_id,
                    "release_interval_s": release_interval,
                    "transition_distance_m": transition_distance,
                    "available_travel_distance_m": available,
                    "transition_slack_m": slack,
                    "minimum_release_interval_s": PARAMS.minimum_release_interval_s,
                    "release_interval_verified": interval_ok,
                    "relative_transition_verified": transition_ok,
                }
            )
        candidates.append(
            {
                "release_heading_signs": list(signs),
                "relative_release_positions_m": release_positions,
                "release_times_s": [smoke.t_d_s for smoke in ordered],
                "transitions": transitions,
                "minimum_transition_slack_m": min(slacks, default=0.0),
                "relative_transition_status": "feasible" if feasible else "infeasible",
            }
        )
    feasible_candidates = [
        candidate
        for candidate in candidates
        if candidate["relative_transition_status"] == "feasible"
    ]
    if not feasible_candidates:
        best = max(candidates, key=lambda candidate: candidate["minimum_transition_slack_m"])
        status = "infeasible"
    else:
        best = max(
            feasible_candidates,
            key=lambda candidate: (
                candidate["minimum_transition_slack_m"],
                tuple(-value for value in candidate["release_heading_signs"]),
            ),
        )
        status = "feasible"
    return {
        "relative_transition_status": status,
        "selected_heading_combination": best,
        "enumerated_heading_count": len(candidates),
        "feasible_heading_count": len(feasible_candidates),
        "all_candidates": candidates,
        "absolute_execution_status": (
            "blocked_missing_uav_initial_state_and_base_reference"
        ),
        "operating_radius_status": "not_evaluated_missing_base_reference",
        "absolute_first_release_position": "not_generated",
    }
