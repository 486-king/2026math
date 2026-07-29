from __future__ import annotations

from dataclasses import dataclass
import itertools
import math
from typing import Any

import numpy as np

from q3_common import CONSTANTS

from q2_common import CANDIDATE as Q2_CANDIDATE, CONSTANTS as Q2_CONSTANTS
from q2_union_optimizer import (
    Schedule,
    adaptive_continuous_check,
    fixed_time_union_slack_sq,
)


WINDOW_START = 0.0
WINDOW_END = CONSTANTS.g1_window_upper_s
TIME_SHIFT = -Q2_CANDIDATE.window_start_s
SPACE_SHIFT = CONSTANTS.ship_speed_mps * TIME_SHIFT
BASE_CENTERS = tuple(c + SPACE_SHIFT for c in Q2_CANDIDATE.cloud_centers_m)
BASE_BURSTS = tuple(b + TIME_SHIFT for b in Q2_CANDIDATE.burst_times_s)
INHERITED_M = 28.0 * 3.5
SEARCH_TIMES = np.linspace(WINDOW_START, WINDOW_END, 601)
TOL = 1e-7


@dataclass(frozen=True)
class Route:
    uav: int
    bomb: int
    start: tuple[float, float]
    initial_heading: float
    center: tuple[float, float]
    release_point: tuple[float, float]
    direction: tuple[float, float]
    burst_time: float
    release_time: float
    command_time: float
    latest_available_time: float
    path_length: float
    turn_angle: float


def wrap_abs(angle: float) -> float:
    return abs((angle + math.pi) % (2.0 * math.pi) - math.pi)


def make_route(
    uav: int,
    bomb: int,
    start: tuple[float, float],
    initial_heading: float,
    center_x: float,
    burst_time: float,
) -> Route:
    center = np.array([center_x, 0.0], dtype=float)
    origin = np.array(start, dtype=float)
    delta = center - origin
    distance = float(np.linalg.norm(delta))
    if distance <= INHERITED_M:
        raise ValueError("standardized start is too close to the cloud centre")
    direction = delta / distance
    release = center - INHERITED_M * direction
    path_length = float(np.linalg.norm(release - origin))
    release_time = burst_time - 3.5
    command_time = release_time - 2.0
    latest_by_travel = release_time - path_length / 28.0
    latest_available = min(command_time, latest_by_travel)
    route_heading = math.atan2(direction[1], direction[0])
    return Route(
        uav=uav,
        bomb=bomb,
        start=(float(origin[0]), float(origin[1])),
        initial_heading=float(initial_heading),
        center=(float(center[0]), 0.0),
        release_point=(float(release[0]), float(release[1])),
        direction=(float(direction[0]), float(direction[1])),
        burst_time=float(burst_time),
        release_time=float(release_time),
        command_time=float(command_time),
        latest_available_time=float(latest_available),
        path_length=path_length,
        turn_angle=wrap_abs(route_heading - initial_heading),
    )


def route_state(route: Route, t: float) -> tuple[np.ndarray, np.ndarray]:
    start = np.array(route.start)
    release = np.array(route.release_point)
    direction = np.array(route.direction)
    if t <= route.release_time:
        duration = route.release_time - route.latest_available_time
        velocity = (release - start) / duration
        return start + velocity * (t - route.latest_available_time), velocity
    velocity = 28.0 * direction
    return release + velocity * (t - route.release_time), velocity


def minimum_pair_distance(routes: list[Route], end_time: float) -> float:
    best = math.inf
    for r1, r2 in itertools.combinations(routes, 2):
        left = max(r1.latest_available_time, r2.latest_available_time)
        if left > end_time:
            continue
        cuts = sorted(
            {
                left,
                end_time,
                *(
                    value
                    for value in (r1.release_time, r2.release_time)
                    if left <= value <= end_time
                ),
            }
        )
        for a, b in zip(cuts[:-1], cuts[1:]):
            p1, v1 = route_state(r1, a)
            p2, v2 = route_state(r2, a)
            rel = p1 - p2
            vel = v1 - v2
            candidates = [0.0, b - a]
            denom = float(np.dot(vel, vel))
            if denom > 1e-14:
                candidates.append(
                    min(max(-float(np.dot(rel, vel)) / denom, 0.0), b - a)
                )
            for dt in candidates:
                best = min(best, float(np.linalg.norm(rel + vel * dt)))
    return float(best)


def longest_duration(flags: np.ndarray) -> float:
    best = current = 0
    for flag in flags:
        if flag:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return max(0, best - 1) * (WINDOW_END - WINDOW_START) / (len(flags) - 1)


