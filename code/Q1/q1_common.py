"""Shared Q1 definitions for the approved A main and B baseline."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any

import numpy as np


SEED = 2026


@dataclass(frozen=True)
class Q1Constants:
    ship_speed_mps: float = 15.0 * 0.514
    ship_radius_m: float = 80.0
    missile_speed_mps: float = 320.0
    detection_distance_m: float = 8000.0
    fov_half_angle_deg: float = 15.0
    uav_speed_mps: float = 28.0
    uav_operation_radius_m: float = 12000.0
    response_delay_s: float = 2.0
    bomb_burst_delay_s: float = 3.5
    smoke_max_radius_m: float = 120.0
    smoke_constant_duration_s: float = 18.0
    smoke_decay_duration_s: float = 5.0

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


def unit_vector(angle_rad: float) -> np.ndarray:
    return np.array([math.cos(angle_rad), math.sin(angle_rad)], dtype=float)


def smoke_radius(age_s: float | np.ndarray, cfg: Q1Constants) -> float | np.ndarray:
    """Smoke radius under the statement's instantaneous-rise interpretation."""
    age = np.asarray(age_s, dtype=float)
    radius = np.where(
        (age >= 0.0) & (age <= cfg.smoke_constant_duration_s),
        cfg.smoke_max_radius_m,
        np.where(
            (age > cfg.smoke_constant_duration_s)
            & (
                age
                <= cfg.smoke_constant_duration_s + cfg.smoke_decay_duration_s
            ),
            cfg.smoke_max_radius_m
            * (
                cfg.smoke_constant_duration_s
                + cfg.smoke_decay_duration_s
                - age
            )
            / cfg.smoke_decay_duration_s,
            0.0,
        ),
    )
    if np.isscalar(age_s):
        return float(radius)
    return radius


def structural_bounds(cfg: Q1Constants) -> dict[str, Any]:
    """Scenario-independent necessary bounds for M1/S1."""
    cover_margin_m = cfg.smoke_max_radius_m - cfg.ship_radius_m
    if cover_margin_m < 0:
        stationary_cover_s = 0.0
    else:
        stationary_cover_s = 2.0 * cover_margin_m / cfg.ship_speed_mps

    if cfg.smoke_max_radius_m <= 0:
        comoving_relaxation_s = 0.0
    else:
        comoving_relaxation_s = cfg.smoke_constant_duration_s + (
            cfg.smoke_decay_duration_s
            * max(
                0.0,
                1.0 - cfg.ship_radius_m / cfg.smoke_max_radius_m,
            )
        )

    radial_distance_m = cfg.detection_distance_m - cfg.ship_radius_m
    min_detection_s = radial_distance_m / (
        cfg.missile_speed_mps + cfg.ship_speed_mps
    )
    max_detection_s = radial_distance_m / (
        cfg.missile_speed_mps - cfg.ship_speed_mps
    )
    naked_lower_bound_s = max(0.0, min_detection_s - stationary_cover_s)

    return {
        "model_scope": "M1 pure pursuit + S1 stationary smoke after burst",
        "cover_margin_at_max_radius_m": cover_margin_m,
        "stationary_smoke_max_continuous_full_cover_s": stationary_cover_s,
        "comoving_smoke_relaxation_upper_bound_s": comoving_relaxation_s,
        "m1_detection_window_lower_bound_s": min_detection_s,
        "m1_detection_window_upper_bound_s": max_detection_s,
        "strict_full_window_feasible_by_duration_necessary_condition": (
            stationary_cover_s >= min_detection_s
        ),
        "minimum_naked_time_lower_bound_s": naked_lower_bound_s,
        "unique_coordinate_identifiable": False,
        "proof_notes": [
            "For a fixed smoke center, complete cover implies the ship center stays within "
            "R_c-R_s=40 m of that center. A line moving at V_s can remain in this disk for "
            "at most 2(R_c-R_s)/V_s.",
            "Under pure pursuit, range rate is V_s*cos(phi)-V_m and is no smaller in "
            "magnitude than V_m-V_s and no larger than V_m+V_s. The shortest possible "
            "8000 m-to-contact window uses V_m+V_s.",
            "Because the maximum cover upper bound is shorter than the minimum detection "
            "window, strict full-window cover is impossible before UAV reachability is considered.",
        ],
    }


def validate_constants(cfg: Q1Constants) -> list[str]:
    errors: list[str] = []
    positive_fields = {
        "ship_speed_mps": cfg.ship_speed_mps,
        "ship_radius_m": cfg.ship_radius_m,
        "missile_speed_mps": cfg.missile_speed_mps,
        "detection_distance_m": cfg.detection_distance_m,
        "uav_speed_mps": cfg.uav_speed_mps,
        "smoke_max_radius_m": cfg.smoke_max_radius_m,
    }
    for name, value in positive_fields.items():
        if value <= 0:
            errors.append(f"{name} must be positive")
    if cfg.missile_speed_mps <= cfg.ship_speed_mps:
        errors.append("missile_speed_mps must exceed ship_speed_mps")
    if cfg.detection_distance_m <= cfg.ship_radius_m:
        errors.append("detection_distance_m must exceed ship_radius_m")
    return errors
