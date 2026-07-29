from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable

import numpy as np
from scipy.optimize import minimize_scalar
from shapely.geometry import Point
from shapely.ops import unary_union

from q2_common import (
    CANDIDATE,
    CONSTANTS,
    candidate_event_times,
    candidate_window,
    smoke_radius_at,
    unique_sorted,
)


NEG_INF = float("-inf")
POS_INF = float("inf")


def down(value: float) -> float:
    return math.nextafter(float(value), NEG_INF)


def up(value: float) -> float:
    return math.nextafter(float(value), POS_INF)


@dataclass(frozen=True)
class Interval:
    lo: float
    hi: float

    def __post_init__(self) -> None:
        if self.lo > self.hi:
            raise ValueError("invalid interval")

    @staticmethod
    def point(value: float) -> "Interval":
        return Interval(float(value), float(value))

    def __add__(self, other: "Interval | float") -> "Interval":
        other = as_interval(other)
        return Interval(down(self.lo + other.lo), up(self.hi + other.hi))

    __radd__ = __add__

    def __sub__(self, other: "Interval | float") -> "Interval":
        other = as_interval(other)
        return Interval(down(self.lo - other.hi), up(self.hi - other.lo))

    def __rsub__(self, other: "Interval | float") -> "Interval":
        return as_interval(other).__sub__(self)

    def __mul__(self, other: "Interval | float") -> "Interval":
        other = as_interval(other)
        products = (
            self.lo * other.lo,
            self.lo * other.hi,
            self.hi * other.lo,
            self.hi * other.hi,
        )
        return Interval(down(min(products)), up(max(products)))

    __rmul__ = __mul__

    def __truediv__(self, other: "Interval | float") -> "Interval":
        other = as_interval(other)
        if other.lo <= 0.0 <= other.hi:
            raise ZeroDivisionError("interval divisor contains zero")
        reciprocals = (1.0 / other.lo, 1.0 / other.hi)
        reciprocal = Interval(down(min(reciprocals)), up(max(reciprocals)))
        return self * reciprocal

    def square(self) -> "Interval":
        if self.lo <= 0.0 <= self.hi:
            low = 0.0
        else:
            low = min(self.lo * self.lo, self.hi * self.hi)
        high = max(self.lo * self.lo, self.hi * self.hi)
        return Interval(down(low), up(high))

    def max_abs(self) -> float:
        return up(max(abs(self.lo), abs(self.hi)))


def as_interval(value: Interval | float) -> Interval:
    return value if isinstance(value, Interval) else Interval.point(float(value))


def radius_interval(
    t_box: Interval,
    burst_s: float,
    phase: str,
) -> Interval:
    c = CONSTANTS
    if phase == "inactive":
        return Interval.point(0.0)
    if phase == "constant":
        return Interval.point(c.smoke_max_radius_m)
    if phase == "decay":
        age = t_box - burst_s
        return c.smoke_max_radius_m * (
            c.smoke_total_duration_s - age
        ) / c.smoke_decay_duration_s
    raise ValueError(f"unknown phase: {phase}")


def phase_for_open_segment(midpoint_s: float, burst_s: float) -> str:
    age = midpoint_s - burst_s
    if age < 0.0 or age > CONSTANTS.smoke_total_duration_s:
        return "inactive"
    if age <= CONSTANTS.smoke_constant_duration_s:
        return "constant"
    return "decay"


@dataclass
class CertifiedBox:
    start_s: float
    end_s: float
    mode: str
    lower_slack: float
    depth: int


def certify_box(
    start_s: float,
    end_s: float,
    phases: tuple[str, str],
) -> tuple[bool, str, float]:
    c = CONSTANTS
    centers = CANDIDATE.cloud_centers_m
    bursts = CANDIDATE.burst_times_s
    t = Interval(start_s, end_s)
    ship = c.ship_speed_mps * t
    a1 = ship - centers[0]
    a2 = ship - centers[1]
    r1 = radius_interval(t, bursts[0], phases[0])
    r2 = radius_interval(t, bursts[1], phases[1])

    single1 = down(r1.lo - c.ship_radius_m - a1.max_abs())
    single2 = down(r2.lo - c.ship_radius_m - a2.max_abs())
    best_mode = "single_1" if single1 >= single2 else "single_2"
    best_slack = max(single1, single2)
    if best_slack >= 0.0:
        return True, best_mode, best_slack

    if a1.lo <= 0.0 or a2.hi >= 0.0 or r1.lo <= 0.0 or r2.lo <= 0.0:
        return False, "unresolved", best_slack

    try:
        rs2 = c.ship_radius_m * c.ship_radius_m
        q1 = (r1.square() - a1.square() - rs2) / (2.0 * a1)
        q2 = (r2.square() - a2.square() - rs2) / (2.0 * a2)
    except ZeroDivisionError:
        return False, "unresolved", best_slack

    split_slacks = (
        down(q1.lo - q2.hi),
        down(q1.lo + c.ship_radius_m),
        down(c.ship_radius_m - q2.hi),
    )
    split_lower = min(split_slacks)
    if split_lower >= 0.0:
        return True, "joint_split", split_lower
    return False, "unresolved", max(best_slack, split_lower)


