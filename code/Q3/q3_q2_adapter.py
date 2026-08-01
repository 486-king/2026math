"""Read-only adapter to the committed Q2 physical and geometric implementation."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Sequence


Q2_DIR = Path(__file__).resolve().parents[1] / "Q2"
if str(Q2_DIR) not in sys.path:
    sys.path.insert(0, str(Q2_DIR))

from q2_baseline import construct_baseline  # noqa: E402
from q2_common import PARAMS, Q2Parameters, SmokePlan, smoke_radius  # noqa: E402
from q2_continuous_certificate import certify_continuous_window  # noqa: E402
from q2_geometry import (  # noqa: E402
    exact_collinear_section,
    high_precision_uncovered_area,
    union_margin_at_time,
)


T_WORST_S = PARAMS.detect_worst_upper_s


def assert_q2_parameter_contract() -> dict[str, Any]:
    expected = {
        "ship_speed_mps": 7.71,
        "ship_radius_m": 80.0,
        "missile_speed_mps": 320.0,
        "detection_distance_m": 8000.0,
        "uav_speed_mps": 28.0,
        "command_to_release_delay_s": 2.0,
        "release_to_burst_delay_s": 3.5,
        "inertial_displacement_m": 98.0,
        "smoke_max_radius_m": 120.0,
        "smoke_hold_s": 18.0,
        "smoke_decay_s": 5.0,
        "detect_worst_upper_s": 25.36104262064107,
    }
    observed = {
        key: float(getattr(PARAMS, key))
        for key in (
            "ship_speed_mps",
            "ship_radius_m",
            "missile_speed_mps",
            "detection_distance_m",
            "uav_speed_mps",
            "command_to_release_delay_s",
            "release_to_burst_delay_s",
            "smoke_max_radius_m",
            "smoke_hold_s",
            "smoke_decay_s",
        )
    }
    observed["inertial_displacement_m"] = PARAMS.inertial_displacement_m
    observed["detect_worst_upper_s"] = T_WORST_S
    mismatches = {
        key: {"expected": value, "observed": observed[key]}
        for key, value in expected.items()
        if abs(observed[key] - value) > 1e-12
    }
    if mismatches:
        raise ValueError(f"Q2 parameter contract mismatch: {mismatches}")
    return {
        "adapter_status": "verified_read_only_reuse",
        "q2_directory": "code/Q2",
        "parameters": observed,
        "mismatches": mismatches,
    }


def smoke_plans(records: Sequence[dict[str, Any]]) -> list[SmokePlan]:
    return [
        SmokePlan.from_burst(
            smoke_id=str(record.get("smoke_id", record.get("uav_id"))),
            center_m=float(record["smoke_center_m"]),
            t_b_s=float(record["t_b_s"]),
        )
        for record in records
    ]


__all__ = [
    "PARAMS",
    "Q2Parameters",
    "SmokePlan",
    "T_WORST_S",
    "assert_q2_parameter_contract",
    "certify_continuous_window",
    "construct_baseline",
    "exact_collinear_section",
    "high_precision_uncovered_area",
    "smoke_plans",
    "smoke_radius",
    "union_margin_at_time",
]
