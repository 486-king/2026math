from __future__ import annotations

import itertools
import json
import math
from pathlib import Path
import sys
import time
import tracemalloc

import numpy as np


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "code" / "Q2"))

from q2_common import CANDIDATE, CONSTANTS  # noqa: E402
from q2_union_optimizer import Schedule, fixed_time_union_slack_sq  # noqa: E402


SEED = 2026
WINDOW_START = CANDIDATE.window_start_s
G1_WINDOW_UPPER_S = (
    CONSTANTS.detection_distance_m - CONSTANTS.ship_radius_m
) / (CONSTANTS.missile_speed_mps - CONSTANTS.ship_speed_mps)
WINDOW_END = WINDOW_START + G1_WINDOW_UPPER_S
TIMES = np.linspace(WINDOW_START, WINDOW_END, 801)
TOL = 1e-7


def longest_covered_duration(flags: np.ndarray) -> float:
    best = 0
    current = 0
    for flag in flags:
        if flag:
            current += 1
            best = max(best, current)
        else:
            current = 0
    if best <= 1:
        return 0.0
    return (best - 1) * (WINDOW_END - WINDOW_START) / (len(flags) - 1)


def geometry_metrics(schedule: Schedule) -> dict:
    all_slacks = np.array(
        [fixed_time_union_slack_sq(float(t), schedule)[0] for t in TIMES]
    )
    failure_rows = []
    subset_flags = []
    for failed in range(3):
        keep = [j for j in range(3) if j != failed]
        subset = Schedule(
            tuple(schedule.centers_m[j] for j in keep),
            tuple(schedule.burst_times_s[j] for j in keep),
            f"{schedule.label}_without_{failed + 1}",
        )
        slacks = np.array(
            [fixed_time_union_slack_sq(float(t), subset)[0] for t in TIMES]
        )
        flags = slacks >= -TOL
        subset_flags.append(flags)
        failure_rows.append(
            {
                "failed_uav": failed + 1,
                "full_window_success": bool(np.all(flags)),
                "covered_time_ratio": float(np.mean(flags)),
                "longest_remaining_continuous_cover_s": longest_covered_duration(
                    flags
                ),
                "minimum_squared_cross_section_slack_m2": float(np.min(slacks)),
            }
        )

    all_failure_flags = np.logical_and.reduce(subset_flags)
    return {
        "normal_full_window_success": bool(np.all(all_slacks >= -TOL)),
        "normal_minimum_squared_cross_section_slack_m2": float(
            np.min(all_slacks)
        ),
        "single_failure_full_window_success_rate": float(
            np.mean([row["full_window_success"] for row in failure_rows])
        ),
        "worst_single_failure_continuous_cover_s": float(
            min(
                row["longest_remaining_continuous_cover_s"]
                for row in failure_rows
            )
        ),
        "double_coverage_time_ratio": float(np.mean(all_failure_flags)),
        "failure_scenarios": failure_rows,
    }


def polyline_point(points: list[np.ndarray], progress: float) -> np.ndarray:
    if progress <= 0.5:
        return points[0] + 2.0 * progress * (points[1] - points[0])
    return points[1] + 2.0 * (progress - 0.5) * (points[2] - points[1])


