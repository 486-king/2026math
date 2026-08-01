"""Formal Q3 tables, figures, reviews, robustness report, and final manifest."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from q3_common import (
    CODE_DIR,
    FIGURES_DIR,
    FINAL_MANIFEST_PATH,
    METRICS_DIR,
    REVIEWS_DIR,
    ROBUSTNESS_DIR,
    ROOT,
    ROUND_DIR,
    TABLES_DIR,
    relative,
    sha256_file,
    write_json,
)
from q3_q2_adapter import T_WORST_S
from q3_trajectory import position_at


def write_csv(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    materialized = list(rows)
    if not materialized:
        raise ValueError(f"Cannot write an empty formal table: {path}")
    fields: list[str] = []
    for row in materialized:
        for key in row:
            if key not in fields:
                fields.append(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in materialized:
            writer.writerow(
                {
                    key: (
                        json.dumps(value, ensure_ascii=False, sort_keys=True)
                        if isinstance(value, (list, dict))
                        else value
                    )
                    for key, value in row.items()
                }
            )


def _event_rows(formal_plan: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for plan in formal_plan["uav_plans"]:
        rows.append(
            {
                "uav_id": plan["uav_id"],
                "scenario_scope": "SYNTHETIC_SCENARIO_ONLY",
                "freeze_status": "unfrozen",
                "t_start_s": plan["t_start_s"],
                "t_cmd_s": plan["t_cmd_s"],
                "t_d_s": plan["t_d_s"],
                "t_b_s": plan["t_b_s"],
                "pre_lock_mission": plan["event_chain"]["pre_lock_mission"],
                "burst_before_lock": plan["event_chain"]["burst_before_lock"],
                "smoke_center_m": plan["smoke_center_m"],
                "release_point_m": plan["release_point_m"],
                "pre_release_path_length_m": plan["pre_release_path_length_m"],
                "turn_proxy_rad": plan["turn_proxy_rad"],
            }
        )
    return rows


def _trajectory_rows(formal_plan: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for plan in formal_plan["uav_plans"]:
        times = sorted(
            {
                float(plan["t_start_s"]),
                float(plan["t_cmd_s"]),
                float(plan["t_d_s"]),
                float(plan["t_b_s"]),
                0.0,
                T_WORST_S,
            }
        )
        for time_s in times:
            if time_s < plan["t_start_s"] - 1e-10:
                continue
            point = position_at(plan, time_s)
            rows.append(
                {
                    "uav_id": plan["uav_id"],
                    "time_s": time_s,
                    "x_m": float(point[0]),
                    "y_m": float(point[1]),
                    "trajectory_scope": "from_a_i_through_T_worst",
                    "post_release_uav_retained": True,
                    "scenario_scope": "SYNTHETIC_SCENARIO_ONLY",
                    "freeze_status": "unfrozen",
                }
            )
    return rows


def _scheme_row(
    scheme_id: str,
    plans: list[dict[str, Any]],
    safety: dict[str, Any],
    failures: dict[str, Any],
    double: dict[str, Any],
    provenance: str,
) -> dict[str, Any]:
    return {
        "scheme_id": scheme_id,
        "provenance": provenance,
        "common_warning_lead_s": -min(plan["t_start_s"] for plan in plans),
        "nominal_minimum_pairwise_distance_m": safety[
            "minimum_pairwise_distance_m"
        ],
        "N_minus_1_full_window_success_count": failures[
            "full_window_success_count"
        ],
        "N_minus_1_case_count": 3,
        "worst_failure_continuous_coverage_s": failures[
            "worst_failure_continuous_coverage_s"
        ],
        "double_coverage_fraction": double["double_coverage_fraction"],
        "total_deployment_path_length_m": sum(
            plan["deployment_path_length_m"] for plan in plans
        ),
        "total_turn_proxy_rad": sum(plan["turn_proxy_rad"] for plan in plans),
        "scenario_scope": "SYNTHETIC_SCENARIO_ONLY",
        "freeze_status": "unfrozen",
    }


def write_formal_tables(payload: dict[str, Any]) -> dict[str, str]:
    formal = payload["formal_plan"]
    failures = payload["failure"]
    pareto = payload["pareto"]
    sensitivity = payload["sensitivity"]
    write_csv(TABLES_DIR / "q3_p2_events.csv", _event_rows(formal))
    write_csv(TABLES_DIR / "q3_p2_trajectory.csv", _trajectory_rows(formal))
    comparison_rows = payload["comparison_rows"]
    write_csv(TABLES_DIR / "q3_p2_comparison.csv", comparison_rows)
    write_csv(
        TABLES_DIR / "q3_p2_failure_details.csv",
        failures["failure_cases"],
    )
    write_csv(
        TABLES_DIR / "q3_pareto_front.csv",
        [
            {
                key: candidate[key]
                for key in (
                    "candidate_id",
                    "provenance",
                    "nominal_minimum_pairwise_distance_m",
                    "minimum_coverage_margin_m2",
                    "double_coverage_fraction",
                    "double_coverage_percent",
                    "N_minus_1_full_window_success_count",
                    "worst_failure_continuous_coverage_s",
                    "common_warning_lead_s",
                    "total_deployment_path_length_m",
                    "total_turn_proxy_rad",
                )
            }
            for candidate in pareto["pareto_candidates"]
        ],
    )
    write_csv(
        TABLES_DIR / "q3_p2_bearing_sensitivity.csv",
        sensitivity["bearing"]["rows"],
    )
    write_csv(
        TABLES_DIR / "q3_p2_position_sensitivity.csv",
        sensitivity["position"]["rows"],
    )
    write_csv(
        TABLES_DIR / "q3_p2_heading_sensitivity.csv",
        sensitivity["heading"]["rows"],
    )
    write_csv(
        TABLES_DIR / "q3_p2_availability_thresholds.csv",
        sensitivity["availability"]["rows"],
    )
    write_csv(
        TABLES_DIR / "q3_p2_safety_sensitivity.csv",
        sensitivity["d_safe_curve"]["rows"],
    )
    return {
        path.name: relative(path)
        for path in sorted(TABLES_DIR.glob("*.csv"))
    }


def write_figures(payload: dict[str, Any]) -> dict[str, str]:
    formal = payload["formal_plan"]
    fig, ax = plt.subplots(figsize=(9.6, 6.2))
    for plan in formal["uav_plans"]:
        times = np.linspace(plan["t_start_s"], T_WORST_S, 180)
        points = np.asarray([position_at(plan, float(value)) for value in times])
        ax.plot(points[:, 0], points[:, 1], label=f"UAV {plan['uav_id']}")
        release = np.asarray(plan["release_point_m"])
        ax.scatter(release[0], release[1], marker="x", s=70)
        ax.scatter(plan["smoke_center_m"], 0.0, marker="o", s=45)
    ax.plot(
        [0.0, 7.71 * T_WORST_S],
        [0.0, 0.0],
        color="black",
        linestyle="--",
        label="ship track",
    )
    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")
    ax.set_title("Q3 P2 straight deployment trajectories")
    ax.grid(alpha=0.3)
    ax.axis("equal")
    ax.legend()
    fig.text(
        0.5,
        0.01,
        "SYNTHETIC_SCENARIO_ONLY | UNFROZEN",
        ha="center",
        fontsize=10,
        weight="bold",
    )
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    trajectory_path = FIGURES_DIR / "q3_p2_trajectories.png"
    fig.savefig(trajectory_path, dpi=180)
    plt.close(fig)

    curve = payload["sensitivity"]["d_safe_curve"]
    rows = curve["rows"]
    fig, ax = plt.subplots(figsize=(9.2, 5.8))
    x = [row["d_safe_m"] for row in rows]
    ax.plot(
        x,
        [row["fixed_P2_execution_rate_fraction"] for row in rows],
        label="P2 executable fraction",
        color="tab:blue",
        linestyle=":",
    )
    ax.plot(
        x,
        [
            row[
                "fixed_P2_safety_retention_conditional_on_executable_fraction"
            ]
            for row in rows
        ],
        label="P2 safety | executable",
        color="tab:blue",
        linestyle="--",
    )
    ax.plot(
        x,
        [
            row["fixed_P2_safety_retention_unconditional_fraction"]
            for row in rows
        ],
        label="P2 joint executable-and-safe",
        color="tab:blue",
    )
    ax.plot(
        x,
        [row["scheme_switch_execution_rate_fraction"] for row in rows],
        label="scheme-switch executable fraction",
        color="tab:orange",
        linestyle=":",
    )
    ax.plot(
        x,
        [
            row[
                "scheme_switch_safety_retention_conditional_on_executable_fraction"
            ]
            for row in rows
        ],
        label="scheme-switch safety | executable",
        color="tab:orange",
        linestyle="--",
    )
    ax.plot(
        x,
        [
            row["scheme_switch_safety_retention_unconditional_fraction"]
            for row in rows
        ],
        label="scheme-switch joint executable-and-safe",
        color="tab:orange",
    )
    ax.axvline(curve["nominal_P2_distance_m"], color="black", linestyle="--")
    ax.axvline(curve["half_nominal_distance_m"], color="gray", linestyle=":")
    ax.set_xlabel("d_safe (m)")
    ax.set_ylabel("finite-sample fraction")
    ax.set_ylim(-0.02, 1.02)
    ax.grid(alpha=0.3)
    ax.legend()
    ax.set_title("Q3 execution and safety retention are reported separately")
    fig.text(
        0.5,
        0.01,
        (
            "SYNTHETIC_SCENARIO_ONLY | EXPLORATORY_STRESS_TEST | UNFROZEN\n"
            "position ±200 m per coordinate; heading ±45°; availability excluded"
        ),
        ha="center",
        fontsize=9,
        weight="bold",
    )
    fig.tight_layout(rect=(0, 0.09, 1, 1))
    safety_path = FIGURES_DIR / "q3_p2_safety_sensitivity.png"
    fig.savefig(safety_path, dpi=180)
    plt.close(fig)

    front = payload["pareto"]["pareto_candidates"]
    fig, ax = plt.subplots(figsize=(9.2, 5.8))
    scatter = ax.scatter(
        [item["total_deployment_path_length_m"] for item in front],
        [item["nominal_minimum_pairwise_distance_m"] for item in front],
        c=[item["double_coverage_fraction"] for item in front],
        cmap="viridis",
        s=75,
    )
    fig.colorbar(scatter, ax=ax, label="double coverage fraction")
    for item in front:
        if item["candidate_id"] == "P2_REFERENCE_VERIFIED":
            ax.annotate("P2", (
                item["total_deployment_path_length_m"],
                item["nominal_minimum_pairwise_distance_m"],
            ))
    p1 = payload["pareto"]["P1_LEGACY_REFERENCE_VERIFIED"]
    p4 = payload["pareto"]["P4_LEGACY_REFERENCE_VERIFIED"]
    ax.annotate("P1 legacy verified", (
        p1["total_deployment_path_length_m"],
        p1["nominal_minimum_pairwise_distance_m"],
    ))
    ax.annotate("P4 legacy verified", (
        p4["total_deployment_path_length_m"],
        p4["nominal_minimum_pairwise_distance_m"],
    ))
    ax.set_xlabel("total pre-release deployment path (m)")
    ax.set_ylabel("nominal minimum pairwise distance (m)")
    ax.set_title("Verified nondominated synthetic candidate set")
    ax.grid(alpha=0.3)
    fig.text(
        0.5,
        0.01,
        (
            "SYNTHETIC_SCENARIO_ONLY | UNFROZEN | "
            "GLOBAL_OPTIMALITY_NOT_PROVED"
        ),
        ha="center",
        fontsize=9,
        weight="bold",
    )
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    pareto_path = FIGURES_DIR / "q3_pareto_front.png"
    fig.savefig(pareto_path, dpi=180)
    plt.close(fig)
    return {
        path.name: relative(path)
        for path in (trajectory_path, safety_path, pareto_path)
    }


def write_robustness_report(payload: dict[str, Any]) -> Path:
    combined = payload["sensitivity"]["combined"]
    position = payload["sensitivity"]["position"]
    heading = payload["sensitivity"]["heading"]
    availability = payload["sensitivity"]["availability"]
    pareto = payload["pareto"]
    baseline = payload["baseline"]
    text = f"""# Q3 鲁棒性与限制报告（round3）

