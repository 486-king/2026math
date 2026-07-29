"""Approved Q1-B analytic baseline."""

from __future__ import annotations

from q1_common import Q1Constants, structural_bounds


def run_baseline(cfg: Q1Constants) -> dict[str, object]:
    bounds = structural_bounds(cfg)
    return {
        "method_id": "B",
        "role": "usable_baseline",
        "strict_full_window_feasible": bounds[
            "strict_full_window_feasible_by_duration_necessary_condition"
        ],
        "detection_window_seconds": {
            "lower_bound": bounds["m1_detection_window_lower_bound_s"],
            "upper_bound": bounds["m1_detection_window_upper_bound_s"],
        },
        "maximum_continuous_full_cover_seconds": bounds[
            "stationary_smoke_max_continuous_full_cover_s"
        ],
        "minimum_naked_seconds": {
            "lower_bound": bounds["minimum_naked_time_lower_bound_s"]
        },
        "minimum_cover_margin_m": None,
        "coordinate_solution_status": "blocked_missing_scenario_inputs",
        "missing_inputs": [
            "ship_initial_position_m",
            "ship_heading_rad",
            "uav_initial_position_m",
            "task_clock_definition",
        ],
        "output_degeneracy": {
            "strict_feasible_set_empty_under_G1_S1_O0_U0_duration_bound": True,
            "unique_coordinate_identifiable": False,
        },
        "assumptions_used": [
            "G1 range-rate bound with lock acquired at 8000 m",
            "S1 stationary smoke center after burst",
        ],
        "analytic_relations": {
            "fixed_cloud_cover": "2*(R_c-R_s)/V_s",
            "minimum_detection_window": "(D_max-R_s)/(V_m+V_s)",
            "minimum_naked_time": "max(0,T_detect_LB-T_cover_UB)",
        },
        "proof_notes": bounds["proof_notes"],
    }
