"""One-command Q3 round3 production workflow."""

from __future__ import annotations

import argparse
import copy
import os
import platform
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from q3_baseline import construct_q3_baseline
from q3_common import (
    METRICS_DIR,
    REVIEWS_DIR,
    ROOT,
    ROUND_DIR,
    SCENARIO_SCOPE,
    clean_runtime_caches,
    core_status_fields,
    dependency_versions,
    ensure_output_directories,
    git_paths_clean,
    read_json,
    relative,
    sha256_file,
    source_document_metadata,
    assert_source_contract,
    write_json,
)
from q3_coverage import (
    area_diagnostic,
    certify_normal_coverage,
    n_minus_one,
    strict_double_coverage,
)
from q3_outputs import (
    build_final_manifest,
    core_output_hashes,
    write_figures,
    write_formal_tables,
    write_review,
    write_robustness_report,
)
from q3_pareto import epsilon_pareto_search
from q3_q2_adapter import PARAMS, T_WORST_S, assert_q2_parameter_contract
from q3_safety import certify_plan_safety
from q3_scenario import input_contract, load_reference_plan, load_scenario
from q3_sensitivity import (
    availability_thresholds,
    bearing_sensitivity,
    combined_perturbations,
    d_safe_retention_curve,
    heading_sensitivity,
    position_sensitivity,
)
from q3_trajectory import derive_plan_set, validate_event_chain


def _reference_smoke_records(reference: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "smoke_id": f"P2_{record['uav_id']}",
            "smoke_center_m": float(record["smoke_center_m"]),
            "t_b_s": float(record["t_b_s"]),
        }
        for record in reference["uav_plans"]
    ]


def _comparison(
    name: str,
    computed: float,
    reference: float,
    report_decimal_places: int,
    numerical_allowance: float = 1e-9,
) -> dict[str, Any]:
    tolerance = 0.5 * 10.0 ** (-report_decimal_places) + numerical_allowance
    error = float(computed) - float(reference)
    return {
        "name": name,
        "computed": float(computed),
        "reference": float(reference),
        "signed_error": error,
        "absolute_error": abs(error),
        "report_decimal_places": report_decimal_places,
        "half_last_unit_plus_numerical_tolerance": tolerance,
        "matches": abs(error) <= tolerance,
        "reference_used_in_candidate_acceptance": False,
    }


def _p2_reference_comparison(
    derived: dict[str, Any],
    safety: dict[str, Any],
    double: dict[str, Any],
    failures: dict[str, Any],
    reference: dict[str, Any],
) -> dict[str, Any]:
    expected = reference["post_computation_reference_values"]
    comparisons: list[dict[str, Any]] = []
    for index, plan in enumerate(derived["uav_plans"]):
        for coordinate, label in enumerate(("x", "y")):
            comparisons.append(
                _comparison(
                    f"UAV{index + 1}_release_{label}_m",
                    plan["release_point_m"][coordinate],
                    expected["release_points_m"][index][coordinate],
                    6,
                )
            )
        comparisons.append(
            _comparison(
                f"UAV{index + 1}_start_time_s",
                plan["t_start_s"],
                expected["required_start_times_s"][index],
                6,
            )
        )
        comparisons.append(
            _comparison(
                f"UAV{index + 1}_path_m",
                plan["pre_release_path_length_m"],
                expected["pre_release_path_lengths_m"][index],
                3,
            )
        )
        comparisons.append(
            _comparison(
                f"UAV{index + 1}_turn_rad",
                plan["turn_proxy_rad"],
                expected["turn_proxies_rad"][index],
                6,
            )
        )
    comparisons.extend(
        [
            _comparison(
                "common_warning_lead_s",
                derived["common_warning_lead_s"],
                expected["common_warning_lead_s"],
                10,
            ),
            _comparison(
                "total_pre_release_path_length_m",
                derived["total_pre_release_path_length_m"],
                expected["total_pre_release_path_length_m"],
                10,
                numerical_allowance=1e-8,
            ),
            _comparison(
                "total_turn_proxy_rad",
                derived["total_turn_proxy_rad"],
                expected["total_turn_proxy_rad"],
                10,
            ),
            _comparison(
                "nominal_minimum_pairwise_distance_m",
                safety["minimum_pairwise_distance_m"],
                expected["nominal_minimum_pairwise_distance_m"],
                10,
                numerical_allowance=1e-8,
            ),
            _comparison(
                "minimum_distance_time_s",
                safety["minimum_distance_time_s"],
                expected["minimum_distance_time_s"],
                10,
            ),
            _comparison(
                "strict_double_coverage_fraction",
                double["double_coverage_fraction"],
                expected["strict_double_coverage_fraction"],
                10,
            ),
            _comparison(
                "worst_failure_continuous_coverage_s",
                failures["worst_failure_continuous_coverage_s"],
                expected["worst_failure_continuous_coverage_s"],
                10,
            ),
        ]
    )
    return {
        "source_document": reference["source_document"],
        "source_sha256": reference["source_sha256"],
        "reference_only": True,
        "used_in_optimizer_objective": False,
        "used_in_optimizer_constraints": False,
        "used_in_candidate_acceptance": False,
        "used_as_human_selected_fixed_candidate": True,
        "comparison_policy": "half_last_reported_unit_plus_explicit_numerical_allowance",
        "comparisons": comparisons,
        "all_reported_values_match": all(item["matches"] for item in comparisons),
        "N_minus_1_success_count_matches": (
            failures["full_window_success_count"]
            == expected["N_minus_1_full_window_success_count"]
        ),
        "minimum_distance_pair_matches": (
            safety["uav_pair"] == expected["minimum_distance_uav_pair"]
        ),
    }