def fixed_time_spatial_slack_sq(t_s: float) -> tuple[float, float]:
    """Exact collinear cross-section minimum at a fixed time.

    Returns minimum squared half-height slack and the x-coordinate where it
    occurs. Nonnegative means the complete ship disk, including its interior,
    is covered by the smoke union.
    """
    c = CONSTANTS
    ship_x = c.ship_speed_mps * t_s
    left = ship_x - c.ship_radius_m
    right = ship_x + c.ship_radius_m
    centers = CANDIDATE.cloud_centers_m
    radii = [
        smoke_radius_at(t_s, burst)
        for burst in CANDIDATE.burst_times_s
    ]

    cuts = [left, right]
    for center, radius in zip(centers, radii):
        cuts.extend([center - radius, center + radius])
    c1, c2 = centers
    r1, r2 = radii
    if c1 != c2:
        equal_x = (
            r2 * r2 - r1 * r1 + c1 * c1 - c2 * c2
        ) / (2.0 * (c1 - c2))
        cuts.append(equal_x)
    cuts = [x for x in unique_sorted(cuts) if left <= x <= right]

    def slack_at(x: float) -> float:
        target_h2 = c.ship_radius_m**2 - (x - ship_x) ** 2
        smoke_h2 = max(
            radius**2 - (x - center) ** 2
            for center, radius in zip(centers, radii)
        )
        return smoke_h2 - target_h2

    candidates = [(slack_at(x), x) for x in cuts]
    for a, b in zip(cuts[:-1], cuts[1:]):
        midpoint = (a + b) / 2.0
        target_h2 = c.ship_radius_m**2 - (midpoint - ship_x) ** 2
        smoke_values = [
            radius**2 - (midpoint - center) ** 2
            for center, radius in zip(centers, radii)
        ]
        active = int(np.argmax(smoke_values))
        center = centers[active]
        radius = radii[active]
        # The active squared-height slack is linear in x, so endpoints suffice.
        for x in (a, b):
            target = c.ship_radius_m**2 - (x - ship_x) ** 2
            smoke = radius**2 - (x - center) ** 2
            candidates.append((smoke - target, x))
        if max(smoke_values) < 0.0 and target_h2 > 0.0:
            candidates.append((-target_h2, midpoint))

    return min(candidates, key=lambda item: item[0])


def exact_point_coverage(t_s: float) -> bool:
    return fixed_time_spatial_slack_sq(t_s)[0] >= -1e-9


def interval_certificate(
    max_depth: int = 60,
    min_width_s: float = 1e-10,
) -> dict:
    events = candidate_event_times()
    certified: list[CertifiedBox] = []
    unresolved: list[dict] = []

    for event in events:
        slack, x = fixed_time_spatial_slack_sq(event)
        if slack < -1e-8:
            unresolved.append(
                {
                    "start_s": event,
                    "end_s": event,
                    "depth": 0,
                    "reason": "event_point_uncovered",
                    "slack_sq_m2": slack,
                    "x_m": x,
                }
            )

    def visit(a: float, b: float, depth: int, phases: tuple[str, str]) -> None:
        passed, mode, lower = certify_box(a, b, phases)
        if passed:
            certified.append(CertifiedBox(a, b, mode, lower, depth))
            return
        if depth >= max_depth or b - a <= min_width_s:
            midpoint = (a + b) / 2.0
            slack, x = fixed_time_spatial_slack_sq(midpoint)
            unresolved.append(
                {
                    "start_s": a,
                    "end_s": b,
                    "depth": depth,
                    "reason": "interval_not_certified",
                    "midpoint_slack_sq_m2": slack,
                    "x_m": x,
                    "interval_lower_slack": lower,
                }
            )
            return
        midpoint = (a + b) / 2.0
        visit(a, midpoint, depth + 1, phases)
        visit(midpoint, b, depth + 1, phases)

    for a, b in zip(events[:-1], events[1:]):
        midpoint = (a + b) / 2.0
        phases = tuple(
            phase_for_open_segment(midpoint, burst)
            for burst in CANDIDATE.burst_times_s
        )
        visit(a, b, 0, phases)

    start, end = candidate_window()
    total_certified = sum(box.end_s - box.start_s for box in certified)
    return {
        "status": "PASS" if not unresolved else "FAIL",
        "window_start_s": start,
        "window_end_s": end,
        "window_length_s": end - start,
        "certified_box_count": len(certified),
        "unresolved_box_count": len(unresolved),
        "total_certified_box_width_s": total_certified,
        "minimum_interval_lower_slack": (
            min(box.lower_slack for box in certified) if certified else None
        ),
        "maximum_certified_box_width_s": (
            max(box.end_s - box.start_s for box in certified)
            if certified
            else None
        ),
        "maximum_depth_used": max((box.depth for box in certified), default=0),
        "mode_counts": {
            mode: sum(box.mode == mode for box in certified)
            for mode in ("single_1", "joint_split", "single_2")
        },
        "unresolved": unresolved,
    }


