"""Time-limited Q2 probe: collinear stationary smoke disks covering a moving ship disk.

This is diagnostic evidence only, not formal model code. It tests whether
multi-smoke geometric union can beat conservative chaining of individually
complete single-smoke intervals.
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path

import numpy as np
from scipy.optimize import differential_evolution


VS = 7.71
RS = 80.0
RC = 120.0
CONST = 18.0
DECAY = 5.0
H = (RC - RS) / VS
L_SINGLE = 2.0 * H

DT = 0.08
DX = 1.0
T_GRID = np.arange(-12.0, 86.0 + DT / 2, DT)
XI = np.arange(-RS, RS + DX / 2, DX)
SHIP_HALF_HEIGHT = np.sqrt(np.maximum(0.0, RS * RS - XI * XI))


def radii(t: np.ndarray, bursts: np.ndarray) -> np.ndarray:
    age = t[:, None] - bursts[None, :]
    out = np.zeros_like(age)
    constant = (age >= 0.0) & (age <= CONST)
    decay = (age > CONST) & (age <= CONST + DECAY)
    out[constant] = RC
    out[decay] = RC * (CONST + DECAY - age[decay]) / DECAY
    return out


def coverage_margins(centers: np.ndarray, bursts: np.ndarray) -> np.ndarray:
    """Minimum vertical cross-section slack over the ship disk for each time."""
    ship_x = VS * T_GRID
    rr = radii(T_GRID, bursts)
    # shape: time, ship-relative x, smoke
    dx = ship_x[:, None, None] + XI[None, :, None] - centers[None, None, :]
    inside = rr[:, None, :] ** 2 - dx * dx
    smoke_half_height = np.sqrt(np.maximum(0.0, inside))
    smoke_half_height[inside < 0.0] = -1e6
    union_half_height = np.max(smoke_half_height, axis=2)
    return np.min(union_half_height - SHIP_HALF_HEIGHT[None, :], axis=1)


def longest_component(mask: np.ndarray) -> tuple[float, float, float]:
    padded = np.r_[False, mask, False].astype(np.int8)
    changes = np.diff(padded)
    starts = np.flatnonzero(changes == 1)
    ends = np.flatnonzero(changes == -1) - 1
    if starts.size == 0:
        return 0.0, math.nan, math.nan
    k = int(np.argmax(ends - starts))
    start = T_GRID[starts[k]]
    end = T_GRID[ends[k]]
    return float(end - start), float(start), float(end)


def decode(x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    gap1, gap2, b1, b2, b3 = x
    centers = np.array([0.0, gap1, gap1 + gap2])
    bursts = np.array([b1, b2, b3])
    return centers, bursts


def objective(x: np.ndarray) -> float:
    centers, bursts = decode(x)
    margin = coverage_margins(centers, bursts)
    duration, _, _ = longest_component(margin >= -0.10)
    # Tiny penalty discourages highly non-ordered burst schedules.
    order_penalty = 0.02 * (
        max(0.0, bursts[0] - bursts[1]) + max(0.0, bursts[1] - bursts[2])
    )
    return -duration + order_penalty


def evaluate(label: str, centers: np.ndarray, bursts: np.ndarray) -> dict:
    margin = coverage_margins(centers, bursts)
    duration, start, end = longest_component(margin >= -0.10)
    single_complete = []
    for j in range(3):
        d = np.abs(VS * T_GRID - centers[j])
        single_margin = radii(T_GRID, bursts[[j]])[:, 0] - RS - d
        single_complete.append(single_margin >= -0.10)
    joint_only_count = int(np.sum((margin >= -0.10) & ~np.logical_or.reduce(single_complete)))
    return {
        "label": label,
        "centers_m": centers.tolist(),
        "burst_times_s": bursts.tolist(),
        "longest_continuous_union_cover_s_grid": duration,
        "component_start_s_grid": start,
        "component_end_s_grid": end,
        "minimum_margin_in_component_m_grid": float(
            np.min(margin[(T_GRID >= start) & (T_GRID <= end)])
        ) if duration > 0 else None,
        "joint_only_time_grid_count": joint_only_count,
        "joint_only_duration_approx_s": joint_only_count * DT,
    }


def main() -> None:
    started = time.perf_counter()

    # Conservative B: each cloud alone covers one consecutive length-L segment.
    conservative_centers = np.array([0.0, 80.0, 160.0])
    conservative_bursts = conservative_centers / VS - H
    baseline = evaluate("conservative_single-cloud_chain", conservative_centers, conservative_bursts)

    result = differential_evolution(
        objective,
        bounds=[
            (40.0, 190.0),
            (40.0, 190.0),
            (-12.0, 12.0),
            (-2.0, 35.0),
            (8.0, 62.0),
        ],
        seed=2026,
        maxiter=55,
        popsize=10,
        tol=0.01,
        polish=False,
        workers=1,
        updating="immediate",
    )
    centers, bursts = decode(result.x)
    candidate = evaluate("optimized_union_probe", centers, bursts)

    # Small perturbation probe on centers and burst times.
    rng = np.random.default_rng(2026)
    perturbed_durations = []
    for _ in range(80):
        c = centers + rng.normal(0.0, 1.0, size=3)
        c = np.sort(c)
        c -= c[0]
        b = bursts + rng.normal(0.0, 0.10, size=3)
        perturbed_durations.append(evaluate("perturbed", c, b)["longest_continuous_union_cover_s_grid"])

    output = {
        "schema_version": 1,
        "question_id": "Q2",
        "purpose": "risk probe only; dense cross-section grid, not a final certificate",
        "constants": {
            "ship_speed_mps": VS,
            "ship_radius_m": RS,
            "smoke_max_radius_m": RC,
            "constant_phase_s": CONST,
            "decay_phase_s": DECAY,
            "single_cloud_full_cover_upper_s": L_SINGLE,
            "three_cloud_conservative_sum_s": 3 * L_SINGLE,
        },
        "grid": {"dt_s": DT, "dx_m": DX},
        "baseline": baseline,
        "candidate": candidate,
        "candidate_improvement_over_baseline_s_grid": (
            candidate["longest_continuous_union_cover_s_grid"]
            - baseline["longest_continuous_union_cover_s_grid"]
        ),
        "perturbation": {
            "center_sigma_m": 1.0,
            "burst_sigma_s": 0.10,
            "runs": len(perturbed_durations),
            "duration_min_s_grid": float(np.min(perturbed_durations)),
            "duration_median_s_grid": float(np.median(perturbed_durations)),
            "duration_max_s_grid": float(np.max(perturbed_durations)),
        },
        "optimizer": {
            "success": bool(result.success),
            "message": str(result.message),
            "iterations": int(result.nit),
            "evaluations": int(result.nfev),
        },
        "runtime_seconds": time.perf_counter() - started,
        "interpretation_limit": (
            "Collinear smoke centers and grid coverage only. A continuous event/geometric "
            "certificate and UAV reachability are required before any formal claim."
        ),
    }
    out = Path("scratch/q2_union_geometry_probe.json")
    out.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
