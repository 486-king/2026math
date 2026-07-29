"""Production artifact generation, plotting, cleanup, and manifest handling."""

from __future__ import annotations

import csv
import json
import math
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

MPL_CACHE_DIR = Path(tempfile.gettempdir()) / "q1_matplotlib_cache"
os.environ.setdefault("MPLCONFIGDIR", str(MPL_CACHE_DIR))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from q1_certificates import build_global_certificate
from q1_common import (
    BURST_INTERVAL_WIDTH,
    EXPECTED_SOURCE_HASHES,
    PARAMETER_RECORDS,
    PROJECT_ROOT,
    R_S,
    SMOKE_LIFETIME,
    STATUS_SEMANTICS,
    TAU_HOLD,
    T_DETECT_LOWER,
    T_NAKED_LOWER,
    T_STRUCTURAL_MAX,
    V_S,
    assert_core_constants,
    dependency_versions,
    locate_source_documents,
    parameter_dict,
    relative_posix,
    sha256_file,
    smoke_radius,
    source_document_metadata,
    source_hashes,
    write_json,
    h,
)
from q1_compensation import compensation_family, release_point_relation
from q1_coverage import MULTISMOKE_ERROR, random_degeneracy_check
from q1_extensions import wind_drift_interface
from q1_reachability import evaluate_complete_scenario, load_scenario
from q1_robustness_core import robustness_summary

ROUND1 = PROJECT_ROOT / "results/Q1/experiments/round1/metrics/q1_structural_metrics.json"
ROUND2 = PROJECT_ROOT / "results/Q1/experiments/round2/metrics/q1_global_certificate.json"
ROUND3 = PROJECT_ROOT / "results/Q1/experiments/round3/metrics/q1_parametric_compensation.json"
ROUND4 = PROJECT_ROOT / "results/Q1/experiments/round4/metrics/q1_architecture_upgrade.json"
ROUND1_SUMMARY = PROJECT_ROOT / "results/Q1/experiments/round1/run_summary.json"
ROUND2_SUMMARY = PROJECT_ROOT / "results/Q1/experiments/round2/run_summary.json"
ROUND3_SUMMARY = PROJECT_ROOT / "results/Q1/experiments/round3/run_summary.json"
ROUND4_SUMMARY = PROJECT_ROOT / "results/Q1/experiments/round4/run_summary.json"
ROBUSTNESS_PATH = PROJECT_ROOT / "robustness/Q1/q1_robustness_summary.json"
RUN_SUMMARY_PATH = PROJECT_ROOT / "results/Q1/q1_run_summary.json"
CONSISTENCY_PATH = PROJECT_ROOT / "results/Q1/q1_q2_scoped_consistency.json"
MANIFEST_PATH = PROJECT_ROOT / "results/Q1/q1_final_manifest.json"
VALIDATION_PATH = PROJECT_ROOT / "code/Q1/reviews/q1_final_validation.json"
PLOT_DATA = PROJECT_ROOT / "results/Q1/plot_data"
FIGURES = PROJECT_ROOT / "results/Q1/figures"

MODEL_ASSUMPTIONS = [
    "G1 pure pursuit missile",
    "S1 fixed cloud center after burst",
    "O0 full two-dimensional ship disk coverage",
    "U0 no nominal wind drift",
    "ship moves at constant velocity on a straight line",
    "locked at 8000 m for the standard lower-bound certificate",
]

SOURCE_CONFLICTS = [
    {
        "item": "problem_document_filename",
        "adopted": "accept the existing local name with or without suffix (4); never rename the source",
    },
    {
        "item": "unique_absolute_optimum",
        "adopted": "block the executable optimum and output a parameterised family when absolute states are missing",
    },
    {
        "item": "historical_project_references",
        "adopted": "rebuild all four evidence rounds from the mathematical specification",
    },
]


