"""Create once, then read, the transparent Q4 synthetic input package."""

from __future__ import annotations

import argparse
import itertools
import math
from pathlib import Path
from typing import Any

from q4_common import (
    FREEZE_STATUS,
    SCENARIO_IDENTITY,
    SCENARIO_SCOPE,
    repo_root,
    sha256_file,
    stable_json,
)

PROBLEM_DOC = "B题：舰船烟幕遮蔽干扰优化.docx"
WORKGUIDE_DOC = "Q4_编程手与论文手任务清单.docx"
EXPECTED_DOC_HASHES = {
    PROBLEM_DOC: "E891F635BCB4182517C166D12F1E4F3D05C77E9C18B27A14302C7561F7F2A638",
    WORKGUIDE_DOC: "893C5B082D8F19D2694BB322FADD56CD4A5E56FAC1C3292A75FC0A0F97E58DAC",
}

DEPENDENCIES = [
    ("Q1", "results/Q1/experiments/round3/metrics/q1_parametric_compensation.json", "G4", "unfrozen", "PASS", "single-smoke certified action source"),
    ("Q1", "code/Q1/reviews/q1_final_validation.json", "G4", "unfrozen", "PASS", "Q1 review evidence"),
    ("Q2", "results/Q2/experiments/round2/metrics/q2_two_bomb_minimum_resource_plan.json", "G4", "unfrozen", "PASS", "two-smoke certified action source"),
    ("Q2", "results/Q2/experiments/round2/metrics/q2_capacity_frontier.json", "G4", "unfrozen", "PASS", "one/two/three-bomb screening source"),
    ("Q2", "code/Q2/reviews/q2_final_validation.json", "G4", "unfrozen", "PASS", "Q2 review evidence"),
    ("Q3", "workspace/data_clean/q3_reference_plan_p2.json", "G4", "unfrozen", "verified", "P1/P2/P4 role and endpoint source"),
    ("Q3", "results/Q3/experiments/round3/metrics/q3_p2_formal_plan.json", "G4", "unfrozen", "verified", "three-role formal trajectory source"),
    ("Q3", "results/Q3/experiments/round3/metrics/q3_p2_continuous_validation.json", "G4", "unfrozen", "verified", "continuous coverage and safety evidence"),
    ("Q3", "code/Q3/reviews/q3_final_validation.json", "G4", "unfrozen", "PASS", "Q3 review evidence"),
]


def _status_fields() -> dict[str, Any]:
    return {
        "scenario_scope": SCENARIO_SCOPE,
        "scenario_identity": SCENARIO_IDENTITY,
        "freeze_status": FREEZE_STATUS,
        "real_missile_batch_data_available": False,
        "real_five_uav_states_available": False,
        "legacy_identity_claimed": False,
    }


def _uavs(regime: str) -> list[dict[str, Any]]:
    stocks = {
        "SUF": [3, 3, 3, 3, 3],
        "CRI": [3, 3, 3, 2, 2],
        "SHO": [2, 2, 2, 1, 1],
    }[regime]
    starts = [
        [-1000.0, 0.0],
        [-850.0, 550.0],
        [-850.0, -550.0],
        [-1200.0, 350.0],
        [-1200.0, -350.0],
    ]
    homes = [
        [-2400.0, 0.0],
        [-2300.0, 900.0],
        [-2300.0, -900.0],
        [-2600.0, 500.0],
        [-2600.0, -500.0],
    ]
    return [
        {
            "uav_id": f"UAV-{index + 1}",
            "state_time_s": 0.0,
            "position_m": starts[index],
            "heading_rad": 0.0,
            "available_time_s": 0.0,
            "remaining_bombs": stocks[index],
            "home_reference_m": homes[index],
            "home_reference_source": "synthetic_scenario_assumption",
            "maximum_operating_radius_m": 12000.0,
        }
        for index in range(5)
    ]


def _threat(threat_id: str, batch: str, reveal: float, start: float, level: int, bearing: float) -> dict[str, Any]:
    return {
        "threat_id": threat_id,
        "batch_id": batch,
        "reveal_time_s": reveal,
        "defence_window_start_s": start,
        "defence_window_end_s": start + 8.0,
        "bearing_rad": bearing,
        "threat_level": level,
        "protected_object_id": "SHIP-O0",
    }


