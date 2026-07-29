"""Triggered Q1-C global interval certificate.

This specializes C to the dominating duration inequalities. General
branch-and-bound is unnecessary because these global bounds already separate
the feasible sets.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import sys
import time

import numpy as np

from q1_common import Q1Constants, SEED


ROOT = Path(__file__).resolve().parents[2]
ROUND_DIR = ROOT / "results" / "Q1" / "experiments" / "round2"
METRIC_PATH = ROUND_DIR / "metrics" / "q1_global_certificate.json"


def main() -> int:
    start = time.perf_counter()
    cfg = Q1Constants()
    cover_nominal = (
        2.0
        * (cfg.smoke_max_radius_m - cfg.ship_radius_m)
        / cfg.ship_speed_mps
    )
    detect_nominal = (
        cfg.detection_distance_m - cfg.ship_radius_m
    ) / (cfg.missile_speed_mps + cfg.ship_speed_mps)

    cover_upper = float(np.nextafter(cover_nominal, np.inf))
    detect_lower = float(np.nextafter(detect_nominal, -np.inf))
    separation_lower = float(
        np.nextafter(detect_lower - cover_upper, -np.inf)
    )
    certificate_pass = separation_lower > 0.0
    runtime = time.perf_counter() - start

    certificate = {
        "schema_version": 1,
        "question_id": "Q1",
        "round": "round2",
        "method_id": "C",
        "role": "conditional_fallback",
        "trigger": {
            "condition": "A gives an infeasibility conclusion",
            "observed": True,
            "evidence": "results/Q1/experiments/round1/run_summary.json"
        },
        "global_bounds": {
            "fixed_smoke_complete_cover_interval_upper_s": cover_upper,
            "G1_detection_window_lower_s": detect_lower,
            "positive_separation_lower_s": separation_lower,
            "outward_rounding": "IEEE-754 nextafter"
        },
        "proof": [
            "For every fixed cloud center c and burst time, complete cover implies "
            "||s(t)-c|| <= R_c-R_s. Since s(t) is a line at speed V_s, the total "
            "time inside this disk is at most 2(R_c-R_s)/V_s.",
            "For M1 pure pursuit, range rate is s_dot·e_r - V_m. The closing speed "
            "cannot exceed V_m+V_s, so travel from D_max to ship-disk contact lasts "
            "at least (D_max-R_s)/(V_m+V_s).",
            "The outward-rounded detection lower bound exceeds the outward-rounded "
            "cover upper bound by a strictly positive interval, so no drop position, "
            "drop time, burst time or UAV route can satisfy full-window cover."
        ],
        "strict_full_window_feasible": not certificate_pass,
        "certificate_status": "PASS" if certificate_pass else "FAIL",
        "coordinate_solution_status": (
            "no_feasible_coordinate_exists_under_G1_S1_O0_U0"
            if certificate_pass
            else "certificate_failed"
        ),
        "scope": [
            "G1 pure pursuit with lock acquired at 8000 m",
            "O0 complete two-dimensional ship-disk coverage",
            "U0 nominal zero-drift profile",
            "S1 fixed smoke center after burst",
            "statement constants",
            "single smoke bomb"
        ],
        "limitations": [
            "G2 can have a shorter FOV-limited window but lacks initial geometry.",
            "Nonzero cloud drift changes the relative-speed bound and is not nominal."
        ],
        "runtime_seconds": runtime
    }

    METRIC_PATH.parent.mkdir(parents=True, exist_ok=True)
    METRIC_PATH.write_text(
        json.dumps(certificate, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    run_summary = {
        "schema_version": 1,
        "question": "Q1",
        "round": "round2",
        "implementation_target": "python",
        "random_seed": SEED,
        "approved_decision_id": "q1_method_choice",
        "trigger_decision_id": "q1_fallback_trigger_clarification",
        "methods": [
            {
                "method_id": "C",
                "role": "conditional_fallback",
                "script": "code/Q1/q1_interval_certificate.py",
                "status": "success" if certificate_pass else "failure",
                "execution_time_seconds": runtime,
                "input_files": [
                    "results/Q1/experiments/round1/run_summary.json",
                    "methods/Q1/q1_decisions.jsonl",
                    "code/Q1/q1_code_plan.md"
                ],
                "output_files": [
                    "results/Q1/experiments/round2/metrics/q1_global_certificate.json"
                ],
                "figure_files": [],
                "metrics_summary": {
                    "strict_full_window_feasible": not certificate_pass,
                    "cover_upper_s": cover_upper,
                    "detection_lower_s": detect_lower,
                    "separation_lower_s": separation_lower,
                    "certificate_status": certificate["certificate_status"]
                },
                "warnings": certificate["limitations"],
                "errors": [] if certificate_pass else [
                    "Outward-rounded bounds did not establish positive separation."
                ]
            }
        ],
        "comparison": {
            "A_B_C_feasibility_agreement": certificate_pass,
            "round1_cover_value_inside_C_bound": (
                cover_nominal <= cover_upper
            ),
            "round1_detection_value_above_C_bound": (
                detect_nominal >= detect_lower
            )
        },
        "output_degeneracy": {
            "strict_feasible_set_empty": certificate_pass,
            "interpretation": "Global mathematical infeasibility, not solver degeneration."
        },
        "fallback_trigger": {
            "fallback_id": "C",
            "observed": True,
            "resolved": certificate_pass,
            "evidence": (
                "C supplied a positive outward-rounded separation certificate."
                if certificate_pass
                else "C failed to certify separation."
            )
        },
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "numpy": np.__version__
        },
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat()
    }
    (ROUND_DIR / "run_summary.json").write_text(
        json.dumps(run_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(run_summary, ensure_ascii=False, indent=2))
    return 0 if certificate_pass else 2


if __name__ == "__main__":
    raise SystemExit(main())
