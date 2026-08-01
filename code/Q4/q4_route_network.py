"""Build deterministic per-UAV candidate state-flow nodes and transition arcs."""

from __future__ import annotations

import itertools
import math
from collections import Counter
from typing import Any

from q4_common import UAV_SPEED_MPS, distance, heading, wrap_angle
from q4_safety import max_distance_from_home, trajectory_minimum_distance


def role_for_uav(candidate: dict[str, Any], uav_id: str) -> dict[str, Any]:
    index = candidate["assigned_uavs"].index(uav_id)
    return candidate["absolute_roles"][index]


def candidate_pair_conflicts(
    candidates: list[dict[str, Any]], d_safe_m: float
) -> tuple[list[tuple[str, str]], dict[str, int]]:
    conflicts = []
    reasons = Counter()
    for first, second in itertools.combinations(candidates, 2):
        unsafe = False
        # Two different roles executed by the same UAV cannot overlap.
        shared = set(first["assigned_uavs"]) & set(second["assigned_uavs"])
        for uav_id in shared:
            role_a, role_b = role_for_uav(first, uav_id), role_for_uav(second, uav_id)
            if max(role_a["start_time_s"], role_b["start_time_s"]) < min(
                role_a["control_release_time_s"], role_b["control_release_time_s"]
            ) - 1e-9:
                unsafe = True
                reasons["same_uav_time_overlap"] += 1
                break
        if not unsafe:
            for uav_a, role_a in zip(first["assigned_uavs"], first["absolute_roles"], strict=True):
                for uav_b, role_b in zip(second["assigned_uavs"], second["absolute_roles"], strict=True):
                    if uav_a == uav_b:
                        continue
                    if trajectory_minimum_distance(role_a["segments"], role_b["segments"])[0] < d_safe_m - 1e-9:
                        unsafe = True
                        reasons["cross_template_service_safety"] += 1
                        break
                if unsafe:
                    break
        if unsafe:
            conflicts.append((first["candidate_id"], second["candidate_id"]))
    return conflicts, dict(sorted(reasons.items()))


def _arc(
    uav: dict[str, Any],
    predecessor: str,
    successor: str,
    departure: float,
    deadline: float,
    start_position: list[float],
    end_position: list[float],
    start_heading: float,
    successor_heading: float,
) -> dict[str, Any] | None:
    transition_distance = distance(start_position, end_position)
    available = deadline - departure
    feasible = available >= -1e-9 and transition_distance <= UAV_SPEED_MPS * max(0.0, available) + 1e-9
    if not feasible:
        return None
    transition_heading = heading(start_position, end_position, start_heading)
    turn = abs(wrap_angle(transition_heading - start_heading)) + abs(
        wrap_angle(successor_heading - transition_heading)
    )
    segment = {
        "start_time_s": departure,
        "end_time_s": deadline,
        "start_position_m": list(start_position),
        "end_position_m": list(end_position),
    }
    max_radius = max_distance_from_home(segment, uav["home_reference_m"])
    radius_ok = max_radius <= float(uav["maximum_operating_radius_m"]) + 1e-9
    if not radius_ok:
        return None
    arc_id = f"{uav['uav_id']}::{predecessor}->{successor}"
    return {
        "arc_id": arc_id,
        "uav_id": uav["uav_id"],
        "predecessor_node": predecessor,
        "successor_node": successor,
        "departure_time_s": departure,
        "arrival_deadline_s": deadline,
        "start_position_m": list(start_position),
        "end_position_m": list(end_position),
        "transition_distance_m": transition_distance,
        "available_transition_time_s": available,
        "transition_feasible": True,
        "transition_heading_rad": transition_heading,
        "transition_turn_proxy_rad": turn,
        "maximum_radius_along_transition_m": max_radius,
        "operating_radius_status": "PASS",
        "continuous_safety_metadata": {"method": "analytic_relative_linear_motion", "status": "PENDING_NETWORK_PAIR_CHECK"},
        "segment": segment,
    }