状态：`SYNTHETIC_SCENARIO_ONLY`、`EXPLORATORY_STRESS_TEST`、`UNFROZEN`。

## 口径

- 固定 P2 与有限方案切换分开报告。
- 组合扰动只包含每个初始位置坐标 ±200 m、初始航向 ±45°。
- 可用时刻没有受支持的范围或分布，因此未纳入随机扰动；只报告精确阈值。
- 均匀独立采样是额外探索性设计，不是题面分布、真实作战概率或置信度。

## 结果

- 旧 Q3-B 方案：`{baseline['legacy_reference']['scheme_id']}`，当前复验状态为 `{baseline['legacy_reference']['independent_verification_status']}`，不作为已验证比较候选。
- 当前可用基线：`{baseline['scheme_id']}`，来源为 `{baseline['provenance']}`；它与旧 Q3-B 不是同一方案。
- P1/P4 来自只读 Git 历史完整配置，并在当前模型中独立复验；对应标识为 `P1_LEGACY_REFERENCE_VERIFIED` 与 `P4_LEGACY_REFERENCE_VERIFIED`。
- 已验证合成候选池非支配集：搜索范围 `{pareto['search_scope']}`，由固定核心候选 {pareto['restricted_fixed_core_candidate_count']} 个、六变量候选 {pareto['full_six_variable_candidate_count']} 个、历史复验候选 {pareto['historical_verified_candidate_count']} 个组成，总计 {pareto['total_verified_candidate_count']} 个。
- 非支配关系口径：`{pareto['pareto_relation_scope']}`；连续问题 Pareto 完备性：`{pareto['continuous_problem_pareto_completeness']}`；不声明连续非凸问题的完整或全局 Pareto 前沿。
- 样本数：{combined['sample_count']}，固定种子：{combined['seed']}。
- 固定 P2 可执行样本：{combined['execution_success_count']}，执行率 {combined['execution_rate_fraction']:.6f}。
- 固定 P2 失败样本：{combined['execution_failure_count']}。
- 有限方案切换执行率：{combined['switch_execution_rate_fraction']:.6f}。
- 最小样本机间距：{combined['minimum_sample_distance_m']:.12f} m。
- 固定 P2 在半名义 d_safe 下的无条件联合保留率：{combined['fixed_P2_safety_retention_unconditional_at_half_nominal_fraction']:.6f}。
- 无条件联合比例表示“可执行且安全”的全部样本比例；条件安全比例只在可执行样本中评价安全距离，二者不可互换。
- 位置单因素案例：{position['case_count']}，执行失败：{position['failure_count']}。
- 航向效应：`{heading['heading_effect_status']}`。
- 可用时刻分布：`{availability['availability_distribution_status']}`。
- 旧 96.05% 与 0.2337720332 m 的状态：`{combined['legacy_reference_comparison_status']}`。

