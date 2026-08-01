"""Explicitly separated G2/S2 boundary-validation utilities."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import numpy as np
from scipy.optimize import brentq

from q1_common import R_S, T_STRUCTURAL_MAX


def g2_necessary_duration_check(
    detection_duration: float,
    *,
    uav_reachable: bool,
) -> dict[str, Any]:
    duration_condition = float(detection_duration) <= T_STRUCTURAL_MAX
    executable = duration_condition and bool(uav_reachable)
    return {
        "model": "G2_fixed_heading_boundary_validation",
        "scenario_type": "synthetic_validation",
        "duration_necessary_condition": duration_condition,
        "uav_reachable": bool(uav_reachable),
        "feasibility_status": "executable_feasible" if executable else "executable_infeasible",
        "warning": "A short detection window is necessary, not sufficient.",
    }


def s2_margin(
    t: float,
    ship_position_fn: Callable[[float], Sequence[float]],
    cloud_position_fn: Callable[[float], Sequence[float]],
    smoke_radius_fn: Callable[[float], float],
) -> float:
    ship = np.asarray(ship_position_fn(float(t)), dtype=float)
    cloud = np.asarray(cloud_position_fn(float(t)), dtype=float)
    return float(smoke_radius_fn(float(t))) - float(np.linalg.norm(ship - cloud)) - R_S


def s2_continuous_coverage_events(
    t_start: float,
    t_end: float,
    margin_fn: Callable[[float], float],
    brackets: Sequence[tuple[float, float]],
) -> dict[str, Any]:
    roots = [
        brentq(margin_fn, left, right, xtol=1e-13, rtol=1e-13)
        for left, right in brackets
    ]
    return {
        "model": "S2_moving_cloud_extension",
        "scenario_type": "synthetic_validation",
        "time_domain_s": [float(t_start), float(t_end)],
        "event_roots_s": roots,
        "method": "continuous_event_roots_including_radius_decay",
        "nominal_result_overwritten": False,
    }


def wind_drift_interface() -> dict[str, Any]:
    return {
        "implemented_scope": "formula_interface_only",
        "formula": "c(t)=c(t_b)+integral_{t_b}^{t} v_wind(u) du",
        "nominal_model": "U0_no_wind_drift",
        "numerical_nominal_wind_result": "not_generated",
        "reason": "No wind data or uncertainty range is supplied by the problem.",
    }
