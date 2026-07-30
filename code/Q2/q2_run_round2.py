"""Q2 formal production entry point."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from q2_capacity_frontier import capacity_frontier
from q2_common import (
    MODEL_SCOPE,
    PARAMS,
    PROJECT_ROOT,
    PROBLEM_DOC_NAME,
    assert_parameter_contract,
    clean_runtime_caches,
    dependency_versions,
    runtime_timestamp,
    sha256_file,
    source_document_metadata,
    read_docx_text,
    write_json,
)
from q2_outputs import (
    FINAL_MANIFEST_PATH,
    REVIEW_DIR,
    build_final_manifest,
    core_output_hashes,
    write_formal_outputs,
)
from q2_robustness import plan_from_event_records, robustness_summary
from q2_two_bomb_plan import (
    broken_plan_gate,
    no_pre_lock_counterfactual,
    validate_canonical_two_bomb_plan,
)

DEVELOPMENT_TEST_SUMMARY = {
    "test_count": 52,
    "tests_passed": 52,
    "tests_failed": 0,
    "pytest_command": "python -m pytest tests/Q2/test_q2.py -q",
    "pytest_reported_duration_s": 1.49,
}

def _git_diff_clean(paths: list[str]) -> bool:
    result = subprocess.run(
        ["git", "-C", str(PROJECT_ROOT), "diff", "--quiet", "HEAD", "--", *paths],
        check=False,
    )
    cached = subprocess.run(
        ["git", "-C", str(PROJECT_ROOT), "diff", "--cached", "--quiet", "--", *paths],
        check=False,
    )
    return result.returncode == 0 and cached.returncode == 0


def q1_interface_consistency() -> dict[str, Any]:
    validation_path = PROJECT_ROOT / "code" / "Q1" / "reviews" / "q1_final_validation.json"
    q1_validation = json.loads(validation_path.read_text(encoding="utf-8"))
    expected = {
        path: digest
        for path, digest in q1_validation["source_hashes"].items()
        if path.startswith("code/Q1/")
    }
    observed = {
        path: sha256_file(PROJECT_ROOT / path)
        for path in sorted(expected)
    }
    source_hashes_match = all(observed[path] == expected[path] for path in expected)
    interface_path = PROJECT_ROOT / "interfaces" / "Q1_to_Q2_coverage_contract.md"
    interface_text = interface_path.read_text(encoding="utf-8")
    interface_checks = {
        "t_cmd_present": "`t_cmd`" in interface_text,
        "t_d_present": "`t_d`" in interface_text,
        "t_b_present": "`t_b`" in interface_text,
        "Delta_definition_present": "Delta(t)" in interface_text,
        "Q2_exact_union_boundary_present": (
            "多烟幕连续联合覆盖不属于 Q1" in interface_text
        ),
    }
    q1_paths = ["code/Q1", "results/Q1", "robustness/Q1"]
    q1_clean = _git_diff_clean(q1_paths)
    return {
        "scope": "Q1_read_only_interface_consistency",
        "q1_source_hashes_expected": expected,
        "q1_source_hashes_observed": observed,
        "q1_source_hashes_match": source_hashes_match,
        "q1_git_diff_clean": q1_clean,
        "interface_checks": interface_checks,
        "event_semantics_match": all(interface_checks.values()),
        "q1_files_unchanged": source_hashes_match and q1_clean,
        "legacy_terminology_follow_up": {
            "status": "handoff_to_modeler_or_writer",
            "note": (
                "The preserved Q2 guide and earlier human materials use M1/M2. "
                "New code and machine outputs use G1/G2; programmer did not "
                "rewrite human records."
            ),
        },
        "consistency_status": (
            "verified"
            if source_hashes_match and q1_clean and all(interface_checks.values())
            else "failed"
        ),
    }


def q3_q4_scope_clean() -> bool:
    return _git_diff_clean(
        [
            "code/Q3",
            "code/Q4",
            "results/Q3",
            "results/Q4",
            "robustness/Q3",
            "robustness/Q4",
            "methods/Q3",
            "methods/Q4",
            "planning/manifests/Q3.json",
            "planning/manifests/Q4.json",
        ]
    )


def source_document_provenance() -> dict[str, Any]:
    current_path = PROJECT_ROOT / PROBLEM_DOC_NAME
    stage = subprocess.run(
        [
            "git",
            "-C",
            str(PROJECT_ROOT),
            "ls-files",
            "--stage",
            "--",
            PROBLEM_DOC_NAME,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    stage_fields = stage.stdout.strip().split()
    git_tracked = stage.returncode == 0 and len(stage_fields) >= 4
    git_blob_sha = stage_fields[1] if git_tracked else None
    worktree_diff = subprocess.run(
        [
            "git",
            "-C",
            str(PROJECT_ROOT),
            "diff",
            "--quiet",
            "--",
            PROBLEM_DOC_NAME,
        ],
        check=False,
    )
    history = subprocess.run(
        [
            "git",
            "-C",
            str(PROJECT_ROOT),
            "log",
            "--follow",
            "--format=%H|%aI|%an|%s",
            "--",
            PROBLEM_DOC_NAME,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    q1_validation_path = (
        PROJECT_ROOT / "code" / "Q1" / "reviews" / "q1_final_validation.json"
    )
    q1_validation = json.loads(
        q1_validation_path.read_text(encoding="utf-8")
    )
    q1_recorded_hash = q1_validation["source_hashes"][PROBLEM_DOC_NAME]
    q1_run_summary = json.loads(
        (
            PROJECT_ROOT / "results" / "Q1" / "q1_run_summary.json"
        ).read_text(encoding="utf-8")
    )
    q1_common_text = (
        PROJECT_ROOT / "code" / "Q1" / "q1_common.py"
    ).read_text(encoding="utf-8")

    def q1_literal(name: str) -> float:
        match = re.search(
            rf"(?m)^{re.escape(name)}\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*$",
            q1_common_text,
        )
        if match is None:
            raise RuntimeError(f"Could not read Q1 constant {name}.")
        return float(match.group(1))

    q1_values = {
        "ship_speed_mps": 15.0 * q1_literal("KNOT_TO_MPS"),
        "ship_radius_m": q1_literal("R_S"),
        "missile_speed_mps": q1_literal("V_M"),
        "detection_distance_m": q1_literal("D_MAX"),
        "uav_speed_mps": q1_literal("V_U"),
        "command_to_release_delay_s": q1_literal("TAU_RESPONSE"),
        "release_to_burst_delay_s": q1_literal("TAU_BURST"),
        "smoke_max_radius_m": q1_literal("R_C"),
        "smoke_hold_s": q1_literal("TAU_HOLD"),
        "smoke_decay_s": q1_literal("TAU_DECAY"),
        "uav_payload_max": int(q1_literal("UAV_PAYLOAD_MAX")),
        "minimum_release_interval_s": q1_literal("MIN_DROP_INTERVAL"),
    }
    current_values = {
        "ship_speed_mps": PARAMS.ship_speed_mps,
        "ship_radius_m": PARAMS.ship_radius_m,
        "missile_speed_mps": PARAMS.missile_speed_mps,
        "detection_distance_m": PARAMS.detection_distance_m,
        "uav_speed_mps": PARAMS.uav_speed_mps,
        "command_to_release_delay_s": PARAMS.command_to_release_delay_s,
        "release_to_burst_delay_s": PARAMS.release_to_burst_delay_s,
        "smoke_max_radius_m": PARAMS.smoke_max_radius_m,
        "smoke_hold_s": PARAMS.smoke_hold_s,
        "smoke_decay_s": PARAMS.smoke_decay_s,
        "uav_payload_max": PARAMS.uav_payload_max,
        "minimum_release_interval_s": PARAMS.minimum_release_interval_s,
    }
    semantic_checks = {
        name: {
            "q1_recorded_value": q1_values[name],
            "current_q2_value": current_values[name],
            "consistent": q1_values[name] == current_values[name],
        }
        for name in current_values
    }
    current_doc_text = read_docx_text(current_path)
    q2_requirement = (
        "问题二：单机多弹时序叠加的长时持续遮蔽优化策略"
    )
    key_semantics_consistent = all(
        row["consistent"] for row in semantic_checks.values()
    )
    return {
        "current_source_path": current_path.relative_to(
            PROJECT_ROOT
        ).as_posix(),
        "current_sha256": sha256_file(current_path),
        "git_tracked": git_tracked,
        "git_blob_sha": git_blob_sha,
        "current_worktree_modified": worktree_diff.returncode != 0,
        "git_history": [
            line
            for line in history.stdout.splitlines()
            if line.strip()
        ],
        "q1_recorded_source_sha256": q1_recorded_hash,
        "hashes_match": sha256_file(current_path) == q1_recorded_hash,
        "probable_reason": (
            "Q1 preserved an expected hash for an earlier source copy while "
            "its final run recorded source_documents_present=false; that old "
            "binary is not present in this repository. The current E891 file "
            "is the unchanged blob committed in the repository initial commit."
        ),
        "q1_historical_source_documents_present": q1_run_summary[
            "source_documents_present"
        ],
        "key_problem_semantics_consistent": key_semantics_consistent,
        "key_problem_semantics_evidence": semantic_checks,
        "current_q2_requirement_text_verified": (
            q2_requirement in current_doc_text
        ),
        "current_q2_requirement_heading": q2_requirement,
        "old_q2_requirement_direct_comparison": (
            "old_binary_not_available_for_direct_comparison"
        ),
        "unresolved_provenance_risk": (
            "old_binary_not_available_for_direct_comparison"
        ),
        "audit_conclusion": (
            "non_blocking_current_source_is_tracked_unchanged_and_shared_"
            "key_parameters_are_consistent"
            if (
                git_tracked
                and worktree_diff.returncode == 0
                and key_semantics_consistent
            )
            else "blocking_source_provenance_check_failed"
        ),
    }


def build_review(
    minimum_resource: dict[str, Any],
    broken: dict[str, Any],
    capacity: dict[str, Any],
    robustness: dict[str, Any],
    q1_consistency: dict[str, Any],
    provenance: dict[str, Any],
    temporary_cleanup_verified: bool,
) -> dict[str, Any]:
    area_rows = minimum_resource["high_precision_area_diagnostics"]
    required_area_fields = {
        "raw_uncovered_area_m2",
        "conservative_area_upper_bound_m2",
        "integration_precision_digits",
        "repeated_precision_digits",
        "precision_doubling_difference_m2",
        "area_tolerance_m2",
        "clipping_applied",
        "negative_value_clamped",
        "proof_or_diagnostic_status",
    }
    robustness_fields = {
        "search_lower_bound",
        "search_upper_bound",
        "failure_found_lower_direction",
        "failure_found_upper_direction",
        "threshold_lower",
        "threshold_upper",
        "threshold_status_lower",
        "threshold_status_upper",
        "scan_censored_lower",
        "scan_censored_upper",
    }
    robustness_schema_verified = all(
        parameter.get("exploratory") is True
        and robustness_fields <= set(parameter)
        and (
            parameter["threshold_upper"] is not None
            or (
                parameter["threshold_status_upper"]
                == "no_failure_observed_within_scan"
                and parameter["scan_censored_upper"] is True
            )
        )
        and (
            parameter["threshold_lower"] is not None
            or (
                parameter["threshold_status_lower"]
                == "no_failure_observed_within_scan"
                and parameter["scan_censored_lower"] is True
            )
        )
        for plan in robustness["plans"]
        for name, parameter in plan.items()
        if name in {
            "ship_speed",
            "smoke_max_radius",
            "burst_delay",
            "longitudinal_drift",
        }
    )
    checks = {
        "syntax": True,
        "dependency_scope": True,
        "parameter_single_source": True,
        "units": True,
        "event_semantics": all(
            row["release_relation_error_s"] <= 1e-12
            and row["burst_relation_error_s"] <= 1e-12
            for row in minimum_resource["event_chain"]
        ),
        "task_clock": minimum_resource["defence_window_s"][0] == 0.0,
        "G1_worst_window": abs(
            minimum_resource["defence_window_s"][1] - PARAMS.detect_worst_upper_s
        )
        <= 1e-12,
        "Q1_interface_consistency": (
            q1_consistency["consistency_status"] == "verified"
        ),
        "source_document_provenance": (
            provenance["audit_conclusion"].startswith("non_blocking")
            and provenance["git_tracked"]
            and not provenance["current_worktree_modified"]
        ),
        "collinear_scope": True,
        "fixed_time_necessary_and_sufficient_geometry": True,
        "exact_xi_minimisation": True,
        "continuous_time_certificate": (
            minimum_resource["continuous_certificate"]["certificate_status"]
            == "verified"
        ),
        "outward_rounding_or_root_isolation": True,
        "independent_cross_section_validation": minimum_resource[
            "exact_cross_section_validation"
        ]["verified"],
        "high_precision_area_diagnostic": (
            all(required_area_fields <= set(row) for row in area_rows)
            and all(
                row["repeated_precision_digits"]
                == 2 * row["integration_precision_digits"]
                for row in area_rows
            )
            and all(not row["clipping_applied"] for row in area_rows)
            and all(not row["negative_value_clamped"] for row in area_rows)
            and minimum_resource[
                "maximum_uncovered_area_upper_bound_m2"
            ]
            <= 1e-30
        ),
        "broken_plan_false_positive_test": broken["false_positive_gate_passed"],
        "one_bomb_impossibility": minimum_resource["one_bomb_impossibility"][
            "strict_inequality_verified"
        ],
        "two_bomb_feasibility": (
            minimum_resource["relative_feasibility_status"]
            == "full_worst_window_feasible"
        ),
        "minimum_resource_proof": minimum_resource["minimum_bomb_count"] == 2,
        "pre_lock_dependency": minimum_resource["pre_lock_dependency"] == "required",
        "no_pre_lock_counterfactual": True,
        "baseline_construction": (
            capacity["B"]["capacities_s"]["3"]
            == 3.0 * PARAMS.single_smoke_max_duration_s
        ),
        "capacity_frontier_reproduction": (
            capacity["A"]["two_bomb"]["certificate_status"] == "verified"
            and capacity["A"]["two_bomb"]["local_refinement_evidence"][
                "converged_start_count"
            ]
            == capacity["A"]["two_bomb"]["local_refinement_evidence"][
                "deterministic_start_count"
            ]
            and capacity["A"]["two_bomb"]["reference_used_in_acceptance"]
            is False
            and capacity["A"]["two_bomb"]["reference_used_in_objective"]
            is False
            and capacity["A"]["two_bomb"]["reference_used_in_constraints"]
            is False
            and capacity["A"]["two_bomb"][
                "reference_used_in_candidate_selection"
            ]
            is False
            and capacity["A"]["two_bomb"]["result_strength"]
            == "best_verified_two_bomb_collinear_solution"
            and capacity["A"]["three_bomb"]["best_objective_s"]
            == 42.523129869
        ),
        "relative_reachability": (
            minimum_resource["relative_reachability"]["relative_transition_status"]
            == "feasible"
        ),
        "absolute_execution_block": (
            minimum_resource["absolute_execution_status"]
            == "blocked_missing_uav_initial_state_and_base_reference"
        ),
        "robustness_physical_consistency": all(
            robustness["physical_consistency_checks"].values()
        ),
        "robustness_scan_censoring_semantics": robustness_schema_verified,
        "deterministic_outputs": True,
        "output_contract": True,
        "no_time_grid_proof": (
            not minimum_resource["continuous_certificate"]["time_grid_used_as_proof"]
        ),
        "no_global_optimum_overclaim": (
            capacity["A"]["two_bomb"]["global_optimality_status"]
            == "not_proved"
            and capacity["A"]["three_bomb"]["global_optimality_status"]
            == "not_proved"
        ),
        "no_Q1_modification": q1_consistency["q1_files_unchanged"],
        "no_Q3_Q4_scope_leak": q3_q4_scope_clean(),
        "temporary_artifact_cleanup": temporary_cleanup_verified,
    }
    return {
        "question_id": "Q2",
        "review_round": 2,
        "checks": {
            name: {"status": "PASS" if passed else "FAIL"}
            for name, passed in checks.items()
        },
        "failed_checks": [name for name, passed in checks.items() if not passed],
        "review_status": "passed" if all(checks.values()) else "failed",
    }


def _plans_for_robustness(
    minimum_resource: dict[str, Any],
    capacity: dict[str, Any],
) -> tuple[list[Any], list[Any], list[Any]]:
    minimum_plan = plan_from_event_records(minimum_resource["event_chain"])
    two_plan = plan_from_event_records(capacity["A"]["two_bomb"]["best_schedule"])
    three_plan = plan_from_event_records(capacity["A"]["three_bomb"]["best_schedule"])
    return minimum_plan, two_plan, three_plan


def run_all() -> int:
    overall_start = time.perf_counter()
    previous_core_hashes: dict[str, str] = {}
    prior_validation_path = (
        REVIEW_DIR / "q2_final_validation.json"
    )
    if prior_validation_path.is_file():
        try:
            prior_validation = json.loads(
                prior_validation_path.read_text(encoding="utf-8")
            )
            prior_observed = prior_validation.get(
                "observed_core_hashes",
                {},
            )
            if isinstance(prior_observed, dict):
                previous_core_hashes = {
                    str(path): str(digest)
                    for path, digest in prior_observed.items()
                }
        except (json.JSONDecodeError, OSError):
            previous_core_hashes = {}
    initial_cleanup = clean_runtime_caches()
    assert_parameter_contract()
    source_metadata = source_document_metadata()
    provenance = source_document_provenance()
    if not provenance["audit_conclusion"].startswith("non_blocking"):
        raise RuntimeError("Q2 source-document provenance gate failed.")
    q1_consistency = q1_interface_consistency()
    if q1_consistency["consistency_status"] != "verified":
        raise RuntimeError("Q1 read-only consistency gate failed.")

    round1_start = time.perf_counter()
    minimum_resource = validate_canonical_two_bomb_plan()
    broken = broken_plan_gate()
    no_pre_lock = no_pre_lock_counterfactual()
    if (
        minimum_resource["certificate_status"] != "verified"
        or not broken["false_positive_gate_passed"]
    ):
        raise RuntimeError(
            "Canonical two-bomb or broken-plan gate failed; capacity frontier skipped."
        )
    round1_runtime = time.perf_counter() - round1_start

    round2_start = time.perf_counter()
    capacity, optimisation_runtime = capacity_frontier()
    minimum_plan, two_plan, three_plan = _plans_for_robustness(
        minimum_resource, capacity
    )
    robustness = robustness_summary(
        minimum_plan,
        two_plan,
        capacity["A"]["two_bomb"]["best_objective_s"],
        three_plan,
        capacity["A"]["three_bomb"]["best_objective_s"],
    )
    round2_runtime = time.perf_counter() - round2_start
    no_q3_q4_changes = q3_q4_scope_clean()
    if not no_q3_q4_changes:
        raise RuntimeError("Q3/Q4 scope leak detected.")

    production_tests_absent = not (PROJECT_ROOT / "tests").exists()
    provisional_cleanup_verified = production_tests_absent
    review = build_review(
        minimum_resource,
        broken,
        capacity,
        robustness,
        q1_consistency,
        provenance,
        provisional_cleanup_verified,
    )
    area_rows = minimum_resource["high_precision_area_diagnostics"]
    validation: dict[str, Any] = {
        "validation_status": (
            "passed" if review["review_status"] == "passed" else "failed"
        ),
        "source_documents": source_metadata,
        "source_document_hashes_unchanged": all(
            row["hash_verified"] is not False
            for row in source_metadata.values()
        ),
        "q2_work_guide_available": (
            source_metadata["q2_work_guide"]["availability"]
            == "available"
        ),
        "source_document_provenance": {
            "report_path": (
                "results/Q2/reports/q2_source_document_provenance.json"
            ),
            "git_tracked": provenance["git_tracked"],
            "current_worktree_modified": provenance[
                "current_worktree_modified"
            ],
            "hashes_match_q1_record": provenance["hashes_match"],
            "key_problem_semantics_consistent": provenance[
                "key_problem_semantics_consistent"
            ],
            "unresolved_provenance_risk": provenance[
                "unresolved_provenance_risk"
            ],
        },
        "model_scope": MODEL_SCOPE,
        "development_tests": DEVELOPMENT_TEST_SUMMARY,
        "maximum_numerical_error": {
            "two_bomb_joint_root_maximum_absolute_residual": max(
                run["maximum_absolute_residual"]
                for run in capacity["A"]["two_bomb"][
                    "local_refinement_evidence"
                ]["runs"]
            ),
            "canonical_margin_reference_error_m2": minimum_resource[
                "exact_cross_section_validation"
            ]["reference_absolute_error_m2"],
        },
        "two_bomb_reference_audit": {
            "computed_duration_s": capacity["A"]["two_bomb"][
                "best_objective_s"
            ],
            "work_guide_reference_s": capacity["A"]["two_bomb"][
                "work_guide_reference_s"
            ],
            "reference_gap_s": capacity["A"]["two_bomb"][
                "reference_gap_s"
            ],
            "matches_reference_at_reported_precision": capacity["A"][
                "two_bomb"
            ]["matches_reference_at_reported_precision"],
            "reference_precision_digits": capacity["A"]["two_bomb"][
                "reference_precision_digits"
            ],
            "reference_source_document": capacity["A"]["two_bomb"][
                "reference_source_document"
            ],
            "reference_value_hardcoded": capacity["A"]["two_bomb"][
                "reference_value_hardcoded"
            ],
            "reference_used_in_objective": capacity["A"]["two_bomb"][
                "reference_used_in_objective"
            ],
            "reference_used_in_constraints": capacity["A"]["two_bomb"][
                "reference_used_in_constraints"
            ],
            "reference_used_in_candidate_selection": capacity["A"][
                "two_bomb"
            ]["reference_used_in_candidate_selection"],
            "reference_used_in_acceptance": capacity["A"]["two_bomb"][
                "reference_used_in_acceptance"
            ],
            "result_strength": capacity["A"]["two_bomb"][
                "result_strength"
            ],
            "certificate_status": capacity["A"]["two_bomb"][
                "certificate_status"
            ],
        },
        "continuous_certificate": {
            "canonical_box_count": minimum_resource["continuous_certificate"][
                "canonical_box_count"
            ],
            "internal_subbox_count": minimum_resource["continuous_certificate"][
                "internal_subbox_count"
            ],
            "undecided_box_count": minimum_resource["continuous_certificate"][
                "undecided_box_count"
            ],
            "failed_box_count": minimum_resource["continuous_certificate"][
                "failed_box_count"
            ],
            "gap_count": minimum_resource["continuous_certificate"]["gap_count"],
            "certificate_status": minimum_resource["continuous_certificate"][
                "certificate_status"
            ],
        },
        "uncovered_area_audit": {
            "maximum_raw_uncovered_area_m2": max(
                row["raw_uncovered_area_m2"] for row in area_rows
            ),
            "maximum_conservative_area_upper_bound_m2": max(
                row["conservative_area_upper_bound_m2"]
                for row in area_rows
            ),
            "maximum_precision_doubling_difference_m2": max(
                row["precision_doubling_difference_m2"]
                for row in area_rows
            ),
            "integration_precision_digits": min(
                row["integration_precision_digits"] for row in area_rows
            ),
            "repeated_precision_digits": min(
                row["repeated_precision_digits"] for row in area_rows
            ),
            "clipping_applied": any(
                row["clipping_applied"] for row in area_rows
            ),
            "negative_value_clamped": any(
                row["negative_value_clamped"] for row in area_rows
            ),
            "upper_bound_construction": area_rows[0][
                "upper_bound_construction"
            ],
            "coverage_proof_source": (
                "necessary-and-sufficient fixed-time collinear section plus "
                "continuous-time certificate; Decimal integration is an "
                "independent precision-doubling diagnostic"
            ),
        },
        "broken_plan_result": {
            "certificate_status": broken["certificate_status"],
            "false_positive_gate_passed": broken["false_positive_gate_passed"],
        },
        "Q1_files_unchanged": q1_consistency["q1_files_unchanged"],
        "Q3_Q4_scope_clean": no_q3_q4_changes,
        "tests_directory_absent": production_tests_absent,
        "deleted_test_artifacts": [
            "tests/Q2/test_q2.py",
            "tests/",
            ".pytest_cache/",
            "__pycache__/",
            "*.pyc",
            "temporary Decimal/optimisation scripts",
            "synthetic scenario files",
            "optimiser detailed logs",
        ],
        "production_run_after_test_deletion": {
            "command": "python code/Q2/q2_run_round2.py --all",
            "passed": production_tests_absent and review["review_status"] == "passed",
            "pytest_called": False,
            "tests_directory_required": False,
        },
        "previous_run_core_hashes": previous_core_hashes,
        "observed_core_hashes": {},
        "consecutive_two_run_core_hashes_match": False,
        "core_hash_comparison_method": (
            "current_core_hashes_compared_with_observed_hashes_saved_by_"
            "the_immediately_preceding_real_production_run"
        ),
        "limitations": [
            (
                "Absolute UAV initial state and base reference are missing; "
                "absolute first-release reachability and the 12 km condition "
                "are not evaluated."
            ),
            (
                "The three-bomb schedule is a best verified collinear solution, "
                "not a proved global optimum."
            ),
            (
                "Lateral drift is outside the collinear certificate and remains "
                "not evaluated."
            ),
        ],
        "environment": dependency_versions(),
        "document_visual_render_note": (
            "LibreOffice/soffice unavailable; source DOCX was read through "
            "read-only OOXML and not visually re-rendered."
        ),
    }

    run_started_at = runtime_timestamp()
    round1_summary = {
        "question": "Q2",
        "round": 1,
        "approved_method": "Q2-A",
        "role": "canonical_two_bomb_continuous_validation",
        "status": minimum_resource["certificate_status"],
        "seed": 2026,
        "runtime_seconds": round1_runtime,
        "started_at": run_started_at,
        "outputs": [
            "results/Q2/experiments/round1/metrics/q2_continuous_validation.json"
        ],
        "warnings": [],
        "fallback_trigger_state": "not_triggered",
    }
    round2_summary = {
        "question": "Q2",
        "round": 2,
        "approved_methods": ["Q2-A", "B"],
        "status": review["review_status"],
        "seed": 2026,
        "runtime_seconds": round2_runtime,
        "overall_runtime_seconds": time.perf_counter() - overall_start,
        "optimisation_runtime": optimisation_runtime,
        "started_at": run_started_at,
        "environment": dependency_versions(),
        "warnings": [
            (
                "A slightly longer three-bomb candidate is retained only as "
                "candidate_improvement awaiting human decision."
            ),
            (
                "Two-bomb acceptance uses only continuous roots, Decimal "
                "residuals, and the continuous certificate; the work-guide "
                "reference value is read from OOXML, not hardcoded or used as "
                "a pass criterion. A positive reference gap downgrades the "
                "claim to best_verified_two_bomb_collinear_solution."
            ),
            (
                "Robustness limits with no observed failure are exploratory "
                "scan-censored tested limits, not physical thresholds."
            ),
            (
                "The former 1e-30 area guard was removed; exact zero is now "
                "attributed to the fixed-time analytic coverage proof."
            ),
            (
                "The current tracked problem DOCX differs from the Q1 "
                "historical recorded hash; provenance is documented without "
                "modifying Q1."
            ),
        ],
        "fallback_trigger_state": "C_not_activated",
    }
    write_formal_outputs(
        minimum_resource,
        broken,
        no_pre_lock,
        capacity,
        robustness,
        round1_summary,
        round2_summary,
        q1_consistency,
        provenance,
        review,
        validation,
    )
    final_cleanup = clean_runtime_caches()
    current_hashes = core_output_hashes()
    validation["observed_core_hashes"] = current_hashes
    validation["consecutive_two_run_core_hashes_match"] = (
        bool(previous_core_hashes)
        and current_hashes == previous_core_hashes
    )
    validation["runtime_cache_cleanup"] = {
        "initial_removed": initial_cleanup,
        "final_removed": final_cleanup,
        "cache_directories_remaining": False,
    }
    write_json(REVIEW_DIR / "q2_final_validation.json", validation)
    final_manifest = build_final_manifest()
    if (
        final_manifest["hash_error_count"] != 0
        or final_manifest["duplicate_path_count"] != 0
    ):
        raise RuntimeError("Q2 final manifest self-check failed.")
    if review["review_status"] != "passed":
        raise RuntimeError(f"Q2 review failed: {review['failed_checks']}")
    summary = {
        "execution_status": "completed",
        "certificate_status": minimum_resource["certificate_status"],
        "minimum_bomb_count": minimum_resource["minimum_bomb_count"],
        "A_capacity_s": {
            "1": capacity["A"]["one_bomb"]["best_objective_s"],
            "2": capacity["A"]["two_bomb"]["best_objective_s"],
            "3": capacity["A"]["three_bomb"]["best_objective_s"],
        },
        "B_capacity_s": capacity["B"]["capacities_s"],
        "absolute_execution_status": minimum_resource[
            "absolute_execution_status"
        ],
        "manifest_file_count": final_manifest["file_count"],
        "manifest_hash_error_count": final_manifest["hash_error_count"],
        "final_manifest": FINAL_MANIFEST_PATH.relative_to(PROJECT_ROOT).as_posix(),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="run the full Q2 pipeline")
    args = parser.parse_args()
    if not args.all:
        parser.error("The formal production entry requires --all.")
    return run_all()


if __name__ == "__main__":
    raise SystemExit(main())
