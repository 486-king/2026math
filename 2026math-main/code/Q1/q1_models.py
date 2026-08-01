"""Continuous two-dimensional motion models for the nominal Q1 scope."""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np

from q1_common import D_MAX, FOV_HALF_ANGLE_DEG, R_S, V_M, V_S

Vector = Sequence[float]


def as_vector2(value: Vector) -> np.ndarray:
    array = np.asarray(value, dtype=float)
    if array.shape != (2,):
        raise ValueError("Expected a two-dimensional vector.")
    return array


def unit_vector(value: Vector, *, tolerance: float = 1e-12) -> np.ndarray:
    vector = as_vector2(value)
    norm = float(np.linalg.norm(vector))
    if norm <= tolerance:
        raise ValueError("Direction vector norm is too close to zero.")
    return vector / norm


def ship_position(t: float, s_0: Vector, v_s: Vector, t_0: float) -> np.ndarray:
    velocity = as_vector2(v_s)
    if not math.isclose(float(np.linalg.norm(velocity)), V_S, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError(f"Ship speed must equal {V_S} m/s.")
    return as_vector2(s_0) + velocity * (float(t) - float(t_0))


def g1_missile_derivative(
    t: float,
    missile_position: Vector,
    s_0: Vector,
    v_s: Vector,
    t_0: float,
    *,
    collision_tolerance: float = 1e-9,
) -> np.ndarray:
    target = ship_position(t, s_0, v_s, t_0)
    line_of_sight = target - as_vector2(missile_position)
    distance = float(np.linalg.norm(line_of_sight))
    if distance <= collision_tolerance:
        return np.zeros(2, dtype=float)
    return V_M * line_of_sight / distance


def sight_axis_error_deg(missile_velocity: Vector, target_line_of_sight: Vector) -> float:
    velocity = unit_vector(missile_velocity)
    sight = unit_vector(target_line_of_sight)
    cosine = float(np.clip(np.dot(velocity, sight), -1.0, 1.0))
    return math.degrees(math.acos(cosine))


def g1_axis_error_deg(
    t: float,
    missile_position: Vector,
    s_0: Vector,
    v_s: Vector,
    t_0: float,
) -> float:
    target = ship_position(t, s_0, v_s, t_0)
    line_of_sight = target - as_vector2(missile_position)
    velocity = g1_missile_derivative(t, missile_position, s_0, v_s, t_0)
    if float(np.linalg.norm(velocity)) == 0.0:
        return 0.0
    return sight_axis_error_deg(velocity, line_of_sight)


def detection_active(distance: float, beta_deg: float) -> bool:
    return float(distance) <= D_MAX and abs(float(beta_deg)) <= FOV_HALF_ANGLE_DEG


def worst_case_locked_distance(t_since_lock: float) -> float:
    """Synthetic validation configuration with radial closing speed V_m+V_s."""
    return D_MAX - (V_M + V_S) * float(t_since_lock)


def time_to_effective_radius_worst_case() -> float:
    return (D_MAX - R_S) / (V_M + V_S)
