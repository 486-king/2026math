"""Exact single-smoke complete-disk coverage geometry."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np

from q1_common import R_S

MULTISMOKE_ERROR = (
    "Exact continuous multi-smoke union coverage belongs to Q2 and is "
    "intentionally not implemented in Q1."
)


def single_smoke_margin(
    ship_center: Sequence[float],
    smoke_center: Sequence[float],
    smoke_radius: float,
    ship_radius: float = R_S,
) -> float:
    distance = float(
        np.linalg.norm(np.asarray(ship_center, dtype=float) - np.asarray(smoke_center, dtype=float))
    )
    return float(smoke_radius) - (distance + float(ship_radius))


def delta_single(
    ship_center: Sequence[float],
    smoke_center: Sequence[float],
    smoke_radius: float,
    ship_radius: float = R_S,
) -> float:
    distance = float(
        np.linalg.norm(np.asarray(ship_center, dtype=float) - np.asarray(smoke_center, dtype=float))
    )
    return (distance + float(ship_radius)) - float(smoke_radius)


def is_fully_covered_single(
    ship_center: Sequence[float],
    smoke_center: Sequence[float],
    smoke_radius: float,
    ship_radius: float = R_S,
) -> bool:
    return delta_single(ship_center, smoke_center, smoke_radius, ship_radius) <= 0.0


def coverage_defect(
    ship_center: Sequence[float],
    smokes: Sequence[dict[str, Any]],
    ship_radius: float = R_S,
) -> float:
    if len(smokes) != 1:
        if len(smokes) > 1:
            raise NotImplementedError(MULTISMOKE_ERROR)
        raise ValueError("Q1 coverage requires exactly one smoke.")
    smoke = smokes[0]
    return delta_single(ship_center, smoke["center"], smoke["radius"], ship_radius)


def random_degeneracy_check(seed: int = 20260729, count: int = 1000) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    max_abs_error = 0.0
    for _ in range(count):
        ship = rng.uniform(-20000.0, 20000.0, size=2)
        smoke = rng.uniform(-20000.0, 20000.0, size=2)
        radius = float(rng.uniform(0.0, 250.0))
        ship_radius = float(rng.uniform(1.0, 200.0))
        error = abs(
            single_smoke_margin(ship, smoke, radius, ship_radius)
            + delta_single(ship, smoke, radius, ship_radius)
        )
        max_abs_error = max(max_abs_error, error)
    return {
        "random_seed": seed,
        "sample_count": count,
        "max_abs_error_m": max_abs_error,
        "tolerance_m": 1e-12,
        "verified": max_abs_error <= 1e-12,
        "method": "exact_closed_form_no_boundary_grid",
    }
