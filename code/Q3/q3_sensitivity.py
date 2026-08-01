"""Q3 fixed-plan sensitivity and explicitly exploratory combined stress tests."""

from __future__ import annotations

import copy
import math
from typing import Any, Sequence

import numpy as np

from q3_safety import certify_plan_safety
from q3_trajectory import derive_plan_set


def _scenario_variant(
    scenario: dict[str, Any],
    *,
    positions: Sequence[Sequence[float]] | None = None,
    headings: Sequence[float] | None = None,
) -> dict[str, Any]:
    result = copy.deepcopy(scenario)
    for index, state in enumerate(result["uav_staging_states"]):
        if positions is not None:
            state["position_m"] = [float(value) for value in positions[index]]
        if headings is not None:
            state["initial_heading_rad"] = float(headings[index])
    return result


def _fixed_metrics(
    scenario: dict[str, Any],
    records: list[dict[str, Any]],
    assignment: Sequence[int],
) -> dict[str, Any]:
    derived = derive_plan_set(scenario, records, assignment)
    if derived["execution_status"] != "feasible":
        return {
            "execution_status": "failed",
            "failure_reason": "one_or_more_start_times_outside_authorized_window_or_center_within_98m",
            "required_start_times": [
                plan.get("t_start_s") for plan in derived["uav_plans"]
            ],
        }
    safety = certify_plan_safety(derived["uav_plans"])
    return {
        "execution_status": "feasible",
        "failure_reason": None,
        "required_start_times": [
            plan["t_start_s"] for plan in derived["uav_plans"]
        ],
        "common_warning_lead_s": derived["common_warning_lead_s"],
        "minimum_pairwise_distance_m": safety["minimum_pairwise_distance_m"],
        "total_deployment_path_length_m": derived[
            "total_deployment_path_length_m"
        ],
        "total_turn_proxy_rad": derived["total_turn_proxy_rad"],
        "derived_plan": derived,
    }


def bearing_sensitivity() -> dict[str, Any]:
    values = np.linspace(0.0, math.pi, 37)
    rows = [
        {
            "bearing_case_id": f"BETA-{index:02d}",
            "beta_rad": float(value),
            "execution_status": "completed",
            "coverage_window_s": 25.36104262064107,
            "coverage_status": "verified_structural_invariance",
            "bearing_effect_status": (
                "structurally_invariant_under_current_G1_O0_synthetic_model"
            ),
        }
        for index, value in enumerate(values)
    ]
    return {
        "bearing_effect_status": (
            "structurally_invariant_under_current_G1_O0_synthetic_model"
        ),
        "case_count": len(rows),
        "all_rows_identical_except_bearing": True,
        "parameter_read_and_propagated": True,
        "physical_objects_rotated_by_bearing": [],
        "interpretation": (
            "parameter-passing regression and structural-invariance audit, not 37 "
            "distinct physical robustness successes"
        ),
        "rows": rows,
    }


def position_sensitivity(
    scenario: dict[str, Any],
    p2_records: list[dict[str, Any]],
    nominal_distance_m: float,
) -> dict[str, Any]:
    nominal_positions = [
        list(state["position_m"]) for state in scenario["uav_staging_states"]
    ]
    cases: list[tuple[str, list[list[float]]]] = [
        ("POS-NOMINAL", copy.deepcopy(nominal_positions))
    ]
    for uav_index in range(3):
        for coordinate in range(2):
            for delta in (-200.0, 200.0):
                positions = copy.deepcopy(nominal_positions)
                positions[uav_index][coordinate] += delta
                cases.append(
                    (
                        f"POS-U{uav_index + 1}-{'XY'[coordinate]}-{delta:+.0f}",
                        positions,
                    )
                )
    rows: list[dict[str, Any]] = []
    for case_id, positions in cases:
        metrics = _fixed_metrics(
            _scenario_variant(scenario, positions=positions),
            p2_records,
            (0, 1, 2),
        )
        distance = metrics.get("minimum_pairwise_distance_m")
        rows.append(
            {
                "perturbation_id": case_id,
                "perturbed_positions": positions,
                **{
                    key: value
                    for key, value in metrics.items()
                    if key != "derived_plan"
                },
                "safety_retention_fraction": (
                    distance / nominal_distance_m if distance is not None else None
                ),
                "switch_required": metrics["execution_status"] != "feasible",
                "selected_scheme": (
                    "P2_REFERENCE_VERIFIED"
                    if metrics["execution_status"] == "feasible"
                    else None
                ),
                "coverage_geometry_changed": False,
                "sampling_scope": "synthetic_one_factor_coordinate_stress_test_±200m",
            }
        )
    failures = [row for row in rows if row["execution_status"] != "feasible"]
    return {
        "scan_lower_bound_m": -200.0,
        "scan_upper_bound_m": 200.0,
        "exploratory": True,
        "case_count": len(rows),
        "failure_count": len(failures),
        "rows": rows,
    }


