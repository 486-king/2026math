from __future__ import annotations

import csv
import json
from pathlib import Path
import platform
import sys
import time

import matplotlib.pyplot as plt
import numpy as np

from q3_common import LABEL, ROOT, load_scenario

Q2_DIR = ROOT / "code" / "Q2"
sys.path.insert(0, str(Q2_DIR))

from q3_pretask_optimizer import (  # noqa: E402
    WINDOW_END,
    continuous_and_independent_validation,
    generate_baseline,
    generate_main_candidates,
    pareto,
    representatives,
)


OUT = ROOT / "results" / "Q3" / "experiments" / "round2"


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def compact(row: dict) -> dict:
    return {
        "candidate_id": row["candidate_id"],
        "lead_required_s": row["lead_required_s"],
        "user_defined_latest_uav_warning_lead_s": row[
            "user_defined_latest_uav_warning_lead_s"
        ],
        "d_safe_max_m": row["d_safe_max_m"],
        "normal_min_slack_sq_m2": row["normal_min_slack_sq_m2"],
        "n_minus_one_success_rate": row["n_minus_one_success_rate"],
        "worst_failure_continuous_cover_s": row[
            "worst_failure_continuous_cover_s"
        ],
        "double_cover_time_ratio": row["double_cover_time_ratio"],
        "total_path_length_m": row["total_path_length_m"],
        "total_turn_angle_rad": row["total_turn_angle_rad"],
    }