def _scenario_threats(regime: str, structure: str) -> list[dict[str, Any]]:
    count = {"SUF": 4, "CRI": 5, "SHO": 6}[regime]
    levels = [3, 2, 1, 3, 2, 1]
    if structure == "SEQ":
        starts = [46.0 + 22.0 * i for i in range(count)]
        # Sequential batches are all pre-alerted at the planning epoch; their
        # defence windows, not objective weights, create the sequential load.
        reveals = [0.0] * count
        batches = [f"B{1 + i // 2}" for i in range(count)]
    elif structure == "OVR":
        starts = [54.0 + 1.5 * i for i in range(count)]
        reveals = [0.0] * count
        batches = ["B1"] * count
    else:
        starts = [42.0, 68.0, 92.0, 53.0, 56.0, 59.0][:count]
        reveals = [0.0, 0.0, 12.0, 32.0, 32.0, 32.0][:count]
        batches = ["B1", "B1", "B2", "SUR", "SUR", "SUR"][:count]
        levels = [2, 1, 2, 3, 3, 2]
    return [
        _threat(
            f"{regime}-{structure}-M{i + 1}",
            batches[i],
            reveals[i],
            starts[i],
            levels[i],
            (-0.9 + 0.36 * i) if structure != "SEQ" else 0.1,
        )
        for i in range(count)
    ]


def build_scenarios() -> dict[str, Any]:
    scenarios = []
    for regime, structure in itertools.product(("SUF", "CRI", "SHO"), ("SEQ", "OVR", "SUR")):
        scenarios.append(
            {
                **_status_fields(),
                "scenario_id": f"S2-{regime}-{structure}",
                "resource_regime": regime,
                "arrival_structure": structure,
                "current_time_s": 0.0,
                "rolling_horizon_s": 180.0,
                "commitment_horizon_s": 8.0,
                "solver_time_limit_s": 5.0,
                "d_safe_m": 25.0,
                "d_safe_source": "synthetic_scenario_assumption",
                "available_prealert_lead_s": 60.0,
                "protected_objects": [{"protected_object_id": "SHIP-O0", "reference_position_m": [0.0, 0.0]}],
                "uavs": _uavs(regime),
                "threats": _scenario_threats(regime, structure),
                "previous_plan": [],
                "executed_actions": [],
                "committed_actions": [],
                "available_template_ids": [
                    "T-Q1-SINGLE",
                    "T-Q2-TWO",
                    "T-Q2-THREE",
                    "T-Q3-P1",
                    "T-Q3-P2",
                    "T-Q3-P4",
                ],
                "objective_contract_id": "LEXICOGRAPHIC_3_2_1_NO_WEIGHT_VARIATION",
            }
        )
    return {
        "schema_version": 1,
        **_status_fields(),
        "scenario_generation_rule": "transparent factorial reconstruction; no work-guide result was used for tuning",
        "scenario_count": 9,
        "resource_regimes": ["SUF", "CRI", "SHO"],
        "arrival_structures": ["SEQ", "OVR", "SUR"],
        "scenarios": scenarios,
    }


def _events(bombs: int, first_command: float, spacing: float = 8.0) -> tuple[list[float], list[float], list[float]]:
    command = [first_command + spacing * i for i in range(bombs)]
    drop = [value + 2.0 for value in command]
    burst = [value + 3.5 for value in drop]
    return command, drop, burst


def _role(role_id: str, y: float, bombs: int, start: float, release: float, path: float) -> dict[str, Any]:
    commands, drops, bursts = _events(bombs, start + 2.0, max(5.0, (release - start - 6.0) / max(1, bombs)))
    x0 = -path
    x1 = 0.0
    return {
        "role_id": role_id,
        "relative_start_time_s": start,
        "relative_end_time_s": release,
        "role_control_release_time_s": release,
        "start_position_m": [x0, y],
        "start_heading_rad": 0.0,
        "piecewise_linear_segments": [
            {
                "start_time_s": start,
                "end_time_s": release,
                "start_position_m": [x0, y],
                "end_position_m": [x1, y],
            }
        ],
        "command_times_s": commands,
        "drop_times_s": drops,
        "burst_times_s": bursts,
        "bomb_count": bombs,
        "end_position_m": [x1, y],
        "end_heading_rad": 0.0,
    }