def _base_status(scenario_state: dict[str, Any], certificate_status: str) -> dict[str, Any]:
    if (
        scenario_state["input_status"] == "complete"
        and scenario_state.get("feasibility_status")
        in {"executable_feasible", "executable_infeasible"}
    ):
        feasibility = scenario_state["feasibility_status"]
    else:
        feasibility = (
            "full_window_structurally_infeasible"
            if certificate_status == "verified"
            else "not_evaluated"
        )
    return {
        "execution_status": "completed",
        "input_status": scenario_state["input_status"],
        "feasibility_status": feasibility,
        "certificate_status": certificate_status,
        "T_executable_star": scenario_state.get("T_executable_star", "not_evaluated"),
    }


def build_structural_metrics(
    scenario_state: dict[str, Any],
    *,
    locked_at_8000m: bool,
) -> dict[str, Any]:
    return {
        "model_scope": "Q1 nominal G1+S1+O0+U0",
        "parameters": parameter_dict(),
        "units": {"length": "m", "time": "s", "speed": "m/s", "angle": "degree"},
        "assumptions": MODEL_ASSUMPTIONS,
        "h_s": h,
        "T_structural_max_s": T_STRUCTURAL_MAX,
        "T_detect_lower_s": T_DETECT_LOWER if locked_at_8000m else "conditional_not_active",
        "T_naked_lower_s": T_NAKED_LOWER if locked_at_8000m else "conditional_not_active",
        "comparison_gap_s": T_NAKED_LOWER if locked_at_8000m else "conditional_not_active",
        "burst_interval_width_s": BURST_INTERVAL_WIDTH,
        "locked_at_8000m": locked_at_8000m,
        "status": _base_status(
            scenario_state, "verified" if locked_at_8000m else "conditional"
        ),
        "floating_point": {
            "type": "IEEE-754 binary64",
            "formulae": {
                "h": "(R_c-R_s)/V_s",
                "T_structural_max": "2h",
                "T_detect_lower": "(D_max-R_s)/(V_m+V_s)",
                "T_naked_lower": "T_detect_lower-T_structural_max",
            },
        },
    }