def main() -> None:
    started = time.perf_counter()
    scenario = load_scenario()
    candidates = generate_main_candidates(scenario)
    if not candidates:
        raise RuntimeError("Q3-A pre-task search produced no legal candidate")
    baseline = generate_baseline(scenario)
    minimum_lead = min(row["lead_required_s"] for row in candidates)
    minimum_user_defined_lead = min(
        row["user_defined_latest_uav_warning_lead_s"] for row in candidates
    )

    lead_rows = []
    for lead in np.arange(5.5, 60.0001, 2.5):
        feasible = [row for row in candidates if row["lead_required_s"] <= lead]
        lead_rows.append(
            {
                "scenario_label": LABEL,
                "lead_time_s": float(lead),
                "complete_defense_feasible": bool(feasible),
                "feasible_candidate_count": len(feasible),
                "pareto_count_at_dsafe0": len(pareto(feasible)) if feasible else 0,
                "maximum_d_safe_m": max(
                    (row["d_safe_max_m"] for row in feasible), default=None
                ),
            }
        )

    safety_rows = []
    fronts_by_safety: dict[str, list[dict]] = {}
    representative_rows = []
    for d_safe in np.arange(0.0, 150.0001, 10.0):
        feasible = [
            row
            for row in candidates
            if row["d_safe_max_m"] + 1e-9 >= d_safe
            and row["lead_required_s"] <= 60.0
        ]
        front = pareto(feasible)
        rep = representatives(front)
        fronts_by_safety[str(float(d_safe))] = [compact(row) for row in front]
        safety_rows.append(
            {
                "scenario_label": LABEL,
                "d_safe_m": float(d_safe),
                "feasible_candidate_count": len(feasible),
                "pareto_count": len(front),
                "representative_status": rep["status"],
                "representative_candidate_id": rep.get("selected_candidate_id"),
                "ideal_point_id": rep.get("methods", {}).get("ideal_point"),
                "knee_id": rep.get("methods", {}).get("knee_chebyshev"),
                "layered_id": rep.get("methods", {}).get("layered"),
            }
        )
        representative_rows.append({"d_safe_m": float(d_safe), **rep})

    front0 = pareto(candidates)
    rep0 = representatives(front0)
    validation_ids = set()
    if rep0.get("methods"):
        validation_ids.update(rep0["methods"].values())
    validation_ids.add(min(candidates, key=lambda row: row["lead_required_s"])["candidate_id"])
    by_id = {row["candidate_id"]: row for row in candidates}
    formal_validations = {
        candidate_id: continuous_and_independent_validation(by_id[candidate_id])
        for candidate_id in sorted(validation_ids)
    }
    baseline_validation = continuous_and_independent_validation(baseline)

    n1_found = [
        row
        for row in candidates
        if row["n_minus_one_success_rate"] >= 1.0 - 1e-12
    ]
    main_metrics = {
        "scenario_label": LABEL,
        "claim_scope": "standardized scenario; canonical collinear smoke-centre candidate family",
        "candidate_count": len(candidates),
        "minimum_actual_warning_lead_s": minimum_lead,
        "minimum_common_all_uav_warning_lead_s": minimum_lead,
        "minimum_user_defined_latest_uav_warning_lead_s": minimum_user_defined_lead,
        "warning_lead_definition_note": (
            "-max_i(a_i) is the lead of the latest-available UAV; "
            "-min_i(a_i) is the common warning lead needed to make every "
            "selected route executable."
        ),
        "event_delay_lower_bound_s": 5.5,
        "pareto_front_dsafe0": [compact(row) for row in front0],
        "representative_dsafe0": rep0,
        "representative_candidates": {
            candidate_id: by_id[candidate_id]
            for candidate_id in sorted(
                set(rep0.get("methods", {}).values())
            )
        },
        "minimum_lead_candidate": min(
            candidates, key=lambda row: row["lead_required_s"]
        ),
        "representatives_by_dsafe": representative_rows,
        "n_minus_one_full_window_candidates_found": len(n1_found),
        "n_minus_one_claim": (
            "found in recorded search family"
            if n1_found
            else "not found in recorded search family; not a proof of impossibility"
        ),
        "formal_candidate_validations": formal_validations,
    }
    baseline_metrics = {
        "scenario_label": LABEL,
        "claim_scope": "front-middle-rear analytic construction baseline",
        "candidate": baseline,
        "validation": baseline_validation,
    }

    metrics_dir = OUT / "metrics"
    tables_dir = OUT / "tables"
    figures_dir = OUT / "figures"
    write_json(metrics_dir / "q3_main_pareto.json", main_metrics)
    write_json(metrics_dir / "q3_baseline.json", baseline_metrics)
    write_json(metrics_dir / "q3_pareto_by_dsafe.json", fronts_by_safety)
    write_csv(tables_dir / "q3_lead_time_sensitivity.csv", lead_rows)
    write_csv(tables_dir / "q3_safety_thresholds.csv", safety_rows)
    write_csv(
        tables_dir / "q3_pareto_front_dsafe0.csv",
        [{"scenario_label": LABEL, **compact(row)} for row in front0],
    )
    comparison = [
        {
            "scenario_label": LABEL,
            "method_id": "Q3-A",
            "minimum_lead_s": minimum_lead,
            "user_defined_latest_uav_warning_lead_s": minimum_user_defined_lead,
            "maximum_d_safe_m": max(row["d_safe_max_m"] for row in candidates),
            "pareto_count_dsafe0": len(front0),
            "n_minus_one_full_candidates_found": len(n1_found),
            "representative_status_dsafe0": rep0["status"],
            "total_path_length_m": None,
            "total_turn_angle_rad": None,
        },
        {
            "scenario_label": LABEL,
            "method_id": "Q3-B",
            "minimum_lead_s": baseline["lead_required_s"],
            "user_defined_latest_uav_warning_lead_s": baseline[
                "user_defined_latest_uav_warning_lead_s"
            ],
            "maximum_d_safe_m": baseline["d_safe_max_m"],
            "pareto_count_dsafe0": 1,
            "n_minus_one_full_candidates_found": int(
                baseline["n_minus_one_success_rate"] == 1.0
            ),
            "representative_status_dsafe0": "CONSTRUCTIVE_BASELINE",
            "total_path_length_m": baseline["total_path_length_m"],
            "total_turn_angle_rad": baseline["total_turn_angle_rad"],
        },
    ]
    write_csv(tables_dir / "q3_method_comparison.csv", comparison)

    figures_dir.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7.6, 4.2))
    ax.plot(
        [row["lead_time_s"] for row in lead_rows],
        [row["feasible_candidate_count"] for row in lead_rows],
        marker="o",
        color="#2563eb",
    )
    ax.axvline(5.5, color="#dc2626", linestyle="--", label="event lower bound 5.5 s")
    ax.axvline(minimum_lead, color="#047857", linestyle="-.", label="first feasible candidate")
    ax.set_xlabel("common warning lead / s")
    ax.set_ylabel("complete-defense candidate count")
    ax.set_title("Q3 pre-task lead-time feasibility (synthetic scenario only)")
    ax.grid(alpha=0.22)
    ax.legend()
    fig.tight_layout()
    fig.savefig(figures_dir / "q3_lead_time_feasibility.png", dpi=180)
    plt.close(fig)

    elapsed = time.perf_counter() - started
    summary = {
        "schema_version": 1,
        "question": "Q3",
        "round": "round2",
        "round_label": "prewarning_pareto",
        "implementation_target": "python",
        "random_seed": 2026,
        "approved_decision_ids": [
            "q3_method_choice",
            "q3_parameterized_and_standardized_scenario",
            "q3_result_adjust_pretask",
        ],
        "scenario_label": LABEL,
        "methods": [
            {
                "method_id": "Q3-A",
                "role": "main_candidate",
                "status": "executed",
                "metrics_summary": {
                    "candidate_count": len(candidates),
                    "minimum_actual_warning_lead_s": minimum_lead,
                    "minimum_user_defined_latest_uav_warning_lead_s": minimum_user_defined_lead,
                    "pareto_count_dsafe0": len(front0),
                    "representative_status_dsafe0": rep0["status"],
                    "n_minus_one_full_candidates_found": len(n1_found),
                },
            },
            {
                "method_id": "Q3-B",
                "role": "usable_baseline",
                "status": "executed",
                "metrics_summary": compact(baseline),
            },
        ],
        "comparison": comparison,
        "continuous_validation": {
            "main_reported_candidates_all_pass": all(
                value["validators_agree"] for value in formal_validations.values()
            ),
            "baseline_pass": baseline_validation["validators_agree"],
        },
        "representative_decision": rep0,
        "claim_limits": [
            "All coordinates are SYNTHETIC_SCENARIO_ONLY.",
            "Q3-A searches a canonical collinear smoke-centre family, not the full two-dimensional global space.",
            "Absence of an N-1 full-window candidate is not an impossibility proof.",
            "The 864-candidate and 127.73 m risk-probe values are not imported."
        ],
        "fallback_trigger": {
            "fallback_id": "Q3-C",
            "observed": False,
            "reason": "No traceable uncertainty set and no recorded fragility trigger."
        },
        "outputs": [
            "results/Q3/experiments/round2/metrics/q3_main_pareto.json",
            "results/Q3/experiments/round2/metrics/q3_baseline.json",
            "results/Q3/experiments/round2/metrics/q3_pareto_by_dsafe.json",
            "results/Q3/experiments/round2/tables/q3_lead_time_sensitivity.csv",
            "results/Q3/experiments/round2/tables/q3_safety_thresholds.csv",
            "results/Q3/experiments/round2/tables/q3_pareto_front_dsafe0.csv",
            "results/Q3/experiments/round2/tables/q3_method_comparison.csv",
            "results/Q3/experiments/round2/figures/q3_lead_time_feasibility.png"
        ],
        "runtime_seconds": elapsed,
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "numpy": np.__version__
        }
    }
    write_json(OUT / "run_summary.json", summary)
    print(
        json.dumps(
            {
                "candidate_count": len(candidates),
                "minimum_lead_s": minimum_lead,
                "pareto_count_dsafe0": len(front0),
                "representative_status": rep0["status"],
                "n1_found": len(n1_found),
                "baseline_lead_s": baseline["lead_required_s"],
                "runtime_seconds": elapsed,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
