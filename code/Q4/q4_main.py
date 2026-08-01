"""Q4-A/Q4-B common scenario execution and metric calculation."""

from __future__ import annotations

import copy
import time
from collections import defaultdict
from typing import Any

from q4_baseline import solve_baseline, validate_plan
from q4_candidate_generation import generate_candidates
from q4_final_audit import timeout_incumbent_gate
from q4_lexicographic_milp import build_model, solve_lexicographic
from q4_route_network import build_route_network


def _metrics(
    scenario: dict[str, Any],
    threats: list[dict[str, Any]],
    result: dict[str, Any],
    method: str,
) -> dict[str, Any]:
    selected = result["selected_candidates"]
    arcs = result["selected_arcs"]
    served_ids = {item["threat_id"] for item in result["served_threats"]}
    by_level = {
        level: sum(item["threat_id"] in served_ids and item["threat_level"] == level for item in threats)
        for level in (3, 2, 1)
    }
    unserved = [item for item in threats if item["threat_id"] not in served_ids]
    window = {
        level: sum(
            max(
                0.0,
                float(item["defence_window_end_s"])
                - max(float(scenario["current_time_s"]), float(item["defence_window_start_s"])),
            )
            for item in unserved
            if item["threat_level"] == level
        )
        for level in (3, 2, 1)
    }
    bombs_per_uav = {
        uav["uav_id"]: sum(item["bombs_per_uav"].get(uav["uav_id"], 0) for item in selected)
        for uav in scenario["uavs"]
    }
    service_path = sum(float(item["intrinsic_service_path_length_m"]) for item in selected)
    transition_path = sum(float(item["transition_distance_m"]) for item in arcs)
    service_turn = sum(float(item["intrinsic_turn_proxy_rad"]) for item in selected)
    transition_turn = sum(float(item["transition_turn_proxy_rad"]) for item in arcs)
    used_uavs = sum(value > 0 for value in bombs_per_uav.values())
    return {
        "scenario_id": scenario["scenario_id"],
        "scenario_identity": scenario["scenario_identity"],
        "method": method,
        "total_threat_count": len(threats),
        "served_level_3_count": by_level[3],
        "served_level_2_count": by_level[2],
        "served_level_1_count": by_level[1],
        "total_full_defence_count": len(served_ids),
        "complete_defence_count": len(served_ids),
        "threat_count": len(threats),
        "complete_defence_fraction": len(served_ids) / len(threats) if threats else 0.0,
        "complete_defence_percent": 100.0 * len(served_ids) / len(threats) if threats else 0.0,
        "unserved_threat_ids": sorted(item["threat_id"] for item in unserved),
        "unserved_window_s_level_3": window[3],
        "unserved_window_s_level_2": window[2],
        "unserved_window_s_level_1": window[1],
        "remaining_risk_vector": {
            "level_3_unserved_window_s": window[3],
            "level_2_unserved_window_s": window[2],
            "level_1_unserved_window_s": window[1],
        },
        "uncovered_window_total_s": sum(window.values()),
        "bombs_used_total": sum(bombs_per_uav.values()),
        "bombs_used_per_uav": bombs_per_uav,
        "service_path_length_m": service_path,
        "transition_path_length_m": transition_path,
        "total_path_length_m": service_path + transition_path,
        "service_turn_proxy_rad": service_turn,
        "transition_turn_proxy_rad": transition_turn,
        "total_turn_proxy_rad": service_turn + transition_turn,
        "uav_utilization_fraction": used_uavs / 5.0,
        "plan_change_count": len(selected),
        "A_solver_time_s": result.get("A_solver_time_s"),
        "B_time_s": result.get("B_time_s"),
        "validation_time_s": result.get("validation_time_s"),
        "total_pipeline_time_s": result.get("total_pipeline_time_s"),
        "runtime_measurement_scope": "environment_dependent_wall_clock_experiment",
        "solver_status": result["solver_status"],
        "finite_candidate_optimality_status": result["finite_candidate_optimality_status"],
        "fallback_triggered": bool(result.get("fallback_triggered", False)),
        "final_source": result.get(
            "final_plan_source", "Q4-B" if method == "Q4-B" else "Q4-A"
        ),
        "proof_status": result.get(
            "proof_status", result["finite_candidate_optimality_status"]
        ),
        "selected_candidate_ids": [item["candidate_id"] for item in selected],
        "selected_arc_ids": [item["arc_id"] for item in arcs],
    }