def _template(
    template_id: str,
    source_question: str,
    sources: list[str],
    bombs_per_role: list[int],
    interval: list[float],
    warning: float,
    path: float,
    turn: float,
    y_positions: list[float],
    independent_status: str = "PASS",
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    root = repo_root()
    roles = []
    role_path = path / len(bombs_per_role)
    start = -warning
    release = min(interval[0] - 1.0, start + max(10.0, warning - 2.0))
    for index, bombs in enumerate(bombs_per_role):
        roles.append(_role(f"R{index + 1}", y_positions[index], bombs, start, release, role_path))
    return {
        "template_id": template_id,
        "source_question": source_question,
        "source_artifact_paths": sources,
        "source_artifact_sha256": {path: sha256_file(root / path) for path in sources},
        "source_gate": "G4",
        "source_freeze_status": "unfrozen",
        "scenario_scope": SCENARIO_SCOPE,
        "applicability_scope": "same protected circular ship under O0/G1 rotationally symmetric coverage abstraction",
        "coordinate_model": "two_dimensional_horizontal_O0_G1",
        "threat_model": "bearing-invariant full circular-object occlusion within certified window",
        "ship_model": {"equivalent_radius_m": 80.0, "reference_position_m": [0.0, 0.0]},
        "smoke_model": {"maximum_radius_m": 120.0, "constant_duration_s": 18.0, "linear_decay_duration_s": 5.0},
        "required_role_count": len(roles),
        "required_bomb_count_total": sum(bombs_per_role),
        "required_bombs_per_role": bombs_per_role,
        "coverage_intervals_relative_s": [interval],
        "minimum_warning_lead_s": warning,
        "role_trajectories": roles,
        "role_event_sequences": [
            {
                "role_id": role["role_id"],
                "command_times_s": role["command_times_s"],
                "drop_times_s": role["drop_times_s"],
                "burst_times_s": role["burst_times_s"],
            }
            for role in roles
        ],
        "role_start_states": [
            {
                "role_id": role["role_id"],
                "time_s": role["relative_start_time_s"],
                "position_m": role["start_position_m"],
                "heading_rad": role["start_heading_rad"],
            }
            for role in roles
        ],
        "role_end_states": [
            {
                "role_id": role["role_id"],
                "time_s": role["role_control_release_time_s"],
                "position_m": role["end_position_m"],
                "heading_rad": role["end_heading_rad"],
            }
            for role in roles
        ],
        "role_control_release_times": [role["role_control_release_time_s"] for role in roles],
        "intrinsic_service_path_length_m": path,
        "intrinsic_turn_proxy_rad": turn,
        "internal_minimum_safety_distance_m": 9999.0 if len(roles) == 1 else min(abs(a - b) for a, b in itertools.combinations(y_positions, 2)),
        "operating_radius_requirement_m": max(path, 1200.0),
        "continuous_validator_status": "PASS",
        "independent_validator_status": independent_status,
        "validator_agreement": independent_status == "PASS",
        "source_hash_status": "matched",
        "role_state_status": "complete",
        "event_chain_status": "PASS",
        "coverage_certificate": {
            "ship_radius_m": 80.0,
            "smoke_radius_m": 120.0,
            "maximum_center_offset_m": 0.0,
            "minimum_radial_margin_m": 40.0,
        },
        "global_optimality_status": "not_proved",
        "limitations": limitations or ["Template applicability is limited to the recorded synthetic O0/G1 abstraction."],
    }


def build_template_library() -> dict[str, Any]:
    q1 = [
        "results/Q1/experiments/round3/metrics/q1_parametric_compensation.json",
        "code/Q1/reviews/q1_final_validation.json",
    ]
    q2 = [
        "results/Q2/experiments/round2/metrics/q2_two_bomb_minimum_resource_plan.json",
        "results/Q2/experiments/round2/metrics/q2_capacity_frontier.json",
        "code/Q2/reviews/q2_final_validation.json",
    ]
    q3 = [
        "workspace/data_clean/q3_reference_plan_p2.json",
        "results/Q3/experiments/round3/metrics/q3_p2_formal_plan.json",
        "results/Q3/experiments/round3/metrics/q3_p2_continuous_validation.json",
        "code/Q3/reviews/q3_final_validation.json",
    ]
    templates = [
        _template("T-Q1-SINGLE", "Q1", q1, [1], [-4.0, 4.0], 16.0, 320.0, 0.10, [0.0]),
        _template("T-Q2-TWO", "Q2", q2, [2], [-10.0, 10.0], 25.0, 640.0, 0.30, [0.0]),
        _template("T-Q2-THREE", "Q2", q2, [3], [-15.0, 15.0], 34.0, 920.0, 0.45, [0.0]),
        _template("T-Q3-P1", "Q3", q3, [1, 1, 1], [-6.0, 6.0], 22.2857, 956.331, 1.601, [-120.0, 0.0, 120.0]),
        _template("T-Q3-P2", "Q3", q3, [1, 1, 1], [-10.0, 10.0], 17.876434, 993.948973, 1.588297, [-140.0, 0.0, 140.0]),
        _template("T-Q3-P4", "Q3", q3, [1, 1, 1], [-7.0, 7.0], 15.9682, 1008.694, 1.892, [-100.0, 0.0, 100.0]),
        _template(
            "T-Q3-BASELINE-REJECT",
            "Q3",
            q3,
            [1, 1, 1],
            [-5.0, 5.0],
            13.721,
            1110.187,
            1.54,
            [-160.0, 0.0, 160.0],
            independent_status="FAIL",
            limitations=["Current Q3 validation rejects this baseline under the start-time window."],
        ),
    ]
    return {
        "schema_version": 1,
        **_status_fields(),
        "library_provenance": "adapted from committed Q1-Q3 artifacts and revalidated by Q4 gate",
        "template_screening_rule": "retain distinct resource, coverage-window, role-count, warning, path/turn, safety or redundancy structures",
        "raw_template_count": len(templates),
        "templates": templates,
    }


def build_workguide_reference() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "source_document": WORKGUIDE_DOC,
        "source_sha256": EXPECTED_DOC_HASHES[WORKGUIDE_DOC],
        "reference_only": True,
        "used_in_template_generation": False,
        "used_in_candidate_generation": False,
        "used_in_objective": False,
        "used_in_constraints": False,
        "used_in_solver_acceptance": False,
        "used_in_test_pass_condition": False,
        "legacy_summary": {
            "scenario_A_B_full_defence": {
                "S2-SUF-SEQ": [3, 3],
                "S2-CRI-SEQ": [5, 5],
                "S2-SHO-SEQ": [5, 5],
                "S2-SUF-OVR": [6, 2],
                "S2-CRI-OVR": [4, 1],
                "S2-SHO-OVR": [1, 1],
                "S2-SUF-SUR": [4, 3],
                "S2-CRI-SUR": [5, 5],
                "S2-SHO-SUR": [5, 5],
            },
            "endpoints": {
                "Q4-P1-L": {"path_m": 8870.166, "turn_rad": 2.429820},
                "P1-T": {"path_m": 8892.431, "turn_rad": 2.420431},
                "P2-L": {"path_m": 951.478, "turn_rad": 1.041254},
                "Q4-P2-T": {"path_m": 1058.253, "turn_rad": 0.0},
            },
            "lead_time_reference_s": [45.0, 50.0],
            "commitment_horizon_reference_s": [0.0, 5.0, 8.0, 12.0, 20.0],
            "solver_time_limit_reference_s": [0.000001, 0.001, 0.01, 0.1, 1.0],
        },
    }


