"""Structural-gap sensitivity without invented uncertainty distributions."""

from __future__ import annotations

from typing import Any

from q1_common import D_MAX, R_C, R_S, V_M, V_S


def structural_gap(
    *,
    R_c: float = R_C,
    R_s: float = R_S,
    V_s: float = V_S,
    V_m: float = V_M,
    D_max: float = D_MAX,
) -> float:
    return (float(D_max) - float(R_s)) / (float(V_m) + float(V_s)) - (
        2.0 * (float(R_c) - float(R_s)) / float(V_s)
    )


def gap_meaning(gap: float, tolerance: float = 1e-12) -> str:
    if gap > tolerance:
        return "full_window_structurally_infeasible_certificate_remains_valid"
    if gap < -tolerance:
        return "duration_necessary_condition_only_not_overall_feasibility"
    return "structural_flip_boundary"


def robustness_summary() -> dict[str, Any]:
    nominal = structural_gap()
    critical_cloud_radius = R_S + (
        V_S * (D_MAX - R_S) / (2.0 * (V_M + V_S))
    )
    return {
        "model_scope": "Q1_G1_S1_O0_U0_structural_sensitivity",
        "G_formula": "(D_max-R_s)/(V_m+V_s)-2(R_c-R_s)/V_s",
        "G_nominal_s": nominal,
        "nominal_meaning": gap_meaning(nominal),
        "sign_semantics": {
            "G>0": "single-smoke full-window structural infeasibility certificate remains valid",
            "G=0": "structural duration flip boundary",
            "G<0": "duration necessary condition passes; overall feasibility is not established",
        },
        "parameterised_interface": {
            "arguments": ["R_c", "R_s", "V_s", "V_m", "D_max"],
            "units": ["m", "m", "m/s", "m/s", "m"],
        },
        "analytic_flip_relation": "T_detect_lower = T_structural_max",
        "critical_R_c_given_other_nominal_parameters_m": critical_cloud_radius,
        "uncertainty_ranges": "not_supplied_not_invented",
        "wind_drift": "excluded_from_nominal_U0; formula interface only",
        "exploratory": False,
    }
