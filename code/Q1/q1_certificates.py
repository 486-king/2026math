"""Independent continuous-event, analytic, and outward-rounded certificates."""

from __future__ import annotations

import math
from typing import Any

from scipy.optimize import brentq

from q1_common import (
    D_MAX,
    R_C,
    R_S,
    T_DETECT_LOWER,
    T_NAKED_LOWER,
    T_STRUCTURAL_MAX,
    V_M,
    V_S,
    h,
)


def _outward_interval(value: float) -> dict[str, float]:
    return {
        "lower": math.nextafter(float(value), -math.inf),
        "upper": math.nextafter(float(value), math.inf),
    }


def continuous_event_certificate() -> dict[str, Any]:
    def margin_before(t: float) -> float:
        return R_C - abs(V_S * t) - R_S

    entry = brentq(margin_before, -2.0 * h, -0.25 * h, xtol=1e-14, rtol=1e-14)
    exit_ = brentq(margin_before, 0.25 * h, 2.0 * h, xtol=1e-14, rtol=1e-14)
    coverage_duration = exit_ - entry

    def distance_event(t: float) -> float:
        return D_MAX - (V_M + V_S) * t - R_S

    detection_end = brentq(distance_event, 0.0, 2.0 * T_DETECT_LOWER, xtol=1e-14, rtol=1e-14)
    gap = detection_end - coverage_duration
    return {
        "method": "continuous_roots_scipy_brentq",
        "scenario_type": "synthetic_validation",
        "structural_scenario": {
            "cloud_center": "reference_origin",
            "ship_path": "diameter_through_cloud_center",
            "entry_time_s": entry,
            "exit_time_s": exit_,
            "duration_s": coverage_duration,
            "root_residual_entry_m": margin_before(entry),
            "root_residual_exit_m": margin_before(exit_),
        },
        "detection_scenario": {
            "locked_distance_m": D_MAX,
            "configuration": "collinear_head_on_maximum_radial_closing_speed",
            "end_time_s": detection_end,
            "root_residual_m": distance_event(detection_end),
        },
        "separation_s": gap,
        "conclusion": "full_window_structurally_infeasible",
        "verified": (
            math.isclose(coverage_duration, T_STRUCTURAL_MAX, abs_tol=1e-12)
            and math.isclose(detection_end, T_DETECT_LOWER, abs_tol=1e-12)
            and gap > 0.0
        ),
    }


def analytic_certificate() -> dict[str, Any]:
    return {
        "method": "closed_form_analytic",
        "h_s": h,
        "T_structural_max_s": T_STRUCTURAL_MAX,
        "T_detect_lower_s": T_DETECT_LOWER,
        "T_naked_lower_s": T_NAKED_LOWER,
        "formulae": {
            "h": "(R_c-R_s)/V_s",
            "T_structural_max": "2(R_c-R_s)/V_s",
            "T_detect_lower": "(D_max-R_s)/(V_m+V_s)",
            "T_naked_lower": "T_detect_lower-T_structural_max",
        },
        "conclusion": "full_window_structurally_infeasible",
        "verified": T_STRUCTURAL_MAX < T_DETECT_LOWER,
    }


def interval_certificate() -> dict[str, Any]:
    structural = _outward_interval(T_STRUCTURAL_MAX)
    detect = _outward_interval(T_DETECT_LOWER)
    naked_lower = math.nextafter(detect["lower"] - structural["upper"], -math.inf)
    naked_upper = math.nextafter(detect["upper"] - structural["lower"], math.inf)
    verified = detect["lower"] - structural["upper"] > 0.0
    return {
        "method": "IEEE-754_math.nextafter_outward_rounding",
        "T_structural_max_interval_s": structural,
        "T_detect_lower_interval_s": detect,
        "T_naked_lower_interval_s": {"lower": naked_lower, "upper": naked_upper},
        "conservative_positive_separation_lower_s": naked_lower,
        "strict_check": "detect_lower_interval.lower - structural_interval.upper > 0",
        "strict_check_value_s": detect["lower"] - structural["upper"],
        "nondegenerate_intervals": (
            structural["lower"] < structural["upper"]
            and detect["lower"] < detect["upper"]
            and naked_lower < naked_upper
        ),
        "conclusion": "full_window_structurally_infeasible",
        "verified": verified,
    }


def build_global_certificate(locked_at_8000m: bool = True) -> dict[str, Any]:
    event = continuous_event_certificate()
    analytic = analytic_certificate()
    interval = interval_certificate()
    conclusions = {
        event["conclusion"],
        analytic["conclusion"],
        interval["conclusion"],
    }
    consistent = len(conclusions) == 1 and all(
        part["verified"] for part in (event, analytic, interval)
    )
    if not consistent:
        status = "failed"
    elif locked_at_8000m:
        status = "verified"
    else:
        status = "conditional"
    return {
        "model": "G1+S1+O0+U0",
        "locked_at_8000m": bool(locked_at_8000m),
        "lock_condition_note": (
            "The 8000 m detection-window lower-bound certificate is active."
            if locked_at_8000m
            else "The numerical detection-window certificate is conditional until lock at 8000 m is enabled."
        ),
        "event_certificate_A": event,
        "analytic_certificate_B": analytic,
        "interval_certificate_C": interval,
        "conclusion_consistency": consistent,
        "certificate_status": status,
    }