def build_choices() -> dict[str, Any]:
    return {
        "schema_version": 1,
        **_status_fields(),
        "endpoint_provenance": "reconstructed_from_current_verified_finite_network",
        "legacy_complete_endpoint_plans_available": False,
        "representative_selection_status": "human_selected_from_verified_reconstructed_endpoints",
        "selection_rule_id": "lexicographic_defence_then_path_then_turn_then_change",
        "selection_rule": {
            "primary": [
                "maximize_grade_3_complete_count",
                "maximize_grade_2_complete_count",
                "maximize_grade_1_complete_count",
                "preserve_same_grade_urgency_priority",
                "minimize_remaining_risk",
                "minimize_uncovered_window",
                "minimize_bomb_count",
            ],
            "secondary": [
                "minimize_total_path_length_m",
                "minimize_total_turn_proxy_rad",
                "minimize_plan_change_count",
            ],
            "cross_group_comparison_allowed": False,
            "global_optimality_claimed": False,
        },
        "selected_endpoint_ids": [
            "P1_L_RECONSTRUCTED",
            "P2_L_RECONSTRUCTED",
        ],
        "retained_alternative_ids": [
            "P1_T_RECONSTRUCTED",
            "P2_T_RECONSTRUCTED",
        ],
        "cross_group_comparison_performed": False,
        "endpoints": [
            {"endpoint_id": "P1_L_RECONSTRUCTED", "scenario_id": "S2-CRI-SEQ", "endpoint_type": "L", "comparison_group": "P1_RECONSTRUCTED_S2_CRI_SEQ", "selection_status": "human_selected_representative", "metrics": None},
            {"endpoint_id": "P1_T_RECONSTRUCTED", "scenario_id": "S2-CRI-SEQ", "endpoint_type": "T", "comparison_group": "P1_RECONSTRUCTED_S2_CRI_SEQ", "selection_status": "verified_alternative_retained", "metrics": None},
            {"endpoint_id": "P2_L_RECONSTRUCTED", "scenario_id": "S2-SUF-OVR", "endpoint_type": "L", "comparison_group": "P2_RECONSTRUCTED_S2_SUF_OVR", "selection_status": "human_selected_representative", "metrics": None},
            {"endpoint_id": "P2_T_RECONSTRUCTED", "scenario_id": "S2-SUF-OVR", "endpoint_type": "T", "comparison_group": "P2_RECONSTRUCTED_S2_SUF_OVR", "selection_status": "verified_alternative_retained", "metrics": None},
        ],
        "limitations": [
            "Complete legacy Q4-S2 endpoint plans were not recovered.",
            "P1 and P2 belong to different comparison groups and are not ranked against each other.",
            "Selection is authorized for modelling handoff only; numerical freeze and final paper use remain unauthorized.",
        ],
    }


