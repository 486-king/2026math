"""Approved Q1-A event-driven continuous-time model.

The structural certificate runs without scenario inputs. Scenario functions
never default missing positions or headings to zero.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import minimize_scalar
from scipy.optimize import brentq

from q1_common import (
    Q1Constants,
    command_release_burst_times,
    smoke_radius,
    structural_bounds,
    unit_vector,
)


@dataclass(frozen=True)
class Scenario:
    ship_initial_position_m: tuple[float, float]
    ship_heading_rad: float
    missile_initial_position_m: tuple[float, float]
    missile_model: str = "G1"
    missile_fixed_heading_rad: float | None = None
    uav_initial_position_m: tuple[float, float] | None = None

    def validate(self) -> None:
        if self.missile_model not in {"G1", "G2", "M1", "M2"}:
            raise ValueError("missile_model must be G1 or G2")
        if self.missile_model in {"G2", "M2"} and self.missile_fixed_heading_rad is None:
            raise ValueError("G2 requires missile_fixed_heading_rad")


def ship_position(t_s: float, scenario: Scenario, cfg: Q1Constants) -> np.ndarray:
    return np.asarray(scenario.ship_initial_position_m, dtype=float) + (
        cfg.ship_speed_mps * t_s * unit_vector(scenario.ship_heading_rad)
    )


def integrate_missile(
    scenario: Scenario,
    cfg: Q1Constants,
    max_time_s: float = 300.0,
):
    """Integrate G1 pure pursuit or G2 fixed-heading flight to target contact."""
    scenario.validate()
    m0 = np.asarray(scenario.missile_initial_position_m, dtype=float)

    def rhs(t_s: float, missile_pos: np.ndarray) -> np.ndarray:
        if scenario.missile_model in {"G1", "M1"}:
            line_of_sight = ship_position(t_s, scenario, cfg) - missile_pos
            distance = np.linalg.norm(line_of_sight)
            if distance <= 1e-12:
                return np.zeros(2)
            direction = line_of_sight / distance
        else:
            direction = unit_vector(float(scenario.missile_fixed_heading_rad))
        return cfg.missile_speed_mps * direction

    def contact_event(t_s: float, missile_pos: np.ndarray) -> float:
        return (
            np.linalg.norm(ship_position(t_s, scenario, cfg) - missile_pos)
            - cfg.ship_radius_m
        )

    contact_event.terminal = True
    contact_event.direction = -1

    solution = solve_ivp(
        rhs,
        (0.0, max_time_s),
        m0,
        events=contact_event,
        dense_output=True,
        rtol=1e-10,
        atol=1e-12,
        max_step=0.05,
    )
    if not solution.success:
        raise RuntimeError(solution.message)
    return solution


def detection_indicator(
    t_s: float,
    missile_position_m: np.ndarray,
    missile_velocity_mps: np.ndarray,
    scenario: Scenario,
    cfg: Q1Constants,
) -> tuple[bool, float, float]:
    target_vector = ship_position(t_s, scenario, cfg) - missile_position_m
    distance = float(np.linalg.norm(target_vector))
    target_direction = target_vector / max(distance, 1e-15)
    velocity_norm = float(np.linalg.norm(missile_velocity_mps))
    velocity_direction = missile_velocity_mps / max(velocity_norm, 1e-15)
    cosine = float(np.clip(np.dot(target_direction, velocity_direction), -1.0, 1.0))
    offset = math.acos(cosine)
    visible = (distance <= cfg.detection_distance_m) and (
        offset <= math.radians(cfg.fov_half_angle_deg)
    )
    return visible, distance, offset


def fixed_smoke_margin(
    t_s: float,
    cloud_center_m: np.ndarray,
    burst_time_s: float,
    scenario: Scenario,
    cfg: Q1Constants,
    drift_velocity_mps: np.ndarray | None = None,
) -> float:
    drift = (
        np.zeros(2, dtype=float)
        if drift_velocity_mps is None
        else np.asarray(drift_velocity_mps, dtype=float)
    )
    age = t_s - burst_time_s
    center = np.asarray(cloud_center_m, dtype=float) + drift * max(age, 0.0)
    return float(
        smoke_radius(age, cfg)
        - cfg.ship_radius_m
        - np.linalg.norm(center - ship_position(t_s, scenario, cfg))
    )


def coverage_intervals(
    window: tuple[float, float],
    cloud_center_m: np.ndarray,
    burst_time_s: float,
    scenario: Scenario,
    cfg: Q1Constants,
    drift_velocity_mps: np.ndarray | None = None,
) -> list[tuple[float, float]]:
    """Find complete-cover intervals by phase events and scalar roots."""
    start, end = window
    if end <= start:
        return []
    events = sorted(
        {
            start,
            end,
            max(start, burst_time_s),
            min(end, burst_time_s + cfg.smoke_constant_duration_s),
            min(
                end,
                burst_time_s
                + cfg.smoke_constant_duration_s
                + cfg.smoke_decay_duration_s,
            ),
        }
    )
    events = [x for x in events if start <= x <= end]
    intervals: list[tuple[float, float]] = []

    margin: Callable[[float], float] = lambda t: fixed_smoke_margin(
        t,
        cloud_center_m,
        burst_time_s,
        scenario,
        cfg,
        drift_velocity_mps,
    )

    for left, right in zip(events[:-1], events[1:]):
        if right - left <= 1e-12:
            continue
        maximum_result = minimize_scalar(
            lambda t: -margin(t),
            bounds=(left, right),
            method="bounded",
            options={"xatol": 1e-12},
        )
        peak_t = float(maximum_result.x)
        peak_margin = margin(peak_t)
        if peak_margin < -1e-9:
            continue

        left_margin = margin(left)
        right_margin = margin(right)
        cover_left = left
        cover_right = right
        if left_margin < 0.0:
            cover_left = brentq(margin, left, peak_t, xtol=1e-12)
        if right_margin < 0.0:
            cover_right = brentq(margin, peak_t, right, xtol=1e-12)
        if cover_right >= cover_left:
            intervals.append((float(cover_left), float(cover_right)))

    merged: list[tuple[float, float]] = []
    for left, right in intervals:
        if merged and left <= merged[-1][1] + 1e-9:
            merged[-1] = (merged[-1][0], max(merged[-1][1], right))
        else:
            merged.append((left, right))
    return merged


def parametric_drop_relation(
    cloud_center_m: tuple[float, float],
    burst_time_s: float,
    bomb_heading_rad: float,
    cfg: Q1Constants,
) -> dict[str, object]:
    """S1 relation; reachability needs a supplied UAV initial position."""
    cloud_center = np.asarray(cloud_center_m, dtype=float)
    inherited_displacement = (
        cfg.bomb_burst_delay_s
        * cfg.uav_speed_mps
        * unit_vector(bomb_heading_rad)
    )
    drop_position = cloud_center - inherited_displacement
    drop_time = burst_time_s - cfg.bomb_burst_delay_s
    command_time = drop_time - cfg.response_delay_s
    timing = command_release_burst_times(command_time, cfg)
    return {
        "cloud_center_m": cloud_center.tolist(),
        "drop_position_m": drop_position.tolist(),
        "drop_time_s": drop_time,
        "command_time_s": command_time,
        "burst_time_s": burst_time_s,
        "inertial_displacement_m": float(np.linalg.norm(inherited_displacement)),
        "timing_chain": {
            "primary_interpretation": "command_to_release_response_delay",
            "t_release_minus_t_command_s": (
                timing["release_time_s"] - timing["command_time_s"]
            ),
            "t_burst_minus_t_release_s": (
                timing["burst_time_s"] - timing["release_time_s"]
            ),
            "t_burst_minus_t_command_s": (
                cfg.response_delay_s + cfg.bomb_burst_delay_s
            ),
            "command_legal_if_task_clock_starts_at_zero": command_time >= 0.0,
        },
        "uav_reachability": "blocked_without_uav_initial_position_and_task_clock",
    }


def structural_main_result(cfg: Q1Constants) -> dict[str, object]:
    bounds = structural_bounds(cfg)
    return {
        "method_id": "A",
        "role": "main_candidate",
        "strict_full_window_feasible": bounds[
            "strict_full_window_feasible_by_duration_necessary_condition"
        ],
        "detection_window_seconds": {
            "lower_bound": bounds["m1_detection_window_lower_bound_s"],
            "upper_bound": bounds["m1_detection_window_upper_bound_s"],
        },
        "maximum_continuous_full_cover_seconds": bounds[
            "stationary_smoke_max_continuous_full_cover_s"
        ],
        "minimum_naked_seconds": {
            "lower_bound": bounds["minimum_naked_time_lower_bound_s"]
        },
        "minimum_cover_margin_m": None,
        "coordinate_solution_status": "blocked_missing_scenario_inputs",
        "missing_inputs": [
            "ship_initial_position_m",
            "ship_heading_rad",
            "missile_initial_position_m",
            "uav_initial_position_m",
            "task_clock_definition",
        ],
        "output_degeneracy": {
            "strict_feasible_set_empty_under_G1_S1_O0_U0_duration_bound": True,
            "unique_coordinate_identifiable": False,
        },
        "assumptions_used": [
            "G1 pure pursuit with lock already acquired at 8000 m",
            "S1 inherited bomb velocity for 3.5 s",
            "stationary smoke center after burst",
            "no wind drift in the nominal model",
            "2 s response delay is interpreted as command-to-release",
        ],
        "proof_notes": bounds["proof_notes"],
    }
