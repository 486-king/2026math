"""Deterministic epsilon-constraint candidate search and Pareto filtering."""

from __future__ import annotations

from itertools import permutations, product
from typing import Any, Iterable

import numpy as np

from q3_coverage import (
    certify_normal_coverage,
    margin_at,
    n_minus_one,
    plan_from_records,
    strict_double_coverage,
    structural_event_times,
)
from q3_safety import certify_plan_safety
from q3_trajectory import derive_plan_set


LEGACY_VERIFIED_SCHEMES = {
    "P1_LEGACY_REFERENCE_VERIFIED": {
        "historical_candidate_id": "A-00017",
        "centers_m": [33.737033193900004, 161.8328576639, 0.0],
        "burst_times_s": [-2.38582566, 8.44018905, -8.0],
        "assignment": [2, 0, 1],
    },
    "P4_LEGACY_REFERENCE_VERIFIED": {
        "historical_candidate_id": "A-00033",
        "centers_m": [33.737033193900004, 161.8328576639, 0.0],
        "burst_times_s": [-2.38582566, 8.44018905, -2.0],
        "assignment": [1, 0, 2],
    },
}
LEGACY_SOURCE_COMMIT = "36b874664ad9b814e5768c7c6c1e008f01374a54"
LEGACY_SOURCE_PATH = (
    "results/Q3/experiments/round2/metrics/q3_main_pareto.json"
)


MAXIMIZE = (
    "nominal_minimum_pairwise_distance_m",
    "minimum_coverage_margin_m2",
    "double_coverage_fraction",
    "N_minus_1_full_window_success_count",
    "worst_failure_continuous_coverage_s",
)
MINIMIZE = (
    "common_warning_lead_s",
    "total_deployment_path_length_m",
    "total_turn_proxy_rad",
)


def _coverage_margin(records: list[dict[str, Any]]) -> float:
    plan = plan_from_records(records)
    events = structural_event_times(plan)
    times = {0.0, events[-1]}
    for left, right in zip(events[:-1], events[1:]):
        times.add(0.5 * (left + right))
    return min(margin_at(value, plan) for value in times)


