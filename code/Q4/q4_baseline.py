"""Q4-B feasibility-filtered stable greedy baseline and takeover plan."""

from __future__ import annotations

from typing import Any

from q4_route_network import selected_route_arcs


def _schedule_feasible(
    scenario: dict[str, Any],
    selected: list[dict[str, Any]],
    network: dict[str, Any],
) -> tuple[bool, list[dict[str, Any]]]:
    selected_ids = {item["candidate_id"] for item in selected}
    for first, second in network["candidate_conflicts"]:
        if first in selected_ids and second in selected_ids:
            return False, []
    for uav in scenario["uavs"]:
        used = sum(item["bombs_per_uav"].get(uav["uav_id"], 0) for item in selected)
        if used > int(uav["remaining_bombs"]):
            return False, []
    if sum(item["total_bombs"] for item in selected) > min(
        15, sum(int(item["remaining_bombs"]) for item in scenario["uavs"])
    ):
        return False, []
    try:
        arcs = selected_route_arcs(scenario, selected, network)
    except RuntimeError:
        return False, []
    arc_ids = {item["arc_id"] for item in arcs}
    for arc_id, candidate_id in network["arc_candidate_conflicts"]:
        if arc_id in arc_ids and candidate_id in selected_ids:
            return False, []
    for first, second in network["arc_arc_conflicts"]:
        if first in arc_ids and second in arc_ids:
            return False, []
    return True, arcs


def solve_baseline(
    scenario: dict[str, Any],
    threats: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    network: dict[str, Any],
) -> dict[str, Any]:
    now = float(scenario["current_time_s"])
    threat_candidates = {
        threat["threat_id"]: [
            item for item in candidates if threat["threat_id"] in item["covered_threat_ids"]
        ]
        for threat in threats
    }

    def remaining_reaction(threat: dict[str, Any]) -> float:
        options = threat_candidates[threat["threat_id"]]
        if not options:
            return float("inf")
        return max(
            min(min(role["command_times_s"]) for role in item["absolute_roles"])
            for item in options
        ) - now

    ordered_threats = sorted(
        threats,
        key=lambda item: (
            remaining_reaction(item),
            -int(item["threat_level"]),
            min((candidate["total_bombs"] for candidate in threat_candidates[item["threat_id"]]), default=10**9),
            len(threat_candidates[item["threat_id"]]),
            item["threat_id"],
        ),
    )
    selected: list[dict[str, Any]] = []
    served: set[str] = set()
    selected_arcs: list[dict[str, Any]] = []
    rejected = []
    for threat in ordered_threats:
        if threat["threat_id"] in served:
            continue
        options = sorted(
            threat_candidates[threat["threat_id"]],
            key=lambda item: (
                item["total_bombs"],
                item["intrinsic_service_path_length_m"],
                item["intrinsic_turn_proxy_rad"],
                -sum(
                    int(uav["remaining_bombs"]) - item["bombs_per_uav"].get(uav["uav_id"], 0)
                    for uav in scenario["uavs"]
                ),
                item["candidate_id"],
            ),
        )
        chosen = None
        for candidate in options:
            if candidate in selected:
                chosen = candidate
                break
            feasible, arcs = _schedule_feasible(scenario, selected + [candidate], network)
            if feasible:
                chosen = candidate
                selected.append(candidate)
                selected_arcs = arcs
                served.update(candidate["covered_threat_ids"])
                break
        if chosen is None:
            rejected.append(
                {
                    "threat_id": threat["threat_id"],
                    "rejection_reason": (
                        "no_admitted_template"
                        if not options
                        else "baseline_greedy_blocked"
                    ),
                }
            )
    feasible, selected_arcs = _schedule_feasible(scenario, selected, network)
    return {
        "solver_status": "greedy_completed",
        "feasible_incumbent_available": feasible,
        "finite_candidate_optimality_status": "not_applicable_greedy_baseline",
        "selected_candidates": sorted(selected, key=lambda item: item["candidate_id"]),
        "served_threats": sorted(
            [item for item in threats if item["threat_id"] in served],
            key=lambda item: item["threat_id"],
        ),
        "selected_arcs": selected_arcs,
        "rejected": rejected,
        "B_validation_status": "PASS" if feasible else "FAIL",
        "result_strength": "verified_feasibility_filtered_greedy_baseline",
        "baseline_order": [
            "reachability_filter",
            "remaining_reaction_time_ascending",
            "threat_level_descending",
            "minimum_required_bombs_ascending",
            "uav_state_and_assignment_scarcity",
        ],
        "global_exchange_performed": False,
    }


def validate_plan(
    scenario: dict[str, Any],
    selected: list[dict[str, Any]],
    network: dict[str, Any],
) -> str:
    return "PASS" if _schedule_feasible(scenario, selected, network)[0] else "FAIL"