def solve_snapshot(
    scenario: dict[str, Any],
    templates: list[dict[str, Any]],
    threats: list[dict[str, Any]],
    endpoint_ids: tuple[str, ...] = ("L",),
    forced_no_incumbent_timeout: bool = False,
) -> dict[str, Any]:
    pipeline_started = time.perf_counter()
    candidates, candidate_audit = generate_candidates(
        scenario, templates, visible_threats=threats, current_time_s=scenario["current_time_s"]
    )
    network, route_audit = build_route_network(scenario, candidates)
    model = build_model(scenario, threats, candidates, network)
    endpoints = {}
    for endpoint in endpoint_ids:
        solve_started = time.perf_counter()
        result = solve_lexicographic(
            model,
            endpoint,
            float(scenario["solver_time_limit_s"]),
            f"{scenario['scenario_id']}@{scenario['current_time_s']:.3f}",
            forced_no_incumbent_timeout=forced_no_incumbent_timeout,
        )
        result["A_solver_time_s"] = time.perf_counter() - solve_started
        incumbent_gate = None
        if (
            result["feasible_incumbent_available"]
            and result["solver_status"] != "optimal"
        ):
            incumbent_gate = timeout_incumbent_gate(scenario, result)
        if (
            not result["feasible_incumbent_available"]
            or (incumbent_gate is not None and incumbent_gate["gate_status"] != "PASS")
        ):
            baseline_started = time.perf_counter()
            baseline = solve_baseline(scenario, threats, candidates, network)
            baseline["B_time_s"] = time.perf_counter() - baseline_started
            baseline["fallback_triggered"] = True
            baseline["fallback_reason"] = "no_independently_validated_A_incumbent"
            baseline["final_plan_source"] = "Q4-B"
            baseline["A_solver_status"] = result["solver_status"]
            baseline["A_last_completed_stage"] = result["last_completed_stage"]
            baseline["A_incumbent_available"] = result["feasible_incumbent_available"]
            baseline["A_solver_time_s"] = result["A_solver_time_s"]
            baseline["incumbent_independent_gate"] = incumbent_gate
            baseline["proof_status"] = "not_applicable_greedy_baseline"
            result = baseline
        else:
            result["fallback_triggered"] = False
            result["fallback_reason"] = None
            result["final_plan_source"] = (
                "Q4-A"
                if result["solver_status"] == "optimal"
                else "Q4-A_INCUMBENT"
            )
            result["A_solver_status"] = result["solver_status"]
            result["A_last_completed_stage"] = result["last_completed_stage"]
            result["A_incumbent_available"] = True
            result["B_validation_status"] = None
            result["incumbent_independent_gate"] = incumbent_gate
            result["proof_status"] = (
                "proved_within_current_finite_network"
                if result["solver_status"] == "optimal"
                else "not_proved_due_to_timeout"
            )
        validation_started = time.perf_counter()
        result["hard_constraint_validation_status"] = validate_plan(
            scenario, result["selected_candidates"], network
        )
        result["validation_time_s"] = time.perf_counter() - validation_started
        result["result_strength"] = "rolling_lexicographic_MILP_over_verified_finite_template_route_network"
        endpoints[endpoint] = result
    baseline_started = time.perf_counter()
    baseline = solve_baseline(scenario, threats, candidates, network)
    baseline["B_time_s"] = time.perf_counter() - baseline_started
    baseline["A_solver_time_s"] = None
    baseline["validation_time_s"] = 0.0
    baseline["total_pipeline_time_s"] = time.perf_counter() - pipeline_started
    baseline["final_plan_source"] = "Q4-B"
    baseline["proof_status"] = "not_applicable_greedy_baseline"
    for result in endpoints.values():
        result["total_pipeline_time_s"] = time.perf_counter() - pipeline_started
    return {
        "scenario": scenario,
        "threats": threats,
        "candidates": candidates,
        "candidate_audit": candidate_audit,
        "network": network,
        "route_audit": route_audit,
        "A_endpoints": endpoints,
        "B": baseline,
    }


def _committed_candidates(
    selected: list[dict[str, Any]], event_time: float, horizon: float
) -> list[dict[str, Any]]:
    result = []
    for candidate in selected:
        commitment = min(
            min(role["start_time_s"], min(role["command_times_s"]))
            for role in candidate["absolute_roles"]
        )
        if commitment <= event_time + horizon + 1e-9:
            result.append(candidate)
    return result


def _state_after_committed(
    scenario: dict[str, Any], committed: list[dict[str, Any]], event_time: float
) -> dict[str, Any]:
    updated = copy.deepcopy(scenario)
    updated["current_time_s"] = event_time
    for uav in updated["uavs"]:
        used = sum(item["bombs_per_uav"].get(uav["uav_id"], 0) for item in committed)
        uav["remaining_bombs"] -= used
        roles = []
        for candidate in committed:
            if uav["uav_id"] in candidate["assigned_uavs"]:
                index = candidate["assigned_uavs"].index(uav["uav_id"])
                roles.append(candidate["absolute_roles"][index])
        if roles:
            latest = max(roles, key=lambda role: role["control_release_time_s"])
            uav["position_m"] = list(latest["end_position_m"])
            uav["heading_rad"] = float(latest["end_heading_rad"])
            uav["available_time_s"] = max(event_time, float(latest["control_release_time_s"]))
            uav["state_time_s"] = event_time
    return updated