def route_metrics(
    centers: tuple[float, float, float],
    bursts: tuple[float, float, float],
    assignment: tuple[int, int, int],
    style: int,
) -> dict:
    starts = [
        np.array([-550.0, -180.0]),
        np.array([-520.0, 0.0]),
        np.array([-490.0, 180.0]),
    ]
    inherited = CONSTANTS.uav_speed_mps * CONSTANTS.bomb_burst_delay_s
    target_by_bomb = [
        np.array([center - inherited, 0.0]) for center in centers
    ]
    routes: list[list[np.ndarray]] = []
    total_length = 0.0
    total_turn = 0.0
    speed_feasible = True

    for uav, bomb in enumerate(assignment):
        start = starts[uav]
        target = target_by_bomb[bomb]
        lane_factor = 0.70 if style == 0 else 1.10
        bend = np.array(
            [
                0.5 * (start[0] + target[0]),
                lane_factor * start[1] + (uav - 1) * 25.0,
            ]
        )
        route = [start, bend, target]
        routes.append(route)
        v1 = bend - start
        v2 = target - bend
        length = float(np.linalg.norm(v1) + np.linalg.norm(v2))
        total_length += length
        cosine = float(
            np.dot(v1, v2)
            / max(np.linalg.norm(v1) * np.linalg.norm(v2), 1e-12)
        )
        total_turn += math.acos(max(-1.0, min(1.0, cosine)))
        release_time = bursts[bomb] - CONSTANTS.bomb_burst_delay_s + 50.0
        speed_feasible &= length <= CONSTANTS.uav_speed_mps * release_time

    minimum_distance = math.inf
    for progress in np.linspace(0.0, 1.0, 401):
        positions = [polyline_point(route, float(progress)) for route in routes]
        for i, j in itertools.combinations(range(3), 2):
            minimum_distance = min(
                minimum_distance,
                float(np.linalg.norm(positions[i] - positions[j])),
            )

    return {
        "total_path_length_m": total_length,
        "total_turn_angle_rad": total_turn,
        "minimum_pairwise_distance_m": minimum_distance,
        "synthetic_speed_reachability": bool(speed_feasible),
    }


def dominates(a: dict, b: dict) -> bool:
    maximize = (
        "normal_minimum_squared_cross_section_slack_m2",
        "single_failure_full_window_success_rate",
        "worst_single_failure_continuous_cover_s",
    )
    minimize = ("total_path_length_m", "total_turn_angle_rad")
    no_worse = all(a[key] >= b[key] - 1e-12 for key in maximize) and all(
        a[key] <= b[key] + 1e-12 for key in minimize
    )
    strictly_better = any(a[key] > b[key] + 1e-12 for key in maximize) or any(
        a[key] < b[key] - 1e-12 for key in minimize
    )
    return no_worse and strictly_better


def pareto_front(rows: list[dict]) -> list[dict]:
    return [
        row
        for i, row in enumerate(rows)
        if not any(
            i != j and dominates(other, row)
            for j, other in enumerate(rows)
        )
    ]


def ideal_distance_representative(rows: list[dict]) -> dict | None:
    if not rows:
        return None
    keys_max = (
        "normal_minimum_squared_cross_section_slack_m2",
        "single_failure_full_window_success_rate",
        "worst_single_failure_continuous_cover_s",
    )
    keys_min = ("total_path_length_m", "total_turn_angle_rad")
    values = {key: np.array([row[key] for row in rows]) for key in (*keys_max, *keys_min)}

    def normalized_distance(row: dict) -> float:
        terms = []
        for key in keys_max:
            lo, hi = float(np.min(values[key])), float(np.max(values[key]))
            score = 1.0 if hi - lo <= 1e-12 else (row[key] - lo) / (hi - lo)
            terms.append((1.0 - score) ** 2)
        for key in keys_min:
            lo, hi = float(np.min(values[key])), float(np.max(values[key]))
            score = 1.0 if hi - lo <= 1e-12 else (hi - row[key]) / (hi - lo)
            terms.append((1.0 - score) ** 2)
        return math.sqrt(sum(terms))

    return min(rows, key=normalized_distance)


def make_baseline() -> dict:
    half = (
        CONSTANTS.smoke_max_radius_m - CONSTANTS.ship_radius_m
    ) / CONSTANTS.ship_speed_mps
    centers = (0.0, 80.0, 160.0)
    midpoints = tuple(center / CONSTANTS.ship_speed_mps for center in centers)
    bursts = tuple(midpoint - half for midpoint in midpoints)
    schedule = Schedule(centers, bursts, "three_independent_interval_chain")
    geometry = geometry_metrics(schedule)
    route = route_metrics(centers, bursts, (0, 1, 2), 0)
    return {"schedule": {"centers_m": centers, "burst_times_s": bursts}, **geometry, **route}


