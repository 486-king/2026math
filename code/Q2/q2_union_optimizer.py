from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

import numpy as np
from scipy.optimize import brentq, minimize_scalar

from q2_common import CONSTANTS, smoke_radius_at, unique_sorted


@dataclass(frozen=True)
class Schedule:
    centers_m: tuple[float, ...]
    burst_times_s: tuple[float, ...]
    label: str

    def __post_init__(self) -> None:
        if len(self.centers_m) != len(self.burst_times_s):
            raise ValueError("centres and burst times must have equal length")


def fixed_time_union_slack_sq(t_s: float, schedule: Schedule) -> tuple[float, float]:
    """Minimum exact cross-section squared-height slack at a fixed time."""
    c = CONSTANTS
    ship_x = c.ship_speed_mps * t_s
    radii = [smoke_radius_at(t_s, b) for b in schedule.burst_times_s]
    slopes = []
    intercepts = []
    for center, radius in zip(schedule.centers_m, radii):
        a = ship_x - center
        slopes.append(-2.0 * a)
        intercepts.append(radius * radius - c.ship_radius_m**2 - a * a)

    cuts = [-c.ship_radius_m, c.ship_radius_m]
    for j in range(len(slopes)):
        for k in range(j + 1, len(slopes)):
            denominator = slopes[j] - slopes[k]
            if abs(denominator) > 1e-14:
                xi = (intercepts[k] - intercepts[j]) / denominator
                if -c.ship_radius_m <= xi <= c.ship_radius_m:
                    cuts.append(float(xi))
    cuts = unique_sorted(cuts)

    candidates = []
    for xi in cuts:
        value = max(m * xi + q for m, q in zip(slopes, intercepts))
        candidates.append((float(value), float(xi)))
    return min(candidates, key=lambda item: item[0])


def schedule_events(schedule: Schedule, start_s: float, end_s: float) -> list[float]:
    events = {float(start_s), float(end_s)}
    for burst in schedule.burst_times_s:
        events.update(
            {
                burst,
                burst + CONSTANTS.smoke_constant_duration_s,
                burst + CONSTANTS.smoke_total_duration_s,
            }
        )
    return unique_sorted(t for t in events if start_s <= t <= end_s)


def adaptive_continuous_check(
    schedule: Schedule,
    start_s: float,
    end_s: float,
    dense_points: int = 20001,
) -> dict:
    """Independent phase-wise time check of the exact spatial envelope."""
    events = schedule_events(schedule, start_s, end_s)
    candidates: list[tuple[float, float, float, str]] = []
    for event in events:
        slack, xi = fixed_time_union_slack_sq(event, schedule)
        candidates.append((slack, event, xi, "event"))

    for left, right in zip(events[:-1], events[1:]):
        if right - left <= 1e-12:
            continue
        grid = np.linspace(left, right, 65)
        values = np.array(
            [fixed_time_union_slack_sq(float(t), schedule)[0] for t in grid]
        )
        indices = {0, len(grid) - 1, int(np.argmin(values))}
        indices.update(
            i
            for i in range(1, len(grid) - 1)
            if values[i] <= values[i - 1] and values[i] <= values[i + 1]
        )
        for i in sorted(indices):
            a = grid[max(0, i - 1)]
            b = grid[min(len(grid) - 1, i + 1)]
            if b > a:
                result = minimize_scalar(
                    lambda t: fixed_time_union_slack_sq(float(t), schedule)[0],
                    bounds=(float(a), float(b)),
                    method="bounded",
                    options={"xatol": 1e-12, "maxiter": 1000},
                )
                slack, xi = fixed_time_union_slack_sq(float(result.x), schedule)
                candidates.append((slack, float(result.x), xi, "phase_minimum"))

    fine_times = np.linspace(start_s, end_s, dense_points)
    fine_values = np.array(
        [fixed_time_union_slack_sq(float(t), schedule)[0] for t in fine_times]
    )
    fine_index = int(np.argmin(fine_values))
    best = min(candidates, key=lambda item: item[0])
    gap_count = int(np.count_nonzero(fine_values < -1e-7))
    return {
        "status": "PASS" if best[0] >= -1e-7 and gap_count == 0 else "FAIL",
        "start_s": start_s,
        "end_s": end_s,
        "duration_s": end_s - start_s,
        "adaptive_minimum_slack_sq_m2": best[0],
        "adaptive_minimum_time_s": best[1],
        "adaptive_minimum_ship_relative_x_m": best[2],
        "adaptive_minimum_source": best[3],
        "independent_fine_scan_minimum_slack_sq_m2": float(fine_values[fine_index]),
        "independent_fine_scan_minimum_time_s": float(fine_times[fine_index]),
        "fine_scan_negative_count": gap_count,
        "fine_scan_points": dense_points,
        "validators_agree": (best[0] >= -1e-7) == (gap_count == 0),
    }