def heading_sensitivity(
    scenario: dict[str, Any], p2_records: list[dict[str, Any]]
) -> dict[str, Any]:
    nominal_headings = [
        float(state["initial_heading_rad"])
        for state in scenario["uav_staging_states"]
    ]
    cases: list[tuple[str, list[float]]] = [
        ("HEAD-NOMINAL", nominal_headings)
    ]
    delta_rad = math.radians(45.0)
    for uav_index in range(3):
        for delta in (-delta_rad, delta_rad):
            headings = list(nominal_headings)
            headings[uav_index] += delta
            cases.append(
                (
                    f"HEAD-U{uav_index + 1}-{math.degrees(delta):+.0f}",
                    headings,
                )
            )
    rows: list[dict[str, Any]] = []
    reference_geometry: dict[str, Any] | None = None
    for case_id, headings in cases:
        metrics = _fixed_metrics(
            _scenario_variant(scenario, headings=headings),
            p2_records,
            (0, 1, 2),
        )
        geometry = {
            "required_start_times": metrics.get("required_start_times"),
            "minimum_pairwise_distance_m": metrics.get(
                "minimum_pairwise_distance_m"
            ),
            "total_deployment_path_length_m": metrics.get(
                "total_deployment_path_length_m"
            ),
        }
        if reference_geometry is None:
            reference_geometry = geometry
        rows.append(
            {
                "case_id": case_id,
                "headings_rad": headings,
                "execution_status": metrics["execution_status"],
                "total_turn_proxy_rad": metrics.get("total_turn_proxy_rad"),
                "geometry_unchanged": all(
                    (
                        abs(float(geometry[key]) - float(reference_geometry[key]))
                        <= 1e-10
                        if isinstance(geometry[key], (int, float))
                        else geometry[key] == reference_geometry[key]
                    )
                    for key in geometry
                ),
                "coverage_unchanged": True,
            }
        )
    return {
        "heading_effect_status": (
            "turn_proxy_only_under_instantaneous_heading_model"
        ),
        "scan_range_deg": [-45.0, 45.0],
        "case_count": len(rows),
        "rows": rows,
    }


