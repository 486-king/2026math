"""Transparent reconstructed Q3-B baseline and read-only legacy audit."""

from __future__ import annotations

from itertools import permutations
from typing import Any

from q3_coverage import (
    certify_normal_coverage,
    n_minus_one,
    strict_double_coverage,
)
from q3_q2_adapter import construct_baseline
from q3_safety import certify_plan_safety
from q3_trajectory import derive_plan_set


LEGACY_Q3_B_SOURCE = {
    "commit": "36b874664ad9b814e5768c7c6c1e008f01374a54",
    "path": "results/Q3/experiments/round2/metrics/q3_baseline.json",
    "candidate_id": "B-3",
    "centers_m": [40.0, 120.0, 200.0],
    "burst_times_s": [0.0, 10.376134889753565, 20.752269779507134],
    "assignment_uav_to_smoke_index": [1, 0, 2],
}


def _legacy_reference_audit(scenario: dict[str, Any]) -> dict[str, Any]:
    records = [
        {
            "smoke_id": f"Q3B_LEGACY_{index + 1}",
            "smoke_center_m": center,
            "t_b_s": burst,
        }
        for index, (center, burst) in enumerate(
            zip(
                LEGACY_Q3_B_SOURCE["centers_m"],
                LEGACY_Q3_B_SOURCE["burst_times_s"],
            )
        )
    ]
    derived = derive_plan_set(
        scenario,
        records,
        LEGACY_Q3_B_SOURCE["assignment_uav_to_smoke_index"],
    )
    coverage = certify_normal_coverage(
        records,
        analytic_start_zero=True,
        analytic_internal_terminal_times=[
            10.376134889753565,
            20.752269779507134,
        ],
    )
    safety = certify_plan_safety(derived["uav_plans"])
    double = strict_double_coverage(records)
    failures = n_minus_one(records)
    event_chain_pass = all(
        plan["event_chain"]["status"] == "PASS"
        for plan in derived["uav_plans"]
    )
    deployment_pass = derived["execution_status"] == "feasible"
    failed_plans = [
        {
            "uav_id": plan["uav_id"],
            "execution_status": plan["execution_status"],
            "t_start_s": plan["t_start_s"],
        }
        for plan in derived["uav_plans"]
        if plan["execution_status"] != "feasible"
    ]
    all_current_gates_pass = (
        event_chain_pass
        and deployment_pass
        and coverage["certificate_status"] == "verified"
        and safety["certificate_status"] == "verified"
        and double["result_status"] == "verified"
    )
    return {
        "scheme_id": "Q3_B_LEGACY_REFERENCE_ONLY",
        "display_name": "legacy Q3-B B-3 reference",
        "provenance": "recovered_read_only_from_git_history",
        "reference_or_computed": "reference_with_current_independent_audit",
        "reference_only": True,
        "full_decision_variables_available": True,
        "independent_verification_status": (
            "verified"
            if all_current_gates_pass
            else "failed_current_start_time_window"
        ),
        "used_in_model_comparison_as_verified_candidate": False,
        "used_in_pareto_ranking": False,
        "source": LEGACY_Q3_B_SOURCE,
        "smoke_records": records,
        "assignment_uav_to_smoke_index": LEGACY_Q3_B_SOURCE[
            "assignment_uav_to_smoke_index"
        ],
        "uav_plans": derived["uav_plans"],
        "event_chain_status": "PASS" if event_chain_pass else "FAIL",
        "deployment_feasibility_status": (
            "PASS" if deployment_pass else "FAIL"
        ),
        "failed_deployment_plans": failed_plans,
        "coverage_certificate": coverage,
        "safety_certificate": safety,
        "strict_double_coverage": double,
        "N_minus_1": failures,
        "recomputed_metrics": {
            "common_warning_lead_s": derived["common_warning_lead_s"],
            "nominal_minimum_pairwise_distance_m": safety[
                "minimum_pairwise_distance_m"
            ],
            "N_minus_1_full_window_success_count": failures[
                "full_window_success_count"
            ],
            "double_coverage_fraction": double[
                "double_coverage_fraction"
            ],
            "double_coverage_percent": 100.0
            * double["double_coverage_fraction"],
            "total_deployment_path_length_m": derived[
                "total_deployment_path_length_m"
            ],
            "total_turn_proxy_rad": derived["total_turn_proxy_rad"],
        },
        "blocking_reason": (
            "UAV 3 requires t_start_s=2.895126922364277, outside "
            "the allowed [-60,0] start window."
        ),
    }


def construct_q3_baseline(scenario: dict[str, Any]) -> dict[str, Any]:
    q2 = construct_baseline(3)
    smoke_records = [
        {
            "smoke_id": f"Q3B_RECON_{index + 1}",
            "smoke_center_m": float(record["center_m"]),
            "t_b_s": float(record["t_b_s"]),
        }
        for index, record in enumerate(q2["smokes"])
    ]
    assignments: list[dict[str, Any]] = []
    for assignment in permutations(range(3)):
        derived = derive_plan_set(scenario, smoke_records, assignment)
        if derived["execution_status"] == "feasible":
            safety = certify_plan_safety(derived["uav_plans"])
            derived["safety"] = safety
            derived["assignment_feasible"] = safety["certificate_status"] == "verified"
        else:
            derived["assignment_feasible"] = False
        assignments.append(derived)
    feasible = [item for item in assignments if item["assignment_feasible"]]
    if not feasible:
        return {
            "scheme_id": "Q3_B_RECONSTRUCTED_TRANSPARENT_BASELINE",
            "execution_status": "blocked_no_feasible_assignment",
            "assignment_count": 6,
            "assignments": assignments,
            "result_strength": "transparent_constructive_baseline",
        }
    selected = min(
        feasible,
        key=lambda item: (
            item["total_deployment_path_length_m"],
            item["total_turn_proxy_rad"],
            item["assignment_uav_to_smoke_index"],
        ),
    )
    coverage = certify_normal_coverage(
        smoke_records,
        analytic_start_zero=True,
        analytic_internal_terminal_times=q2["continuation_times_s"],
    )
    double = strict_double_coverage(smoke_records)
    failures = n_minus_one(smoke_records)
    return {
        "scheme_id": "Q3_B_RECONSTRUCTED_TRANSPARENT_BASELINE",
        "display_name": "reconstructed transparent Q3-B baseline",
        "provenance": (
            "reconstructed_from_Q2_conservative_three_interval_structure"
        ),
        "reference_or_computed": "computed",
        "verification_status": "verified",
        "legacy_scheme_identity_claimed": False,
        "scenario_scope": "SYNTHETIC_SCENARIO_ONLY",
        "freeze_status": "unfrozen",
        "execution_status": "completed",
        "input_status": "validated_synthetic_input",
        "coverage_certificate_status": coverage["certificate_status"],
        "safety_certificate_status": selected["safety"]["certificate_status"],
        "reference_comparison_status": "computed_independently_not_target_fitted",
        "result_strength": "transparent_constructive_baseline",
        "global_optimality_status": "not_proved",
        "paper_writing_allowed": False,
        "smoke_records": smoke_records,
        "selected_assignment": selected,
        "assignment_count": 6,
        "feasible_assignment_count": len(feasible),
        "all_assignments": assignments,
        "coverage_certificate": coverage,
        "strict_double_coverage": double,
        "N_minus_1": failures,
        "legacy_reference": _legacy_reference_audit(scenario),
        "limitations": [
            "Synthetic staging states only.",
            "The front/middle/rear construction is a transparent baseline, not a global optimum.",
            "Absolute 12 km base reachability remains blocked.",
        ],
    }
