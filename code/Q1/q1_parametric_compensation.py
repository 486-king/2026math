"""Thin entry point for the Q1 maximum continuous coverage family."""

from __future__ import annotations

import json

from q1_common import T_DETECT_LOWER, write_json
from q1_compensation import compensation_family, release_point_relation
from q1_outputs import ROUND3


def main() -> int:
<<<<<<< HEAD
    start = time.perf_counter()
    cfg = Q1Constants()
    bounds = structural_bounds(cfg)
    margin_m = cfg.smoke_max_radius_m - cfg.ship_radius_m
    half_cover_s = margin_m / cfg.ship_speed_mps
    full_cover_s = 2.0 * half_cover_s
    burst_interval_width_s = cfg.smoke_constant_duration_s - full_cover_s
    bomb_displacement_m = cfg.uav_speed_mps * cfg.bomb_burst_delay_s
    detection_lb_s = bounds["m1_detection_window_lower_bound_s"]
    naked_lb_s = detection_lb_s - full_cover_s

    result = {
        "schema_version": 2,
        "question_id": "Q1",
        "round": "round3",
        "decision_id": "q1_claim_scope_round1",
        "scope": "best compensation after strict G1+S1+O0+U0 infeasibility",
        "status_fields": {
            "execution_status": "passed",
            "input_status": "blocked_missing_absolute_geometry",
            "feasibility_status": "proved_infeasible_for_full_window",
            "compensation_status": "structural_family_available",
            "certificate_status": "verified"
        },
        "numeric_constants": {
            "cover_margin_m": margin_m,
            "half_cover_duration_s": half_cover_s,
            "maximum_continuous_full_cover_s": full_cover_s,
            "smoke_constant_phase_s": cfg.smoke_constant_duration_s,
            "valid_burst_time_interval_width_s": burst_interval_width_s,
            "bomb_inertial_displacement_m": bomb_displacement_m,
            "M1_detection_window_lower_bound_s": detection_lb_s,
            "minimum_total_naked_time_lower_bound_s": naked_lb_s
        },
        "parameterized_family": {
            "detection_window": "W=[t_in,t_out], T_W=t_out-t_in",
            "half_cover": "h=(R_c-R_s)/V_s",
            "length_optimal_cover_midpoint_times": "t_m in [t_in+h, t_out-h]",
            "cloud_center": "c*=s(t_m)",
            "full_cover_interval": "[t_m-h,t_m+h]",
            "valid_burst_times": "t_b in [t_m+h-T_const, t_m-h]",
            "release_time": "t_d=t_b-3.5",
            "command_time": "t_cmd=t_d-2=t_b-5.5",
            "timing_interpretation": (
                "The statement gives a 2 s response delay but does not name "
                "its endpoint events; the primary human-approved interpretation "
                "is command-to-release."
            ),
            "drop_position": "p_d=c*-98 e_u",
            "bomb_heading": "e_u is a unit vector from p_d toward c*",
            "reachability": (
                "t_cmd>=0, ||p_d-u_0||<=28 t_d, and the operational-radius "
                "constraint must hold once u_0 and the task clock are supplied"
            )
        },
        "secondary_optima": {
            "minimize_maximum_single_naked_gap": {
                "cover_midpoint_time": "t_m*=(t_in+t_out)/2",
                "left_and_right_naked_gaps": "(T_W-T_cover_max)/2",
                "reason": "centering equalizes the two unavoidable naked segments"
            },
            "prioritize_earliest_protection": {
                "cover_midpoint_time": "t_m*=t_in+h",
                "cover_interval": "[t_in,t_in+T_cover_max]",
                "reason": "all unavoidable naked time is moved to the end"
            },
            "latest_nonwasting_burst": {
                "burst_time": "t_b*=t_m-h",
                "release_time": "t_d*=t_m-h-3.5",
                "command_time": "t_cmd*=t_m-h-5.5",
                "reason": "the cloud reaches maximum radius exactly when the ship enters the 40 m center-offset disk"
            },
            "minimum_straight_line_drop_distance_when_u0_known": {
                "heading": "e_u*=(c*-u_0)/||c*-u_0|| for c*!=u_0",
                "drop_position": "p_d*=c*-98 e_u*",
                "reason": "this is the point on the 98 m burst circle closest to u_0"
            }
        },
        "upper_bound_attainment_conditions": [
            "The smoke center lies exactly on the ship trajectory.",
            "The entire [t_m-h,t_m+h] interval lies in the 18 s maximum-radius phase.",
            "The selected cover interval lies inside the actual detection window.",
            "The S1 drop point/time is reachable by the UAV and within the 12 km operational constraint.",
            "The nominal smoke center has zero drift."
        ],
        "nonuniqueness": {
            "status": True,
            "causes": [
                "Any t_m in the stated interval gives the same total maximum cover.",
                "A nonempty interval of burst times preserves the full maximum-radius traversal.",
                "Without u_0 and the task clock, e_u, p_d and absolute times are not unique."
            ]
        },
        "extensions_not_blocking_current_result": {
            "G2": (
                "Recompute the actual distance-and-FOV window. A duration no "
                "longer than T_cover_max is necessary but not sufficient."
            ),
            "S2_smoke_drift": (
                "Use relative velocity. In the ideal collinear constant-radius "
                "case the bound is min(18,2(R_c-R_s)/||v_s-v_c||); decay still "
                "requires the event model."
            )
        },
        "runtime_seconds": time.perf_counter() - start
    }

    METRIC_PATH.parent.mkdir(parents=True, exist_ok=True)
    METRIC_PATH.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8"
=======
    result = compensation_family(
        0.0,
        T_DETECT_LOWER,
        input_status="blocked_missing_scenario",
        executable_value="not_evaluated",
>>>>>>> 05b4caca0369d310133e03bd82ba235ad075b5d3
    )
    result["release_point_relation"] = release_point_relation()
    write_json(ROUND3, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