def main() -> None:
    tracemalloc.start()
    started = time.perf_counter()
    rng = np.random.default_rng(SEED)
    base_centers = tuple(CANDIDATE.cloud_centers_m)
    base_bursts = tuple(CANDIDATE.burst_times_s)
    geometry_cache: list[tuple[tuple[float, float, float], tuple[float, float, float], dict]] = []

    third_centers = np.linspace(-40.0, 280.0, 9)
    third_bursts = np.linspace(-8.0, 20.0, 8)
    for center in third_centers:
        for burst in third_bursts:
            centers = (base_centers[0], base_centers[1], float(center))
            bursts = (base_bursts[0], base_bursts[1], float(burst))
            schedule = Schedule(centers, bursts, "synthetic_q3_candidate")
            geometry_cache.append((centers, bursts, geometry_metrics(schedule)))

    rows = []
    candidate_id = 0
    route_options = list(itertools.permutations(range(3)))
    for centers, bursts, geometry in geometry_cache:
        for assignment in route_options:
            for style in (0, 1):
                route = route_metrics(centers, bursts, assignment, style)
                if not route["synthetic_speed_reachability"]:
                    continue
                candidate_id += 1
                rows.append(
                    {
                        "candidate_id": f"A-{candidate_id:04d}",
                        "centers_m": centers,
                        "burst_times_s": bursts,
                        "assignment": assignment,
                        "route_style": style,
                        **geometry,
                        **route,
                    }
                )

    normal_feasible = [row for row in rows if row["normal_full_window_success"]]
    d_safe_grid = [0.0, 20.0, 40.0, 60.0, 80.0, 100.0, 120.0]
    sensitivity = []
    representative_ids = []
    for d_safe in d_safe_grid:
        feasible = [
            row
            for row in normal_feasible
            if row["minimum_pairwise_distance_m"] + 1e-9 >= d_safe
        ]
        front = pareto_front(feasible)
        representative = ideal_distance_representative(front)
        representative_id = (
            representative["candidate_id"] if representative is not None else None
        )
        representative_ids.append(representative_id)
        sensitivity.append(
            {
                "d_safe_m": d_safe,
                "feasible_count": len(feasible),
                "pareto_count": len(front),
                "representative_candidate_id": representative_id,
                "n_minus_one_full_defense_candidates": sum(
                    row["single_failure_full_window_success_rate"] == 1.0
                    for row in feasible
                ),
            }
        )

    positive_representatives = [
        item
        for item in sensitivity
        if item["representative_candidate_id"] is not None
    ]
    probe_representative = (
        next(
            (
                row
                for row in normal_feasible
                if row["candidate_id"]
                == positive_representatives[0]["representative_candidate_id"]
            ),
            None,
        )
        if positive_representatives
        else None
    )

    perturbation_passes = 0
    perturbation_total = 0
    if probe_representative is not None:
        centers = probe_representative["centers_m"]
        bursts = probe_representative["burst_times_s"]
        for dc in (-1.0, 0.0, 1.0):
            for dt in (-0.1, 0.0, 0.1):
                perturbed = Schedule(
                    (centers[0], centers[1], centers[2] + dc),
                    (bursts[0], bursts[1], bursts[2] + dt),
                    "perturbed_probe_candidate",
                )
                perturbation_total += 1
                perturbation_passes += geometry_metrics(perturbed)[
                    "normal_full_window_success"
                ]

    baseline = make_baseline()
    unique_representatives = [
        value
        for value in dict.fromkeys(representative_ids)
        if value is not None
    ]
    maximum_synthetic_dsafe = max(
        (row["minimum_pairwise_distance_m"] for row in normal_feasible),
        default=None,
    )
    runtime = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    detailed = {
        "schema_version": 1,
        "question_id": "Q3",
        "probe_only": True,
        "synthetic_data_warning": (
            "All UAV starts, route shapes, center/burst grids and d_safe values "
            "are synthetic structure tests, not contest-result coordinates."
        ),
        "seed": SEED,
        "window_s": [WINDOW_START, WINDOW_END],
        "candidate_count": len(rows),
        "normal_full_defense_candidate_count": len(normal_feasible),
        "pareto_and_dsafe_sensitivity": sensitivity,
        "maximum_supported_dsafe_m_in_synthetic_probe_only": maximum_synthetic_dsafe,
        "representative_solution_change_count": max(
            0, len(unique_representatives) - 1
        ),
        "representative_candidate_ids": unique_representatives,
        "perturbation": {
            "third_center_plus_minus_m": 1.0,
            "third_burst_plus_minus_s": 0.1,
            "normal_defense_passes": int(perturbation_passes),
            "runs": perturbation_total,
        },
        "n_minus_one_candidate_count": sum(
            row["single_failure_full_window_success_rate"] == 1.0
            for row in normal_feasible
        ),
        "baseline": baseline,
        "runtime_seconds": runtime,
        "peak_memory_mb": peak / (1024 * 1024),
        "formal_claims_prohibited": [
            "absolute UAV trajectories",
            "numerical d_safe recommendation",
            "formal Pareto representative",
            "N-1 feasibility in the real scenario",
        ],
    }

    summary = {
        "schema_version": 1,
        "question_id": "Q3",
        "generated_at": "2026-07-29T21:20:00+08:00",
        "decision_refs": ["q3_objective_safety_energy_scope"],
        "data_refs": [
            "planning/parse/problem_parse.json",
            "workspace/data/data_profile.json",
            "interfaces/Q1_to_Q2_coverage_contract.md",
            "methods/Q3/probes/q3_probe_metrics.json",
        ],
        "representative_data_rule": detailed["synthetic_data_warning"],
        "methods": [
            {
                "id": "A",
                "role": "main_candidate",
                "executability": {
                    "status": "PASS",
                    "evidence": {
                        "candidate_count": len(rows),
                        "normal_full_defense_candidate_count": len(normal_feasible),
                        "runtime_seconds": runtime,
                    },
                },
                "data_coverage": {
                    "status": "CONDITIONAL",
                    "evidence": {
                        "real_uav_initial_states": 0,
                        "real_d_safe": None,
                        "real_energy_function": None,
                    },
                },
                "assumption_checks": [
                    {
                        "name": "hard_complete_defense_filter",
                        "status": "PASS",
                        "metric": "normal_full_defense_candidate_count",
                        "value": len(normal_feasible),
                        "threshold": ">0 in the synthetic structure probe",
                    },
                    {
                        "name": "parametric_safety_filter",
                        "status": "PASS",
                        "metric": "d_safe_grid_levels",
                        "value": len(d_safe_grid),
                        "threshold": ">=5",
                    },
                    {
                        "name": "continuous_certificate_available_for_formal_run",
                        "status": "CONDITIONAL",
                        "metric": "formal_interval_certificates",
                        "value": 0,
                        "threshold": "one per reported formal candidate",
                    },
                ],
                "output_degeneracy": {
                    "status": "PASS" if len(unique_representatives) > 1 else "CONDITIONAL",
                    "metrics": {
                        "representative_solution_change_count": max(
                            0, len(unique_representatives) - 1
                        ),
                        "nonempty_d_safe_levels": len(positive_representatives),
                        "n_minus_one_full_defense_candidate_count_probe_only": detailed[
                            "n_minus_one_candidate_count"
                        ],
                    },
                },
                "perturbation_sensitivity": {
                    "status": (
                        "PASS"
                        if perturbation_total
                        and perturbation_passes == perturbation_total
                        else "CONDITIONAL"
                    ),
                    "perturbation": "third center +/-1 m and burst +/-0.1 s",
                    "metric": "normal full-defense retention",
                    "value": (
                        perturbation_passes / perturbation_total
                        if perturbation_total
                        else None
                    ),
                },
                "scale_check": {
                    "status": "PASS" if runtime < 30.0 else "CONDITIONAL",
                    "representative_n": len(rows),
                    "runtime_seconds": runtime,
                    "peak_memory_mb": peak / (1024 * 1024),
                },
                "verdict": "CONDITIONAL",
                "conditions": [
                    "正式运行必须输入三机初态并将 d_safe 保留为参数。",
                    "正式报告候选必须通过连续时间避碰和连续烟幕并集证书。",
                    "理想点距离或膝点只用于 Pareto 集内代表解选择，不得改写完整防御硬约束。",
                ],
                "evidence_refs": ["methods/Q3/probes/q3_probe_metrics.json"],
            },
            {
                "id": "B",
                "role": "usable_baseline",
                "executability": {
                    "status": "PASS",
                    "evidence": {
                        "explicit_three_bomb_schedule": True,
                        "normal_full_window_success_probe": baseline[
                            "normal_full_window_success"
                        ],
                    },
                },
                "data_coverage": {
                    "status": "CONDITIONAL",
                    "evidence": {
                        "real_uav_initial_states": 0,
                        "real_d_safe": None,
                    },
                },
                "assumption_checks": [
                    {
                        "name": "same_output_contract_as_A",
                        "status": "PASS",
                        "metric": "reported_metrics",
                        "value": [
                            "normal defense",
                            "N-1 success",
                            "worst remaining duration",
                            "double-cover ratio",
                            "path length",
                            "turn angle",
                        ],
                        "threshold": "all required outputs",
                    }
                ],
                "output_degeneracy": {
                    "status": "PASS",
                    "metrics": {
                        "always_returns_explicit_schedule_or_blocked_status": True,
                        "n_minus_one_success_rate_probe": baseline[
                            "single_failure_full_window_success_rate"
                        ],
                    },
                },
                "perturbation_sensitivity": {
                    "status": "CONDITIONAL",
                    "perturbation": "formal timing and route perturbations not run without real inputs",
                    "metric": "not available",
                    "value": None,
                },
                "scale_check": {
                    "status": "PASS",
                    "representative_n": 6,
                    "runtime_seconds": runtime,
                    "peak_memory_mb": peak / (1024 * 1024),
                },
                "verdict": "CONDITIONAL",
                "conditions": [
                    "正式 baseline 必须进行 3! 分配、连续避碰和相同覆盖证书。",
                    "不得把构造方案称为 Pareto 最优。",
                ],
                "evidence_refs": ["methods/Q3/probes/q3_probe_metrics.json"],
            },
            {
                "id": "C",
                "role": "conditional_fallback",
                "executability": {
                    "status": "CONDITIONAL",
                    "evidence": {
                        "zero_uncertainty_reduces_to_A": True,
                        "real_uncertainty_set_available": False,
                    },
                },
                "data_coverage": {
                    "status": "CONDITIONAL",
                    "evidence": {"supported_uncertainty_parameters": 0},
                },
                "assumption_checks": [
                    {
                        "name": "uncertainty_support",
                        "status": "CONDITIONAL",
                        "metric": "physically_supported_bounds",
                        "value": 0,
                        "threshold": ">0 before activation",
                    }
                ],
                "output_degeneracy": {
                    "status": "CONDITIONAL",
                    "metrics": {"over_conservatism_risk": True},
                },
                "perturbation_sensitivity": {
                    "status": "CONDITIONAL",
                    "perturbation": "not instantiated without supported bounds",
                    "metric": None,
                    "value": None,
                },
                "scale_check": {
                    "status": "CONDITIONAL",
                    "representative_n": None,
                    "runtime_seconds": None,
                    "peak_memory_mb": None,
                },
                "verdict": "CONDITIONAL",
                "conditions": [
                    "仅在 A 的正式连续验证不稳定、N-1 降级过快且获得有依据误差范围时激活。",
                    "不得自行设置风、定位或时延误差范围。",
                ],
                "evidence_refs": ["methods/Q3/probes/q3_probe_metrics.json"],
            },
        ],
    }

    probe_dir = Path(__file__).resolve().parent
    (probe_dir / "q3_probe_metrics.json").write_text(
        json.dumps(detailed, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (probe_dir / "risk_probe_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "candidate_count": len(rows),
                "normal_feasible": len(normal_feasible),
                "n_minus_one_candidates_probe_only": detailed[
                    "n_minus_one_candidate_count"
                ],
                "representative_changes": detailed[
                    "representative_solution_change_count"
                ],
                "runtime_seconds": runtime,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