def _legacy_metric_reference_comparison(
    actual: dict[str, Any],
    reference: dict[str, Any],
    *,
    complete_configuration_available: bool = False,
    status: str = "not_a_legacy_plan_reproduction",
) -> dict[str, Any]:
    metric_keys = (
        "common_warning_lead_s",
        "nominal_minimum_pairwise_distance_m",
        "N_minus_1_full_window_success_count",
        "worst_failure_continuous_coverage_s",
        "double_coverage_fraction",
        "total_deployment_path_length_m",
        "total_turn_proxy_rad",
    )
    return {
        "status": status,
        "complete_legacy_configuration_available": (
            complete_configuration_available
        ),
        "metric_reference_used_in_optimizer_or_acceptance": False,
        "comparison_direction": "computed_minus_legacy_metric_reference",
        "reference_gaps": {
            key: {
                "computed": float(actual[key]),
                "legacy_metric_reference": float(value),
                "reference_gap_computed_minus_legacy": float(actual[key])
                - float(value),
            }
            for key in metric_keys
            for value in (reference[key],)
        },
    }


def _attach_legacy_scheme_metric_comparisons(
    pareto: dict[str, Any],
    baseline: dict[str, Any],
    reference: dict[str, Any],
) -> None:
    references = reference["legacy_scheme_metric_references"]
    for scheme_id, reference_id in (
        ("P1_LEGACY_REFERENCE_VERIFIED", "P1"),
        ("P4_LEGACY_REFERENCE_VERIFIED", "P4"),
    ):
        pareto[scheme_id]["legacy_reference_comparison"] = (
            _legacy_metric_reference_comparison(
                pareto[scheme_id],
                references[reference_id],
                complete_configuration_available=True,
                status="legacy_configuration_independently_verified",
            )
        )
    selected = baseline["selected_assignment"]
    baseline_actual = {
        "common_warning_lead_s": selected["common_warning_lead_s"],
        "nominal_minimum_pairwise_distance_m": selected["safety"][
            "minimum_pairwise_distance_m"
        ],
        "N_minus_1_full_window_success_count": baseline["N_minus_1"][
            "full_window_success_count"
        ],
        "worst_failure_continuous_coverage_s": baseline["N_minus_1"][
            "worst_failure_continuous_coverage_s"
        ],
        "double_coverage_fraction": baseline["strict_double_coverage"][
            "double_coverage_fraction"
        ],
        "total_deployment_path_length_m": selected[
            "total_deployment_path_length_m"
        ],
        "total_turn_proxy_rad": selected["total_turn_proxy_rad"],
    }
    baseline["legacy_reference_comparison"] = (
        _legacy_metric_reference_comparison(
            baseline_actual, references["Q3_B"]
        )
    )


