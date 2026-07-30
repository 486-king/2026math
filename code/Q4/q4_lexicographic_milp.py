"""Lexicographic MILP on the finite Q4 candidate/state-flow network."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import csr_matrix, lil_matrix, vstack


@dataclass
class Model:
    names: list[str]
    index: dict[str, int]
    base_matrix: csr_matrix
    base_lb: np.ndarray
    base_ub: np.ndarray
    candidates: list[dict[str, Any]]
    threats: list[dict[str, Any]]
    arcs: list[dict[str, Any]]
    scenario: dict[str, Any]


def _constraint_row(size: int, coefficients: dict[int, float]) -> dict[int, float]:
    return {index: value for index, value in coefficients.items() if abs(value) > 1e-15}


def build_model(
    scenario: dict[str, Any],
    threats: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    network: dict[str, Any],
) -> Model:
    candidates = sorted(candidates, key=lambda item: item["candidate_id"])
    threats = sorted(threats, key=lambda item: item["threat_id"])
    arcs = sorted(network["arcs"], key=lambda item: item["arc_id"])
    uavs = sorted(scenario["uavs"], key=lambda item: item["uav_id"])
    names = (
        [f"x::{item['candidate_id']}" for item in candidates]
        + [f"y::{item['threat_id']}" for item in threats]
        + [f"u::{item['uav_id']}" for item in uavs]
        + [f"w::{item['arc_id']}" for item in arcs]
    )
    index = {name: position for position, name in enumerate(names)}
    rows: list[dict[int, float]] = []
    lower: list[float] = []
    upper: list[float] = []

    def add(coefficients: dict[int, float], lo: float, hi: float) -> None:
        rows.append(_constraint_row(len(names), coefficients))
        lower.append(lo)
        upper.append(hi)

    # Per-UAV and total inventory.
    for uav in uavs:
        coeff = {}
        for candidate in candidates:
            bombs = candidate["bombs_per_uav"].get(uav["uav_id"], 0)
            if bombs:
                coeff[index[f"x::{candidate['candidate_id']}"]] = float(bombs)
        add(coeff, -np.inf, float(uav["remaining_bombs"]))
    add(
        {
            index[f"x::{candidate['candidate_id']}"]: float(candidate["total_bombs"])
            for candidate in candidates
        },
        -np.inf,
        min(15.0, float(sum(item["remaining_bombs"] for item in uavs))),
    )

    # Full-defence variable equivalence without the erroneous sum(x)<=1 rule.
    for threat in threats:
        covering = [item for item in candidates if threat["threat_id"] in item["covered_threat_ids"]]
        y = index[f"y::{threat['threat_id']}"]
        add(
            {y: 1.0, **{index[f"x::{item['candidate_id']}"]: -1.0 for item in covering}},
            -np.inf,
            0.0,
        )
        for candidate in covering:
            add({y: -1.0, index[f"x::{candidate['candidate_id']}"]: 1.0}, -np.inf, 0.0)

    # Candidate conflicts.
    for first, second in network["candidate_conflicts"]:
        add(
            {index[f"x::{first}"]: 1.0, index[f"x::{second}"]: 1.0},
            -np.inf,
            1.0,
        )

    # State-flow conservation. Each multi-role candidate activates every role
    # node through the same x variable.
    incoming: dict[str, list[dict[str, Any]]] = {}
    outgoing: dict[str, list[dict[str, Any]]] = {}
    for arc in arcs:
        outgoing.setdefault(arc["predecessor_node"], []).append(arc)
        incoming.setdefault(arc["successor_node"], []).append(arc)
    for candidate in candidates:
        x = index[f"x::{candidate['candidate_id']}"]
        for uav_id in candidate["assigned_uavs"]:
            node = f"N::{uav_id}::{candidate['candidate_id']}"
            add(
                {**{index[f"w::{arc['arc_id']}"]: 1.0 for arc in incoming.get(node, [])}, x: -1.0},
                0.0,
                0.0,
            )
            add(
                {**{index[f"w::{arc['arc_id']}"]: 1.0 for arc in outgoing.get(node, [])}, x: -1.0},
                0.0,
                0.0,
            )
    for uav in uavs:
        u = index[f"u::{uav['uav_id']}"]
        source, sink = f"S::{uav['uav_id']}", f"T::{uav['uav_id']}"
        add(
            {**{index[f"w::{arc['arc_id']}"]: 1.0 for arc in outgoing.get(source, [])}, u: -1.0},
            0.0,
            0.0,
        )
        add(
            {**{index[f"w::{arc['arc_id']}"]: 1.0 for arc in incoming.get(sink, [])}, u: -1.0},
            0.0,
            0.0,
        )

    for arc_id, candidate_id in network["arc_candidate_conflicts"]:
        add(
            {index[f"w::{arc_id}"]: 1.0, index[f"x::{candidate_id}"]: 1.0},
            -np.inf,
            1.0,
        )
    for first, second in network["arc_arc_conflicts"]:
        add(
            {index[f"w::{first}"]: 1.0, index[f"w::{second}"]: 1.0},
            -np.inf,
            1.0,
        )

    matrix = lil_matrix((len(rows), len(names)), dtype=float)
    for row_index, row in enumerate(rows):
        for column, value in row.items():
            matrix[row_index, column] = value
    return Model(
        names=names,
        index=index,
        base_matrix=matrix.tocsr(),
        base_lb=np.asarray(lower, dtype=float),
        base_ub=np.asarray(upper, dtype=float),
        candidates=candidates,
        threats=threats,
        arcs=arcs,
        scenario=scenario,
    )


def _vector(model: Model, values: dict[str, float]) -> np.ndarray:
    result = np.zeros(len(model.names), dtype=float)
    for name, value in values.items():
        result[model.index[name]] = value
    return result


def _stage_specs(model: Model, endpoint: str) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    now = float(model.scenario["current_time_s"])
    for level in (3, 2, 1):
        level_threats = [item for item in model.threats if item["threat_level"] == level]
        specs.append(
            {
                "stage_name": f"maximize_full_defence_level_{level}",
                "sense": "maximize",
                "definition": f"sum y_m for threat_level={level}",
                "objective": _vector(
                    model, {f"y::{item['threat_id']}": 1.0 for item in level_threats}
                ),
            }
        )
        latest_by_threat = {}
        for threat in level_threats:
            command_times = [
                min(min(role["command_times_s"]) for role in candidate["absolute_roles"])
                for candidate in model.candidates
                if threat["threat_id"] in candidate["covered_threat_ids"]
            ]
            latest_by_threat[threat["threat_id"]] = (max(command_times) - now) if command_times else 1e6
        specs.append(
            {
                "stage_name": f"minimize_served_reaction_time_level_{level}",
                "sense": "minimize",
                "definition": "sum y_m*(latest_feasible_command_time-current_time)",
                "objective": _vector(
                    model,
                    {
                        f"y::{item['threat_id']}": latest_by_threat[item["threat_id"]]
                        for item in level_threats
                    },
                ),
            }
        )
    for level in (3, 2, 1):
        level_threats = [item for item in model.threats if item["threat_level"] == level]
        # Minimize unserved duration == maximize served duration; report the
        # unserved value by adding the constant after solution.
        specs.append(
            {
                "stage_name": f"minimize_unserved_remaining_window_level_{level}",
                "sense": "maximize",
                "definition": "served-duration equivalent of lexicographic unserved-window minimization",
                "objective": _vector(
                    model,
                    {
                        f"y::{item['threat_id']}": max(
                            0.0,
                            float(item["defence_window_end_s"])
                            - max(now, float(item["defence_window_start_s"])),
                        )
                        for item in level_threats
                    },
                ),
            }
        )
    specs.append(
        {
            "stage_name": "minimize_bombs_used_and_reserved",
            "sense": "minimize",
            "definition": "sum candidate total bombs",
            "objective": _vector(
                model,
                {
                    f"x::{item['candidate_id']}": float(item["total_bombs"])
                    for item in model.candidates
                },
            ),
        }
    )
    path = _vector(
        model,
        {
            **{
                f"x::{item['candidate_id']}": float(item["intrinsic_service_path_length_m"])
                for item in model.candidates
            },
            **{
                f"w::{item['arc_id']}": float(item["transition_distance_m"])
                for item in model.arcs
            },
        },
    )
    turn = _vector(
        model,
        {
            **{
                f"x::{item['candidate_id']}": float(item["intrinsic_turn_proxy_rad"])
                for item in model.candidates
            },
            **{
                f"w::{item['arc_id']}": float(item["transition_turn_proxy_rad"])
                for item in model.arcs
            },
        },
    )
    if endpoint == "L":
        specs.extend(
            [
                {"stage_name": "L_minimize_total_path", "sense": "minimize", "definition": "service plus selected transition path", "objective": path},
                {"stage_name": "L_minimize_turn_at_minimum_path", "sense": "minimize", "definition": "service plus transition turn proxy", "objective": turn},
            ]
        )
    else:
        specs.extend(
            [
                {"stage_name": "T_minimize_total_turn", "sense": "minimize", "definition": "service plus selected transition turn proxy", "objective": turn},
                {"stage_name": "T_minimize_path_at_minimum_turn", "sense": "minimize", "definition": "service plus selected transition path", "objective": path},
            ]
        )
    specs.append(
        {
            "stage_name": "minimize_flexible_plan_changes",
            "sense": "minimize",
            "definition": "explicit new-instance count; executed and committed instances are outside the flexible set",
            "objective": _vector(
                model, {f"x::{item['candidate_id']}": 1.0 for item in model.candidates}
            ),
        }
    )
    return specs


def _extract_solution(model: Model, vector: np.ndarray) -> dict[str, Any]:
    chosen = {model.names[index] for index, value in enumerate(vector) if value > 0.5}
    candidates = [item for item in model.candidates if f"x::{item['candidate_id']}" in chosen]
    threats = [item for item in model.threats if f"y::{item['threat_id']}" in chosen]
    arcs = [item for item in model.arcs if f"w::{item['arc_id']}" in chosen]
    return {
        "selected_candidates": candidates,
        "served_threats": threats,
        "selected_arcs": arcs,
    }


def solve_lexicographic(
    model: Model,
    endpoint: str,
    time_limit_s: float,
    rolling_event_id: str,
    forced_no_incumbent_timeout: bool = False,
) -> dict[str, Any]:
    if forced_no_incumbent_timeout:
        return {
            "solver_status": "time_limit_no_incumbent_forced_test",
            "feasible_incumbent_available": False,
            "finite_candidate_optimality_status": "not_proved_no_incumbent",
            "last_completed_stage": None,
            "stage_log": [],
            "selected_candidates": [],
            "served_threats": [],
            "selected_arcs": [],
            "incumbent_vector_available": False,
            "incumbent_integrality_status": "FAIL",
        }
    locks: list[tuple[np.ndarray, float, float]] = []
    stage_log = []
    solution: np.ndarray | None = None
    last_completed = None
    for stage_id, spec in enumerate(_stage_specs(model, endpoint), start=1):
        matrices = [model.base_matrix]
        lbs = [model.base_lb]
        ubs = [model.base_ub]
        if locks:
            lock_matrix = np.vstack([item[0] for item in locks])
            matrices.append(csr_matrix(lock_matrix))
            lbs.append(np.asarray([item[1] for item in locks]))
            ubs.append(np.asarray([item[2] for item in locks]))
        matrix = vstack(matrices, format="csr")
        constraint = LinearConstraint(matrix, np.concatenate(lbs), np.concatenate(ubs))
        raw_objective = spec["objective"]
        c = -raw_objective if spec["sense"] == "maximize" else raw_objective
        result = milp(
            c,
            integrality=np.ones(len(model.names), dtype=int),
            bounds=Bounds(np.zeros(len(model.names)), np.ones(len(model.names))),
            constraints=constraint,
            options={"time_limit": max(float(time_limit_s), 1e-9), "disp": False},
        )
        incumbent = result.x is not None and np.all(np.isfinite(result.x))
        if incumbent:
            solution = result.x
        status = {0: "optimal", 1: "time_limit_or_iteration_limit", 2: "infeasible", 3: "unbounded", 4: "solver_error"}.get(result.status, f"status_{result.status}")
        extracted = _extract_solution(model, solution) if solution is not None else {
            "selected_candidates": [],
            "served_threats": [],
            "selected_arcs": [],
        }
        value = float(np.dot(raw_objective, solution)) if solution is not None else None
        if result.status == 0 and value is not None:
            tolerance = max(1e-7, abs(value) * 1e-8)
            locks.append((raw_objective.copy(), value - tolerance, value + tolerance))
            last_completed = spec["stage_name"]
        stage_log.append(
            {
                "rolling_event_id": rolling_event_id,
                "endpoint_id": endpoint,
                "stage_id": stage_id,
                "stage_name": spec["stage_name"],
                "objective_sense": spec["sense"],
                "objective_definition": spec["definition"],
                "solver_status": status,
                "feasible_incumbent_available": bool(incumbent),
                "optimal_value": value if result.status == 0 else None,
                "mip_gap": float(result.mip_gap) if getattr(result, "mip_gap", None) is not None else None,
                "time_limit_s": float(time_limit_s),
                "runtime_s": None,
                "locked_constraint": (
                    {"value": value, "absolute_tolerance": max(1e-7, abs(value) * 1e-8)}
                    if result.status == 0 and value is not None
                    else None
                ),
                "selected_candidate_ids": [item["candidate_id"] for item in extracted["selected_candidates"]],
                "selected_arc_ids": [item["arc_id"] for item in extracted["selected_arcs"]],
                "served_threat_ids": [item["threat_id"] for item in extracted["served_threats"]],
                "resource_usage": sum(item["total_bombs"] for item in extracted["selected_candidates"]),
            }
        )
        if result.status != 0:
            break
    if solution is None:
        return {
            "solver_status": stage_log[-1]["solver_status"] if stage_log else "no_run",
            "feasible_incumbent_available": False,
            "finite_candidate_optimality_status": "not_proved_no_incumbent",
            "last_completed_stage": last_completed,
            "stage_log": stage_log,
            "selected_candidates": [],
            "served_threats": [],
            "selected_arcs": [],
            "incumbent_vector_available": False,
            "incumbent_integrality_status": "FAIL",
        }
    extracted = _extract_solution(model, solution)
    all_optimal = len(stage_log) == len(_stage_specs(model, endpoint)) and all(
        item["solver_status"] == "optimal" for item in stage_log
    )
    return {
        "solver_status": "optimal" if all_optimal else "feasible_incumbent_time_limited",
        "feasible_incumbent_available": True,
        "finite_candidate_optimality_status": (
            "proved_within_current_finite_network"
            if all_optimal
            else "not_proved_due_to_timeout"
        ),
        "last_completed_stage": last_completed,
        "incumbent_vector_available": True,
        "incumbent_integrality_status": (
            "PASS"
            if float(np.max(np.abs(solution - np.rint(solution)))) <= 1e-6
            else "FAIL"
        ),
        "stage_log": stage_log,
        **extracted,
    }