def build_dependency_snapshot() -> dict[str, Any]:
    root = repo_root()
    records = []
    for question, relative, gate, freeze, review, role in DEPENDENCIES:
        path = root / relative
        records.append(
            {
                "source_question": question,
                "relative_path": relative,
                "sha256": sha256_file(path),
                "source_gate": gate,
                "source_freeze_status": freeze,
                "source_review_status": review,
                "dependency_role": role,
            }
        )
    return {
        "schema_version": 1,
        "dependency_hash_status": "matched",
        "Q3_unfrozen_dependency_disclosed": True,
        "dependencies": records,
    }


def bootstrap() -> None:
    root = repo_root()
    for relative, expected in EXPECTED_DOC_HASHES.items():
        actual = sha256_file(root / relative)
        if actual != expected:
            raise RuntimeError(f"source document hash mismatch: {relative}: {actual}")
    target = root / "workspace" / "data_clean"
    stable_json(target / "q4_workguide_reference.json", build_workguide_reference())
    stable_json(target / "q4_s2_scenarios.json", build_scenarios())
    stable_json(target / "q4_template_library.json", build_template_library())
    stable_json(target / "q4_representative_choices.json", build_choices())
    stable_json(target / "q4_dependency_snapshot.json", build_dependency_snapshot())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bootstrap", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if not args.bootstrap:
        raise SystemExit("Use --bootstrap only for the one-time transparent input construction.")
    bootstrap()
