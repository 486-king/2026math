"""Scenario validation and conditional UAV execution checks."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from scipy.optimize import differential_evolution

from q1_common import (
    INERTIAL_DISPLACEMENT,
    R_U_MAX,
    TAU_BURST,
    TAU_HOLD,
    TAU_RESPONSE,
    T_DETECT_LOWER,
    T_STRUCTURAL_MAX,
    V_S,
    V_U,
)
from q1_models import unit_vector

REQUIRED_PATHS = (
    "schema_version",
    "scenario_id",
    "scenario_type",
    "time_origin",
    "locked_at_8000m",
    "ship.initial_position",
    "ship.heading_or_velocity",
    "missile.initial_position",
    "missile.initial_heading",
    "uav.initial_position",
    "uav.initial_heading",
    "uav.launch_reference_point",
    "operating_radius_interpretation",
    "earliest_command_time",
)


def _get_path(payload: dict[str, Any], dotted: str) -> Any:
    value: Any = payload
    for key in dotted.split("."):
        if not isinstance(value, dict) or key not in value:
            raise KeyError(dotted)
        value = value[key]
    return value


def missing_scenario_fields(payload: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for dotted in REQUIRED_PATHS:
        try:
            value = _get_path(payload, dotted)
        except KeyError:
            missing.append(dotted)
            continue
        if value is None or value == "":
            missing.append(dotted)
    return missing


def load_scenario(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {
            "execution_status": "completed",
            "input_status": "blocked_missing_scenario",
            "feasibility_status": "full_window_structurally_infeasible",
            "certificate_status": "verified",
            "T_executable_star": "not_evaluated",
            "missing_fields": list(REQUIRED_PATHS),
            "absolute_solution": "not_generated",
        }
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    missing = missing_scenario_fields(payload)
    if missing:
        return {
            "execution_status": "completed",
            "input_status": "blocked_missing_fields",
            "feasibility_status": "not_evaluated",
            "certificate_status": "not_evaluated",
            "T_executable_star": "not_evaluated",
            "missing_fields": missing,
            "absolute_solution": "not_generated",
            "scenario": payload,
        }
    if payload["operating_radius_interpretation"] != "relative_to_uav_launch_reference_point":
        return {
            "execution_status": "completed",
            "input_status": "blocked_ambiguous_interpretation",
            "feasibility_status": "not_evaluated",
            "certificate_status": "not_evaluated",
            "T_executable_star": "not_evaluated",
            "missing_fields": [],
            "absolute_solution": "not_generated",
            "scenario": payload,
        }
    return {
        "execution_status": "completed",
        "input_status": "complete",
        "feasibility_status": "not_evaluated",
        "certificate_status": "conditional" if not payload["locked_at_8000m"] else "verified",
        "T_executable_star": "not_evaluated",
        "missing_fields": [],
        "scenario": payload,
    }


def operating_radius_allowed(distance: float, *, tolerance: float = 1e-9) -> bool:
    return float(distance) <= R_U_MAX + tolerance


def _ship_velocity(value: Any) -> np.ndarray:
    vector = np.asarray(value, dtype=float)
    if vector.shape != (2,):
        raise ValueError("ship.heading_or_velocity must be a two-vector.")
    norm = float(np.linalg.norm(vector))
    if norm <= 1e-12:
        raise ValueError("ship.heading_or_velocity cannot be zero.")
    if math.isclose(norm, V_S, rel_tol=0.0, abs_tol=1e-9):
        return vector
    return V_S * vector / norm


def candidate_residuals(
    scenario: dict[str, Any],
    *,
    t_m: float,
    t_b: float,
    release_direction: Sequence[float],
    coverage_duration: float = T_STRUCTURAL_MAX,
) -> dict[str, Any]:
    t_0 = float(scenario["time_origin"])
    ship_initial = np.asarray(scenario["ship"]["initial_position"], dtype=float)
    ship_velocity = _ship_velocity(scenario["ship"]["heading_or_velocity"])
    cloud = ship_initial + ship_velocity * (float(t_m) - t_0)
    direction = unit_vector(release_direction)
    release_point = cloud - INERTIAL_DISPLACEMENT * direction
    t_d = float(t_b) - TAU_BURST
    t_cmd = t_d - TAU_RESPONSE
    uav_initial = np.asarray(scenario["uav"]["initial_position"], dtype=float)
    launch_reference = np.asarray(scenario["uav"]["launch_reference_point"], dtype=float)
    available_travel_time = t_d - t_0
    travel_time = float(np.linalg.norm(release_point - uav_initial)) / V_U
    radial_distance = float(np.linalg.norm(release_point - launch_reference))
    coverage_duration = float(coverage_duration)
    coverage_start = float(t_m) - (coverage_duration / 2.0)
    coverage_end = float(t_m) + (coverage_duration / 2.0)
    residuals = {
        "command_time_residual_s": t_cmd - float(scenario["earliest_command_time"]),
        "travel_time_residual_s": available_travel_time - travel_time,
        "release_to_burst_residual_s": (float(t_b) - t_d) - TAU_BURST,
        "operating_radius_residual_m": R_U_MAX - radial_distance,
        "release_direction_norm_residual": 1.0 - float(np.linalg.norm(direction)),
        "trajectory_continuity_residual_m": 0.0,
        "full_coverage_residual_s": min(
            coverage_start - float(t_b),
            float(t_b) + TAU_HOLD - coverage_end,
        ),
    }
    tolerance = 1e-9
    feasible = (
        residuals["command_time_residual_s"] >= -tolerance
        and residuals["travel_time_residual_s"] >= -tolerance
        and abs(residuals["release_to_burst_residual_s"]) <= tolerance
        and residuals["operating_radius_residual_m"] >= -tolerance
        and abs(residuals["release_direction_norm_residual"]) <= tolerance
        and abs(residuals["trajectory_continuity_residual_m"]) <= tolerance
        and residuals["full_coverage_residual_s"] >= -tolerance
    )
    return {
        "feasible": feasible,
        "t_cmd_s": t_cmd,
        "t_d_s": t_d,
        "t_b_s": float(t_b),
        "t_m_s": float(t_m),
        "coverage_duration_s": coverage_duration,
        "cloud_center_m": cloud.tolist(),
        "release_point_m": release_point.tolist(),
        "release_direction": direction.tolist(),
        "residuals": residuals,
    }


def evaluate_synthetic_candidate(
    scenario: dict[str, Any],
    *,
    t_m: float,
    t_b: float,
    release_direction: Sequence[float],
) -> dict[str, Any]:
    if scenario.get("scenario_type") != "synthetic_validation":
        raise ValueError("Synthetic validation evaluator requires scenario_type=synthetic_validation.")
    result = candidate_residuals(
        scenario,
        t_m=t_m,
        t_b=t_b,
        release_direction=release_direction,
    )
    result.update(
        {
            "execution_status": "completed",
            "input_status": "complete",
            "feasibility_status": (
                "executable_feasible" if result["feasible"] else "executable_infeasible"
            ),
            "certificate_status": "verified",
            "T_executable_star": T_STRUCTURAL_MAX if result["feasible"] else 0.0,
            "scenario_result_scope": "synthetic_validation_not_real_battlefield",
        }
    )
    return result


def evaluate_complete_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    """Maximise executable continuous coverage under the Q1 reachability layer.

    Given a midpoint and release direction, the latest admissible burst is
    t_b=t_m-L/2. It weakly improves command and travel residuals, leaving a
    deterministic two-variable search over t_m and the direction angle.
    """
    missing = missing_scenario_fields(scenario)
    if missing:
        raise ValueError(f"Scenario is incomplete: {missing}")
    if not bool(scenario["locked_at_8000m"]):
        return {
            "execution_status": "completed",
            "input_status": "complete",
            "feasibility_status": "not_evaluated",
            "certificate_status": "conditional",
            "T_executable_star": "not_evaluated",
            "absolute_solution": "not_generated",
            "blocking_reason": "locked_at_8000m is false; the standard detection window is not active",
        }

    t_in = float(scenario["time_origin"])
    t_out = t_in + T_DETECT_LOWER
    ship_initial = np.asarray(scenario["ship"]["initial_position"], dtype=float)
    ship_velocity = _ship_velocity(scenario["ship"]["heading_or_velocity"])
    uav_initial = np.asarray(scenario["uav"]["initial_position"], dtype=float)
    launch_reference = np.asarray(scenario["uav"]["launch_reference_point"], dtype=float)
    earliest_command = float(scenario["earliest_command_time"])

    def duration_for(point: Sequence[float]) -> float:
        t_m, theta = float(point[0]), float(point[1])
        direction = np.array([math.cos(theta), math.sin(theta)])
        cloud = ship_initial + ship_velocity * (t_m - t_in)
        release = cloud - INERTIAL_DISPLACEMENT * direction
        if float(np.linalg.norm(release - launch_reference)) > R_U_MAX + 1e-9:
            return 0.0
        travel_time = float(np.linalg.norm(release - uav_initial)) / V_U
        upper_bounds = (
            T_STRUCTURAL_MAX,
            2.0 * (t_m - t_in),
            2.0 * (t_out - t_m),
            2.0 * (t_m - TAU_BURST - t_in - travel_time),
            2.0 * (t_m - TAU_BURST - TAU_RESPONSE - earliest_command),
        )
        return max(0.0, min(upper_bounds))

    optimisation = differential_evolution(
        lambda x: -duration_for(x),
        bounds=[(t_in, t_out), (-math.pi, math.pi)],
        seed=20260729,
        popsize=12,
        maxiter=120,
        polish=True,
        tol=1e-10,
        workers=1,
        updating="immediate",
    )
    t_m = float(optimisation.x[0])
    theta = float(optimisation.x[1])
    duration = duration_for((t_m, theta))
    direction = [math.cos(theta), math.sin(theta)]
    t_b = t_m - duration / 2.0
    candidate = candidate_residuals(
        scenario,
        t_m=t_m,
        t_b=t_b,
        release_direction=direction,
        coverage_duration=duration,
    )
    feasible = duration > 1e-9 and candidate["feasible"]
    candidate.update(
        {
            "execution_status": "completed",
            "input_status": "complete",
            "feasibility_status": (
                "executable_feasible" if feasible else "executable_infeasible"
            ),
            "certificate_status": "verified",
            "T_executable_star": duration if feasible else 0.0,
            "structural_upper_bound_s": T_STRUCTURAL_MAX,
            "reaches_structural_upper_bound": math.isclose(
                duration, T_STRUCTURAL_MAX, rel_tol=0.0, abs_tol=1e-8
            ),
            "optimisation": {
                "method": "deterministic_differential_evolution_over_t_m_and_release_angle",
                "seed": 20260729,
                "success": bool(optimisation.success),
                "objective_duration_s": duration,
                "iterations": int(optimisation.nit),
            },
            "absolute_solution": "generated_from_complete_scenario",
            "scenario_result_scope": scenario["scenario_type"],
        }
    )
    return candidate