## 限制

当前结果不包含真实三机初态、真实 d_safe、真实能耗、最小转弯半径、风漂或基地 12 km 绝对可达性。P2 的名义最小距离不是刚性鲁棒保证；方案切换后可行也不能表述成固定 P2 鲁棒。
"""
    path = ROBUSTNESS_DIR / "q3_robustness_report_round3.md"
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def write_review(checks: dict[str, bool], details: dict[str, Any]) -> dict[str, Any]:
    failed = sorted(key for key, value in checks.items() if not value)
    review = {
        "schema_version": 1,
        "question_id": "Q3",
        "review_status": "passed" if not failed else "failed",
        "checks": {
            key: {"status": "PASS" if value else "FAIL"}
            for key, value in sorted(checks.items())
        },
        "failed_checks": failed,
        "details": details,
    }
    write_json(REVIEWS_DIR / "q3_python_review_round3.json", review)
    return review


def _artifact_role(path: Path) -> str:
    value = relative(path)
    if value.startswith("code/Q3/reviews/"):
        return "review_or_final_validation"
    if value.startswith("code/Q3/"):
        return "production_code_or_documentation"
    if value.startswith("methods/Q3/"):
        return "method_or_human_decision_record"
    if value.startswith("planning/manifests/"):
        return "workflow_manifest"
    if value.startswith("workspace/data_clean/"):
        return "standardized_synthetic_input"
    if "/figures/" in value:
        return "formal_figure"
    if "/tables/" in value:
        return "formal_table"
    if value.startswith("robustness/Q3/"):
        return "robustness_report"
    return "formal_machine_result"


def build_final_manifest() -> dict[str, Any]:
    paths: list[Path] = []
    for base in (
        CODE_DIR,
        ROOT / "methods" / "Q3",
        ROOT / "workspace" / "data_clean",
        ROUND_DIR,
        ROBUSTNESS_DIR,
    ):
        if base.exists():
            paths.extend(path for path in base.rglob("*") if path.is_file())
    paths.append(ROOT / "planning" / "manifests" / "Q3.json")
    allowed_data = {
        "q3_standardized_scenario.json",
        "q3_reference_plan_p2.json",
    }
    filtered: list[Path] = []
    for path in paths:
        rel = relative(path)
        if path == FINAL_MANIFEST_PATH:
            continue
        if "tests/" in rel or "__pycache__" in rel or path.suffix == ".pyc":
            continue
        if rel.startswith("workspace/data_clean/") and path.name not in allowed_data:
            continue
        if path.suffix.lower() == ".docx":
            continue
        if rel.startswith(("code/Q1/", "code/Q2/", "code/Q4/")):
            continue
        filtered.append(path)
    unique = sorted({path.resolve() for path in filtered}, key=lambda p: relative(p))
    entries = [
        {
            "relative_path": relative(path),
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
            "artifact_role": _artifact_role(path),
        }
        for path in unique
    ]
    manifest = {
        "schema_version": 1,
        "question_id": "Q3",
        "file_count": len(entries),
        "files": entries,
        "hash_error_count": 0,
        "duplicate_path_count": len(entries)
        - len({entry["relative_path"] for entry in entries}),
        "missing_path_count": 0,
        "unallowed_path_count": 0,
        "workspace_data_clean_files": sorted(
            relative(path)
            for path in (ROOT / "workspace" / "data_clean").rglob("*")
            if path.is_file()
        ),
        "workspace_data_clean_scope_status": (
            "only_expected_q3_files_present"
            if sorted(
                relative(path)
                for path in (ROOT / "workspace" / "data_clean").rglob("*")
                if path.is_file()
            )
            == [
                "workspace/data_clean/q3_reference_plan_p2.json",
                "workspace/data_clean/q3_standardized_scenario.json",
            ]
            else "unexpected_files_present_and_excluded_from_q3_manifest"
        ),
        "self_manifest_policy": (
            "q3_final_manifest.json is excluded because a stable recursive "
            "self-hash is impossible"
        ),
        "source_documents_excluded": [
            "B题：舰船烟幕遮蔽干扰优化.docx",
            "Q3_编程手与论文手任务清单.docx",
        ],
    }
    write_json(FINAL_MANIFEST_PATH, manifest)
    return manifest


def core_output_hashes() -> dict[str, str]:
    paths = sorted(METRICS_DIR.glob("*.json")) + sorted(
        TABLES_DIR.glob("*.csv")
    )
    return {relative(path): sha256_file(path) for path in paths}