def single_bomb_capacity() -> dict:
    c = CONSTANTS
    half = (c.smoke_max_radius_m - c.ship_radius_m) / c.ship_speed_mps
    schedule = Schedule((0.0,), (-half,), "one_bomb_analytic")
    start = -half
    end = half
    return {
        "schedule": schedule,
        "start_s": start,
        "end_s": end,
        "duration_s": end - start,
        "derivation": "2*(Rc-Rs)/Vs",
        "validation": adaptive_continuous_check(schedule, start, end),
    }


def _two_bomb_bridge_minimum(center_gap_m: float, half_s: float) -> tuple[float, float]:
    schedule = Schedule(
        (0.0, center_gap_m),
        (-half_s, half_s),
        "two_bomb_bridge_trial",
    )
    result = minimize_scalar(
        lambda t: fixed_time_union_slack_sq(float(t), schedule)[0],
        # The bridge begins when smoke 2 bursts and ends when its 18 s
        # constant-radius phase ends. Including the global covered-interval
        # endpoints would make the minimizer select the intentional zero
        # endpoint rather than the internal bridge bottleneck.
        bounds=(half_s, half_s + CONSTANTS.smoke_constant_duration_s),
        method="bounded",
        options={"xatol": 1e-12, "maxiter": 2000},
    )
    return float(result.fun), float(result.x)


def two_bomb_capacity() -> dict:
    c = CONSTANTS
    half = (c.smoke_max_radius_m - c.ship_radius_m) / c.ship_speed_mps

    def bridge_value(gap: float) -> float:
        return _two_bomb_bridge_minimum(gap, half)[0]

    gap = brentq(bridge_value, 150.0, 170.0, xtol=1e-12)
    bridge_slack, bridge_time = _two_bomb_bridge_minimum(gap, half)
    schedule = Schedule((0.0, gap), (-half, half), "two_bomb_tangent_frontier")

    def terminal_value(t: float) -> float:
        return fixed_time_union_slack_sq(t, schedule)[0]

    terminal = brentq(
        terminal_value,
        half + c.smoke_constant_duration_s,
        half + c.smoke_total_duration_s,
        xtol=1e-12,
    )
    start = -half
    validation = adaptive_continuous_check(schedule, start, terminal, 30001)
    return {
        "schedule": schedule,
        "start_s": start,
        "end_s": terminal,
        "duration_s": terminal - start,
        "center_gap_m": gap,
        "bridge_tangency_time_s": bridge_time,
        "bridge_tangency_slack_sq_m2": bridge_slack,
        "derivation": (
            "canonical collinear normalization; solve zero minimum bridge "
            "slack, then solve terminal decay containment root"
        ),
        "validation": validation,
        "claim_scope": "optimized canonical two-bomb collinear frontier",
    }


def _covered_components(times: np.ndarray, values: np.ndarray) -> list[tuple[int, int]]:
    covered = values >= -1e-7
    components: list[tuple[int, int]] = []
    start = None
    for i, flag in enumerate(covered):
        if flag and start is None:
            start = i
        if start is not None and (not flag or i == len(covered) - 1):
            end = i if flag and i == len(covered) - 1 else i - 1
            components.append((start, end))
            start = None
    return components


def refine_component(
    schedule: Schedule,
    coarse_start_s: float,
    coarse_end_s: float,
    search_left_s: float,
    search_right_s: float,
) -> tuple[float, float]:
    f = lambda t: fixed_time_union_slack_sq(float(t), schedule)[0]

    left = coarse_start_s
    if f(left) > 1e-7:
        probe = np.linspace(search_left_s, left, 1001)
        vals = [f(float(t)) for t in probe]
        for a, b, va, vb in zip(probe[:-1], probe[1:], vals[:-1], vals[1:]):
            if va < 0.0 <= vb:
                left = brentq(f, float(a), float(b), xtol=1e-12)

    right = coarse_end_s
    if f(right) > 1e-7:
        probe = np.linspace(right, search_right_s, 1001)
        vals = [f(float(t)) for t in probe]
        for a, b, va, vb in zip(probe[:-1], probe[1:], vals[:-1], vals[1:]):
            if va >= 0.0 > vb:
                right = brentq(f, float(a), float(b), xtol=1e-12)
                break
    return float(left), float(right)


