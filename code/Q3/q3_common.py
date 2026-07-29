from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SCENARIO_PATH = ROOT / "workspace" / "data_clean" / "q3_standardized_scenario.json"
LABEL = "SYNTHETIC_SCENARIO_ONLY"


@dataclass(frozen=True)
class Constants:
    response_delay_s: float = 2.0
    burst_delay_s: float = 3.5
    ship_speed_mps: float = 7.71
    ship_radius_m: float = 80.0
    missile_speed_mps: float = 320.0
    lock_distance_m: float = 8000.0

    @property
    def command_to_burst_s(self) -> float:
        return self.response_delay_s + self.burst_delay_s

    @property
    def g1_window_upper_s(self) -> float:
        return (self.lock_distance_m - self.ship_radius_m) / (
            self.missile_speed_mps - self.ship_speed_mps
        )


CONSTANTS = Constants()


def load_scenario(path: Path = SCENARIO_PATH) -> dict[str, Any]:
    scenario = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "scenario_label",
        "task_clock_zero_definition",
        "ship_initial_position_m",
        "ship_heading_rad",
        "g1_lock_time_s",
        "uav_initial_positions_m",
        "uav_initial_headings_rad",
        "uav_available_times_s",
        "operation_radius_reference_points_m",
        "sensitivity_ranges",
    }
    missing = sorted(required - scenario.keys())
    if missing:
        raise ValueError(f"missing Q3 scenario fields: {missing}")
    if scenario["scenario_label"] != LABEL:
        raise ValueError("standardized Q3 scenario must retain SYNTHETIC_SCENARIO_ONLY")
    for key in (
        "uav_initial_positions_m",
        "uav_initial_headings_rad",
        "uav_available_times_s",
        "operation_radius_reference_points_m",
    ):
        if len(scenario[key]) != 3:
            raise ValueError(f"{key} must contain exactly three UAV records")
    return scenario


def event_feasibility_certificate(scenario: dict[str, Any]) -> dict[str, Any]:
    availability = [float(value) for value in scenario["uav_available_times_s"]]
    earliest_command = min(availability)
    earliest_release = earliest_command + CONSTANTS.response_delay_s
    earliest_burst = earliest_release + CONSTANTS.burst_delay_s
    window_start = float(scenario["g1_lock_time_s"])
    naked_duration = max(0.0, min(earliest_burst, CONSTANTS.g1_window_upper_s) - window_start)
    feasible_necessary_condition = earliest_burst <= window_start
    return {
        "scenario_label": LABEL,
        "event_chain": "t_cmd>=a_i; t_d=t_cmd+2; t_b=t_d+3.5",
        "defense_window_start_s": window_start,
        "defense_window_conservative_end_s": window_start
        + CONSTANTS.g1_window_upper_s,
        "minimum_availability_s": earliest_command,
        "earliest_command_s": earliest_command,
        "earliest_release_s": earliest_release,
        "earliest_burst_s": earliest_burst,
        "guaranteed_initial_naked_interval_s": [window_start, earliest_burst],
        "guaranteed_initial_naked_duration_s": naked_duration,
        "necessary_availability_threshold_s": window_start
        - CONSTANTS.command_to_burst_s,
        "necessary_condition": "min_i(a_i)<=window_start-5.5",
        "necessary_condition_passes": feasible_necessary_condition,
        "full_window_defense_feasible": False
        if not feasible_necessary_condition
        else None,
        "proof": (
            "All smoke radii equal zero before their burst times. Since every "
            "command is issued no earlier than UAV availability, the first "
            "possible smoke appears at min(a_i)+5.5 s. If this is later than "
            "the lock-window start, the ship is necessarily uncovered on a "
            "nonempty continuous interval."
        ),
        "independent_of": [
            "uav initial positions",
            "uav initial headings",
            "d_safe",
            "missile bearing beta",
            "smoke union geometry after first burst",
        ],
        "certificate_status": "PASS",
    }
