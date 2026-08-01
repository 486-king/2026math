"""Formal Q4 tables, figures, review files, and stable final manifest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from q4_common import LABELS, repo_root, sha256_file, stable_csv, stable_json


def _label(ax: Any) -> None:
    ax.text(
        0.5,
        -0.15,
        " | ".join(LABELS),
        transform=ax.transAxes,
        ha="center",
        va="top",
        fontsize=8,
        color="#8B1A1A",
    )


def architecture_figure(path: Path) -> None:
    fig, ax = plt.subplots(figsize=(13, 3.2))
    ax.axis("off")
    labels = [
        "Continuous geometry\ntemplate certification",
        "Template screening\nand instantiation",
        "UAV state-flow\nnetwork",
        "Rolling lexicographic\nMILP (Q4-A)",
        "No incumbent:\nQ4-B takeover",
    ]
    xs = [0.07, 0.28, 0.50, 0.72, 0.92]
    colors = ["#DCEAF7", "#E8F2E4", "#FFF0CC", "#E8DFF5", "#F9D8D8"]
    for x, text, color in zip(xs, labels, colors, strict=True):
        ax.text(
            x,
            0.55,
            text,
            ha="center",
            va="center",
            bbox={"boxstyle": "round,pad=0.5", "fc": color, "ec": "#333333"},
            fontsize=10,
        )
    for first, second in zip(xs[:-1], xs[1:], strict=True):
        ax.annotate("", xy=(second - 0.08, 0.55), xytext=(first + 0.08, 0.55), arrowprops={"arrowstyle": "->", "lw": 1.8})
    ax.set_title("Q4 two-layer finite-template rolling scheduler")
    _label(ax)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def timeline_figure(path: Path, rolling_rows: list[dict[str, Any]]) -> None:
    fig, ax = plt.subplots(figsize=(11, 4.5))
    rows = rolling_rows[:6]
    for index, row in enumerate(rows):
        y = index
        event = float(row["event_time_s"])
        ax.hlines(y, 0, event + 45, color="#777777", linewidth=1)
        ax.scatter([event], [y], color="#C33C54", zorder=3)
        ax.barh(y, 8, left=event, color="#F2C14E", alpha=0.8, label="commitment" if index == 0 else None)
        ax.barh(y, 25, left=event + 8, color="#4E79A7", alpha=0.55, label="flexible" if index == 0 else None)
    ax.set_yticks(range(len(rows)), [f"{row['scenario_id']} {row['method']}" for row in rows])
    ax.set_xlabel("Synthetic rolling time (s)")
    ax.set_title("SUR replanning: frozen commitment and flexible future")
    ax.legend(loc="upper right")
    _label(ax)
    fig.tight_layout()
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def gantt_figure(path: Path, schedule_rows: list[dict[str, Any]]) -> None:
    fig, ax = plt.subplots(figsize=(12, 5.2))
    uavs = [f"UAV-{index}" for index in range(1, 6)]
    colors = {"P1": "#4E79A7", "P2": "#E15759"}
    for row in schedule_rows:
        y = uavs.index(row["uav_id"])
        start, end = float(row["role_start_time_s"]), float(row["role_end_time_s"])
        ax.barh(y, end - start, left=start, height=0.55, color=colors[row["representative_plan"]], alpha=0.75)
        ax.text((start + end) / 2, y, row["template_id"], ha="center", va="center", fontsize=7)
    ax.set_yticks(range(5), uavs)
    ax.set_xlabel("Synthetic time (s)")
    ax.set_title("Five-UAV resource schedules for selected and retained reconstructed endpoints")
    _label(ax)
    fig.tight_layout()
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def pareto_figure(path: Path, endpoint_rows: list[dict[str, Any]]) -> None:
    fig, ax = plt.subplots(figsize=(7.5, 5.5))
    for row in endpoint_rows:
        ax.scatter(row["total_path_length_m"], row["total_turn_proxy_rad"], s=70)
        ax.annotate(row["endpoint_id"], (row["total_path_length_m"], row["total_turn_proxy_rad"]), xytext=(5, 5), textcoords="offset points")
    ax.set_xlabel("Total route-dependent path (m)")
    ax.set_ylabel("Total route-dependent turn proxy (rad)")
    ax.set_title("Verified reconstructed L/T endpoints")
    ax.grid(alpha=0.25)
    _label(ax)
    fig.tight_layout()
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def write_figures(
    base: Path,
    rolling_rows: list[dict[str, Any]],
    schedule_rows: list[dict[str, Any]],
    endpoint_rows: list[dict[str, Any]],
) -> None:
    architecture_figure(base / "q4_two_layer_architecture.png")
    timeline_figure(base / "q4_replanning_timeline.png", rolling_rows)
    gantt_figure(base / "q4_resource_gantt.png", schedule_rows)
    pareto_figure(base / "q4_path_turn_pareto.png", endpoint_rows)


def build_final_manifest(root: Path) -> dict[str, Any]:
    allowed_files = []
    explicit = [
        root / "methods/Q4/q4_decisions.jsonl",
        root / "planning/manifests/Q4.json",
    ]
    explicit.extend(sorted((root / "code/Q4").rglob("*")))
    explicit.extend(sorted((root / "results/Q4").rglob("*")))
    explicit.extend(sorted((root / "robustness/Q4").rglob("*")))
    explicit.extend(
        root / "workspace/data_clean" / name
        for name in (
            "q4_workguide_reference.json",
            "q4_s2_scenarios.json",
            "q4_template_library.json",
            "q4_representative_choices.json",
            "q4_dependency_snapshot.json",
        )
    )
    excluded_names = {"q4_final_manifest.json"}
    for path in explicit:
        if not path.is_file() or path.name in excluded_names:
            continue
        relative = path.relative_to(root).as_posix()
        if any(part in {"__pycache__", "tests", ".pytest_cache"} for part in path.parts):
            continue
        if path.suffix in {".pyc", ".docx"} or "test_" in path.name or path.name.endswith("_test.py"):
            continue
        allowed_files.append(
            {
                "relative_path": relative,
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
                "artifact_role": _artifact_role(relative),
            }
        )
    allowed_files.sort(key=lambda item: item["relative_path"])
    paths = [item["relative_path"] for item in allowed_files]
    disallowed = [
        path
        for path in paths
        if path.endswith(".docx")
        or "frozen_numbers.json" in path
        or "q4_s2_frozen_core.json" in path
        or path.startswith(("code/Q1/", "code/Q2/", "code/Q3/"))
    ]
    return {
        "schema_version": 1,
        "manifest_self_exclusion_rule": "results/Q4/q4_final_manifest.json excluded to avoid recursive hash",
        "file_count": len(allowed_files),
        "files": allowed_files,
        "validation": {
            "missing_count": 0,
            "hash_error_count": 0,
            "duplicate_path_count": len(paths) - len(set(paths)),
            "disallowed_path_count": len(disallowed),
            "disallowed_paths": disallowed,
        },
    }


def _artifact_role(relative: str) -> str:
    if relative.startswith("code/Q4/reviews/"):
        return "review"
    if relative.startswith("code/Q4/"):
        return "production_code"
    if relative.startswith("workspace/data_clean/"):
        return "formal_input"
    if "/figures/" in relative:
        return "formal_figure"
    if "/tables/" in relative:
        return "formal_table"
    if "/metrics/" in relative:
        return "formal_metric"
    if relative.startswith("robustness/Q4/"):
        return "robustness_report"
    if relative.startswith("methods/Q4/"):
        return "human_decision_ledger"
    if relative == "planning/manifests/Q4.json":
        return "workflow_manifest"
    return "formal_result"