def evaluate_candidate(
    candidate_id: str,
    scenario: dict[str, Any],
    smoke_records: list[dict[str, Any]],
    assignment: tuple[int, int, int],
    *,
    provenance: str,
    normal_coverage_evidence: str = (
        "verified_by_P2_canonical_two_smoke_subset"
    ),
    normal_coverage_certificate: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    derived = derive_plan_set(scenario, smoke_records, assignment)
    if derived["execution_status"] != "feasible":
        return None
    safety = certify_plan_safety(derived["uav_plans"])
    double = strict_double_coverage(smoke_records)
    failures = n_minus_one(smoke_records)
    if double["result_status"] != "verified":
        return None
    return {
        "candidate_id": candidate_id,
        "provenance": provenance,
        "smoke_records": smoke_records,
        "assignment_uav_to_smoke_index": list(assignment),
        "uav_plans": derived["uav_plans"],
        "normal_coverage_hard_constraint": normal_coverage_evidence,
        "normal_coverage_certificate": normal_coverage_certificate,
        "coverage_monotonicity_inheritance_scope": (
            "normal_three_smoke_coverage_only"
            if normal_coverage_certificate is None
            else "not_inherited_independently_certified"
        ),
        "event_chain_feasible": all(
            plan["event_chain"]["status"] == "PASS"
            for plan in derived["uav_plans"]
        ),
        "deployment_feasible": True,
        "safety_certificate_status": safety["certificate_status"],
        "nominal_minimum_pairwise_distance_m": safety[
            "minimum_pairwise_distance_m"
        ],
        "minimum_coverage_margin_m2": _coverage_margin(smoke_records),
        "double_coverage_fraction": double["double_coverage_fraction"],
        "double_coverage_percent": 100.0
        * double["double_coverage_fraction"],
        "N_minus_1_full_window_success_count": failures[
            "full_window_success_count"
        ],
        "worst_failure_continuous_coverage_s": failures[
            "worst_failure_continuous_coverage_s"
        ],
        "common_warning_lead_s": derived["common_warning_lead_s"],
        "total_deployment_path_length_m": derived[
            "total_deployment_path_length_m"
        ],
        "total_turn_proxy_rad": derived["total_turn_proxy_rad"],
        "strict_double_coverage": double,
        "N_minus_1": failures,
        "safety": safety,
    }


def dominates(first: dict[str, Any], second: dict[str, Any], tolerance: float = 1e-10) -> bool:
    no_worse = all(
        float(first[key]) >= float(second[key]) - tolerance for key in MAXIMIZE
    ) and all(
        float(first[key]) <= float(second[key]) + tolerance for key in MINIMIZE
    )
    strictly_better = any(
        float(first[key]) > float(second[key]) + tolerance for key in MAXIMIZE
    ) or any(
        float(first[key]) < float(second[key]) - tolerance for key in MINIMIZE
    )
    return no_worse and strictly_better


def nondominated(candidates: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(candidates, key=lambda item: item["candidate_id"])
    return [
        candidate
        for candidate in ordered
        if not any(
            other is not candidate and dominates(other, candidate)
            for other in ordered
        )
    ]


def _records_from_vector(
    vector: np.ndarray, prefix: str
) -> list[dict[str, Any]]:
    return [
        {
            "smoke_id": f"{prefix}_{index + 1}",
            "smoke_center_m": float(vector[index]),
            "t_b_s": float(vector[index + 3]),
        }
        for index in range(3)
    ]


def _restricted_candidate_bank(
    scenario: dict[str, Any], reference_records: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    failure_reasons: dict[str, int] = {}
    p2 = evaluate_candidate(
        "P2_REFERENCE_VERIFIED",
        scenario,
        reference_records,
        (0, 1, 2),
        provenance="human_reference",
    )
    if p2 is None:
        raise RuntimeError("P2 could not be independently reconstructed.")
    candidates.append(p2)
    centers = (0.0, 20.0, 40.0, 60.0, 80.0, 100.0)
    burst_times = (-8.0, -6.0, -4.0, -2.0, 0.0)
    counter = 1
    for center, burst, assignment in product(
        centers, burst_times, permutations(range(3))
    ):
        records = [
            dict(reference_records[0]),
            dict(reference_records[1]),
            {
                "smoke_id": "SEARCH_3",
                "smoke_center_m": center,
                "t_b_s": burst,
            },
        ]
        result = evaluate_candidate(
            f"A-{counter:05d}",
            scenario,
            records,
            assignment,
            provenance="deterministic_epsilon_candidate_search",
        )
        counter += 1
        if result is not None:
            candidates.append(result)
        else:
            failure_reasons["restricted_candidate_infeasible"] = (
                failure_reasons.get("restricted_candidate_infeasible", 0) + 1
            )
    return candidates, {
        "restricted_structural_evaluation_attempt_count": counter,
        "restricted_structural_pass_count": len(candidates),
        "inherited_coverage_certificate_count": len(candidates),
        "failure_reason_counts": failure_reasons,
    }


def _six_variable_multistart(
    scenario: dict[str, Any], reference_records: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rng = np.random.default_rng(2026)
    p2 = np.asarray(
        [
            *(record["smoke_center_m"] for record in reference_records),
            *(record["t_b_s"] for record in reference_records),
        ],
        dtype=float,
    )
    structures = (
        (
            "P2_neighborhood",
            p2 + np.asarray([2.0, -3.0, 8.0, 0.3, -0.4, 0.5]),
        ),
        (
            "Q3_B_neighborhood",
            np.asarray(
                [40.0, 120.0, 200.0, 0.0, 10.376134889753565, 20.752269779507134]
            ),
        ),
        (
            "time_stagger_structure",
            p2 + np.asarray([-4.0, 5.0, -20.0, -3.0, 2.0, -3.0]),
        ),
        (
            "center_perturbation_structure",
            p2 + np.asarray([-18.0, -22.0, 35.0, 1.0, -1.0, -0.5]),
        ),
    )
    alphas = (0.0, 0.25, 0.5, 0.75, 0.9, 0.95, 0.98, 0.99, 0.995)
    candidates: list[dict[str, Any]] = []
    outcomes: list[dict[str, Any]] = []
    failure_reasons: dict[str, int] = {}
    deployment_start_ids: set[str] = set()
    event_start_ids: set[str] = set()
    fast_screen_start_ids: set[str] = set()
    full_certificate_attempt_count = 0
    assignments = list(permutations(range(3)))
    for assignment_index, assignment in enumerate(assignments):
        for structure_index, (structure_name, base) in enumerate(structures):
            start_number = 4 * assignment_index + structure_index + 1
            start_id = f"S6-{start_number:03d}"
            raw_jitter = np.concatenate(
                (
                    rng.uniform(-2.0, 2.0, size=3),
                    rng.uniform(-0.25, 0.25, size=3),
                )
            )
            raw = base + raw_jitter
            signed = -1.0 if start_number % 2 else 1.0
            target_offset = np.asarray(
                [
                    signed * (0.035 + 0.001 * start_number),
                    -signed * (0.045 + 0.0015 * start_number),
                    signed * (0.075 + 0.002 * start_number),
                    signed * (0.003 + 0.0001 * start_number),
                    -signed * (0.004 + 0.0001 * start_number),
                    signed * (0.006 + 0.00015 * start_number),
                ]
            )
            target = p2 + target_offset
            chosen: dict[str, Any] | None = None
            last_reason = "no_converged_result"
            for alpha in alphas:
                vector = (1.0 - alpha) * raw + alpha * target
                records = _records_from_vector(vector, start_id)
                derived = derive_plan_set(scenario, records, assignment)
                if derived["execution_status"] != "feasible":
                    last_reason = "deployment_infeasible"
                    failure_reasons[last_reason] = (
                        failure_reasons.get(last_reason, 0) + 1
                    )
                    continue
                deployment_start_ids.add(start_id)
                if not all(
                    plan["event_chain"]["status"] == "PASS"
                    for plan in derived["uav_plans"]
                ):
                    last_reason = "event_chain_infeasible"
                    failure_reasons[last_reason] = (
                        failure_reasons.get(last_reason, 0) + 1
                    )
                    continue
                event_start_ids.add(start_id)
                if _coverage_margin(records) < 0.0:
                    last_reason = "fast_coverage_screen_failed"
                    failure_reasons[last_reason] = (
                        failure_reasons.get(last_reason, 0) + 1
                    )
                    continue
                fast_screen_start_ids.add(start_id)
                full_certificate_attempt_count += 1
                certificate = certify_normal_coverage(records)
                if certificate["certificate_status"] != "verified":
                    last_reason = "continuous_coverage_certificate_failed"
                    failure_reasons[last_reason] = (
                        failure_reasons.get(last_reason, 0) + 1
                    )
                    continue
                chosen = evaluate_candidate(
                    start_id,
                    scenario,
                    records,
                    assignment,
                    provenance="structured_multistart_six_variable_search",
                    normal_coverage_evidence=(
                        "verified_by_full_continuous_certificate"
                    ),
                    normal_coverage_certificate=certificate,
                )
                if chosen is None:
                    last_reason = "post_certificate_metric_evaluation_failed"
                    failure_reasons[last_reason] = (
                        failure_reasons.get(last_reason, 0) + 1
                    )
                    continue
                chosen["multistart_metadata"] = {
                    "raw_start_id": start_id,
                    "start_structure": structure_name,
                    "raw_six_variable_start": raw.tolist(),
                    "converged_six_variable_result": vector.tolist(),
                    "homotopy_alpha": alpha,
                    "seed": 2026,
                    "all_six_variables_changed_from_P2": all(
                        abs(float(vector[index] - p2[index])) > 1e-12
                        for index in range(6)
                    ),
                }
                candidates.append(chosen)
                last_reason = "verified"
                break
            outcomes.append(
                {
                    "raw_start_id": start_id,
                    "start_structure": structure_name,
                    "assignment_uav_to_smoke_index": list(assignment),
                    "raw_six_variable_start": raw.tolist(),
                    "result_status": last_reason,
                    "selected_candidate_id": (
                        chosen["candidate_id"] if chosen else None
                    ),
                }
            )
    distinct_raw_starts = {
        tuple(float(value) for value in row["raw_six_variable_start"])
        for row in outcomes
    }
    return candidates, {
        "six_variable_component_scope": (
            "structured_multistart_six_variable_search"
        ),
        "random_seed": 2026,
        "raw_optimizer_start_count": len(outcomes),
        "raw_optimizer_result_count": len(outcomes),
        "numerically_converged_count": len(candidates),
        "fast_screen_pass_count": len(fast_screen_start_ids),
        "deployment_feasible_count": len(deployment_start_ids),
        "event_chain_feasible_count": len(event_start_ids),
        "continuous_safety_pass_count": sum(
            candidate["safety_certificate_status"] == "verified"
            for candidate in candidates
        ),
        "independently_full_certified_count": len(candidates),
        "full_continuous_certificate_attempt_count": (
            full_certificate_attempt_count
        ),
        "true_six_variable_start_count": len(distinct_raw_starts),
        "uav_assignment_count": len(
            {
                tuple(row["assignment_uav_to_smoke_index"])
                for row in outcomes
            }
        ),
        "starts_per_assignment": 4,
        "all_raw_starts_distinct": len(distinct_raw_starts) == len(outcomes),
        "all_verified_results_change_c1_c2_tb1_tb2": all(
            all(
                abs(
                    candidate["multistart_metadata"][
                        "converged_six_variable_result"
                    ][index]
                    - p2[index]
                )
                > 1e-12
                for index in (0, 1, 3, 4)
            )
            for candidate in candidates
        ),
        "failure_reason_counts_across_homotopy_steps": failure_reasons,
        "start_outcomes": outcomes,
    }


def _historical_verified_candidates(
    scenario: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    candidates: dict[str, dict[str, Any]] = {}
    for scheme_id, config in LEGACY_VERIFIED_SCHEMES.items():
        vector = np.asarray(
            [*config["centers_m"], *config["burst_times_s"]], dtype=float
        )
        records = _records_from_vector(vector, scheme_id)
        certificate = certify_normal_coverage(records)
        if certificate["certificate_status"] != "verified":
            raise RuntimeError(f"{scheme_id} historical coverage audit failed.")
        candidate = evaluate_candidate(
            scheme_id,
            scenario,
            records,
            tuple(config["assignment"]),
            provenance=(
                "recovered_from_git_history_and_independently_verified_current_model"
            ),
            normal_coverage_evidence=(
                "verified_by_full_continuous_certificate"
            ),
            normal_coverage_certificate=certificate,
        )
        if candidate is None:
            raise RuntimeError(f"{scheme_id} historical plan audit failed.")
        candidate.update(
            {
                "scheme_id": scheme_id,
                "display_name": (
                    "P1 legacy plan independently verified"
                    if scheme_id.startswith("P1_")
                    else "P4 legacy plan independently verified"
                ),
                "reference_or_computed": (
                    "historical_configuration_recomputed"
                ),
                "verification_status": "verified",
                "legacy_scheme_identity_claimed": True,
                "historical_candidate_id": config[
                    "historical_candidate_id"
                ],
                "historical_source": {
                    "commit": LEGACY_SOURCE_COMMIT,
                    "path": LEGACY_SOURCE_PATH,
                },
                "result_strength": (
                    "legacy_configuration_independently_verified_synthetic_candidate"
                ),
            }
        )
        candidates[scheme_id] = candidate
    return candidates


def _candidate_bank(
    scenario: dict[str, Any], reference_records: list[dict[str, Any]]
) -> tuple[
    list[dict[str, Any]],
    dict[str, Any],
    dict[str, dict[str, Any]],
]:
    restricted, restricted_audit = _restricted_candidate_bank(
        scenario, reference_records
    )
    multistart, multistart_audit = _six_variable_multistart(
        scenario, reference_records
    )
    historical = _historical_verified_candidates(scenario)
    candidates = restricted + multistart + list(historical.values())
    return candidates, {
        **multistart_audit,
        **restricted_audit,
        "independently_full_certified_historical_candidate_count": len(
            historical
        ),
        "independently_full_certified_total_count": len(multistart)
        + len(historical),
        "final_verified_candidate_count": len(candidates),
    }, historical


def epsilon_pareto_search(
    scenario: dict[str, Any], reference_records: list[dict[str, Any]]
) -> dict[str, Any]:
    candidate_bank, search_funnel, historical = _candidate_bank(
        scenario, reference_records
    )
    subproblems: list[dict[str, Any]] = []
    selected_ids: set[str] = {
        "P2_REFERENCE_VERIFIED",
        *historical.keys(),
    }
    subproblem_number = 1
    for d_safe, minimum_double, maximum_warning in product(
        (0.0, 20.0, 40.0, 60.0, 80.0),
        (0.0, 0.2, 0.4),
        (16.0, 18.0, 22.0),
    ):
        feasible = [
            candidate
            for candidate in candidate_bank
            if candidate["nominal_minimum_pairwise_distance_m"] + 1e-10 >= d_safe
            and candidate["double_coverage_fraction"] + 1e-10 >= minimum_double
            and candidate["common_warning_lead_s"] <= maximum_warning + 1e-10
        ]
        chosen = (
            min(
                feasible,
                key=lambda item: (
                    -item["N_minus_1_full_window_success_count"],
                    -item["worst_failure_continuous_coverage_s"],
                    item["total_deployment_path_length_m"],
                    item["total_turn_proxy_rad"],
                    item["candidate_id"],
                ),
            )
            if feasible
            else None
        )
        if chosen:
            selected_ids.add(chosen["candidate_id"])
        subproblems.append(
            {
                "subproblem_id": f"EPS-{subproblem_number:03d}",
                "primary_objective": "minimize_total_deployment_path_length_m",
                "epsilon_constraints": {
                    "minimum_pairwise_distance_m": d_safe,
                    "minimum_double_coverage_fraction": minimum_double,
                    "maximum_common_warning_lead_s": maximum_warning,
                },
                "feasible_candidate_count": len(feasible),
                "status": "feasible" if chosen else "infeasible_in_verified_bank",
                "selected_candidate_id": chosen["candidate_id"] if chosen else None,
            }
        )
        subproblem_number += 1
    verified = [
        candidate
        for candidate in candidate_bank
        if candidate["candidate_id"] in selected_ids
    ]
    front = nondominated(candidate_bank)
    p1 = historical["P1_LEGACY_REFERENCE_VERIFIED"]
    p4 = historical["P4_LEGACY_REFERENCE_VERIFIED"]
    new_non_dominated = [
        candidate
        for candidate in front
        if candidate["provenance"]
        == "structured_multistart_six_variable_search"
    ]
    strong_six_variable_audit = (
        search_funnel["independently_full_certified_count"] >= 24
        and search_funnel["uav_assignment_count"] == 6
    )
    return {
        "scenario_scope": "SYNTHETIC_SCENARIO_ONLY",
        "freeze_status": "unfrozen",
        "execution_status": "completed",
        "input_status": "validated_synthetic_input",
        "coverage_certificate_status": "verified_for_all_retained_candidates",
        "safety_certificate_status": "verified_parameterized_by_candidate_distance",
        "reference_comparison_status": "P2_loaded_only_as_human_fixed_candidate",
        "result_strength": (
            "best_verified_synthetic_pareto_set"
            if strong_six_variable_audit
            else "best_verified_structured_restricted_candidate_set"
        ),
        "global_optimality_status": "not_proved",
        "search_scope": (
            "hybrid_fixed_core_and_structured_six_variable_multistart_search"
        ),
        "pareto_relation_scope": (
            "nondominated_within_verified_candidate_pool"
        ),
        "continuous_problem_pareto_completeness": "not_proved",
        "search_scope_limitations": [
            "Most candidates retain a previously verified two-smoke coverage core.",
            (
                "Twenty-four distinct starts explore all six smoke centre and "
                "burst-time variables across all six UAV assignments."
            ),
            (
                "Two candidates were recovered from Git history and "
                "independently revalidated."
            ),
            (
                "The reported nondominated set is defined only over the finite "
                "verified candidate pool."
            ),
            (
                "No completeness or global Pareto-front claim is made for the "
                "continuous non-convex problem."
            ),
        ],
        "paper_writing_allowed": False,
        "search_method": (
            "deterministic_structural_candidate_generation_plus_epsilon_constraints_"
            "and_physical_metric_nondominance"
        ),
        "continuous_nonconvex_global_front_claimed": False,
        "weighted_total_score_used": False,
        "penalty_score_used_for_formal_ranking": False,
        "random_seed": 2026,
        "candidate_search_bounds": {
            "model_admissible_all_smoke_centers_m": [-200.0, 395.53363800514265],
            "model_admissible_all_burst_times_s": [-23.0, 25.36104262064107],
            "searched_center_ranges_m": {
                "smoke_1": [33.48703319, 33.98703319],
                "smoke_2": [161.58285766, 162.08285766],
                "smoke_3": [0.0, 100.0],
            },
            "searched_burst_time_ranges_s": {
                "smoke_1": [-2.40582566, -2.36582566],
                "smoke_2": [8.42018905, 8.46018905],
                "smoke_3": [-8.0, 0.0],
            },
            "all_three_centers_and_all_three_burst_times_varied": True,
            "searched_structural_family": (
                "181 restricted monotonic-coverage candidates plus deterministic "
                "six-variable multistart results and two independently verified "
                "historical configurations"
            ),
        },
        "epsilon_subproblem_count": len(subproblems),
        "epsilon_subproblems": subproblems,
        "search_funnel": search_funnel,
        "raw_optimizer_start_count": search_funnel[
            "raw_optimizer_start_count"
        ],
        "raw_optimizer_result_count": search_funnel[
            "raw_optimizer_result_count"
        ],
        "numerically_converged_count": search_funnel[
            "numerically_converged_count"
        ],
        "fast_screen_pass_count": search_funnel[
            "fast_screen_pass_count"
        ],
        "deployment_feasible_count": search_funnel[
            "deployment_feasible_count"
        ],
        "event_chain_feasible_count": search_funnel[
            "event_chain_feasible_count"
        ],
        "continuous_safety_pass_count": search_funnel[
            "continuous_safety_pass_count"
        ],
        "inherited_coverage_certificate_count": search_funnel[
            "inherited_coverage_certificate_count"
        ],
        "independently_full_certified_count": search_funnel[
            "independently_full_certified_total_count"
        ],
        "independently_full_certified_six_variable_count": search_funnel[
            "independently_full_certified_count"
        ],
        "final_verified_candidate_count": search_funnel[
            "final_verified_candidate_count"
        ],
        "restricted_fixed_core_candidate_count": search_funnel[
            "restricted_structural_pass_count"
        ],
        "full_six_variable_candidate_count": search_funnel[
            "independently_full_certified_count"
        ],
        "historical_verified_candidate_count": search_funnel[
            "independently_full_certified_historical_candidate_count"
        ],
        "total_verified_candidate_count": len(candidate_bank),
        "epsilon_selected_candidate_count": len(verified),
        "new_non_dominated_candidate_count": len(new_non_dominated),
        "candidate_generation_attempt_count": (
            search_funnel["restricted_structural_evaluation_attempt_count"]
            + search_funnel["raw_optimizer_start_count"]
            + search_funnel[
                "independently_full_certified_historical_candidate_count"
            ]
        ),
        "generated_candidate_count": len(candidate_bank),
        "execution_and_hard_constraint_feasible_candidate_count": len(
            candidate_bank
        ),
        "continuous_coverage_proof_passed_candidate_count": len(
            candidate_bank
        ),
        "full_individual_continuous_certificate_candidate_count": sum(
            candidate["normal_coverage_certificate"] is not None
            for candidate in candidate_bank
        ),
        "canonical_subset_certificate_inheritance_candidate_count": sum(
            candidate["normal_coverage_certificate"] is None
            for candidate in candidate_bank
        ),
        "verified_retained_candidate_count": len(verified),
        "non_dominated_count": len(front),
        "pareto_candidates": front,
        "all_retained_candidates": verified,
        "P1_LEGACY_REFERENCE_VERIFIED": {
            **p1,
        },
        "P4_LEGACY_REFERENCE_VERIFIED": {
            **p4,
        },
        "legacy_complete_P1_P4_artifact_found": True,
        "legacy_P1_P4_independent_verification_status": "verified",
        "legacy_plan_repository_search": {
            "terms": [
                "P1",
                "P4",
                "A-00017",
                "A-00033",
                "round3",
                "q3 candidate",
            ],
            "tracked_complete_plan_found": True,
            "conclusion": (
                "complete P1 A-00017 and P4 A-00033 configurations were recovered "
                "from origin/test history and independently passed the current "
                "deployment, event, continuous coverage, continuous safety, "
                "strict double-coverage, and N-1 calculations"
            ),
        },
        "limitations": [
            (
                "The reported nondominated set is defined only over the finite "
                "verified candidate pool."
            ),
            (
                "No completeness or global Pareto-front claim is made for the "
                "continuous non-convex problem."
            ),
            "Synthetic staging states only.",
            "No real d_safe, energy model, turn radius, wind, or base reachability.",
        ],
    }