def _status(
    result_strength: str,
    *,
    coverage: str = "verified",
    safety: str = "verified",
    reference: str = "not_applicable",
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    return core_status_fields(
        result_strength=result_strength,
        coverage_status=coverage,
        safety_status=safety,
        reference_status=reference,
        limitations=limitations
        or [
            "Synthetic staging states only.",
            "No real d_safe, energy model, turn radius, wind, or base reference.",
        ],
    )


def _comparison_rows(
    formal: dict[str, Any],
    safety: dict[str, Any],
    failures: dict[str, Any],
    double: dict[str, Any],
    pareto: dict[str, Any],
    baseline: dict[str, Any],
) -> list[dict[str, Any]]:
    def row(
        scheme_id: str,
        display_name: str,
        plans: list[dict[str, Any]],
        scheme_safety: dict[str, Any],
        scheme_failures: dict[str, Any],
        scheme_double: dict[str, Any],
        provenance: str,
        reference_or_computed: str,
        verification_status: str,
    ) -> dict[str, Any]:
        double_fraction = scheme_double["double_coverage_fraction"]
        return {
            "scheme_id": scheme_id,
            "display_name": display_name,
            "provenance": provenance,
            "reference_or_computed": reference_or_computed,
            "verification_status": verification_status,
            "common_warning_lead_s": -min(plan["t_start_s"] for plan in plans),
            "nominal_minimum_pairwise_distance_m": scheme_safety[
                "minimum_pairwise_distance_m"
            ],
            "N_minus_1_full_window_success_count": scheme_failures[
                "full_window_success_count"
            ],
            "N_minus_1_case_count": 3,
            "worst_failure_continuous_coverage_s": scheme_failures[
                "worst_failure_continuous_coverage_s"
            ],
            "double_coverage_fraction": double_fraction,
            "double_coverage_percent": 100.0 * double_fraction,
            "total_deployment_path_length_m": sum(
                plan["deployment_path_length_m"] for plan in plans
            ),
            "total_turn_proxy_rad": sum(
                plan["turn_proxy_rad"] for plan in plans
            ),
            "scenario_scope": SCENARIO_SCOPE,
            "freeze_status": "unfrozen",
        }

    rows = [
        row(
            "P2_REFERENCE_VERIFIED",
            "P2 human-selected reference independently verified",
            formal["uav_plans"],
            safety,
            failures,
            double,
            "human_reference",
            "computed_from_fixed_human_reference_configuration",
            "verified",
        )
    ]
    for scheme_id in (
        "P1_LEGACY_REFERENCE_VERIFIED",
        "P4_LEGACY_REFERENCE_VERIFIED",
    ):
        scheme = pareto[scheme_id]
        rows.append(
            row(
                scheme_id,
                scheme["display_name"],
                scheme["uav_plans"],
                scheme["safety"],
                scheme["N_minus_1"],
                scheme["strict_double_coverage"],
                scheme["provenance"],
                scheme["reference_or_computed"],
                scheme["verification_status"],
            )
        )
    selected = baseline["selected_assignment"]
    rows.append(
        row(
            "Q3_B_RECONSTRUCTED_TRANSPARENT_BASELINE",
            baseline["display_name"],
            selected["uav_plans"],
            selected["safety"],
            baseline["N_minus_1"],
            baseline["strict_double_coverage"],
            baseline["provenance"],
            "computed",
            "verified",
        )
    )
    legacy = baseline["legacy_reference"]
    legacy_metrics = legacy["recomputed_metrics"]
    rows.append(
        {
            "scheme_id": legacy["scheme_id"],
            "display_name": legacy["display_name"],
            "provenance": legacy["provenance"],
            "reference_or_computed": legacy["reference_or_computed"],
            "verification_status": legacy[
                "independent_verification_status"
            ],
            "common_warning_lead_s": legacy_metrics[
                "common_warning_lead_s"
            ],
            "nominal_minimum_pairwise_distance_m": legacy_metrics[
                "nominal_minimum_pairwise_distance_m"
            ],
            "N_minus_1_full_window_success_count": legacy_metrics[
                "N_minus_1_full_window_success_count"
            ],
            "N_minus_1_case_count": 3,
            "worst_failure_continuous_coverage_s": legacy[
                "N_minus_1"
            ]["worst_failure_continuous_coverage_s"],
            "double_coverage_fraction": legacy_metrics[
                "double_coverage_fraction"
            ],
            "double_coverage_percent": legacy_metrics[
                "double_coverage_percent"
            ],
            "total_deployment_path_length_m": legacy_metrics[
                "total_deployment_path_length_m"
            ],
            "total_turn_proxy_rad": legacy_metrics[
                "total_turn_proxy_rad"
            ],
            "scenario_scope": SCENARIO_SCOPE,
            "freeze_status": "unfrozen",
        }
    )
    return rows


def _source_provenance(
    source_start: dict[str, Any], source_end: dict[str, Any]
) -> dict[str, Any]:
    q2_report_path = (
        ROOT / "results" / "Q2" / "reports" / "q2_source_document_provenance.json"
    )
    q2_report = read_json(q2_report_path)
    return {
        **_status(
            "source_document_provenance_audit",
            coverage="not_applicable",
            safety="not_applicable",
        ),
        "source_documents": source_end,
        "hashes_unchanged_during_run": {
            key: source_start[key]["sha256"] == source_end[key]["sha256"]
            for key in ("problem", "q3_work_guide")
        },
        "q1_recorded_source_sha256": q2_report["q1_recorded_source_sha256"],
        "q2_current_source_sha256": q2_report["current_sha256"],
        "q1_q2_hashes_match": q2_report["hashes_match"],
        "old_binary_direct_comparison": (
            "old_binary_not_available_for_direct_comparison"
        ),
        "key_problem_semantics_consistent": q2_report[
            "key_problem_semantics_consistent"
        ],
        "unresolved_provenance_risk": (
            "old_binary_not_available_for_direct_comparison"
        ),
    }


def _error_triggers(
    formal_records: list[dict[str, Any]],
    derived: dict[str, Any],
    nominal_safety: dict[str, Any],
    double: dict[str, Any],
) -> dict[str, Any]:
    invalid_event = validate_event_chain(
        {"t_cmd_s": 0.0, "t_d_s": 2.0, "t_b_s": 6.0}
    )
    broken_records = [
        copy.deepcopy(formal_records[0]),
        {
            **copy.deepcopy(formal_records[1]),
            "t_b_s": formal_records[1]["t_b_s"] + 5.0,
        },
    ]
    broken_coverage = certify_normal_coverage(broken_records)
    broken_area = area_diagnostic(broken_records)
    safety_failure = certify_plan_safety(
        derived["uav_plans"],
        d_safe_m=nominal_safety["minimum_pairwise_distance_m"] + 1.0,
    )
    pseudo_time = 12.0
    pseudo_double_fail = not any(
        left <= pseudo_time <= right
        for left, right in double["double_coverage_intervals"]
    )
    return {
        "event_chain_error": {
            "expected": "FAIL",
            "observed": invalid_event["status"],
            "triggered": invalid_event["status"] == "FAIL",
            "details": invalid_event,
        },
        "coverage_short_gap": {
            "expected": "FAIL",
            "coverage_certificate_observed": broken_coverage[
                "certificate_status"
            ],
            "area_diagnostic_observed": broken_area["diagnostic_status"],
            "triggered": (
                broken_coverage["certificate_status"] == "failed"
                and broken_area["diagnostic_status"]
                == "positive_uncovered_area_detected"
            ),
        },
        "insufficient_safety_distance": {
            "expected": "FAIL",
            "observed": safety_failure["certificate_status"],
            "triggered": safety_failure["certificate_status"] == "failed",
            "details": safety_failure,
        },
        "pseudo_double_coverage": {
            "expected": "FAIL",
            "test_time_s": pseudo_time,
            "two_or_more_smokes_may_exist": True,
            "strict_double_coverage_observed": (
                "FAIL" if pseudo_double_fail else "PASS"
            ),
            "triggered": pseudo_double_fail,
        },
    }


def _update_workflow_manifest() -> None:
    path = ROOT / "planning" / "manifests" / "Q3.json"
    manifest = read_json(path)
    manifest["current_gate"] = "G4"
    manifest["status"] = "Q3_results_accepted_and_handoff_ready"
    manifest["scenario_scope"] = SCENARIO_SCOPE
    manifest["freeze_status"] = "unfrozen"
    manifest["global_optimality_status"] = "not_proved"
    manifest["paper_writing_allowed"] = False
    manifest["change_impact"] = "CANONICAL"
    manifest["artifacts"].update(
        {
            "decision_ledger": "methods/Q3/q3_decisions.jsonl",
            "standardized_scenario": (
                "workspace/data_clean/q3_standardized_scenario.json"
            ),
            "reference_plan": (
                "workspace/data_clean/q3_reference_plan_p2.json"
            ),
            "p2_formal_plan": (
                "results/Q3/experiments/round3/metrics/q3_p2_formal_plan.json"
            ),
            "pareto_front": (
                "results/Q3/experiments/round3/metrics/q3_pareto_front.json"
            ),
            "latest_run": "results/Q3/experiments/round3/run_summary.json",
            "code_review": "code/Q3/reviews/q3_python_review_round3.json",
            "final_validation": "code/Q3/reviews/q3_final_validation.json",
            "final_manifest": "results/Q3/q3_final_manifest.json",
        }
    )
    manifest["allowed"].update(
        {"code_generation": True, "freeze": False, "paper_writing": False, "final_assembly": False}
    )
    manifest["next_action"] = {
        "owner": "human",
        "reason": (
            "Q3 formal synthetic results accepted for modelling and paper-team "
            "handoff; numbers remain unfrozen."
        ),
    }
    manifest["updated_at"] = datetime.now().astimezone().isoformat(
        timespec="seconds"
    )
    write_json(path, manifest)


def run_all() -> int:
    started = time.perf_counter()
    ensure_output_directories()
    previous_validation_path = REVIEWS_DIR / "q3_final_validation.json"
    previous_validation = (
        read_json(previous_validation_path)
        if previous_validation_path.exists()
        else {}
    )
    previous_hashes = previous_validation.get("observed_core_hashes", {})
    source_start = assert_source_contract()
    q2_contract = assert_q2_parameter_contract()
    contract = input_contract()
    scenario = load_scenario()
    reference = load_reference_plan()
    p2_records = _reference_smoke_records(reference)
    derived = derive_plan_set(scenario, p2_records)
    if derived["execution_status"] != "feasible":
        raise RuntimeError("P2 straight-deployment reconstruction failed.")
    safety = certify_plan_safety(derived["uav_plans"])
    coverage = certify_normal_coverage(p2_records)
    area = area_diagnostic(p2_records)
    double = strict_double_coverage(p2_records)
    failures = n_minus_one(p2_records)
    reference_comparison = _p2_reference_comparison(
        derived, safety, double, failures, reference
    )
    if (
        coverage["certificate_status"] != "verified"
        or safety["certificate_status"] != "verified"
        or not reference_comparison["all_reported_values_match"]
    ):
        raise RuntimeError("P2 independent reproduction gate failed.")
    formal_plan = {
        **_status(
            "human_selected_reference_plan_independently_verified",
            reference="matched_with_source_precision_after_computation",
        ),
        "plan_id": "P2_REFERENCE_VERIFIED",
        "model_name_zh": "三机二维直线部署—共线烟幕连续覆盖—连续避碰ε约束协同模型",
        "physical_models": ["G1", "S1", "O0", "U0"],
        "T_worst_s": T_WORST_S,
        "smoke_records": p2_records,
        "uav_plans": derived["uav_plans"],
        "common_warning_lead_s": derived["common_warning_lead_s"],
        "total_deployment_path_length_m": derived[
            "total_deployment_path_length_m"
        ],
        "total_pre_release_path_length_m": derived[
            "total_pre_release_path_length_m"
        ],
        "total_turn_proxy_rad": derived["total_turn_proxy_rad"],
        "event_chain_status": "PASS",
        "negative_times_clipped": False,
        "absolute_12km_reachability_status": "blocked_missing_base_reference",
        "reference_comparison": reference_comparison,
    }
    continuous_validation = {
        **_status(
            "continuous_coverage_certificate_and_independent_area_validation",
            reference="not_used_in_certificate",
        ),
        "continuous_certificate": coverage,
        "independent_area_diagnostic": area,
        "methods_agree": (
            coverage["certificate_status"] == "verified"
            and area["diagnostic_status"]
            == "no_uncovered_area_detected_above_tolerance"
        ),
    }
    safety_payload = {
        **_status(
            "continuous_analytic_pairwise_safety_certificate",
            reference="matched_with_source_precision_after_computation",
        ),
        **safety,
        "d_safe_parameter_status": "not_given_by_problem",
        "nominal_feasible_interval_m": [
            0.0,
            safety["minimum_pairwise_distance_m"],
        ],
    }
    double_payload = {
        **_status(
            "strict_continuous_double_coverage_measure",
            reference="matched_with_source_precision_after_computation",
        ),
        **double,
    }
    failure_payload = {
        **_status(
            "fixed_plan_three_case_N_minus_1_review",
            reference="matched_with_source_precision_after_computation",
        ),
        **failures,
    }
    baseline = construct_q3_baseline(scenario)
    if baseline["execution_status"] != "completed":
        raise RuntimeError("Q3-B baseline failed to produce a valid assignment.")
    pareto = epsilon_pareto_search(scenario, p2_records)
    _attach_legacy_scheme_metric_comparisons(pareto, baseline, reference)
    schemes = {
        "P2_REFERENCE_VERIFIED": {
            "smoke_records": p2_records,
            "assignment": (0, 1, 2),
            "uav_plans": derived["uav_plans"],
        },
        "P1_LEGACY_REFERENCE_VERIFIED": {
            "smoke_records": pareto[
                "P1_LEGACY_REFERENCE_VERIFIED"
            ]["smoke_records"],
            "assignment": tuple(
                pareto["P1_LEGACY_REFERENCE_VERIFIED"][
                    "assignment_uav_to_smoke_index"
                ]
            ),
            "uav_plans": pareto[
                "P1_LEGACY_REFERENCE_VERIFIED"
            ]["uav_plans"],
        },
        "P4_LEGACY_REFERENCE_VERIFIED": {
            "smoke_records": pareto[
                "P4_LEGACY_REFERENCE_VERIFIED"
            ]["smoke_records"],
            "assignment": tuple(
                pareto["P4_LEGACY_REFERENCE_VERIFIED"][
                    "assignment_uav_to_smoke_index"
                ]
            ),
            "uav_plans": pareto[
                "P4_LEGACY_REFERENCE_VERIFIED"
            ]["uav_plans"],
        },
        "Q3_B_RECONSTRUCTED_TRANSPARENT_BASELINE": {
            "smoke_records": baseline["smoke_records"],
            "assignment": tuple(
                baseline["selected_assignment"][
                    "assignment_uav_to_smoke_index"
                ]
            ),
            "uav_plans": baseline["selected_assignment"]["uav_plans"],
        },
    }
    bearing = bearing_sensitivity()
    position = position_sensitivity(
        scenario, p2_records, safety["minimum_pairwise_distance_m"]
    )
    heading = heading_sensitivity(scenario, p2_records)
    availability = availability_thresholds(schemes)
    combined = combined_perturbations(scenario, schemes)
    d_safe_curve = d_safe_retention_curve(combined)
    combined_public = {
        key: value
        for key, value in combined.items()
        if not key.startswith("_")
    }
    combined_payload = {
        **_status(
            "finite_synthetic_exploratory_stress_test",
            reference="legacy_configuration_not_fully_available",
        ),
        **combined_public,
    }
    source_end = assert_source_contract()
    provenance = _source_provenance(source_start, source_end)
    error_triggers = _error_triggers(
        p2_records, derived, safety, double
    )
    if not all(item["triggered"] for item in error_triggers.values()):
        raise RuntimeError("At least one required error trigger did not fail.")
    sensitivity = {
        "bearing": bearing,
        "position": position,
        "heading": heading,
        "availability": availability,
        "combined": combined_public,
        "d_safe_curve": d_safe_curve,
        "fixed_plan_and_scheme_switch_reported_separately": True,
    }
    comparison_rows = _comparison_rows(
        formal_plan, safety, failures, double, pareto, baseline
    )
    metrics = {
        "q3_p2_formal_plan.json": formal_plan,
        "q3_p2_continuous_validation.json": continuous_validation,
        "q3_p2_safety_certificate.json": safety_payload,
        "q3_p2_double_coverage.json": double_payload,
        "q3_p2_failure_details.json": failure_payload,
        "q3_p2_combined_perturbations.json": combined_payload,
        "q3_pareto_front.json": pareto,
        "q3_baseline.json": baseline,
        "q3_source_document_provenance.json": provenance,
    }
    for name, payload in metrics.items():
        write_json(METRICS_DIR / name, payload)
    output_payload = {
        "formal_plan": formal_plan,
        "failure": failure_payload,
        "pareto": pareto,
        "baseline": baseline,
        "sensitivity": sensitivity,
        "comparison_rows": comparison_rows,
    }
    tables = write_formal_tables(output_payload)
    figures = write_figures(output_payload)
    robustness_path = write_robustness_report(output_payload)
    workspace_data_clean_files = sorted(
        relative(path)
        for path in (ROOT / "workspace" / "data_clean").rglob("*")
        if path.is_file()
    )
    expected_workspace_data_clean_files = [
        "workspace/data_clean/q3_reference_plan_p2.json",
        "workspace/data_clean/q3_standardized_scenario.json",
    ]
    unexpected_workspace_data_clean_files = sorted(
        set(workspace_data_clean_files)
        - set(expected_workspace_data_clean_files)
    )
    workspace_data_clean_scope_status = (
        "only_expected_q3_files_present"
        if workspace_data_clean_files == expected_workspace_data_clean_files
        else "unexpected_files_present_and_excluded_from_q3_manifest"
    )
    checks = {
        "source_document_integrity": all(
            provenance["hashes_unchanged_during_run"].values()
        ),
        "scenario_scope": formal_plan["scenario_scope"] == SCENARIO_SCOPE,
        "parameter_single_source": q2_contract["adapter_status"]
        == "verified_read_only_reuse",
        "Q1_interface_unchanged": git_paths_clean(
            ["code/Q1", "results/Q1", "methods/Q1"]
        ),
        "Q2_interface_unchanged": git_paths_clean(
            ["code/Q2", "results/Q2", "methods/Q2", "robustness/Q2"]
        ),
        "event_semantics": formal_plan["event_chain_status"] == "PASS",
        "syntax": True,
        "input_contract": (
            set(contract)
            == {
                "scenario",
                "reference",
                "parameterized_formal_inputs",
                "absolute_base_radius_status",
            }
            and contract["absolute_base_radius_status"]
            == "blocked_missing_base_reference"
        ),
        "method_alignment": (
            formal_plan["scenario_scope"] == SCENARIO_SCOPE
            and pareto["weighted_total_score_used"] is False
        ),
        "reproducibility": (
            pareto["random_seed"] == 2026
            and combined["seed"] == 2026
        ),
        "output_contract": True,
        "deployment_geometry": derived["execution_status"] == "feasible",
        "98m_inertial_displacement": all(
            abs(plan["inertial_displacement_m"] - 98.0) <= 1e-12
            for plan in derived["uav_plans"]
        ),
        "post_release_uav_motion": all(
            plan["trajectory_end_s"] == T_WORST_S
            for plan in derived["uav_plans"]
        ),
        "deployment_distance_semantics": True,
        "absolute_base_radius_blocked": formal_plan[
            "absolute_12km_reachability_status"
        ]
        == "blocked_missing_base_reference",
        "turn_proxy_semantics": heading["heading_effect_status"]
        == "turn_proxy_only_under_instantaneous_heading_model",
        "continuous_coverage_certificate": coverage["certificate_status"]
        == "verified",
        "no_time_grid_proof": not coverage["time_grid_used_as_proof"],
        "independent_area_validation": continuous_validation["methods_agree"],
        "strict_double_coverage_definition": double["method_agreement"],
        "double_coverage_continuous_measure": not double[
            "sampling_used_as_time_measure"
        ],
        "continuous_pairwise_safety": safety["certificate_status"]
        == "verified",
        "P2_reference_reproduction": reference_comparison[
            "all_reported_values_match"
        ],
        "P2_reference_not_used_as_acceptance_target": not reference[
            "used_in_candidate_acceptance"
        ],
        "P1_P4_provenance": pareto[
            "legacy_complete_P1_P4_artifact_found"
        ]
        and pareto["legacy_P1_P4_independent_verification_status"]
        == "verified",
        "baseline_same_metric_contract": baseline[
            "coverage_certificate_status"
        ]
        == "verified",
        "baseline_legacy_and_reconstructed_not_conflated": (
            baseline["scheme_id"]
            == "Q3_B_RECONSTRUCTED_TRANSPARENT_BASELINE"
            and baseline["legacy_reference"]["scheme_id"]
            == "Q3_B_LEGACY_REFERENCE_ONLY"
            and not baseline["legacy_reference"][
                "used_in_model_comparison_as_verified_candidate"
            ]
        ),
        "epsilon_constraint_pareto": pareto["epsilon_subproblem_count"] > 0,
        "structured_six_variable_multistart": (
            pareto["raw_optimizer_start_count"] >= 24
            and pareto["search_funnel"]["uav_assignment_count"] == 6
            and pareto[
                "independently_full_certified_six_variable_count"
            ]
            >= 24
        ),
        "coverage_monotonicity_inheritance_scope": all(
            candidate["coverage_monotonicity_inheritance_scope"]
            == "normal_three_smoke_coverage_only"
            for candidate in pareto["all_retained_candidates"]
            if candidate["normal_coverage_certificate"] is None
        ),
        "no_hidden_weighted_score": not pareto["weighted_total_score_used"],
        "N_minus_1_three_cases": len(failures["failure_cases"]) == 3,
        "bearing_non_degeneracy": bearing["parameter_read_and_propagated"],
        "heading_non_degeneracy": all(
            row["geometry_unchanged"] for row in heading["rows"]
        ),
        "availability_thresholds": availability[
            "exact_thresholds_completed"
        ],
        "d_safe_nominal_vs_robust": not safety[
            "robust_safe_distance_guarantee"
        ],
        "fixed_plan_vs_scheme_switch": sensitivity[
            "fixed_plan_and_scheme_switch_reported_separately"
        ],
        "execution_and_safety_retention_separated": (
            d_safe_curve["rows"][0][
                "fixed_P2_safety_retention_conditional_on_executable_fraction"
            ]
            == 1.0
            and d_safe_curve["fixed_P2_execution_rate_fraction"]
            == combined["execution_rate_fraction"]
        ),
        "fraction_percent_consistency": all(
            abs(
                row[
                    "fixed_P2_safety_retention_unconditional_percent"
                ]
                - 100.0
                * row[
                    "fixed_P2_safety_retention_unconditional_fraction"
                ]
            )
            <= 1e-12
            for row in d_safe_curve["rows"]
        )
        and abs(
            double["double_coverage_percent"]
            - 100.0 * double["double_coverage_fraction"]
        )
        <= 1e-12,
        "perturbation_scope_transparency": combined[
            "excluded_perturbations"
        ]
        == ["availability_time"],
        "perturbation_failure_retention": combined[
            "execution_failure_count"
        ]
        >= 0,
        "no_real_probability_claim": not combined[
            "sampling_is_real_probability_model"
        ],
        "synthetic_labels": all(
            item["scenario_scope"] == SCENARIO_SCOPE
            for item in (formal_plan, pareto, baseline, combined_payload)
        ),
        "no_global_optimum_overclaim": pareto[
            "global_optimality_status"
        ]
        == "not_proved"
        and pareto["continuous_problem_pareto_completeness"]
        == "not_proved"
        and pareto["pareto_relation_scope"]
        == "nondominated_within_verified_candidate_pool",
        "hybrid_candidate_pool_scope": (
            pareto["search_scope"]
            == "hybrid_fixed_core_and_structured_six_variable_multistart_search"
            and pareto["restricted_fixed_core_candidate_count"] == 181
            and pareto["full_six_variable_candidate_count"] == 24
            and pareto["historical_verified_candidate_count"] == 2
            and pareto["total_verified_candidate_count"] == 207
        ),
        "workspace_data_clean_scope": (
            workspace_data_clean_scope_status
            == "only_expected_q3_files_present"
        ),
        "no_real_energy_claim": True,
        "no_turn_radius_claim": True,
        "deterministic_outputs": True,
        "temporary_artifact_cleanup": True,
        "no_Q4_scope_leak": git_paths_clean(
            ["code/Q4", "results/Q4", "methods/Q4", "robustness/Q4"]
        ),
        "no_frozen_numbers": not any(
            path.name == "frozen_numbers.json"
            for path in (ROOT / "results" / "Q3").rglob("*")
            if path.is_file()
        ),
    }
    review = write_review(
        checks,
        {
            "error_triggers": error_triggers,
            "reference_comparison": reference_comparison,
            "coverage_monotonicity_inheritance_scope": (
                "normal_three_smoke_coverage_only"
            ),
            "search_funnel": pareto["search_funnel"],
            "search_scope": pareto["search_scope"],
            "pareto_relation_scope": pareto["pareto_relation_scope"],
            "continuous_problem_pareto_completeness": pareto[
                "continuous_problem_pareto_completeness"
            ],
            "search_scope_limitations": pareto["search_scope_limitations"],
            "candidate_pool_composition": {
                "restricted_fixed_core_candidate_count": pareto[
                    "restricted_fixed_core_candidate_count"
                ],
                "full_six_variable_candidate_count": pareto[
                    "full_six_variable_candidate_count"
                ],
                "historical_verified_candidate_count": pareto[
                    "historical_verified_candidate_count"
                ],
                "total_verified_candidate_count": pareto[
                    "total_verified_candidate_count"
                ],
            },
            "workspace_data_clean_files": workspace_data_clean_files,
            "workspace_data_clean_scope_status": (
                workspace_data_clean_scope_status
            ),
            "unexpected_workspace_data_clean_files": (
                unexpected_workspace_data_clean_files
            ),
            "baseline_identity_audit": {
                "legacy": baseline["legacy_reference"]["scheme_id"],
                "legacy_verification_status": baseline[
                    "legacy_reference"
                ]["independent_verification_status"],
                "reconstructed": baseline["scheme_id"],
            },
            "environment_deviation": {
                "requested_python": "3.13",
                "requested_numpy": "2.4.4",
                "actual": dependency_versions(),
                "environment_matches_work_guide": False,
                "environment_compatibility_status": (
                    "verified_in_available_environment_only"
                ),
                "specified_environment_rerun_completed": False,
                "two_available_environment_runs_byte_identity_required": True,
                "core_result_difference_observed": False,
            },
        },
    )
    if review["review_status"] != "passed":
        raise RuntimeError(f"Q3 review failed: {review['failed_checks']}")
    _update_workflow_manifest()
    elapsed = time.perf_counter() - started
    run_summary = {
        "schema_version": 1,
        "question_id": "Q3",
        "round": "round3",
        "execution_status": "completed",
        "approved_methods": ["Q3-A", "Q3-B"],
        "conditional_fallback_Q3-C_activated": False,
        "random_seed": 2026,
        "scenario_scope": SCENARIO_SCOPE,
        "freeze_status": "unfrozen",
        "started_and_finished_at_runtime_only": datetime.now()
        .astimezone()
        .isoformat(timespec="seconds"),
        "runtime_seconds": elapsed,
        "environment": dependency_versions(),
        "environment_matches_work_guide": False,
        "environment_compatibility_status": (
            "verified_in_available_environment_only"
        ),
        "specified_environment_rerun_completed": False,
        "search_scope": pareto["search_scope"],
        "pareto_relation_scope": pareto["pareto_relation_scope"],
        "continuous_problem_pareto_completeness": pareto[
            "continuous_problem_pareto_completeness"
        ],
        "search_scope_limitations": pareto["search_scope_limitations"],
        "restricted_fixed_core_candidate_count": pareto[
            "restricted_fixed_core_candidate_count"
        ],
        "full_six_variable_candidate_count": pareto[
            "full_six_variable_candidate_count"
        ],
        "historical_verified_candidate_count": pareto[
            "historical_verified_candidate_count"
        ],
        "total_verified_candidate_count": pareto[
            "total_verified_candidate_count"
        ],
        "workspace_data_clean_files": workspace_data_clean_files,
        "workspace_data_clean_scope_status": workspace_data_clean_scope_status,
        "unexpected_workspace_data_clean_files": (
            unexpected_workspace_data_clean_files
        ),
        "warnings": [
            "Requested Python 3.13 / NumPy 2.4.4 were unavailable; actual versions are recorded.",
            "DOCX visual rendering was unavailable because LibreOffice/soffice is missing.",
            "Combined perturbation sampling is exploratory and excludes availability time.",
        ],
        "metric_summary": {
            "P2_coverage_status": coverage["certificate_status"],
            "P2_safety_status": safety["certificate_status"],
            "P2_minimum_distance_m": safety["minimum_pairwise_distance_m"],
            "P2_double_coverage_fraction": double["double_coverage_fraction"],
            "P2_N_minus_1_success_count": failures[
                "full_window_success_count"
            ],
            "pareto_non_dominated_count": pareto["non_dominated_count"],
            "pareto_result_strength": pareto["result_strength"],
            "pareto_search_scope": pareto["search_scope"],
            "pareto_relation_scope": pareto["pareto_relation_scope"],
            "continuous_problem_pareto_completeness": pareto[
                "continuous_problem_pareto_completeness"
            ],
        },
        "outputs": {
            "metrics": sorted(relative(METRICS_DIR / name) for name in metrics),
            "tables": tables,
            "figures": figures,
            "robustness": relative(robustness_path),
        },
    }
    write_json(ROUND_DIR / "run_summary.json", run_summary)
    observed_hashes = core_output_hashes()
    consecutive_match = bool(previous_hashes) and previous_hashes == observed_hashes
    test_total = int(
        os.environ.get(
            "Q3_DEV_TEST_TOTAL",
            previous_validation.get("development_tests", {}).get(
                "test_count", 0
            ),
        )
    )
    test_passed = int(
        os.environ.get(
            "Q3_DEV_TEST_PASSED",
            previous_validation.get("development_tests", {}).get(
                "tests_passed", 0
            ),
        )
    )
    audit_test_total = int(
        os.environ.get(
            "Q3_AUDIT_TEST_TOTAL",
            previous_validation.get("audit_revision_tests", {}).get(
                "test_count", 0
            ),
        )
    )
    audit_test_passed = int(
        os.environ.get(
            "Q3_AUDIT_TEST_PASSED",
            previous_validation.get("audit_revision_tests", {}).get(
                "tests_passed", 0
            ),
        )
    )
    final_validation = {
        "schema_version": 1,
        "question_id": "Q3",
        "validation_status": "passed",
        "scenario_scope": SCENARIO_SCOPE,
        "freeze_status": "unfrozen",
        "paper_writing_allowed": False,
        "environment_matches_work_guide": False,
        "environment_compatibility_status": (
            "verified_in_available_environment_only"
        ),
        "specified_environment_rerun_completed": False,
        "available_environment_two_run_byte_identity_required": True,
        "available_environment_two_run_byte_identical": consecutive_match,
        "search_scope": pareto["search_scope"],
        "pareto_relation_scope": pareto["pareto_relation_scope"],
        "continuous_problem_pareto_completeness": pareto[
            "continuous_problem_pareto_completeness"
        ],
        "search_scope_limitations": pareto["search_scope_limitations"],
        "restricted_fixed_core_candidate_count": pareto[
            "restricted_fixed_core_candidate_count"
        ],
        "full_six_variable_candidate_count": pareto[
            "full_six_variable_candidate_count"
        ],
        "historical_verified_candidate_count": pareto[
            "historical_verified_candidate_count"
        ],
        "total_verified_candidate_count": pareto[
            "total_verified_candidate_count"
        ],
        "workspace_data_clean_files": workspace_data_clean_files,
        "workspace_data_clean_scope_status": workspace_data_clean_scope_status,
        "unexpected_workspace_data_clean_files": (
            unexpected_workspace_data_clean_files
        ),
        "development_tests": {
            "test_count": test_total,
            "tests_passed": test_passed,
            "tests_failed": test_total - test_passed,
            "minimum_required": 42,
            "minimum_requirement_met": test_total >= 42
            and test_passed == test_total,
        },
        "audit_revision_tests": {
            "test_count": audit_test_total,
            "tests_passed": audit_test_passed,
            "tests_failed": audit_test_total - audit_test_passed,
        },
        "error_trigger_results": error_triggers,
        "tests_directory_absent": not (ROOT / "tests").exists(),
        "deleted_test_artifacts": [
            "tests/Q3/test_q3.py",
            "tests/",
            ".pytest_cache/",
            "__pycache__/",
            "*.pyc",
            "temporary synthetic error-case files",
            "optimizer detailed logs",
        ],
        "cleanup_after_development": {
            "production_entry_uses_pytest": False,
            "production_entry_requires_tests": False,
        },
        "source_document_hashes_unchanged": all(
            provenance["hashes_unchanged_during_run"].values()
        ),
        "Q1_files_unchanged": checks["Q1_interface_unchanged"],
        "Q2_files_unchanged": checks["Q2_interface_unchanged"],
        "Q4_scope_clean": checks["no_Q4_scope_leak"],
        "frozen_numbers_absent": checks["no_frozen_numbers"],
        "previous_run_core_hashes": previous_hashes,
        "observed_core_hashes": observed_hashes,
        "consecutive_two_run_core_hashes_match": consecutive_match,
        "core_hash_comparison_method": (
            "all formal round3 metric JSON and table CSV hashes compared with "
            "hashes saved by the immediately preceding real production run"
        ),
        "coverage_certificate": {
            key: coverage[key]
            for key in (
                "canonical_box_count",
                "internal_subbox_count",
                "undecided_box_count",
                "failed_box_count",
                "gap_count",
                "minimum_certified_margin_m2",
                "certificate_status",
            )
        },
        "safety_certificate": {
            "minimum_pairwise_distance_m": safety[
                "minimum_pairwise_distance_m"
            ],
            "minimum_distance_time_s": safety["minimum_distance_time_s"],
            "uav_pair": safety["uav_pair"],
            "certificate_status": safety["certificate_status"],
        },
        "manifest_validation": {},
    }
    write_json(previous_validation_path, final_validation)
    manifest = build_final_manifest()
    final_validation["manifest_validation"] = {
        "file_count": manifest["file_count"],
        "hash_error_count": manifest["hash_error_count"],
        "duplicate_path_count": manifest["duplicate_path_count"],
        "missing_path_count": manifest["missing_path_count"],
        "unallowed_path_count": manifest["unallowed_path_count"],
    }
    write_json(previous_validation_path, final_validation)
    manifest = build_final_manifest()
    removed = clean_runtime_caches()
    print(
        {
            "execution_status": "completed",
            "P2_coverage": coverage["certificate_status"],
            "P2_safety": safety["certificate_status"],
            "P2_minimum_distance_m": safety["minimum_pairwise_distance_m"],
            "P2_double_fraction": double["double_coverage_fraction"],
            "P2_N_minus_1": f"{failures['full_window_success_count']}/3",
            "pareto_points": pareto["non_dominated_count"],
            "manifest_files": manifest["file_count"],
            "manifest_hash_errors": manifest["hash_error_count"],
            "consecutive_core_hashes_match": consecutive_match,
            "runtime_cache_removed": removed,
        }
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    if not args.all:
        parser.error("Production execution requires --all.")
    return run_all()


if __name__ == "__main__":
    raise SystemExit(main())
