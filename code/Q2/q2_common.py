from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable


@dataclass(frozen=True)
class Q2Constants:
    ship_speed_mps: float = 7.71
    ship_radius_m: float = 80.0
    smoke_max_radius_m: float = 120.0
    smoke_constant_duration_s: float = 18.0
    smoke_decay_duration_s: float = 5.0
    bomb_burst_delay_s: float = 3.5
    uav_speed_mps: float = 28.0
    min_drop_interval_s: float = 1.0
    conservative_response_interval_s: float = 2.0
    missile_speed_mps: float = 320.0
    detection_distance_m: float = 8000.0

    @property
    def smoke_total_duration_s(self) -> float:
        return self.smoke_constant_duration_s + self.smoke_decay_duration_s

    @property
    def single_cloud_cover_upper_s(self) -> float:
        return (
            2.0
            * (self.smoke_max_radius_m - self.ship_radius_m)
            / self.ship_speed_mps
        )

    @property
    def m1_detection_lower_s(self) -> float:
        return (
            self.detection_distance_m - self.ship_radius_m
        ) / (self.missile_speed_mps + self.ship_speed_mps)

    @property
    def m1_detection_upper_s(self) -> float:
        return (
            self.detection_distance_m - self.ship_radius_m
        ) / (self.missile_speed_mps - self.ship_speed_mps)


@dataclass(frozen=True)
class TwoBombCandidate:
    cloud_centers_m: tuple[float, float] = (0.0, 128.09582447)
    burst_times_s: tuple[float, float] = (-6.76157575, 4.06443896)
    window_start_s: float = -4.37575009


CONSTANTS = Q2Constants()
CANDIDATE = TwoBombCandidate()


def smoke_radius(age_s: float, constants: Q2Constants = CONSTANTS) -> float:
    if age_s < 0.0:
        return 0.0
    if age_s <= constants.smoke_constant_duration_s:
        return constants.smoke_max_radius_m
    if age_s <= constants.smoke_total_duration_s:
        return constants.smoke_max_radius_m * (
            constants.smoke_total_duration_s - age_s
        ) / constants.smoke_decay_duration_s
    return 0.0


def smoke_radius_at(t_s: float, burst_s: float) -> float:
    return smoke_radius(t_s - burst_s)


def candidate_window() -> tuple[float, float]:
    start = CANDIDATE.window_start_s
    return start, start + CONSTANTS.m1_detection_upper_s


def candidate_event_times() -> list[float]:
    start, end = candidate_window()
    events = {start, end}
    for burst in CANDIDATE.burst_times_s:
        events.update(
            {
                burst,
                burst + CONSTANTS.smoke_constant_duration_s,
                burst + CONSTANTS.smoke_total_duration_s,
            }
        )
    for center in CANDIDATE.cloud_centers_m:
        events.add(center / CONSTANTS.ship_speed_mps)
    return sorted(t for t in events if start <= t <= end)


def candidate_drop_times() -> tuple[float, float]:
    return tuple(
        b - CONSTANTS.bomb_burst_delay_s for b in CANDIDATE.burst_times_s
    )


def unique_sorted(values: Iterable[float], tol: float = 1e-12) -> list[float]:
    result: list[float] = []
    for value in sorted(values):
        if not result or abs(value - result[-1]) > tol:
            result.append(float(value))
    return result


def is_finite_sequence(values: Iterable[float]) -> bool:
    return all(math.isfinite(float(v)) for v in values)