def geometry_metrics(schedule: Schedule) -> dict[str, Any]:
    slacks = np.array(
        [fixed_time_union_slack_sq(float(t), schedule)[0] for t in SEARCH_TIMES]
    )
    failures = []
    pair_flags = []
    for failed in range(3):
        keep = [j for j in range(3) if j != failed]
        subset = Schedule(
            tuple(schedule.centers_m[j] for j in keep),
            tuple(schedule.burst_times_s[j] for j in keep),
            f"{schedule.label}_minus_{failed + 1}",
        )
        values = np.array(
            [fixed_time_union_slack_sq(float(t), subset)[0] for t in SEARCH_TIMES]
        )
        flags = values >= -TOL
        pair_flags.append(flags)
        failures.append(
            {
                "failed_uav_or_bomb": failed + 1,
                "full_window_success": bool(np.all(flags)),
                "longest_continuous_cover_s": longest_duration(flags),
                "covered_time_ratio": float(np.mean(flags)),
            }
        )
    return {
        "normal_full_defense": bool(np.all(slacks >= -TOL)),
        "normal_min_slack_sq_m2": float(np.min(slacks)),
        "n_minus_one_success_rate": float(
            np.mean([row["full_window_success"] for row in failures])
        ),
        "worst_failure_continuous_cover_s": float(
            min(row["longest_continuous_cover_s"] for row in failures)
        ),
        "double_cover_time_ratio": float(
            np.mean(np.logical_and.reduce(pair_flags))
        ),
        "failure_rows": failures,
    }


def candidate_from(
    candidate_id: str,
    centers: tuple[float, float, float],
    bursts: tuple[float, float, float],
    assignment: tuple[int, int, int],
    starts: list[tuple[float, float]],
    headings: list[float],
    geometry: dict[str, Any],
) -> dict[str, Any]:
    routes = [
        make_route(
            uav=i,
            bomb=assignment[i],
            start=starts[i],
            initial_heading=headings[i],
            center_x=centers[assignment[i]],
            burst_time=bursts[assignment[i]],
        )
        for i in range(3)
    ]
    latest_times = [route.latest_available_time for route in routes]
    selected_available_times = [min(0.0, value) for value in latest_times]
    common_lead_required = max(0.0, -min(selected_available_times))
    user_defined_latest_uav_lead = max(0.0, -max(selected_available_times))
    d_safe_max = minimum_pair_distance(routes, WINDOW_END)
    return {
        "candidate_id": candidate_id,
        "centers_m": centers,
        "burst_times_s": bursts,
        "assignment": assignment,
        "routes": [route.__dict__ for route in routes],
        "lead_required_s": float(common_lead_required),
        "common_all_uav_warning_lead_s": float(common_lead_required),
        "user_defined_latest_uav_warning_lead_s": float(
            user_defined_latest_uav_lead
        ),
        "latest_available_times_s": latest_times,
        "selected_available_times_s": selected_available_times,
        "d_safe_max_m": d_safe_max,
        "total_path_length_m": float(sum(r.path_length for r in routes)),
        "total_turn_angle_rad": float(sum(r.turn_angle for r in routes)),
        **geometry,
    }


def dominates(a: dict[str, Any], b: dict[str, Any]) -> bool:
    max_keys = (
        "normal_min_slack_sq_m2",
        "n_minus_one_success_rate",
        "worst_failure_continuous_cover_s",
        "double_cover_time_ratio",
    )
    min_keys = ("total_path_length_m", "total_turn_angle_rad")
    no_worse = all(a[k] >= b[k] - 1e-9 for k in max_keys) and all(
        a[k] <= b[k] + 1e-9 for k in min_keys
    )
    strict = any(a[k] > b[k] + 1e-9 for k in max_keys) or any(
        a[k] < b[k] - 1e-9 for k in min_keys
    )
    return no_worse and strict


def pareto(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row
        for i, row in enumerate(rows)
        if not any(i != j and dominates(other, row) for j, other in enumerate(rows))
    ]


def normalized_matrix(rows: list[dict[str, Any]]) -> np.ndarray:
    keys = (
        "normal_min_slack_sq_m2",
        "n_minus_one_success_rate",
        "worst_failure_continuous_cover_s",
        "double_cover_time_ratio",
        "total_path_length_m",
        "total_turn_angle_rad",
    )
    matrix = np.array([[row[k] for k in keys] for row in rows], dtype=float)
    for j in range(matrix.shape[1]):
        lo, hi = float(np.min(matrix[:, j])), float(np.max(matrix[:, j]))
        if hi - lo <= 1e-12:
            matrix[:, j] = 1.0
        elif j < 4:
            matrix[:, j] = (matrix[:, j] - lo) / (hi - lo)
        else:
            matrix[:, j] = (hi - matrix[:, j]) / (hi - lo)
    return matrix