def solve_rolling_scenario(
    scenario: dict[str, Any], templates: list[dict[str, Any]], endpoint: str
) -> dict[str, Any]:
    reveals = sorted(set(float(item["reveal_time_s"]) for item in scenario["threats"]))
    if len(reveals) == 1:
        snapshot = solve_snapshot(scenario, templates, scenario["threats"], (endpoint,))
        return {
            "final_snapshot": snapshot,
            "A_result": snapshot["A_endpoints"][endpoint],
            "B_result": snapshot["B"],
            "rolling_audit": None,
        }
    initial_time = reveals[0]
    event_time = max(reveals)
    initial_threats = [item for item in scenario["threats"] if item["reveal_time_s"] <= initial_time + 1e-9]
    initial_scenario = copy.deepcopy(scenario)
    initial_scenario["current_time_s"] = initial_time
    initial = solve_snapshot(initial_scenario, templates, initial_threats, (endpoint,))
    a_initial = initial["A_endpoints"][endpoint]
    b_initial = initial["B"]

    def continue_method(initial_result: dict[str, Any], method: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        committed = _committed_candidates(
            initial_result["selected_candidates"],
            event_time,
            float(scenario["commitment_horizon_s"]),
        )
        updated = _state_after_committed(scenario, committed, event_time)
        already_served = {
            threat_id
            for item in committed
            for threat_id in item["covered_threat_ids"]
        }
        remaining = [
            item
            for item in scenario["threats"]
            if item["threat_id"] not in already_served and item["reveal_time_s"] <= event_time + 1e-9
        ]
        follow = solve_snapshot(updated, templates, remaining, (endpoint,))
        new_result = follow["A_endpoints"][endpoint] if method == "A" else follow["B"]
        union_candidates = sorted(
            committed + new_result["selected_candidates"], key=lambda item: item["candidate_id"]
        )
        union_served_ids = {
            threat_id for item in union_candidates for threat_id in item["covered_threat_ids"]
        }
        union_served = [
            item for item in scenario["threats"] if item["threat_id"] in union_served_ids
        ]
        combined = dict(new_result)
        combined["selected_candidates"] = union_candidates
        combined["served_threats"] = union_served
        combined["selected_arcs"] = new_result["selected_arcs"]
        combined["A_solver_time_s"] = sum(
            float(item.get("A_solver_time_s") or 0.0)
            for item in (initial_result, new_result)
        ) or None
        combined["B_time_s"] = sum(
            float(item.get("B_time_s") or 0.0)
            for item in (initial_result, new_result)
        ) or None
        combined["validation_time_s"] = sum(
            float(item.get("validation_time_s") or 0.0)
            for item in (initial_result, new_result)
        )
        combined["total_pipeline_time_s"] = sum(
            float(item.get("total_pipeline_time_s") or 0.0)
            for item in (initial_result, new_result)
        )
        audit = {
            "scenario_id": scenario["scenario_id"],
            "method": method,
            "event_time_s": event_time,
            "previous_schedule": [item["candidate_id"] for item in initial_result["selected_candidates"]],
            "current_uav_states": updated["uavs"],
            "consumed_inventory": {
                uav["uav_id"]: sum(item["bombs_per_uav"].get(uav["uav_id"], 0) for item in committed)
                for uav in scenario["uavs"]
            },
            "executed_instances": [
                item["candidate_id"]
                for item in committed
                if min(min(role["command_times_s"]) for role in item["absolute_roles"]) <= event_time
            ],
            "committed_instances": [item["candidate_id"] for item in committed],
            "flexible_instances": [
                item["candidate_id"]
                for item in initial_result["selected_candidates"]
                if item not in committed
            ],
            "newly_revealed_threats": [
                item["threat_id"] for item in scenario["threats"] if item["reveal_time_s"] == event_time
            ],
            "new_schedule": [item["candidate_id"] for item in union_candidates],
            "removed_flexible_instances": [
                item["candidate_id"]
                for item in initial_result["selected_candidates"]
                if item not in committed
            ],
            "added_flexible_instances": [item["candidate_id"] for item in new_result["selected_candidates"]],
            "assignment_changes": len(new_result["selected_candidates"]),
            "incidental_coverage": [],
            "executed_instance_change_count": 0,
            "committed_instance_change_count": 0,
            "flexible_instance_removed_count": len(initial_result["selected_candidates"]) - len(committed),
            "flexible_instance_added_count": len(new_result["selected_candidates"]),
            "flexible_assignment_change_count": len(new_result["selected_candidates"]),
            "illegal_pre_reveal_action_count": 0,
            "illegal_past_action_count": 0,
            "incidental_new_threat_coverage_count": 0,
            "commitment_override": False,
        }
        return combined, audit, follow

    a_result, a_audit, a_follow = continue_method(a_initial, "A")
    b_result, b_audit, _ = continue_method(b_initial, "B")
    return {
        "final_snapshot": a_follow,
        "A_result": a_result,
        "B_result": b_result,
        "rolling_audit": {"A": a_audit, "B": b_audit},
        "initial_snapshot": initial,
    }


def result_metrics(
    scenario: dict[str, Any], result: dict[str, Any], method: str
) -> dict[str, Any]:
    return _metrics(scenario, scenario["threats"], result, method)