def three_bomb_best_verified() -> dict:
    """Return the best stable candidate found by the recorded multi-start search.

    Search seeds 2031--2033 converged to about 42.52 s. Two nominally similar
    candidates contained small hidden gaps under the exact validator. The
    retained seed-2032 candidate is the one that survives exact validation.
    """
    c = CONSTANTS
    half = (c.smoke_max_radius_m - c.ship_radius_m) / c.ship_speed_mps
    schedule = Schedule(
        (0.0, 135.34710094, 247.85333129),
        (-half, half, 21.57781387),
        "three_bomb_seed_2032_best_verified",
    )
    search_left = -half - 1.0
    search_right = schedule.burst_times_s[-1] + c.smoke_total_duration_s + 1.0
    times = np.linspace(search_left, search_right, 80001)
    values = np.array(
        [fixed_time_union_slack_sq(float(t), schedule)[0] for t in times]
    )
    components = _covered_components(times, values)
    if not components:
        raise RuntimeError("three-bomb candidate has no covered component")
    component = max(components, key=lambda p: times[p[1]] - times[p[0]])
    start, end = refine_component(
        schedule,
        float(times[component[0]]),
        float(times[component[1]]),
        search_left,
        search_right,
    )
    validation = adaptive_continuous_check(schedule, start, end, 50001)
    return {
        "schedule": schedule,
        "start_s": start,
        "end_s": end,
        "duration_s": end - start,
        "search_seeds": [2031, 2032, 2033],
        "nominal_multistart_convergence_s": 42.52,
        "rejected_hidden_gap_candidates": 2,
        "validation": validation,
        "claim_scope": "best verified canonical collinear candidate; global optimum not proved",
        "global_upper_bound_available": False,
        "boundary_sensitive": True,
    }


def serializable_schedule(schedule: Schedule) -> dict:
    release_times = [
        b - CONSTANTS.bomb_burst_delay_s for b in schedule.burst_times_s
    ]
    command_times = [t - 2.0 for t in release_times]
    # Under the selected S1 interpretation and an inherited +x UAV heading,
    # the drop point is 3.5 s of horizontal flight before the fixed burst
    # centre. Translation does not affect consecutive transition distances.
    inherited_displacement = (
        CONSTANTS.uav_speed_mps * CONSTANTS.bomb_burst_delay_s
    )
    drop_points = [center - inherited_displacement for center in schedule.centers_m]
    transition_checks = []
    for j in range(len(release_times) - 1):
        dt = release_times[j + 1] - release_times[j]
        distance = abs(drop_points[j + 1] - drop_points[j])
        transition_checks.append(
            {
                "from_bomb": j + 1,
                "to_bomb": j + 2,
                "drop_time_gap_s": dt,
                "relative_drop_point_distance_m": distance,
                "uav_reachable_distance_m": CONSTANTS.uav_speed_mps * dt,
                "distance_slack_m": CONSTANTS.uav_speed_mps * dt - distance,
                "passes_1s_drop_interval": dt >= CONSTANTS.min_drop_interval_s,
                "passes_conservative_2s_interval": (
                    dt >= CONSTANTS.conservative_response_interval_s
                ),
            }
        )
    return {
        "label": schedule.label,
        "bomb_count": len(schedule.centers_m),
        "cloud_centers_m": list(schedule.centers_m),
        "burst_times_s": list(schedule.burst_times_s),
        "relative_command_times_s": command_times,
        "relative_release_times_s": release_times,
        "relative_drop_times_s": release_times,
        "relative_drop_times_s_note": (
            "Backward-compatible alias for relative_release_times_s"
        ),
        "relative_drop_points_m_assuming_inherited_plus_x_heading": drop_points,
        "transition_checks": transition_checks,
        "timing_interpretation": (
            "t_release=t_command+2; t_burst=t_release+3.5"
        ),
    }


def serialize_frontier_item(item: dict) -> dict:
    result = dict(item)
    result["schedule"] = serializable_schedule(result["schedule"])
    return result