def representatives(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"status": "NO_PARETO_FRONT"}
    matrix = normalized_matrix(rows)
    ideal_idx = int(np.argmin(np.linalg.norm(1.0 - matrix, axis=1)))
    knee_idx = int(np.argmax(np.min(matrix, axis=1)))
    layered_idx = min(
        range(len(rows)),
        key=lambda i: (
            -rows[i]["n_minus_one_success_rate"],
            -rows[i]["worst_failure_continuous_cover_s"],
            -rows[i]["double_cover_time_ratio"],
            -rows[i]["normal_min_slack_sq_m2"],
            rows[i]["total_path_length_m"],
            rows[i]["total_turn_angle_rad"],
        ),
    )
    ids = {
        "ideal_point": rows[ideal_idx]["candidate_id"],
        "knee_chebyshev": rows[knee_idx]["candidate_id"],
        "layered": rows[layered_idx]["candidate_id"],
    }
    unique = set(ids.values())
    return {
        "status": "AGREE_AUTO_SELECT" if len(unique) == 1 else "DISAGREE_HUMAN_REQUIRED",
        "selected_candidate_id": next(iter(unique)) if len(unique) == 1 else None,
        "methods": ids,
    }


def continuous_and_independent_validation(candidate: dict[str, Any]) -> dict[str, Any]:
    from shapely.geometry import Point
    from shapely.ops import unary_union

    schedule = Schedule(
        tuple(candidate["centers_m"]),
        tuple(candidate["burst_times_s"]),
        candidate["candidate_id"],
    )
    continuous = adaptive_continuous_check(
        schedule, WINDOW_START, WINDOW_END, dense_points=12001
    )
    check_times = np.linspace(WINDOW_START, WINDOW_END, 401)
    max_uncovered = 0.0
    for t in check_times:
        ship = Point(CONSTANTS.ship_speed_mps * float(t), 0.0).buffer(
            CONSTANTS.ship_radius_m, quad_segs=256
        )
        smoke = []
        for center, burst in zip(schedule.centers_m, schedule.burst_times_s):
            age = float(t) - burst
            radius = (
                120.0
                if 0.0 <= age <= 18.0
                else 120.0 * (23.0 - age) / 5.0
                if 18.0 < age <= 23.0
                else 0.0
            )
            if radius > 0:
                smoke.append(Point(center, 0.0).buffer(radius, quad_segs=256))
        union = unary_union(smoke) if smoke else Point().buffer(0)
        max_uncovered = max(max_uncovered, float(ship.difference(union).area))
    return {
        "continuous_envelope": continuous,
        "independent_disk_difference": {
            "status": "PASS" if max_uncovered <= 1e-5 else "FAIL",
            "time_checks": len(check_times),
            "maximum_uncovered_area_m2": max_uncovered,
        },
        "validators_agree": continuous["status"] == "PASS"
        and max_uncovered <= 1e-5,
    }


def generate_main_candidates(scenario: dict[str, Any]) -> list[dict[str, Any]]:
    starts = [tuple(map(float, p)) for p in scenario["uav_initial_positions_m"]]
    headings = [float(v) for v in scenario["uav_initial_headings_rad"]]
    rows = []
    counter = 0
    for third_center in np.linspace(0.0, 280.0, 15):
        for third_burst in np.linspace(-12.0, 18.0, 16):
            centers = (BASE_CENTERS[0], BASE_CENTERS[1], float(third_center))
            bursts = (BASE_BURSTS[0], BASE_BURSTS[1], float(third_burst))
            schedule = Schedule(centers, bursts, "Q3-A-grid")
            geometry = geometry_metrics(schedule)
            if not geometry["normal_full_defense"]:
                continue
            for assignment in itertools.permutations(range(3)):
                counter += 1
                row = candidate_from(
                    f"A-{counter:05d}",
                    centers,
                    bursts,
                    assignment,
                    starts,
                    headings,
                    geometry,
                )
                if row["lead_required_s"] <= 60.0 + 1e-9:
                    rows.append(row)
    return rows


def generate_baseline(scenario: dict[str, Any]) -> dict[str, Any]:
    starts = [tuple(map(float, p)) for p in scenario["uav_initial_positions_m"]]
    headings = [float(v) for v in scenario["uav_initial_headings_rad"]]
    half = (120.0 - 80.0) / 7.71
    centers = (40.0, 120.0, 200.0)
    midpoints = tuple(center / 7.71 for center in centers)
    bursts = tuple(midpoint - half for midpoint in midpoints)
    geometry = geometry_metrics(Schedule(centers, bursts, "Q3-B-chain"))
    candidates = [
        candidate_from(
            f"B-{index + 1}",
            centers,
            bursts,
            assignment,
            starts,
            headings,
            geometry,
        )
        for index, assignment in enumerate(itertools.permutations(range(3)))
    ]
    return min(
        candidates,
        key=lambda row: (
            row["lead_required_s"],
            row["total_path_length_m"],
            row["total_turn_angle_rad"],
        ),
    )
