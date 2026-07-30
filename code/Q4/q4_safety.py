"""Analytic continuous minimum-distance checks for piecewise-linear motion."""

from __future__ import annotations

import math
from typing import Any


def position_on_segment(segment: dict[str, Any], time_s: float) -> tuple[float, float]:
    t0, t1 = float(segment["start_time_s"]), float(segment["end_time_s"])
    p0, p1 = segment["start_position_m"], segment["end_position_m"]
    if t1 <= t0:
        return float(p1[0]), float(p1[1])
    fraction = min(1.0, max(0.0, (time_s - t0) / (t1 - t0)))
    return (
        float(p0[0]) + fraction * (float(p1[0]) - float(p0[0])),
        float(p0[1]) + fraction * (float(p1[1]) - float(p0[1])),
    )


def continuous_segment_minimum_distance(
    first: dict[str, Any], second: dict[str, Any]
) -> tuple[float, float | None]:
    lo = max(float(first["start_time_s"]), float(second["start_time_s"]))
    hi = min(float(first["end_time_s"]), float(second["end_time_s"]))
    if lo > hi:
        return math.inf, None
    a0 = position_on_segment(first, lo)
    b0 = position_on_segment(second, lo)
    a1 = position_on_segment(first, hi)
    b1 = position_on_segment(second, hi)
    duration = hi - lo
    r0 = (a0[0] - b0[0], a0[1] - b0[1])
    if duration <= 1e-12:
        return math.hypot(*r0), lo
    velocity = (
        ((a1[0] - a0[0]) - (b1[0] - b0[0])) / duration,
        ((a1[1] - a0[1]) - (b1[1] - b0[1])) / duration,
    )
    speed_sq = velocity[0] ** 2 + velocity[1] ** 2
    tau = 0.0 if speed_sq <= 1e-18 else -(r0[0] * velocity[0] + r0[1] * velocity[1]) / speed_sq
    tau = min(duration, max(0.0, tau))
    dx = r0[0] + velocity[0] * tau
    dy = r0[1] + velocity[1] * tau
    return math.hypot(dx, dy), lo + tau


def trajectory_minimum_distance(
    first_segments: list[dict[str, Any]], second_segments: list[dict[str, Any]]
) -> tuple[float, float | None]:
    best = (math.inf, None)
    for first in first_segments:
        for second in second_segments:
            current = continuous_segment_minimum_distance(first, second)
            if current[0] < best[0]:
                best = current
    return best


def max_distance_from_home(segment: dict[str, Any], home: list[float]) -> float:
    # Squared distance to a fixed point is convex along a line, so its maximum
    # on a closed segment is attained at an endpoint.
    values = []
    for point in (segment["start_position_m"], segment["end_position_m"]):
        values.append(math.hypot(float(point[0]) - home[0], float(point[1]) - home[1]))
    return max(values)
