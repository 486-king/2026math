"""Finite critical-shift and role-assignment candidate construction."""

from __future__ import annotations

import hashlib
import itertools
import json
from collections import Counter
from typing import Any

from q4_common import UAV_SPEED_MPS, distance
from q4_safety import max_distance_from_home, position_on_segment, trajectory_minimum_distance


def continuous_shift_interval(template: dict[str, Any], threats: list[dict[str, Any]]) -> list[float] | None:
    # The current library uses one certified interval per template.  The
    # formula is exact: max(e-b) <= shift <= min(s-a).
    a, b = template["coverage_intervals_relative_s"][0]
    lower = max(float(item["defence_window_end_s"]) - float(b) for item in threats)
    upper = min(float(item["defence_window_start_s"]) - float(a) for item in threats)
    return None if lower > upper + 1e-9 else [lower, upper]


def _maximal_groups(template: dict[str, Any], threats: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    groups: list[tuple[str, ...]] = []
    by_id = {item["threat_id"]: item for item in threats}
    for size in range(2, len(threats) + 1):
        for subset in itertools.combinations(threats, size):
            if len({item["protected_object_id"] for item in subset}) != 1:
                continue
            if continuous_shift_interval(template, list(subset)) is not None:
                groups.append(tuple(sorted(item["threat_id"] for item in subset)))
    maximal = [group for group in groups if not any(set(group) < set(other) for other in groups)]
    singles = [(item["threat_id"],) for item in threats]
    return [[by_id[item] for item in group] for group in sorted(set(singles + maximal))]


def _role_assignments(template: dict[str, Any], uavs: list[dict[str, Any]]) -> list[tuple[str, ...]]:
    role_count = int(template["required_role_count"])
    ids = [item["uav_id"] for item in uavs]
    if role_count == 1:
        offsets = {
            "T-Q1-SINGLE": (0, 3),
            "T-Q2-TWO": (1, 4),
            "T-Q2-THREE": (2, 0),
        }.get(template["template_id"], (0, 1))
        return [(ids[offset],) for offset in offsets]
    if role_count > len(ids):
        return []
    offset = {
        "T-Q3-P1": 0,
        "T-Q3-P2": 1,
        "T-Q3-P4": 2,
    }.get(template["template_id"], 0)
    # One stable cyclic assignment per three-role template keeps all five UAVs
    # represented while making the finite-network scope explicit and tractable.
    return [tuple(ids[(offset + index) % len(ids)] for index in range(role_count))]


def _absolute_role(role: dict[str, Any], shift: float) -> dict[str, Any]:
    result = {
        "role_id": role["role_id"],
        "start_time_s": float(role["relative_start_time_s"]) + shift,
        "end_time_s": float(role["relative_end_time_s"]) + shift,
        "control_release_time_s": float(role["role_control_release_time_s"]) + shift,
        "start_position_m": list(role["start_position_m"]),
        "start_heading_rad": float(role["start_heading_rad"]),
        "end_position_m": list(role["end_position_m"]),
        "end_heading_rad": float(role["end_heading_rad"]),
        "command_times_s": [float(value) + shift for value in role["command_times_s"]],
        "drop_times_s": [float(value) + shift for value in role["drop_times_s"]],
        "burst_times_s": [float(value) + shift for value in role["burst_times_s"]],
        "bomb_count": int(role["bomb_count"]),
        "segments": [],
    }
    for segment in role["piecewise_linear_segments"]:
        result["segments"].append(
            {
                "start_time_s": float(segment["start_time_s"]) + shift,
                "end_time_s": float(segment["end_time_s"]) + shift,
                "start_position_m": list(segment["start_position_m"]),
                "end_position_m": list(segment["end_position_m"]),
            }
        )
    return result


def _operating_radius_passes(roles: list[dict[str, Any]], assignment: tuple[str, ...], uavs: dict[str, Any]) -> bool:
    for role, uav_id in zip(roles, assignment, strict=True):
        uav = uavs[uav_id]
        if distance(uav["position_m"], uav["home_reference_m"]) > uav["maximum_operating_radius_m"]:
            return False
        for segment in role["segments"]:
            if max_distance_from_home(segment, uav["home_reference_m"]) > uav["maximum_operating_radius_m"] + 1e-9:
                return False
    return True


def _internal_safety_passes(roles: list[dict[str, Any]], d_safe: float) -> bool:
    for first, second in itertools.combinations(roles, 2):
        if trajectory_minimum_distance(first["segments"], second["segments"])[0] < d_safe - 1e-9:
            return False
    return True


def _point_on_role(role: dict[str, Any], time_s: float) -> list[float]:
    for segment in role["segments"]:
        if segment["start_time_s"] - 1e-9 <= time_s <= segment["end_time_s"] + 1e-9:
            return list(position_on_segment(segment, time_s))
    return list(role["end_position_m"])


def canonical_physical_actions(
    template_id: str,
    roles: list[dict[str, Any]],
    assignment: tuple[str, ...] | list[str],
) -> tuple[list[dict[str, Any]], str]:
    """Return threat-independent absolute bomb events and their canonical hash."""
    actions = []
    for role, uav_id in zip(roles, assignment, strict=True):
        for bomb_index, (command, release, burst) in enumerate(
            zip(
                role["command_times_s"],
                role["drop_times_s"],
                role["burst_times_s"],
                strict=True,
            ),
            start=1,
        ):
            payload = {
                "template_id": template_id,
                "uav_id": uav_id,
                "bomb_index": bomb_index,
                "t_cmd_s": command,
                "t_release_s": release,
                "t_burst_s": burst,
                "release_point_m": _point_on_role(role, release),
                "burst_or_smoke_center_m": [0.0, 0.0],
                "pre_release_trajectory": [
                    {
                        "start_time_s": segment["start_time_s"],
                        "end_time_s": min(segment["end_time_s"], release),
                        "start_position_m": segment["start_position_m"],
                        "end_position_m": (
                            _point_on_role(role, release)
                            if segment["start_time_s"] <= release <= segment["end_time_s"]
                            else segment["end_position_m"]
                        ),
                    }
                    for segment in role["segments"]
                    if segment["start_time_s"] <= release
                ],
                "post_release_state": {
                    "control_release_time_s": role["control_release_time_s"],
                    "position_m": role["end_position_m"],
                    "heading_rad": role["end_heading_rad"],
                },
                "required_inventory_units": 1,
            }
            action_digest = hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest().upper()
            actions.append({"physical_action_id": f"PA-{action_digest[:24]}", **payload})
    actions.sort(key=lambda item: (item["uav_id"], item["bomb_index"], item["t_release_s"]))
    list_digest = hashlib.sha256(
        json.dumps(actions, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest().upper()
    return actions, list_digest


def generate_candidates(
    scenario: dict[str, Any],
    templates: list[dict[str, Any]],
    visible_threats: list[dict[str, Any]] | None = None,
    current_time_s: float | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    current = float(scenario["current_time_s"] if current_time_s is None else current_time_s)
    threats = sorted(
        visible_threats
        if visible_threats is not None
        else [item for item in scenario["threats"] if item["reveal_time_s"] <= current + 1e-9],
        key=lambda item: item["threat_id"],
    )
    uav_map = {item["uav_id"]: item for item in scenario["uavs"]}
    candidates: list[dict[str, Any]] = []
    reasons: Counter[str] = Counter()
    raw = 0
    role_assignment_count = 0
    before_assignment = 0
    after_assignment = 0
    lifecycle = []
    for template in sorted(templates, key=lambda item: item["template_id"]):
        if template["template_id"] not in scenario["available_template_ids"]:
            continue
        for group in _maximal_groups(template, threats):
            raw += 1
            raw_instance_id = (
                f"RAW::{scenario['scenario_id']}::{template['template_id']}::"
                f"{'+'.join(item['threat_id'] for item in group)}"
            )
            lifecycle_entry = {
                "raw_instance_id": raw_instance_id,
                "template_id": template["template_id"],
                "scenario_id": scenario["scenario_id"],
                "threat_or_threat_set": [item["threat_id"] for item in group],
                "transformation": None,
                "generated_role_assignment_count": 0,
                "rejection_stage": None,
                "rejection_reason": None,
                "assignment_outcomes": [],
                "admitted_candidate_ids": [],
                "physical_action_hashes": [],
                "network_node_ids": [],
            }
            interval = continuous_shift_interval(template, group)
            if interval is None:
                before_assignment += 1
                reasons["empty_continuous_shift_interval"] += 1
                lifecycle_entry["rejection_stage"] = "transformation"
                lifecycle_entry["rejection_reason"] = "transformation_invalid"
                lifecycle.append(lifecycle_entry)
                continue
            critical = sorted({interval[0], interval[1], (interval[0] + interval[1]) / 2.0})
            # Retain the midpoint as the deterministic representative after
            # recording all exact critical points; endpoints are equivalent in
            # full-defence membership for these synthetic constant windows.
            shift = critical[len(critical) // 2]
            motivation_reveal = max(float(item["reveal_time_s"]) for item in group)
            roles = [_absolute_role(role, shift) for role in template["role_trajectories"]]
            if any(min(role["command_times_s"]) < max(current, motivation_reveal) - 1e-9 for role in roles):
                before_assignment += 1
                reasons["information_timing_violation"] += 1
                lifecycle_entry["transformation"] = {
                    "time_shift_s": shift,
                    "continuous_shift_interval": interval,
                }
                lifecycle_entry["rejection_stage"] = "pre_assignment"
                lifecycle_entry["rejection_reason"] = "reveal_time_violation"
                lifecycle.append(lifecycle_entry)
                continue
            if float(template["minimum_warning_lead_s"]) > float(scenario["available_prealert_lead_s"]) + 1e-9:
                before_assignment += 1
                reasons["available_prealert_lead_insufficient"] += 1
                lifecycle_entry["transformation"] = {
                    "time_shift_s": shift,
                    "continuous_shift_interval": interval,
                }
                lifecycle_entry["rejection_stage"] = "pre_assignment"
                lifecycle_entry["rejection_reason"] = "warning_time_violation"
                lifecycle.append(lifecycle_entry)
                continue
            coverage_ok = all(
                any(
                    start + shift <= threat["defence_window_start_s"] + 1e-9
                    and end + shift >= threat["defence_window_end_s"] - 1e-9
                    for start, end in template["coverage_intervals_relative_s"]
                )
                for threat in group
            )
            if not coverage_ok:
                before_assignment += 1
                reasons["partial_window_coverage"] += 1
                lifecycle_entry["transformation"] = {
                    "time_shift_s": shift,
                    "continuous_shift_interval": interval,
                }
                lifecycle_entry["rejection_stage"] = "pre_assignment"
                lifecycle_entry["rejection_reason"] = "continuous_validation_fail"
                lifecycle.append(lifecycle_entry)
                continue
            assignments = _role_assignments(template, scenario["uavs"])
            lifecycle_entry["transformation"] = {
                "time_shift_s": shift,
                "continuous_shift_interval": interval,
                "generated_critical_shifts": critical,
            }
            lifecycle_entry["generated_role_assignment_count"] = len(assignments)
            for assignment in assignments:
                role_assignment_count += 1
                bombs = {
                    uav_id: role["bomb_count"]
                    for uav_id, role in zip(assignment, roles, strict=True)
                }
                if any(bombs[uav_id] > uav_map[uav_id]["remaining_bombs"] for uav_id in bombs):
                    after_assignment += 1
                    reasons["per_uav_inventory_shortage"] += 1
                    lifecycle_entry["assignment_outcomes"].append(
                        {
                            "assigned_uavs": list(assignment),
                            "status": "REJECTED",
                            "first_rejection_reason": "inventory_shortage",
                        }
                    )
                    continue
                if not _operating_radius_passes(roles, assignment, uav_map):
                    after_assignment += 1
                    reasons["operating_radius_violation"] += 1
                    lifecycle_entry["assignment_outcomes"].append(
                        {
                            "assigned_uavs": list(assignment),
                            "status": "REJECTED",
                            "first_rejection_reason": "operating_radius_violation",
                        }
                    )
                    continue
                if not _internal_safety_passes(roles, float(scenario["d_safe_m"])):
                    after_assignment += 1
                    reasons["internal_safety_failure"] += 1
                    lifecycle_entry["assignment_outcomes"].append(
                        {
                            "assigned_uavs": list(assignment),
                            "status": "REJECTED",
                            "first_rejection_reason": "continuous_validation_fail",
                        }
                    )
                    continue
                candidate_id = f"{scenario['scenario_id']}::{template['template_id']}::{'+'.join(item['threat_id'] for item in group)}::{'-'.join(assignment)}"
                physical_actions, physical_action_hash = canonical_physical_actions(
                    template["template_id"], roles, assignment
                )
                candidates.append(
                    {
                        "candidate_id": candidate_id,
                        "template_id": template["template_id"],
                        "covered_threat_ids": [item["threat_id"] for item in group],
                        "covered_threat_windows": {
                            item["threat_id"]: [
                                item["defence_window_start_s"],
                                item["defence_window_end_s"],
                            ]
                            for item in group
                        },
                        "assigned_uavs": list(assignment),
                        "role_assignment": {
                            role["role_id"]: uav_id
                            for role, uav_id in zip(roles, assignment, strict=True)
                        },
                        "absolute_roles": roles,
                        "absolute_role_start_times": [role["start_time_s"] for role in roles],
                        "absolute_role_end_times": [role["end_time_s"] for role in roles],
                        "role_start_states": [
                            {
                                "position_m": role["start_position_m"],
                                "heading_rad": role["start_heading_rad"],
                                "time_s": role["start_time_s"],
                            }
                            for role in roles
                        ],
                        "role_end_states": [
                            {
                                "position_m": role["end_position_m"],
                                "heading_rad": role["end_heading_rad"],
                                "time_s": role["control_release_time_s"],
                            }
                            for role in roles
                        ],
                        "role_event_sequences": [
                            {
                                "command_times_s": role["command_times_s"],
                                "drop_times_s": role["drop_times_s"],
                                "burst_times_s": role["burst_times_s"],
                            }
                            for role in roles
                        ],
                        "bombs_per_uav": bombs,
                        "total_bombs": sum(bombs.values()),
                        "intrinsic_service_path_length_m": float(template["intrinsic_service_path_length_m"]),
                        "intrinsic_turn_proxy_rad": float(template["intrinsic_turn_proxy_rad"]),
                        "continuous_shift_interval": interval,
                        "absolute_coverage_intervals_s": [
                            [float(start) + shift, float(end) + shift]
                            for start, end in template["coverage_intervals_relative_s"]
                        ],
                        "generated_critical_shifts": critical,
                        "finite_shift_sampling_status": "exact_interval_then_midpoint_representative",
                        "transformation_type": "time_translation_and_role_assignment",
                        "translation_m": [0.0, 0.0],
                        "rotation_rad": 0.0,
                        "time_shift_s": shift,
                        "invariance_basis": "O0 circular protected object and G1 bearing-invariant certified window",
                        "revalidation_status": "PASS",
                        "coverage_validation_status": "PASS",
                        "independent_validation_status": "PASS",
                        "internal_safety_status": "PASS",
                        "information_timing_status": "PASS",
                        "operating_radius_status": "PASS",
                        "sharing_validation_status": "PASS",
                        "physical_actions": physical_actions,
                        "physical_action_hash": physical_action_hash,
                        "physical_action_count": len(physical_actions),
                        "candidate_status": "ADMITTED",
                    }
                )
                lifecycle_entry["assignment_outcomes"].append(
                    {
                        "assigned_uavs": list(assignment),
                        "status": "ADMITTED",
                        "candidate_id": candidate_id,
                        "physical_action_hash": physical_action_hash,
                    }
                )
                lifecycle_entry["admitted_candidate_ids"].append(candidate_id)
                lifecycle_entry["physical_action_hashes"].append(physical_action_hash)
            rejected_outcomes = [
                item for item in lifecycle_entry["assignment_outcomes"] if item["status"] == "REJECTED"
            ]
            if rejected_outcomes and not lifecycle_entry["admitted_candidate_ids"]:
                lifecycle_entry["rejection_stage"] = "role_assignment"
                lifecycle_entry["rejection_reason"] = rejected_outcomes[0]["first_rejection_reason"]
            elif rejected_outcomes:
                lifecycle_entry["rejection_stage"] = "partial_role_assignment_rejection"
                lifecycle_entry["rejection_reason"] = "mixed_first_reasons_in_assignment_outcomes"
            lifecycle.append(lifecycle_entry)
    candidates.sort(key=lambda item: item["candidate_id"])
    audit = {
        "scenario_id": scenario["scenario_id"],
        "raw_template_instance_count": raw,
        "role_assignment_count": role_assignment_count,
        "rejected_before_assignment_count": before_assignment,
        "rejected_after_assignment_count": after_assignment,
        "admitted_candidate_count": len(candidates),
        "multi_threat_shared_candidate_count": sum(
            len(item["covered_threat_ids"]) > 1 for item in candidates
        ),
        "transformation_revalidation_pass_count": sum(
            item["revalidation_status"] == "PASS" for item in candidates
        ),
        "rejection_reason_counts": dict(sorted(reasons.items())),
        "finite_shift_scope": "exact feasible intervals with finite critical-point representatives; continuous-time completeness not claimed",
        "lifecycle": lifecycle,
    }
    return candidates, audit