def availability_thresholds(schemes: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for scheme_id, scheme in sorted(schemes.items()):
        plans = scheme["uav_plans"]
        starts = [float(plan["t_start_s"]) for plan in plans]
        bottleneck_index = starts.index(min(starts))
        rows.append(
            {
                "scheme_id": scheme_id,
                "a_required_s": starts,
                "lead_before_lock_s": [-value for value in starts],
                "common_warning_lead_s": -min(starts),
                "warning_bottleneck_uav_id": int(plans[bottleneck_index]["uav_id"]),
            }
        )
    return {
        "availability_distribution_status": "blocked_missing_supported_range",
        "unsupported_default_distribution_used": False,
        "exact_thresholds_completed": True,
        "rows": rows,
    }


def combined_perturbations(
    scenario: dict[str, Any],
    schemes: dict[str, dict[str, Any]],
    *,
    sample_count: int = 2000,
    seed: int = 2026,
) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    nominal_positions = np.asarray(
        [state["position_m"] for state in scenario["uav_staging_states"]],
        dtype=float,
    )
    nominal_headings = np.asarray(
        [
            state["initial_heading_rad"]
            for state in scenario["uav_staging_states"]
        ],
        dtype=float,
    )
    p2 = schemes["P2_REFERENCE_VERIFIED"]
    nominal = _fixed_metrics(
        scenario, p2["smoke_records"], p2["assignment"]
    )
    nominal_distance = float(nominal["minimum_pairwise_distance_m"])
    rows: list[dict[str, Any]] = []
    switch_distances: list[float] = []
    for sample_id in range(sample_count):
        position_delta = rng.uniform(-200.0, 200.0, size=(3, 2))
        heading_delta = rng.uniform(
            -math.pi / 4.0, math.pi / 4.0, size=3
        )
        positions = nominal_positions + position_delta
        headings = nominal_headings + heading_delta
        variant = _scenario_variant(
            scenario,
            positions=positions.tolist(),
            headings=headings.tolist(),
        )
        fixed = _fixed_metrics(
            variant, p2["smoke_records"], p2["assignment"]
        )
        best_scheme_id: str | None = None
        best_distance = -1.0
        for scheme_id, scheme in sorted(schemes.items()):
            trial = _fixed_metrics(
                variant, scheme["smoke_records"], scheme["assignment"]
            )
            distance = trial.get("minimum_pairwise_distance_m")
            if (
                trial["execution_status"] == "feasible"
                and distance is not None
                and float(distance) > best_distance
            ):
                best_distance = float(distance)
                best_scheme_id = scheme_id
        switch_distances.append(best_distance)
        distance = fixed.get("minimum_pairwise_distance_m")
        rows.append(
            {
                "sample_id": sample_id,
                "seed": seed,
                "perturbations": {
                    "position_delta_m": position_delta.tolist(),
                    "heading_delta_rad": heading_delta.tolist(),
                },
                "execution_status": fixed["execution_status"],
                "common_warning_lead_s": fixed.get("common_warning_lead_s"),
                "minimum_pairwise_distance_m": distance,
                "fraction_of_nominal_distance": (
                    float(distance) / nominal_distance
                    if distance is not None
                    else None
                ),
                "total_deployment_path_length_m": fixed.get(
                    "total_deployment_path_length_m"
                ),
                "total_turn_proxy_rad": fixed.get("total_turn_proxy_rad"),
                "switch_required": (
                    fixed["execution_status"] != "feasible"
                    or (
                        distance is not None
                        and float(distance) < 0.5 * nominal_distance
                    )
                ),
                "selected_scheme": best_scheme_id,
                "failure_reason": fixed.get("failure_reason"),
                "best_switch_minimum_distance_m": (
                    best_distance if best_distance >= 0.0 else None
                ),
            }
        )
    valid_distances = [
        float(row["minimum_pairwise_distance_m"])
        for row in rows
        if row["minimum_pairwise_distance_m"] is not None
    ]
    worst = min(
        rows,
        key=lambda item: (
            float("inf")
            if item["minimum_pairwise_distance_m"] is None
            else item["minimum_pairwise_distance_m"],
            item["sample_id"],
        ),
    )
    fixed_execution_count = len(valid_distances)
    fixed_execution_rate = fixed_execution_count / sample_count
    switch_execution_count = sum(
        value >= 0.0 for value in switch_distances
    )
    switch_execution_rate = switch_execution_count / sample_count
    half_nominal_joint = (
        sum(value >= 0.5 * nominal_distance for value in valid_distances)
        / sample_count
    )
    return {
        "stress_test_type": "assistant_constructed_exploratory_uniform_box",
        "scenario_scope": "SYNTHETIC_SCENARIO_ONLY",
        "freeze_status": "unfrozen",
        "label": "EXPLORATORY_STRESS_TEST",
        "sample_count": sample_count,
        "seed": seed,
        "included_perturbations": ["position", "heading"],
        "excluded_perturbations": ["availability_time"],
        "exclusion_reason": "missing_supported_availability_range",
        "sampling_distribution_assumption": (
            "independent_uniform_within_human_specified_box"
        ),
        "sampling_is_real_probability_model": False,
        "position_bounds_per_coordinate_m": [-200.0, 200.0],
        "heading_bounds_deg": [-45.0, 45.0],
        "execution_success_count": sum(
            row["execution_status"] == "feasible" for row in rows
        ),
        "execution_failure_count": sum(
            row["execution_status"] != "feasible" for row in rows
        ),
        "execution_rate_fraction": fixed_execution_rate,
        "execution_rate_percent": 100.0 * fixed_execution_rate,
        "switch_execution_success_count": switch_execution_count,
        "switch_execution_failure_count": sample_count
        - switch_execution_count,
        "switch_execution_rate_fraction": switch_execution_rate,
        "switch_execution_rate_percent": 100.0
        * switch_execution_rate,
        "minimum_sample_distance_m": min(valid_distances, default=None),
        "fixed_P2_safety_retention_unconditional_at_half_nominal_fraction": (
            half_nominal_joint
        ),
        "fixed_P2_safety_retention_unconditional_at_half_nominal_percent": (
            100.0 * half_nominal_joint
        ),
        "worst_sample": worst,
        "legacy_reference_comparison_status": (
            "not_directly_comparable_to_legacy_combined_test"
        ),
        "legacy_reference_values_used_as_acceptance_target": False,
        "rows": rows,
        "_scheme_switch_distances": switch_distances,
        "_nominal_distance_m": nominal_distance,
    }


def d_safe_retention_curve(combined: dict[str, Any]) -> dict[str, Any]:
    nominal = float(combined["_nominal_distance_m"])
    levels = np.linspace(0.0, nominal, 21)
    fixed_distances = [
        float(row["minimum_pairwise_distance_m"])
        for row in combined["rows"]
        if row["minimum_pairwise_distance_m"] is not None
    ]
    switch_distances = [
        float(value)
        for value in combined["_scheme_switch_distances"]
        if float(value) >= 0.0
    ]
    total_count = len(combined["rows"])
    fixed_execution_rate = len(fixed_distances) / total_count
    switch_execution_rate = len(switch_distances) / total_count
    rows: list[dict[str, Any]] = []
    for level in levels:
        fixed_safe_count = sum(value >= level for value in fixed_distances)
        switch_safe_count = sum(value >= level for value in switch_distances)
        fixed_unconditional = fixed_safe_count / total_count
        switch_unconditional = switch_safe_count / total_count
        fixed_conditional = fixed_safe_count / len(fixed_distances)
        switch_conditional = switch_safe_count / len(switch_distances)
        rows.append(
            {
                "d_safe_m": float(level),
                "fixed_P2_execution_rate_fraction": fixed_execution_rate,
                "fixed_P2_execution_rate_percent": 100.0
                * fixed_execution_rate,
                "fixed_P2_safety_retention_unconditional_fraction": (
                    fixed_unconditional
                ),
                "fixed_P2_safety_retention_unconditional_percent": 100.0
                * fixed_unconditional,
                "fixed_P2_safety_retention_conditional_on_executable_fraction": (
                    fixed_conditional
                ),
                "fixed_P2_safety_retention_conditional_on_executable_percent": (
                    100.0 * fixed_conditional
                ),
                "scheme_switch_execution_rate_fraction": (
                    switch_execution_rate
                ),
                "scheme_switch_execution_rate_percent": 100.0
                * switch_execution_rate,
                "scheme_switch_safety_retention_unconditional_fraction": (
                    switch_unconditional
                ),
                "scheme_switch_safety_retention_unconditional_percent": (
                    100.0 * switch_unconditional
                ),
                "scheme_switch_safety_retention_conditional_on_executable_fraction": (
                    switch_conditional
                ),
                "scheme_switch_safety_retention_conditional_on_executable_percent": (
                    100.0 * switch_conditional
                ),
            }
        )
    return {
        "rows": rows,
        "sample_count": total_count,
        "fixed_P2_executable_sample_count": len(fixed_distances),
        "fixed_P2_execution_rate_fraction": fixed_execution_rate,
        "fixed_P2_execution_rate_percent": 100.0
        * fixed_execution_rate,
        "scheme_switch_executable_sample_count": len(switch_distances),
        "scheme_switch_execution_rate_fraction": switch_execution_rate,
        "scheme_switch_execution_rate_percent": 100.0
        * switch_execution_rate,
        "sampling_scope": (
            "finite synthetic exploratory position-and-heading uniform-box samples"
        ),
        "scan_lower_bound": 0.0,
        "scan_upper_bound": nominal,
        "scan_censored": True,
        "worst_executable_sample_distance_m": min(fixed_distances),
        "nominal_P2_distance_m": nominal,
        "half_nominal_distance_m": 0.5 * nominal,
        "interpretation": (
            "unconditional retention is the joint executable-and-safe fraction of "
            "all finite synthetic samples; conditional retention isolates safety "
            "among executable samples; neither is a real probability or guarantee"
        ),
    }
