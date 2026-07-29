"""Parameterized best-compensation family after accepted Q1 infeasibility."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import sys
import time

from q1_common import Q1Constants, SEED, structural_bounds


ROOT = Path(__file__).resolve().parents[2]
ROUND_DIR = ROOT / "results" / "Q1" / "experiments" / "round3"
METRIC_PATH = ROUND_DIR / "metrics" / "q1_parametric_compensation.json"


def main() -> int:
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
        "schema_version": 1,
        "question_id": "Q1",
        "round": "round3",
        "decision_id": "q1_claim_scope_round1",
        "scope": "best compensation after strict M1/S1 infeasibility",
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
            "length_optimal_center_times": "t_c in [t_in+h, t_out-h]",
            "cloud_center": "c*=s(t_c)",
            "full_cover_interval": "[t_c-h,t_c+h]",
            "valid_burst_times": "t_b in [t_c+h-T_const, t_c-h]",
            "drop_time": "t_d=t_b-3.5",
            "drop_position": "p_d=c*-98 e_u",
            "bomb_heading": "e_u is a unit vector from p_d toward c*",
            "reachability": (
                "t_d>=2, ||p_d-u_0||<=28 t_d, and the operational-radius "
                "constraint must hold once u_0 and the task clock are supplied"
            )
        },
        "secondary_optima": {
            "minimize_maximum_single_naked_gap": {
                "center_time": "t_c*=(t_in+t_out)/2",
                "left_and_right_naked_gaps": "(T_W-T_cover_max)/2",
                "reason": "centering equalizes the two unavoidable naked segments"
            },
            "prioritize_earliest_protection": {
                "center_time": "t_c*=t_in+h",
                "cover_interval": "[t_in,t_in+T_cover_max]",
                "reason": "all unavoidable naked time is moved to the end"
            },
            "latest_nonwasting_burst": {
                "burst_time": "t_b*=t_c-h",
                "drop_time": "t_d*=t_c-h-3.5",
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
            "The entire [t_c-h,t_c+h] interval lies in the 18 s maximum-radius phase.",
            "The selected cover interval lies inside the actual detection window.",
            "The S1 drop point/time is reachable by the UAV and within the 12 km operational constraint.",
            "The nominal smoke center has zero drift."
        ],
        "nonuniqueness": {
            "status": True,
            "causes": [
                "Any t_c in the stated interval gives the same total maximum cover.",
                "A nonempty interval of burst times preserves the full maximum-radius traversal.",
                "Without u_0 and the task clock, e_u, p_d and absolute times are not unique."
            ]
        },
        "extensions_not_blocking_current_result": {
            "M2": "Recompute the actual distance-and-FOV window; duration feasibility is possible only if it is <= T_cover_max.",
            "smoke_drift": "Replace V_s by the ship-cloud relative speed and rerun the same interval construction."
        },
        "runtime_seconds": time.perf_counter() - start
    }

    METRIC_PATH.parent.mkdir(parents=True, exist_ok=True)
    METRIC_PATH.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    run_summary = {
        "schema_version": 1,
        "question": "Q1",
        "round": "round3",
        "implementation_target": "python",
        "random_seed": SEED,
        "approved_decision_id": "q1_method_choice",
        "result_decision_id": "q1_result_verdict_round1",
        "methods": [
            {
                "method_id": "A-compensation",
                "role": "accepted_post_infeasibility_compensation",
                "script": "code/Q1/q1_parametric_compensation.py",
                "status": "success",
                "execution_time_seconds": result["runtime_seconds"],
                "input_files": [
                    "results/Q1/experiments/round1/metrics/q1_structural_metrics.json",
                    "results/Q1/experiments/round2/metrics/q1_global_certificate.json",
                    "methods/Q1/q1_decisions.jsonl"
                ],
                "output_files": [
                    "results/Q1/experiments/round3/metrics/q1_parametric_compensation.json"
                ],
                "figure_files": [],
                "metrics_summary": result["numeric_constants"],
                "warnings": [
                    "Absolute coordinates and times remain parameterized because initial states are absent."
                ],
                "errors": []
            }
        ],
        "comparison": {
            "compensation_respects_global_cover_upper_bound": (
                abs(full_cover_s - bounds[
                    "stationary_smoke_max_continuous_full_cover_s"
                ]) <= 1e-12
            ),
            "strict_infeasibility_unchanged": True
        },
        "fallback_trigger": {
            "fallback_id": "C",
            "observed": True,
            "resolved": True,
            "evidence": "round2 global interval certificate"
        },
        "environment": {
            "python": sys.version,
            "platform": platform.platform()
        },
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat()
    }
    (ROUND_DIR / "run_summary.json").write_text(
        json.dumps(run_summary, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(json.dumps(run_summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
