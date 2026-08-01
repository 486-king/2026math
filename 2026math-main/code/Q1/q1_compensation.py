"""Maximum-continuous-coverage compensation family for one fixed smoke."""

from __future__ import annotations

from typing import Any

from q1_common import (
    BURST_INTERVAL_WIDTH,
    TAU_BURST,
    TAU_HOLD,
    TAU_RESPONSE,
    T_STRUCTURAL_MAX,
    h,
)


def event_intervals_for_midpoint(t_m: float) -> dict[str, Any]:
    t_m = float(t_m)
    coverage = [t_m - h, t_m + h]
    t_b = [t_m + h - TAU_HOLD, t_m - h]
    t_d = [value - TAU_BURST for value in t_b]
    t_cmd = [value - TAU_RESPONSE for value in t_d]
    representative_burst = sum(t_b) / 2.0
    return {
        "t_m_s": t_m,
        "cloud_center_relation": "c_star = ship_position(t_m)",
        "full_coverage_interval_s": coverage,
        "t_b_interval_s": t_b,
        "t_d_interval_s": t_d,
        "t_cmd_interval_s": t_cmd,
        "interval_widths_s": {
            "full_coverage": coverage[1] - coverage[0],
            "t_b": t_b[1] - t_b[0],
            "t_d": t_d[1] - t_d[0],
            "t_cmd": t_cmd[1] - t_cmd[0],
        },
        "representative_only": {
            "selection": "midpoint_of_admissible_t_b_interval",
            "t_b_s": representative_burst,
            "t_d_s": representative_burst - TAU_BURST,
            "t_cmd_s": representative_burst - TAU_BURST - TAU_RESPONSE,
            "not_unique": True,
        },
    }


def compensation_family(
    t_in: float | None = None,
    t_out: float | None = None,
    *,
    input_status: str = "blocked_missing_scenario",
    executable_value: float | str = "not_evaluated",
) -> dict[str, Any]:
    if t_in is None or t_out is None:
        return {
            "detect_window_parameterisation": "[t_in, t_out], with t_out-t_in >= 2h",
            "t_m_interval": "[t_in+h, t_out-h]",
            "cloud_center_relation": "c_star = ship_position(t_m)",
            "full_coverage_interval": "[t_m-h, t_m+h]",
            "t_b_interval": "[t_m+h-18, t_m-h]",
            "t_d_interval": "[t_m+h-21.5, t_m-h-3.5]",
            "t_cmd_interval": "[t_m+h-23.5, t_m-h-5.5]",
            "burst_interval_width_s": BURST_INTERVAL_WIDTH,
            "front_strategy": {
                "t_m": "t_in+h",
                "coverage": "[t_in, t_in+2h]",
                "t_b_interval": "[t_in+2h-18, t_in]",
            },
            "middle_strategy": {
                "t_m": "(t_in+t_out)/2",
                "coverage": "[(t_in+t_out)/2-h, (t_in+t_out)/2+h]",
                "t_b_interval": "[(t_in+t_out)/2+h-18, (t_in+t_out)/2-h]",
            },
            "rear_strategy": {
                "t_m": "t_out-h",
                "coverage": "[t_out-2h, t_out]",
                "t_b_interval": "[t_out-18, t_out-2h]",
            },
            "T_structural_max_s": T_STRUCTURAL_MAX,
            "T_executable_star": executable_value,
            "input_status": input_status,
            "attainment_conditions": [
                "detect window duration is at least 2h",
                "fixed cloud center equals ship_position(t_m)",
                "the selected t_b keeps [t_m-h,t_m+h] inside [t_b,t_b+18]",
                "all scenario execution constraints pass",
            ],
        }

    t_in = float(t_in)
    t_out = float(t_out)
    if t_out - t_in < T_STRUCTURAL_MAX:
        raise ValueError("Detection window is shorter than the structural maximum family.")
    front_mid = t_in + h
    middle_mid = (t_in + t_out) / 2.0
    rear_mid = t_out - h
    return {
        "detect_window_parameterisation": {
            "t_in_s": t_in,
            "t_out_s": t_out,
            "duration_s": t_out - t_in,
        },
        "t_m_interval_s": [front_mid, rear_mid],
        "cloud_center_relation": "c_star = ship_position(t_m)",
        "full_coverage_interval": "[t_m-h, t_m+h]",
        "t_b_interval": "[t_m+h-18, t_m-h]",
        "t_d_interval": "[t_m+h-21.5, t_m-h-3.5]",
        "t_cmd_interval": "[t_m+h-23.5, t_m-h-5.5]",
        "burst_interval_width_s": BURST_INTERVAL_WIDTH,
        "front_strategy": event_intervals_for_midpoint(front_mid),
        "middle_strategy": event_intervals_for_midpoint(middle_mid),
        "rear_strategy": event_intervals_for_midpoint(rear_mid),
        "T_structural_max_s": T_STRUCTURAL_MAX,
        "T_executable_star": executable_value,
        "input_status": input_status,
        "attainment_conditions": [
            "detect window duration is at least 2h",
            "fixed cloud center equals ship_position(t_m)",
            "the selected t_b keeps [t_m-h,t_m+h] inside [t_b,t_b+18]",
            "all scenario execution constraints pass",
        ],
    }


def release_point_relation() -> dict[str, Any]:
    return {
        "formula": "p_d = c - 98 e_u",
        "equivalent": "c = p_d + 98 e_u",
        "e_u_constraint": "||e_u||_2 = 1",
        "uniqueness": "parameterised_not_unique",
        "source_type": "derived_quantity",
        "derivation": "under S1 inertial-flight assumption: 28 m/s × 3.5 s = 98 m",
    }