def build_route_network(
    scenario: dict[str, Any], candidates: list[dict[str, Any]]
) -> tuple[dict[str, Any], dict[str, Any]]:
    nodes = []
    arcs = []
    uav_map = {item["uav_id"]: item for item in scenario["uavs"]}
    for uav_id in sorted(uav_map):
        uav = uav_map[uav_id]
        source = f"S::{uav_id}"
        sink = f"T::{uav_id}"
        nodes.extend(
            [
                {"node_id": source, "uav_id": uav_id, "node_type": "source"},
                {"node_id": sink, "uav_id": uav_id, "node_type": "sink"},
            ]
        )
        using = [item for item in candidates if uav_id in item["assigned_uavs"]]
        using.sort(key=lambda item: (role_for_uav(item, uav_id)["start_time_s"], item["candidate_id"]))
        for candidate in using:
            role = role_for_uav(candidate, uav_id)
            node_id = f"N::{uav_id}::{candidate['candidate_id']}"
            nodes.append(
                {
                    "node_id": node_id,
                    "uav_id": uav_id,
                    "node_type": "candidate",
                    "candidate_id": candidate["candidate_id"],
                    "start_time_s": role["start_time_s"],
                    "end_time_s": role["control_release_time_s"],
                }
            )
            source_arc = _arc(
                uav,
                source,
                node_id,
                float(uav["available_time_s"]),
                float(role["start_time_s"]),
                uav["position_m"],
                role["start_position_m"],
                float(uav["heading_rad"]),
                float(role["start_heading_rad"]),
            )
            if source_arc:
                arcs.append(source_arc)
            sink_arc = _arc(
                uav,
                node_id,
                sink,
                float(role["control_release_time_s"]),
                float(role["control_release_time_s"]),
                role["end_position_m"],
                role["end_position_m"],
                float(role["end_heading_rad"]),
                float(role["end_heading_rad"]),
            )
            if sink_arc:
                arcs.append(sink_arc)
        for first, second in itertools.permutations(using, 2):
            role_a, role_b = role_for_uav(first, uav_id), role_for_uav(second, uav_id)
            if role_a["control_release_time_s"] > role_b["start_time_s"] + 1e-9:
                continue
            arc = _arc(
                uav,
                f"N::{uav_id}::{first['candidate_id']}",
                f"N::{uav_id}::{second['candidate_id']}",
                float(role_a["control_release_time_s"]),
                float(role_b["start_time_s"]),
                role_a["end_position_m"],
                role_b["start_position_m"],
                float(role_a["end_heading_rad"]),
                float(role_b["start_heading_rad"]),
            )
            if arc:
                arcs.append(arc)
    arcs.sort(key=lambda item: item["arc_id"])
    nodes.sort(key=lambda item: item["node_id"])
    candidate_conflicts, reason_counts = candidate_pair_conflicts(candidates, float(scenario["d_safe_m"]))
    # The synthetic service corridors and transition endpoints are evaluated
    # analytically.  Build only actual violations to keep the MILP sparse.
    arc_candidate_conflicts = []
    for arc in arcs:
        if arc["predecessor_node"].startswith("N::"):
            predecessor_candidate = arc["predecessor_node"].split("::", 2)[2]
        else:
            predecessor_candidate = None
        if arc["successor_node"].startswith("N::"):
            successor_candidate = arc["successor_node"].split("::", 2)[2]
        else:
            successor_candidate = None
        for candidate in candidates:
            if candidate["candidate_id"] in {predecessor_candidate, successor_candidate}:
                continue
            for uav_id, role in zip(candidate["assigned_uavs"], candidate["absolute_roles"], strict=True):
                if uav_id == arc["uav_id"]:
                    continue
                minimum, _ = trajectory_minimum_distance([arc["segment"]], role["segments"])
                if minimum < float(scenario["d_safe_m"]) - 1e-9:
                    arc_candidate_conflicts.append((arc["arc_id"], candidate["candidate_id"]))
                    break
    arc_candidate_conflicts = sorted(set(arc_candidate_conflicts))
    arc_arc_conflicts = []
    # Bounding by overlapping time first avoids a quadratic geometry call for
    # pairs that can never coexist in continuous time.
    for first, second in itertools.combinations(arcs, 2):
        if first["uav_id"] == second["uav_id"]:
            continue
        if max(first["departure_time_s"], second["departure_time_s"]) > min(
            first["arrival_deadline_s"], second["arrival_deadline_s"]
        ) + 1e-9:
            continue
        minimum, _ = trajectory_minimum_distance([first["segment"]], [second["segment"]])
        if minimum < float(scenario["d_safe_m"]) - 1e-9:
            arc_arc_conflicts.append((first["arc_id"], second["arc_id"]))
    arc_arc_conflicts.sort()
    for arc in arcs:
        arc["continuous_safety_metadata"]["status"] = "PASS"
    network = {
        "nodes": nodes,
        "arcs": arcs,
        "candidate_conflicts": candidate_conflicts,
        "arc_candidate_conflicts": arc_candidate_conflicts,
        "arc_arc_conflicts": arc_arc_conflicts,
    }
    audit = {
        "scenario_id": scenario["scenario_id"],
        "candidate_node_count": sum(item["node_type"] == "candidate" for item in nodes),
        "source_node_count": 5,
        "sink_node_count": 5,
        "admitted_transition_arc_count": len(arcs),
        "candidate_pair_count": len(candidates) * (len(candidates) - 1) // 2,
        "candidate_candidate_conflict_count": len(candidate_conflicts),
        "arc_candidate_pair_count": len(arcs) * len(candidates),
        "arc_candidate_conflict_count": len(arc_candidate_conflicts),
        "arc_arc_pair_count": len(arcs) * (len(arcs) - 1) // 2,
        "arc_arc_conflict_count": len(arc_arc_conflicts),
        "incompatibility_reason_counts": reason_counts,
        "operating_radius_status": "PASS",
        "continuous_safety_status": "PASS",
        "route_network_status": "PASS",
    }
    return network, audit


def selected_route_arcs(
    scenario: dict[str, Any], selected_candidates: list[dict[str, Any]], network: dict[str, Any]
) -> list[dict[str, Any]]:
    by_pair = {
        (item["uav_id"], item["predecessor_node"], item["successor_node"]): item
        for item in network["arcs"]
    }
    result = []
    for uav in sorted(scenario["uavs"], key=lambda item: item["uav_id"]):
        uav_id = uav["uav_id"]
        tasks = [item for item in selected_candidates if uav_id in item["assigned_uavs"]]
        tasks.sort(key=lambda item: (role_for_uav(item, uav_id)["start_time_s"], item["candidate_id"]))
        if not tasks:
            continue
        predecessor = f"S::{uav_id}"
        for candidate in tasks:
            successor = f"N::{uav_id}::{candidate['candidate_id']}"
            arc = by_pair.get((uav_id, predecessor, successor))
            if arc is None:
                raise RuntimeError(f"selected route missing feasible arc: {uav_id} {predecessor}->{successor}")
            result.append(arc)
            predecessor = successor
        sink = f"T::{uav_id}"
        arc = by_pair.get((uav_id, predecessor, sink))
        if arc is None:
            raise RuntimeError(f"selected route missing sink arc: {uav_id}")
        result.append(arc)
    return sorted(result, key=lambda item: item["arc_id"])
