"""Deterministic Q2 JSON/CSV/figure writers and final artifact manifest."""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path
from typing import Any, Iterable, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle

from q2_common import (
    PARAMS,
    PROJECT_ROOT,
    SmokePlan,
    sha256_file,
    source_document_metadata,
    write_json,
)
from q2_geometry import plan_state

ROUND1 = PROJECT_ROOT / "results" / "Q2" / "experiments" / "round1"
ROUND2 = PROJECT_ROOT / "results" / "Q2" / "experiments" / "round2"
ROBUSTNESS_PATH = PROJECT_ROOT / "robustness" / "Q2" / "q2_robustness_summary.json"
REVIEW_DIR = PROJECT_ROOT / "code" / "Q2" / "reviews"
REPORT_DIR = PROJECT_ROOT / "results" / "Q2" / "reports"
FINAL_MANIFEST_PATH = PROJECT_ROOT / "results" / "Q2" / "q2_final_manifest.json"


def _write_csv(
    path: Path,
    fieldnames: Sequence[str],
    rows: Iterable[dict[str, Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def _event_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return list(payload.get("best_schedule", payload.get("event_chain", [])))


def write_schedule_table(
    minimum_resource: dict[str, Any],
    capacity: dict[str, Any],
) -> Path:
    rows: list[dict[str, Any]] = []

    def append_schedule(
        scheme_id: str,
        bomb_count: int,
        purpose: str,
        records: list[dict[str, Any]],
        duration_s: float,
        result_strength: str,
    ) -> None:
        for index, record in enumerate(records, start=1):
            rows.append(
                {
                    "scheme_id": scheme_id,
                    "purpose": purpose,
                    "bomb_count": bomb_count,
                    "smoke_index": index,
                    "smoke_id": record["smoke_id"],
                    "center_m": f"{float(record['center_m']):.12f}",
                    "t_cmd_s": f"{float(record['t_cmd_s']):.12f}",
                    "t_d_s": f"{float(record['t_d_s']):.12f}",
                    "t_b_s": f"{float(record['t_b_s']):.12f}",
                    "pre_lock_mission": str(bool(record["pre_lock_mission"])).lower(),
                    "verified_duration_s": f"{duration_s:.12f}",
                    "result_strength": result_strength,
                }
            )

    append_schedule(
        minimum_resource["scheme_id"],
        2,
        "minimum_resource_full_worst_window",
        minimum_resource["event_chain"],
        PARAMS.detect_worst_upper_s,
        minimum_resource["result_strength"],
    )
    two = capacity["A"]["two_bomb"]
    append_schedule(
        two["scheme_id"],
        2,
        "best_verified_two_bomb_capacity_solution",
        two["best_schedule"],
        two["best_objective_s"],
        two["result_strength"],
    )
    three = capacity["A"]["three_bomb"]
    append_schedule(
        three["scheme_id"],
        3,
        "best_verified_three_bomb_capacity_solution",
        three["best_schedule"],
        three["best_objective_s"],
        three["result_strength"],
    )
    for baseline in capacity["B"]["plans"]:
        append_schedule(
            baseline["scheme_id"],
            baseline["bomb_count"],
            "conservative_constructive_baseline",
            baseline["smokes"],
            baseline["longest_continuous_component_s"],
            baseline["result_strength"],
        )
    path = ROUND2 / "tables" / "q2_verified_schedules.csv"
    fields = [
        "scheme_id",
        "purpose",
        "bomb_count",
        "smoke_index",
        "smoke_id",
        "center_m",
        "t_cmd_s",
        "t_d_s",
        "t_b_s",
        "pre_lock_mission",
        "verified_duration_s",
        "result_strength",
    ]
    _write_csv(path, fields, sorted(rows, key=lambda row: (row["scheme_id"], row["smoke_index"])))
    return path


def write_capacity_table(capacity: dict[str, Any]) -> Path:
    rows = []
    a_values = {
        1: capacity["A"]["one_bomb"]["best_objective_s"],
        2: capacity["A"]["two_bomb"]["best_objective_s"],
        3: capacity["A"]["three_bomb"]["best_objective_s"],
    }
    a_strength = {
        1: capacity["A"]["one_bomb"]["result_strength"],
        2: capacity["A"]["two_bomb"]["result_strength"],
        3: capacity["A"]["three_bomb"]["result_strength"],
    }
    b_values = {
        int(key): value for key, value in capacity["B"]["capacities_s"].items()
    }
    for bomb_count in (1, 2, 3):
        rows.extend(
            [
                {
                    "method": "A",
                    "bomb_count": bomb_count,
                    "continuous_capacity_s": f"{a_values[bomb_count]:.12f}",
                    "result_strength": a_strength[bomb_count],
                    "global_optimality_status": (
                        capacity["A"]["one_bomb"]["global_optimality_status"]
                        if bomb_count == 1
                        else "not_proved"
                    ),
                },
                {
                    "method": "B",
                    "bomb_count": bomb_count,
                    "continuous_capacity_s": f"{b_values[bomb_count]:.12f}",
                    "result_strength": "conservative_constructive_baseline",
                    "global_optimality_status": "not_claimed",
                },
            ]
        )
    path = ROUND2 / "tables" / "q2_capacity_frontier.csv"
    _write_csv(
        path,
        [
            "method",
            "bomb_count",
            "continuous_capacity_s",
            "result_strength",
            "global_optimality_status",
        ],
        rows,
    )
    return path


def write_capacity_figure(capacity: dict[str, Any]) -> tuple[Path, Path]:
    data_path = write_capacity_table(capacity)
    figure_path = ROUND2 / "figures" / "q2_capacity_frontier.png"
    figure_path.parent.mkdir(parents=True, exist_ok=True)
    bomb_counts = [1, 2, 3]
    a_values = [
        capacity["A"]["one_bomb"]["best_objective_s"],
        capacity["A"]["two_bomb"]["best_objective_s"],
        capacity["A"]["three_bomb"]["best_objective_s"],
    ]
    b_values = [
        capacity["B"]["capacities_s"][str(count)] for count in bomb_counts
    ]
    fig, axis = plt.subplots(figsize=(8.4, 5.2), dpi=160)
    axis.plot(
        bomb_counts,
        a_values,
        marker="o",
        linewidth=2.2,
        label="A: verified collinear solutions",
    )
    axis.plot(bomb_counts, b_values, marker="s", linewidth=2.0, label="B: conservative")
    axis.axhline(
        PARAMS.detect_worst_upper_s,
        color="#9c2f2f",
        linestyle="--",
        linewidth=1.6,
        label="G1 worst window",
    )
    axis.set_xticks(bomb_counts)
    axis.set_xlabel("Bomb count")
    axis.set_ylabel("Longest verified continuous coverage (s)")
    axis.set_title("Q2 A/B verified capacity comparison")
    axis.grid(alpha=0.25)
    axis.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(
        figure_path,
        metadata={"Software": "Q2 deterministic matplotlib pipeline"},
    )
    plt.close(fig)
    return figure_path, data_path


def write_two_bomb_geometry_figure(
    minimum_resource: dict[str, Any],
) -> tuple[Path, Path]:
    plan = [
        SmokePlan(
            smoke_id=record["smoke_id"],
            center_m=float(record["center_m"]),
            t_cmd_s=float(record["t_cmd_s"]),
        )
        for record in minimum_resource["event_chain"]
    ]
    cross = minimum_resource["exact_cross_section_validation"]
    times = [
        0.0,
        float(cross["minimum_time_s"]),
        PARAMS.detect_worst_upper_s,
    ]
    labels = [
        "window start",
        "global minimum margin\n(coincides with start)",
        "window end",
    ]
    data_rows = []
    figure_path = ROUND2 / "figures" / "q2_two_bomb_key_geometry.png"
    data_path = ROUND2 / "plot_data" / "q2_two_bomb_key_geometry.csv"
    figure_path.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 3, figsize=(12.0, 4.2), dpi=160)
    for axis, time_s, label in zip(axes, times, labels):
        ship, centers, radii = plan_state(time_s, plan)
        axis.add_patch(
            Circle(
                (ship, 0.0),
                PARAMS.ship_radius_m,
                fill=False,
                linewidth=2.0,
                color="#111111",
                label="ship disk",
            )
        )
        data_rows.append(
            {
                "time_s": f"{time_s:.12f}",
                "object": "ship",
                "center_x_m": f"{ship:.12f}",
                "center_y_m": "0.000000000000",
                "radius_m": f"{PARAMS.ship_radius_m:.12f}",
            }
        )
        colors = ["#4575b4", "#fdae61"]
        for index, (center, radius) in enumerate(zip(centers, radii)):
            if radius <= 0.0:
                continue
            axis.add_patch(
                Circle(
                    (center, 0.0),
                    radius,
                    alpha=0.25,
                    color=colors[index],
                    label=f"smoke {index + 1}",
                )
            )
            data_rows.append(
                {
                    "time_s": f"{time_s:.12f}",
                    "object": f"smoke_{index + 1}",
                    "center_x_m": f"{center:.12f}",
                    "center_y_m": "0.000000000000",
                    "radius_m": f"{radius:.12f}",
                }
            )
        axis.set_aspect("equal", adjustable="box")
        axis.set_xlim(ship - 210.0, ship + 210.0)
        axis.set_ylim(-150.0, 150.0)
        axis.set_title(f"{label}\nt={time_s:.3f} s")
        axis.set_xlabel("x (m)")
        axis.grid(alpha=0.2)
    axes[0].set_ylabel("y (m)")
    legend_handles = [
        Circle(
            (0.0, 0.0),
            1.0,
            fill=False,
            linewidth=2.0,
            color="#111111",
            label="ship disk",
        ),
        Circle(
            (0.0, 0.0),
            1.0,
            alpha=0.25,
            color="#4575b4",
            label="smoke 1",
        ),
        Circle(
            (0.0, 0.0),
            1.0,
            alpha=0.25,
            color="#fdae61",
            label="smoke 2",
        ),
    ]
    fig.legend(
        handles=legend_handles,
        loc="lower center",
        ncol=3,
        frameon=False,
    )
    fig.suptitle("Two-bomb full-window collinear geometry")
    fig.tight_layout(rect=(0, 0.08, 1, 0.94))
    fig.savefig(
        figure_path,
        metadata={"Software": "Q2 deterministic matplotlib pipeline"},
    )
    plt.close(fig)
    _write_csv(
        data_path,
        ["time_s", "object", "center_x_m", "center_y_m", "radius_m"],
        data_rows,
    )
    return figure_path, data_path


def write_formal_outputs(
    minimum_resource: dict[str, Any],
    broken_counterexample: dict[str, Any],
    no_pre_lock: dict[str, Any],
    capacity: dict[str, Any],
    robustness: dict[str, Any],
    round1_summary: dict[str, Any],
    round2_summary: dict[str, Any],
    q1_consistency: dict[str, Any],
    provenance: dict[str, Any],
    review: dict[str, Any],
    validation: dict[str, Any],
) -> list[Path]:
    paths = [
        ROUND1 / "metrics" / "q2_continuous_validation.json",
        ROUND1 / "run_summary.json",
        ROUND2 / "metrics" / "q2_two_bomb_minimum_resource_plan.json",
        ROUND2 / "metrics" / "q2_capacity_frontier.json",
        ROUND2 / "run_summary.json",
        ROBUSTNESS_PATH,
        REVIEW_DIR / "q2_python_review_round2.json",
        REVIEW_DIR / "q2_final_validation.json",
        REPORT_DIR / "q2_q1_interface_consistency.json",
        REPORT_DIR / "q2_source_document_provenance.json",
    ]
    write_json(
        paths[0],
        {
            "canonical_two_bomb_validation": minimum_resource,
            "broken_plan_counterexample": broken_counterexample,
            "no_pre_lock_counterfactual": no_pre_lock,
        },
    )
    write_json(paths[1], round1_summary)
    write_json(paths[2], minimum_resource)
    write_json(paths[3], capacity)
    write_json(paths[4], round2_summary)
    write_json(paths[5], robustness)
    write_json(paths[6], review)
    write_json(paths[7], validation)
    write_json(paths[8], q1_consistency)
    write_json(paths[9], provenance)
    paths.append(write_schedule_table(minimum_resource, capacity))
    capacity_figure, capacity_data = write_capacity_figure(capacity)
    geometry_figure, geometry_data = write_two_bomb_geometry_figure(minimum_resource)
    paths.extend([capacity_figure, capacity_data, geometry_figure, geometry_data])
    return paths


def _artifact_role(path: Path) -> str:
    relative = path.relative_to(PROJECT_ROOT).as_posix()
    if "/figures/" in relative:
        return "formal_figure"
    if "/tables/" in relative or "/plot_data/" in relative:
        return "formal_table_or_plot_data"
    if "/reviews/" in relative:
        return "review_or_final_validation"
    if relative.startswith("code/Q2/"):
        return "production_code_or_documentation"
    if relative.startswith("methods/Q2/"):
        return "human_decision_record"
    if relative.startswith("planning/manifests/"):
        return "workflow_manifest"
    if relative.startswith("robustness/Q2/"):
        return "robustness_result"
    if relative.endswith("q2_source_document_provenance.json"):
        return "source_document_provenance_report"
    if "/reports/" in relative:
        return "interface_consistency_report"
    return "formal_machine_result"


def build_final_manifest() -> dict[str, Any]:
    allowed_files: list[Path] = []
    for root in (
        PROJECT_ROOT / "code" / "Q2",
        PROJECT_ROOT / "results" / "Q2",
        PROJECT_ROOT / "robustness" / "Q2",
    ):
        if root.is_dir():
            allowed_files.extend(path for path in root.rglob("*") if path.is_file())
    allowed_files.extend(
        [
            PROJECT_ROOT / "methods" / "Q2" / "q2_decisions.jsonl",
            PROJECT_ROOT / "planning" / "manifests" / "Q2.json",
        ]
    )
    excluded_names = {"q2_final_manifest.json"}
    forbidden_parts = {
        "tests",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
    }
    files = []
    for path in sorted(set(allowed_files)):
        if not path.is_file() or path.name in excluded_names:
            continue
        relative = path.relative_to(PROJECT_ROOT)
        if any(part in forbidden_parts for part in relative.parts):
            continue
        if path.suffix.lower() in {".pyc", ".docx"}:
            continue
        files.append(
            {
                "relative_path": relative.as_posix(),
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
                "artifact_role": _artifact_role(path),
            }
        )
    paths = [row["relative_path"] for row in files]
    hash_errors = sum(
        sha256_file(PROJECT_ROOT / row["relative_path"]) != row["sha256"]
        for row in files
    )
    payload = {
        "schema_version": 1,
        "question_id": "Q2",
        "files": files,
        "file_count": len(files),
        "hash_error_count": hash_errors,
        "duplicate_path_count": len(paths) - len(set(paths)),
        "self_manifest_policy": (
            "q2_final_manifest.json is excluded because a stable self-hash is impossible"
        ),
        "source_documents": [
            {
                "role": role,
                "relative_path": row["relative_path"],
                "availability": row["availability"],
                "sha256": row["sha256"],
                "read_only": True,
                "included_in_program_delivery_files": False,
            }
            for role, row in source_document_metadata().items()
        ],
    }
    write_json(FINAL_MANIFEST_PATH, payload)
    return payload


def core_output_hashes() -> dict[str, str]:
    paths = [
        ROUND1 / "metrics" / "q2_continuous_validation.json",
        ROUND2 / "metrics" / "q2_two_bomb_minimum_resource_plan.json",
        ROUND2 / "metrics" / "q2_capacity_frontier.json",
        ROUND2 / "tables" / "q2_verified_schedules.csv",
        ROUND2 / "tables" / "q2_capacity_frontier.csv",
        ROBUSTNESS_PATH,
    ]
    return {
        path.relative_to(PROJECT_ROOT).as_posix(): sha256_file(path)
        for path in paths
    }
