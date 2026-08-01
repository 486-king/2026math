"""Front-stage diagnostic only; this is not formal model code.

It evaluates scenario-independent timing/geometry limits from the statement
and exercises small generic scheduling kernels. It never fabricates a contest
scenario or reports a synthetic fixture as an answer.
"""

from __future__ import annotations

import json
import math
import time
import tracemalloc

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp


SEED = 2026
SHIP_SPEED = 15.0 * 0.514
SHIP_RADIUS = 80.0
MISSILE_SPEED = 320.0
DETECTION_DISTANCE = 8000.0
SMOKE_RADIUS = 120.0
SMOKE_CONSTANT = 18.0
SMOKE_DECAY = 5.0


def smoke_radius(age: np.ndarray) -> np.ndarray:
    return np.where(
        (age >= 0.0) & (age <= SMOKE_CONSTANT),
        SMOKE_RADIUS,
        np.where(
            (age > SMOKE_CONSTANT) & (age <= SMOKE_CONSTANT + SMOKE_DECAY),
            SMOKE_RADIUS * (SMOKE_CONSTANT + SMOKE_DECAY - age) / SMOKE_DECAY,
            0.0,
        ),
    )


def structural_limits() -> dict:
    margin = SMOKE_RADIUS - SHIP_RADIUS
    stationary_full_cover = 2.0 * margin / SHIP_SPEED
    comoving_full_cover = SMOKE_CONSTANT + SMOKE_DECAY * (
        1.0 - SHIP_RADIUS / SMOKE_RADIUS
    )
    detect_min = (DETECTION_DISTANCE - SHIP_RADIUS) / (
        MISSILE_SPEED + SHIP_SPEED
    )
    detect_max = (DETECTION_DISTANCE - SHIP_RADIUS) / (
        MISSILE_SPEED - SHIP_SPEED
    )
    return {
        "ship_speed_mps": SHIP_SPEED,
        "single_smoke_stationary_center_full_cover_upper_bound_s": stationary_full_cover,
        "single_smoke_comoving_center_full_cover_upper_bound_s": comoving_full_cover,
        "continuous_lock_detection_window_range_s": [detect_min, detect_max],
        "q1_duration_feasible_under_continuous_lock_stationary_smoke": stationary_full_cover
        >= detect_min,
        "q1_duration_feasible_under_continuous_lock_comoving_smoke": comoving_full_cover
        >= detect_min,
        "three_smoke_stationary_chain_upper_bound_s": 3.0
        * stationary_full_cover,
        "three_smoke_comoving_chain_upper_bound_s": 3.0 * comoving_full_cover,
        "fifteen_smoke_stationary_total_cover_capacity_s": 15.0
        * stationary_full_cover,
    }


def vector_kernel_probe() -> dict:
    ages = np.linspace(-1.0, 24.0, 500_000)
    tracemalloc.start()
    start = time.perf_counter()
    radii = smoke_radius(ages)
    eligible = radii >= SHIP_RADIUS
    runtime = time.perf_counter() - start
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "samples": int(ages.size),
        "runtime_seconds": runtime,
        "peak_memory_mb": peak / (1024.0 * 1024.0),
        "unique_radius_count": int(np.unique(np.round(radii, 6)).size),
        "eligible_fraction": float(np.mean(eligible)),
        "finite_output": bool(np.isfinite(radii).all()),
    }


def perturbation_probe() -> dict:
    speeds = SHIP_SPEED * np.array([0.95, 1.0, 1.05])
    durations = 2.0 * (SMOKE_RADIUS - SHIP_RADIUS) / speeds
    return {
        "perturbation": "ship speed +/-5%",
        "stationary_full_cover_seconds": durations.tolist(),
        "max_relative_change": float(
            np.max(np.abs(durations / durations[1] - 1.0))
        ),
    }


def generic_capacity_milp_probe() -> dict:
    # Dimensionless synthetic recovery fixture: verifies that the assignment
    # kernel can honor a 15-round capacity. It is not a contest result.
    demand = np.array([3, 3, 3, 2, 2, 2, 2, 1], dtype=float)
    value = np.array([9, 8, 7, 6, 5, 4, 3, 2], dtype=float)
    c = -value
    constraint = LinearConstraint(demand.reshape(1, -1), -np.inf, 15.0)
    start = time.perf_counter()
    result = milp(
        c=c,
        integrality=np.ones(len(demand)),
        bounds=Bounds(np.zeros(len(demand)), np.ones(len(demand))),
        constraints=constraint,
        options={"time_limit": 5.0},
    )
    runtime = time.perf_counter() - start
    selected = np.rint(result.x).astype(int) if result.x is not None else None
    return {
        "fixture_label": "dimensionless_synthetic_recovery_only",
        "solver_success": bool(result.success),
        "runtime_seconds": runtime,
        "selected_count": int(selected.sum()) if selected is not None else None,
        "resource_used": float(demand @ selected) if selected is not None else None,
        "capacity": 15.0,
        "constraint_satisfied": bool(demand @ selected <= 15.0 + 1e-9)
        if selected is not None
        else False,
    }


if __name__ == "__main__":
    output = {
        "schema_version": 1,
        "seed": SEED,
        "scope": "front-stage structural and synthetic recovery diagnostics only",
        "structural_limits": structural_limits(),
        "vector_kernel": vector_kernel_probe(),
        "perturbation": perturbation_probe(),
        "generic_capacity_milp": generic_capacity_milp_probe(),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
