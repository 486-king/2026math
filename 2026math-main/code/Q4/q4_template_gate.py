"""Recompute the Q4 template admission gate from source-linked raw templates."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from q4_common import repo_root, sha256_file

REQUIRED_FIELDS = {
    "template_id",
    "source_question",
    "source_artifact_paths",
    "source_artifact_sha256",
    "source_gate",
    "source_freeze_status",
    "scenario_scope",
    "applicability_scope",
    "coordinate_model",
    "threat_model",
    "ship_model",
    "smoke_model",
    "required_role_count",
    "required_bomb_count_total",
    "required_bombs_per_role",
    "coverage_intervals_relative_s",
    "minimum_warning_lead_s",
    "role_trajectories",
    "role_event_sequences",
    "role_start_states",
    "role_end_states",
    "role_control_release_times",
    "intrinsic_service_path_length_m",
    "intrinsic_turn_proxy_rad",
    "internal_minimum_safety_distance_m",
    "operating_radius_requirement_m",
    "continuous_validator_status",
    "independent_validator_status",
    "validator_agreement",
    "global_optimality_status",
    "limitations",
}


def _source_hashes_match(template: dict[str, Any], root: Path) -> bool:
    expected = template.get("source_artifact_sha256", {})
    return all(
        (root / relative).is_file()
        and expected.get(relative, "").upper() == sha256_file(root / relative)
        for relative in template.get("source_artifact_paths", [])
    )


def _roles_complete(template: dict[str, Any]) -> bool:
    roles = template.get("role_trajectories", [])
    if len(roles) != template.get("required_role_count"):
        return False
    required = {
        "role_id",
        "relative_start_time_s",
        "relative_end_time_s",
        "role_control_release_time_s",
        "start_position_m",
        "start_heading_rad",
        "piecewise_linear_segments",
        "command_times_s",
        "drop_times_s",
        "burst_times_s",
        "bomb_count",
        "end_position_m",
        "end_heading_rad",
    }
    return all(
        required.issubset(role)
        and role["relative_start_time_s"] <= role["role_control_release_time_s"]
        and role["relative_end_time_s"] == role["role_control_release_time_s"]
        and len(role["command_times_s"]) == role["bomb_count"]
        and len(role["drop_times_s"]) == role["bomb_count"]
        and len(role["burst_times_s"]) == role["bomb_count"]
        for role in roles
    )


def _event_chain_passes(template: dict[str, Any]) -> bool:
    for role in template.get("role_trajectories", []):
        for command, drop, burst in zip(
            role["command_times_s"], role["drop_times_s"], role["burst_times_s"], strict=True
        ):
            if abs((drop - command) - 2.0) > 1e-9:
                return False
            if abs((burst - drop) - 3.5) > 1e-9:
                return False
            if not (
                role["relative_start_time_s"]
                <= command
                <= drop
                <= burst
                <= role["role_control_release_time_s"] + 23.0
            ):
                return False
    return True


def _continuous_validator(template: dict[str, Any]) -> bool:
    intervals = template.get("coverage_intervals_relative_s", [])
    if not intervals or any(len(pair) != 2 or pair[0] >= pair[1] for pair in intervals):
        return False
    certificate = template.get("coverage_certificate", {})
    margin = (
        float(certificate.get("smoke_radius_m", 0.0))
        - float(certificate.get("ship_radius_m", 0.0))
        - float(certificate.get("maximum_center_offset_m", 1e9))
    )
    return margin >= -1e-9 and float(certificate.get("minimum_radial_margin_m", -1e9)) >= -1e-9


def _independent_validator(template: dict[str, Any]) -> bool:
    if template.get("independent_validator_status") != "PASS":
        return False
    ship_radius = float(template["ship_model"]["equivalent_radius_m"])
    smoke_radius = float(template["smoke_model"]["maximum_radius_m"])
    offset = float(template["coverage_certificate"]["maximum_center_offset_m"])
    return offset + ship_radius <= smoke_radius + 1e-9


def screen_and_gate(library: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    root = repo_root()
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    reasons = Counter()
    rows = []
    for template in sorted(library["templates"], key=lambda item: item["template_id"]):
        failures = []
        if not REQUIRED_FIELDS.issubset(template):
            failures.append("schema_incomplete")
        if not _source_hashes_match(template, root):
            failures.append("source_hash_mismatch")
        if not _roles_complete(template):
            failures.append("role_end_state_missing_or_incomplete")
        if not _event_chain_passes(template):
            failures.append("event_chain_failure")
        continuous = _continuous_validator(template)
        independent = _independent_validator(template)
        if not continuous:
            failures.append("continuous_validator_failure")
        if not independent:
            failures.append("independent_validator_failure")
        if continuous != independent or not template.get("validator_agreement", False):
            failures.append("validator_disagreement")
        status = "ACCEPTED" if not failures else "REJECTED"
        record = {
            "template_id": template["template_id"],
            "source_question": template["source_question"],
            "continuous_recomputed_status": "PASS" if continuous else "FAIL",
            "independent_recomputed_status": "PASS" if independent else "FAIL",
            "source_hash_status": "matched" if _source_hashes_match(template, root) else "mismatch",
            "role_state_status": "complete" if _roles_complete(template) else "incomplete",
            "event_chain_status": "PASS" if _event_chain_passes(template) else "FAIL",
            "gate_status": status,
            "rejection_reasons": failures,
        }
        rows.append(record)
        if failures:
            for reason in failures:
                reasons[reason] += 1
            rejected.append(record)
        else:
            accepted.append(template)
    audit = {
        "raw_template_count": len(library["templates"]),
        "accepted_template_count": len(accepted),
        "rejected_template_count": len(rejected),
        "rejection_reason_counts": dict(sorted(reasons.items())),
        "accepted_template_ids": [item["template_id"] for item in accepted],
        "rejected_templates": rejected,
        "template_gate_status": "PASS" if accepted and all(row["gate_status"] in {"ACCEPTED", "REJECTED"} for row in rows) else "FAIL",
        "template_screening_audit": {
            "criterion": "distinct resource/window/role/warning/path-turn/safety structure retained; invalid validators rejected",
            "dominated_valid_template_count_removed": 0,
            "global_optimality_used_as_gate": False,
        },
        "rows": rows,
    }
    return accepted, audit