def independent_adaptive_validation() -> dict:
    events = candidate_event_times()
    start, end = candidate_window()
    phase_points = unique_sorted([start, *events, end])
    candidates: list[tuple[float, float, float]] = []

    def objective(t: float) -> float:
        return fixed_time_spatial_slack_sq(float(t))[0]

    for t in phase_points:
        slack, x = fixed_time_spatial_slack_sq(t)
        candidates.append((slack, t, x))

    # Independent adaptive scalar minimization on each continuous phase.
    for a, b in zip(phase_points[:-1], phase_points[1:]):
        if b - a <= 1e-12:
            continue
        grid = np.linspace(a, b, 65)
        values = np.array([objective(t) for t in grid])
        local_indices = {
            0,
            len(grid) - 1,
            *(
                i
                for i in range(1, len(grid) - 1)
                if values[i] <= values[i - 1] and values[i] <= values[i + 1]
            ),
        }
        for i in sorted(local_indices):
            lo = grid[max(0, i - 1)]
            hi = grid[min(len(grid) - 1, i + 1)]
            if hi - lo <= 1e-14:
                continue
            result = minimize_scalar(
                objective,
                bounds=(lo, hi),
                method="bounded",
                options={"xatol": 1e-12, "maxiter": 500},
            )
            slack, x = fixed_time_spatial_slack_sq(float(result.x))
            candidates.append((slack, float(result.x), x))

    min_slack, min_time, min_x = min(candidates, key=lambda item: item[0])

    critical_times = unique_sorted(
        [
            *phase_points,
            min_time,
            max(start, min_time - 1e-6),
            min(end, min_time + 1e-6),
        ]
    )
    difference_areas = []
    for t in critical_times:
        ship_x = CONSTANTS.ship_speed_mps * t
        ship_disk = Point(ship_x, 0.0).buffer(
            CONSTANTS.ship_radius_m, quad_segs=512
        )
        smoke_disks = []
        for center, burst in zip(
            CANDIDATE.cloud_centers_m, CANDIDATE.burst_times_s
        ):
            radius = smoke_radius_at(t, burst)
            if radius > 0.0:
                smoke_disks.append(Point(center, 0.0).buffer(radius, quad_segs=512))
        union = unary_union(smoke_disks) if smoke_disks else Point().buffer(0)
        difference_areas.append(
            {
                "time_s": t,
                "uncovered_area_m2": float(ship_disk.difference(union).area),
            }
        )

    return {
        "status": (
            "PASS"
            if min_slack >= -1e-7
            and max(item["uncovered_area_m2"] for item in difference_areas) <= 1e-6
            else "FAIL"
        ),
        "minimum_squared_cross_section_slack_m2": min_slack,
        "minimum_time_s": min_time,
        "minimum_global_x_m": min_x,
        "critical_time_count": len(critical_times),
        "maximum_shapely_uncovered_area_m2": max(
            item["uncovered_area_m2"] for item in difference_areas
        ),
        "disk_difference_checks": difference_areas,
    }


def run_continuous_validation() -> dict:
    interval = interval_certificate()
    independent = independent_adaptive_validation()
    agreement = interval["status"] == independent["status"] == "PASS"
    return {
        "method_id": "A",
        "role": "main_candidate_preoptimization_validation",
        "candidate": {
            "cloud_centers_m": list(CANDIDATE.cloud_centers_m),
            "burst_times_s": list(CANDIDATE.burst_times_s),
            "window": list(candidate_window()),
        },
        "interval_certificate": interval,
        "independent_geometry": independent,
        "validators_agree": agreement,
        "strict_relative_candidate_validated": agreement,
    }