def build_consistency_review() -> dict[str, Any]:
    python_files = list((PROJECT_ROOT / "code/Q1").glob("*.py"))
    source_text = "\n".join(path.read_text(encoding="utf-8") for path in python_files)
    forbidden_multiplication = bool(
        re.search(r"\bn\s*\*\s*(?:10\.3761|T_STRUCTURAL_MAX)", source_text)
    )
    checks = {
        "Q1_event_fields_complete": all(
            token in source_text for token in ("t_cmd", "t_d", "t_b", "t_m")
        ),
        "Delta_definition_provided": "delta_single" in source_text,
        "multi_smoke_correctly_rejected": (
            MULTISMOKE_ERROR
            == "Exact continuous multi-smoke union coverage belongs to Q2 and is intentionally not implemented in Q1."
            and "raise NotImplementedError(MULTISMOKE_ERROR)" in source_text
        ),
        "n_times_structural_max_absent": not forbidden_multiplication,
        "Q2_Q3_Q4_not_implemented_by_Q1": not any(
            (PROJECT_ROOT / name).is_dir() for name in ("Q2", "Q3", "Q4")
        ),
    }
    return {
        "scope": "Q1_to_Q2_interface_boundary_only",
        "Q2_executed": False,
        "checks": checks,
        "preserved_human_and_workflow_files_not_modified": [
            "methods/Q1/q1_decisions.jsonl",
            "methods/Q1/q1_final_method_explanation.md",
            "handoff/Q1/q1_programmer_checklist.md",
            "planning/manifests/Q1.json"
        ],
        "legacy_reference_follow_up": {
            "status": "handoff_to_modeler_or_writer",
            "note": (
                "These preserved records may name superseded Q1 modules. The programmer "
                "hand does not rewrite human decisions or global workflow records; the "
                "canonical production implementation is code/Q1/q1_run.py and its sibling modules."
            )
        },
        "scope_status": "verified" if all(checks.values()) else "failed",
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def generate_plot_data() -> dict[str, Path]:
    PLOT_DATA.mkdir(parents=True, exist_ok=True)
    t_b = 0.0
    t_m = 9.0
    plot_start = -2.0
    plot_end = SMOKE_LIFETIME + 2.0
    key_times = np.array(
        [
            plot_start,
            t_b,
            t_m - h,
            t_m,
            t_m + h,
            t_b + TAU_HOLD,
            t_b + SMOKE_LIFETIME,
            plot_end,
        ]
    )
    times = np.unique(np.concatenate([np.linspace(plot_start, plot_end, 1201), key_times]))
    rows: list[dict[str, Any]] = []
    for t in times:
        radius = smoke_radius(float(t), t_b)
        distance = abs(V_S * (float(t) - t_m))
        margin = radius - distance - R_S
        rows.append(
            {
                "time_s": float(t),
                "smoke_radius_m": radius,
                "ship_cloud_distance_m": distance,
                "single_smoke_margin_m": margin,
                "fully_covered": int(margin >= -1e-12),
                "t_b_s": t_b,
                "t_m_s": t_m,
            }
        )
    margin_path = PLOT_DATA / "q1_single_smoke_margin.csv"
    _write_csv(margin_path, rows)

    timeline_path = PLOT_DATA / "q1_structural_detection_timeline.csv"
    _write_csv(
        timeline_path,
        [
            {
                "item": "single_smoke_structural_max",
                "start_s": 0.0,
                "end_s": T_STRUCTURAL_MAX,
                "duration_s": T_STRUCTURAL_MAX,
            },
            {
                "item": "detection_window_lower_bound",
                "start_s": 0.0,
                "end_s": T_DETECT_LOWER,
                "duration_s": T_DETECT_LOWER,
            },
            {
                "item": "uncovered_time_lower_bound",
                "start_s": T_STRUCTURAL_MAX,
                "end_s": T_DETECT_LOWER,
                "duration_s": T_NAKED_LOWER,
            },
        ],
    )

    family = compensation_family(0.0, T_DETECT_LOWER)
    strategy_rows = []
    for key, label in (
        ("front_strategy", "前段保护"),
        ("middle_strategy", "中段均衡"),
        ("rear_strategy", "后段保护"),
    ):
        strategy = family[key]
        strategy_rows.append(
            {
                "strategy": key,
                "label_zh": label,
                "t_m_s": strategy["t_m_s"],
                "coverage_start_s": strategy["full_coverage_interval_s"][0],
                "coverage_end_s": strategy["full_coverage_interval_s"][1],
                "t_b_min_s": strategy["t_b_interval_s"][0],
                "t_b_max_s": strategy["t_b_interval_s"][1],
                "representative_t_b_s": strategy["representative_only"]["t_b_s"],
            }
        )
    strategies_path = PLOT_DATA / "q1_compensation_strategies.csv"
    _write_csv(strategies_path, strategy_rows)
    return {"margin": margin_path, "timeline": timeline_path, "strategies": strategies_path}


def _configure_chinese_font() -> str:
    candidates = ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Arial Unicode MS"]
    available = {font.name for font in matplotlib.font_manager.fontManager.ttflist}
    selected = next((name for name in candidates if name in available), "DejaVu Sans")
    plt.rcParams["font.sans-serif"] = [selected, "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    return selected


def generate_figures(data_paths: dict[str, Path]) -> dict[str, Any]:
    FIGURES.mkdir(parents=True, exist_ok=True)
    font_name = _configure_chinese_font()

    margin = pd.read_csv(data_paths["margin"])
    fig, ax = plt.subplots(figsize=(10, 5.8), dpi=160)
    ax.plot(
        margin["time_s"],
        margin["single_smoke_margin_m"],
        color="#185FA5",
        lw=2.1,
        label="完整覆盖裕度",
    )
    ax.fill_between(
        margin["time_s"],
        margin["single_smoke_margin_m"],
        0,
        where=margin["single_smoke_margin_m"] >= 0,
        color="#2E8B57",
        alpha=0.22,
        label="完整覆盖段",
    )
    ax.fill_between(
        margin["time_s"],
        margin["single_smoke_margin_m"],
        0,
        where=margin["single_smoke_margin_m"] < 0,
        color="#C44E52",
        alpha=0.12,
        label="裸露段",
    )
    ax.axhline(0.0, color="black", lw=1)
    for x, label in (
        (0.0, "$t_b$"),
        (TAU_HOLD, "$t_b+18$"),
        (SMOKE_LIFETIME, "$t_b+23$"),
    ):
        ax.axvline(x, color="#666666", ls="--", lw=1)
        ax.text(x, ax.get_ylim()[1] * 0.9, label, ha="center", va="top")
    for x in (9.0 - h, 9.0 + h):
        ax.scatter([x], [0], color="#D1495B", zorder=4)
    ax.set_title("单烟幕完整覆盖裕度曲线（标准化验证场景）")
    ax.set_xlabel("时间 / s")
    ax.set_ylabel("single_smoke_margin / m")
    ax.grid(alpha=0.22)
    ax.legend(loc="lower left", ncol=2)
    fig.tight_layout()
    margin_figure = FIGURES / "q1_single_smoke_margin.png"
    fig.savefig(margin_figure, bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 4.8), dpi=160)
    ax.barh(["探测窗口下界"], [T_DETECT_LOWER], color="#9CC3E6", height=0.42)
    ax.barh(["固定单烟幕结构上界"], [T_STRUCTURAL_MAX], color="#2E75B6", height=0.42)
    ax.barh(
        ["至少裸露时间"],
        [T_NAKED_LOWER],
        left=[T_STRUCTURAL_MAX],
        color="#C44E52",
        height=0.42,
    )
    for y, x, text in (
        (0, T_DETECT_LOWER, f"{T_DETECT_LOWER:.10f} s"),
        (1, T_STRUCTURAL_MAX, f"{T_STRUCTURAL_MAX:.10f} s"),
        (2, T_DETECT_LOWER, f"≥ {T_NAKED_LOWER:.10f} s"),
    ):
        ax.text(x, y, text, ha="right", va="center")
    ax.set_xlim(0, T_DETECT_LOWER * 1.08)
    ax.set_xlabel("持续时间 / s")
    ax.set_title("结构上界与导弹探测窗口时间轴")
    ax.grid(axis="x", alpha=0.22)
    fig.tight_layout()
    timeline_figure = FIGURES / "q1_structural_detection_timeline.png"
    fig.savefig(timeline_figure, bbox_inches="tight")
    plt.close(fig)

    strategies = pd.read_csv(data_paths["strategies"])
    fig, ax = plt.subplots(figsize=(10.5, 5.8), dpi=160)
    y_positions = np.arange(len(strategies))
    for y, row in zip(y_positions, strategies.itertuples(index=False)):
        ax.plot(
            [row.coverage_start_s, row.coverage_end_s],
            [y, y],
            color="#2E75B6",
            lw=9,
            solid_capstyle="butt",
            label="完整覆盖区间" if y == 0 else None,
        )
        ax.plot(
            [row.t_b_min_s, row.t_b_max_s],
            [y - 0.22, y - 0.22],
            color="#ED7D31",
            lw=5,
            solid_capstyle="butt",
            label="允许起爆区间" if y == 0 else None,
        )
        ax.scatter(
            [row.representative_t_b_s],
            [y - 0.22],
            color="#7F6000",
            s=25,
            zorder=4,
        )
    ax.axvline(0.0, color="black", lw=1)
    ax.axvline(T_DETECT_LOWER, color="black", lw=1)
    ax.set_yticks(y_positions, strategies["label_zh"])
    ax.set_xlabel("相对探测窗口进入时刻的时间 / s")
    ax.set_title("最大连续遮蔽补偿族的三类代表策略")
    ax.grid(axis="x", alpha=0.22)
    ax.legend(loc="upper center", ncol=2)
    fig.tight_layout()
    strategies_figure = FIGURES / "q1_compensation_strategies.png"
    fig.savefig(strategies_figure, bbox_inches="tight")
    plt.close(fig)
    return {
        "font_selected": font_name,
        "font_fallback_used": font_name == "DejaVu Sans",
        "figures": [
            relative_posix(margin_figure),
            relative_posix(timeline_figure),
            relative_posix(strategies_figure),
        ],
    }


def _source_state() -> tuple[dict[str, Any], dict[str, str], bool]:
    docs = locate_source_documents(required=False)
    if not docs:
        metadata = {
            "policy": "source Word files are intentionally local-only and are not committed",
            "present": False,
            "expected_sha256": EXPECTED_SOURCE_HASHES,
        }
        return metadata, dict(EXPECTED_SOURCE_HASHES), False
    if len(docs) != 2:
        metadata = {
            "policy": "source Word files are local-only; partial repository copies are not treated as validation inputs",
            "present": False,
            "partially_present_files": [path.name for path in docs.values()],
            "expected_sha256": EXPECTED_SOURCE_HASHES,
        }
        return metadata, dict(EXPECTED_SOURCE_HASHES), False
    hashes = source_hashes(required=True)
    if hashes != EXPECTED_SOURCE_HASHES:
        raise RuntimeError("Source document SHA-256 differs from the recorded read-only hash.")
    return source_document_metadata(required=True), hashes, True


def generate_core_outputs(scenario_path: Path | None = None) -> dict[str, Any]:
    assert_core_constants()
    source_metadata, verified_hashes, source_present = _source_state()
    scenario_state = load_scenario(scenario_path)
    if scenario_state.get("input_status") == "complete":
        evaluated = evaluate_complete_scenario(scenario_state["scenario"])
        scenario_payload = scenario_state["scenario"]
        scenario_state.update(evaluated)
        scenario_state["scenario"] = scenario_payload
    locked = (
        bool(scenario_state["scenario"]["locked_at_8000m"])
        if scenario_state.get("input_status") == "complete"
        else True
    )
    certificate = build_global_certificate(locked_at_8000m=locked)
    degeneracy = random_degeneracy_check()
    if certificate["certificate_status"] == "failed":
        raise RuntimeError("A/B/C certificate consistency failed.")
    if not degeneracy["verified"]:
        raise RuntimeError("Single-smoke Delta degeneracy quality gate failed.")

    structural = build_structural_metrics(scenario_state, locked_at_8000m=locked)
    family = compensation_family(
        0.0,
        T_DETECT_LOWER,
        input_status=scenario_state["input_status"],
        executable_value=scenario_state.get("T_executable_star", "not_evaluated"),
    )
    family.update(
        {
            "status": _base_status(scenario_state, certificate["certificate_status"]),
            "absolute_coordinates": (
                "not_generated"
                if scenario_state["input_status"] != "complete"
                else scenario_state.get("absolute_solution", "not_generated")
            ),
            "release_point_relation": release_point_relation(),
        }
    )
    architecture = {
        "model_scope": "Q1 only: G1+S1+O0+U0 single smoke",
        "excluded_scope": [
            "Q2 exact continuous multi-smoke union geometry",
            "Q3 multi-UAV cooperation",
            "Q4 multi-threat scheduling",
            "paper body",
        ],
        "event_semantics": {
            "t_cmd": "command time",
            "t_d": "actual release time; t_d=t_cmd+2",
            "t_b": "burst time; t_b=t_d+3.5=t_cmd+5.5",
            "t_m": "midpoint of maximum continuous coverage interval",
        },
        "status_semantics": STATUS_SEMANTICS,
        "core_values": {
            "h_s": h,
            "T_structural_max_s": T_STRUCTURAL_MAX,
            "T_detect_lower_s": T_DETECT_LOWER,
            "T_naked_lower_s": T_NAKED_LOWER,
            "burst_interval_width_s": BURST_INTERVAL_WIDTH,
        },
        "source_documents": {
            "present_in_this_run": source_present,
            "verified_sha256": verified_hashes,
            "metadata": source_metadata,
        },
        "Delta_single_degeneracy_test": degeneracy,
        "scenario_input_state": scenario_state,
        "Q1_to_Q2_boundary_state": {
            "single_smoke_exact": True,
            "multi_smoke_continuous_union": "intentionally_not_implemented",
            "rejection_message": MULTISMOKE_ERROR,
        },
        "legacy_field_policy": {
            "drop_time": "deprecated legacy alias of release time t_d",
            "command_semantic_for_drop_time": False,
        },
        "release_point_parameterisation": release_point_relation(),
        "source_conflicts_and_adopted_positions": SOURCE_CONFLICTS,
        "dependency_versions": dependency_versions(),
        "cleanup_status": "completed_by_production_finalizer",
    }
    robust = robustness_summary()
    robust["status"] = _base_status(scenario_state, certificate["certificate_status"])
    robust["wind_interface"] = wind_drift_interface()
    consistency = build_consistency_review()
    if consistency["scope_status"] != "verified":
        raise RuntimeError("Q1-to-Q2 scoped consistency gate failed.")

    write_json(ROUND1, structural)
    write_json(ROUND2, certificate)
    write_json(ROUND3, family)
    write_json(ROUND4, architecture)
    environment = dependency_versions()
    round_common = {
        "question": "Q1",
        "approved_model": "G1+S1+O0+U0",
        "status": "completed",
        "seed": 20260729,
        "environment": environment,
        "warnings": [
            "Real absolute initial states are missing; no real absolute coordinate is reported."
        ],
        "fallback_trigger_state": "not_activated",
    }
    write_json(
        ROUND1_SUMMARY,
        {
            **round_common,
            "round": 1,
            "role": "structural_metrics",
            "outputs": [relative_posix(ROUND1)],
            "metric_summary": {
                "T_structural_max_s": T_STRUCTURAL_MAX,
                "T_detect_lower_s": T_DETECT_LOWER,
                "T_naked_lower_s": T_NAKED_LOWER,
            },
        },
    )
    write_json(
        ROUND2_SUMMARY,
        {
            **round_common,
            "round": 2,
            "role": "ABC_global_certificate",
            "outputs": [relative_posix(ROUND2)],
            "metric_summary": {
                "certificate_status": certificate["certificate_status"],
                "conservative_separation_lower_s": certificate[
                    "interval_certificate_C"
                ]["conservative_positive_separation_lower_s"],
            },
        },
    )
    write_json(
        ROUND3_SUMMARY,
        {
            **round_common,
            "round": 3,
            "role": "parametric_compensation_family",
            "outputs": [relative_posix(ROUND3)],
            "metric_summary": {
                "T_structural_max_s": T_STRUCTURAL_MAX,
                "burst_interval_width_s": BURST_INTERVAL_WIDTH,
                "T_executable_star": scenario_state.get(
                    "T_executable_star", "not_evaluated"
                ),
            },
        },
    )
    write_json(
        ROUND4_SUMMARY,
        {
            **round_common,
            "round": 4,
            "role": "architecture_and_scope_freeze",
            "outputs": [relative_posix(ROUND4), relative_posix(CONSISTENCY_PATH)],
            "metric_summary": {
                "scope_status": consistency["scope_status"],
                "maximum_degeneracy_error_m": degeneracy["max_abs_error_m"],
            },
        },
    )
    write_json(ROBUSTNESS_PATH, robust)
    write_json(CONSISTENCY_PATH, consistency)
    data_paths = generate_plot_data()
    figure_info = generate_figures(data_paths)
    run_summary = {
        "execution_status": "completed",
        "input_status": scenario_state["input_status"],
        "feasibility_status": family["status"]["feasibility_status"],
        "certificate_status": certificate["certificate_status"],
        "T_executable_star": scenario_state.get("T_executable_star", "not_evaluated"),
        "core_values": architecture["core_values"],
        "maximum_degeneracy_error_m": degeneracy["max_abs_error_m"],
        "source_documents_present": source_present,
        "source_hashes": verified_hashes,
        "figure_validation": figure_info,
        "production_test_dependency": False,
        "environment": environment,
    }
    write_json(RUN_SUMMARY_PATH, run_summary)
    return {
        "source_metadata": source_metadata,
        "source_hashes_initial": verified_hashes,
        "source_documents_present": source_present,
        "scenario_state": scenario_state,
        "certificate": certificate,
        "degeneracy": degeneracy,
        "figure_info": figure_info,
        "run_summary": run_summary,
    }


def cleanup_generated_caches() -> list[str]:
    removed: list[str] = []
    directory_names = {".pytest_cache", ".mypy_cache", ".ruff_cache", "__pycache__"}
    for path in sorted(PROJECT_ROOT.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if path.is_dir() and path.name in directory_names:
            shutil.rmtree(path)
            removed.append(relative_posix(path))
        elif path.is_file() and (
            path.suffix in {".pyc", ".tmp", ".bak"}
            or path.name.startswith(("debug_", "scratch_"))
        ):
            path.unlink()
            removed.append(relative_posix(path))
    if MPL_CACHE_DIR.is_dir():
        shutil.rmtree(MPL_CACHE_DIR)
        removed.append("system_temp/q1_matplotlib_cache")
    return removed


def _formal_files_for_manifest() -> list[Path]:
    targets = [
        PROJECT_ROOT / "code/Q1",
        PROJECT_ROOT / "planning/scenario_schema.json",
        PROJECT_ROOT / "planning/assumption_register.csv",
        PROJECT_ROOT / "interfaces/Q1_to_Q2_coverage_contract.md",
        ROUND1,
        ROUND2,
        ROUND3,
        ROUND4,
        ROUND1_SUMMARY,
        ROUND2_SUMMARY,
        ROUND3_SUMMARY,
        ROUND4_SUMMARY,
        PROJECT_ROOT / "results/Q1/figures",
        PROJECT_ROOT / "results/Q1/plot_data",
        RUN_SUMMARY_PATH,
        CONSISTENCY_PATH,
        ROBUSTNESS_PATH,
    ]
    files: list[Path] = []
    for target in targets:
        if target.is_file():
            files.append(target)
        elif target.is_dir():
            files.extend(path for path in target.rglob("*") if path.is_file())
    excluded = {MANIFEST_PATH.resolve()}
    return sorted(
        {
            path.resolve()
            for path in files
            if path.resolve() not in excluded
            and "__pycache__" not in path.parts
            and path.suffix != ".pyc"
        },
        key=lambda path: relative_posix(path),
    )


def write_manifest(source_hash_values: dict[str, str]) -> dict[str, Any]:
    files = [
        {
            "path": relative_posix(path),
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
        for path in _formal_files_for_manifest()
    ]
    payload = {
        "manifest_version": "2.0",
        "scope": "Q1 production code, machine results, figures, and required handoff only",
        "source_documents": [
            {
                "path": name,
                "sha256": digest,
                "committed": False,
                "policy": "local source only",
            }
            for name, digest in source_hash_values.items()
        ],
        "formal_files": files,
        "self_entry": {
            "path": relative_posix(MANIFEST_PATH),
            "sha256": "self_referential_not_applicable",
        },
        "formal_file_count_excluding_self": len(files),
        "tests_included": False,
        "temporary_files_included": False,
        "Q2_Q3_Q4_modified_by_Q1": False,
    }
    write_json(MANIFEST_PATH, payload)
    return payload


def finalize_production_run(context: dict[str, Any]) -> dict[str, Any]:
    removed = cleanup_generated_caches()
    if context["source_documents_present"]:
        final_hashes = source_hashes(required=True)
        if final_hashes != context["source_hashes_initial"]:
            raise RuntimeError("Source document hashes changed during production execution.")
    else:
        final_hashes = context["source_hashes_initial"]
    summary = json.loads(RUN_SUMMARY_PATH.read_text(encoding="utf-8"))
    summary["production_run_after_test_deletion"] = "completed"
    summary["cleanup_removed"] = removed
    summary["source_hashes_final"] = final_hashes
    summary["source_documents_unchanged"] = (
        final_hashes == context["source_hashes_initial"]
    )
    write_json(RUN_SUMMARY_PATH, summary)
    manifest = write_manifest(final_hashes)
    return {
        "execution_status": "completed",
        "input_status": context["scenario_state"]["input_status"],
        "feasibility_status": context["run_summary"]["feasibility_status"],
        "certificate_status": context["certificate"]["certificate_status"],
        "T_executable_star": context["scenario_state"].get(
            "T_executable_star", "not_evaluated"
        ),
        "core_values": context["run_summary"]["core_values"],
        "manifest": relative_posix(MANIFEST_PATH),
        "formal_file_count": manifest["formal_file_count_excluding_self"] + 1,
        "production_test_dependency": False,
    }
