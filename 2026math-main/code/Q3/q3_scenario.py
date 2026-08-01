"""Load and validate the two-layer Q3 input contract."""

from __future__ import annotations

from typing import Any

from q3_common import (
    FREEZE_STATUS,
    REFERENCE_PATH,
    SCENARIO_PATH,
    SCENARIO_SCOPE,
    read_json,
    sha256_file,
)


def load_scenario() -> dict[str, Any]:
    scenario = read_json(SCENARIO_PATH)
    if scenario["scenario_scope"] != SCENARIO_SCOPE:
        raise ValueError("The standardized scenario must retain its synthetic label.")
    if scenario["freeze_status"] != FREEZE_STATUS:
        raise ValueError("Q3 values must remain unfrozen.")
    if len(scenario["uav_staging_states"]) != 3:
        raise ValueError("Exactly three synthetic UAV staging states are required.")
    lower, upper = scenario["allowed_start_time_window_s"]
    if (float(lower), float(upper)) != (-60.0, 0.0):
        raise ValueError("The authorized pre-deployment window is [-60, 0] s.")
    return scenario


def load_reference_plan() -> dict[str, Any]:
    reference = read_json(REFERENCE_PATH)
    if sha256_file(REFERENCE_PATH.parent.parent.parent / reference["source_document"]) != reference[
        "source_sha256"
    ]:
        raise ValueError("The Q3 reference source hash changed.")
    for flag in (
        "used_in_optimizer_objective",
        "used_in_optimizer_constraints",
        "used_in_candidate_acceptance",
    ):
        if reference[flag]:
            raise ValueError(f"Reference isolation flag must be false: {flag}")
    if not reference["used_as_human_selected_fixed_candidate"]:
        raise ValueError("P2 must remain the human-selected fixed candidate.")
    return reference


def input_contract() -> dict[str, Any]:
    scenario = load_scenario()
    reference = load_reference_plan()
    return {
        "scenario": scenario,
        "reference": reference,
        "parameterized_formal_inputs": {
            "uav_state_at_available_time": "u_i(a_i)",
            "initial_heading": "psi_i(a_i)",
            "availability_time": "a_i",
            "incoming_bearing": "beta",
            "safety_distance": "d_safe",
            "physical_models": ["G1", "S1", "O0", "U0"],
        },
        "absolute_base_radius_status": "blocked_missing_base_reference",
    }
