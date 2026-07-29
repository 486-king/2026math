from __future__ import annotations

import csv
import json
from pathlib import Path
import platform
import sys
import time

import matplotlib.pyplot as plt
import numpy as np

from q3_common import ROOT

Q2_DIR = ROOT / "code" / "Q2"
sys.path.insert(0, str(Q2_DIR))

from q3_p2_analysis import build_analysis  # noqa: E402


OUT = ROOT / "results" / "Q3" / "experiments" / "round3"


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    started = time.perf_counter()
    analysis = build_analysis()
    metrics = OUT / "metrics"
    tables = OUT / "tables"
    figures = OUT / "figures"

    plan = {
        "scenario_label": "SYNTHETIC_SCENARIO_ONLY",
        "candidate_id": "A-00217",
        "decision_id": "q3_representative_choice_p2",
        "events": analysis["events"],
        "minimum_pair_distance": analysis["minimum_pair_distance"],
        "nominal_safety_distance_feasible_interval_m": analysis[
            "nominal_safety_distance_feasible_interval_m"
        ],
        "continuous_validation": analysis["continuous_validation"],
    }
    sensitivity = {
        "scenario_label": "SYNTHETIC_SCENARIO_ONLY",
        "bearing": analysis["bearing_rows"],
        "summary": analysis["sensitivity_summary"],
    }
    write_json(metrics / "q3_p2_formal_plan.json", plan)
    write_json(metrics / "q3_p2_sensitivity.json", sensitivity)
    write_json(metrics / "q3_p2_failure_details.json", analysis["failure_details"])
    write_json(
        metrics / "q3_p2_combined_perturbations.json",
        analysis["perturbations"]["combined"],
    )
    write_csv(tables / "q3_p2_events.csv", analysis["events"])
    write_csv(tables / "q3_p2_trajectory.csv", analysis["trajectory_rows"])
    write_csv(tables / "q3_p2_bearing_sensitivity.csv", analysis["bearing_rows"])
    write_csv(
        tables / "q3_p2_position_sensitivity.csv",
        analysis["perturbations"]["position_one_at_a_time"],
    )
    write_csv(
        tables / "q3_p2_heading_sensitivity.csv",
        analysis["perturbations"]["heading_one_at_a_time"],
    )
    write_csv(tables / "q3_p2_comparison.csv", analysis["comparison"])

    safety_rows = []
    nominal_limit = analysis["nominal_safety_distance_feasible_interval_m"][1]
    combined = analysis["perturbations"]["combined"]
    for d_safe in np.arange(0.0, 150.0001, 5.0):
        retained = [
            row
            for row in combined
            if row["route_constructible"]
            and row["lead_within_60s"]
            and row["minimum_pair_distance_m"] + 1e-9 >= d_safe
        ]
        safety_rows.append(
            {
                "scenario_label": "SYNTHETIC_SCENARIO_ONLY",
                "d_safe_m": float(d_safe),
                "nominal_p2_feasible": bool(d_safe <= nominal_limit + 1e-9),
                "combined_perturbation_retention_rate": len(retained)
                / len(combined),
            }
        )
    write_csv(tables / "q3_p2_safety_sensitivity.csv", safety_rows)

    figures.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7.6, 5.0))
    colors = ["#2563eb", "#dc2626", "#059669"]
    for uav in range(1, 4):
        rows = [row for row in analysis["trajectory_rows"] if row["uav"] == uav]
        ax.plot(
            [row["x_m"] for row in rows],
            [row["y_m"] for row in rows],
            color=colors[uav - 1],
            label=f"UAV {uav}",
        )
        event = analysis["events"][uav - 1]
        ax.scatter(
            [event["initial_position_m"][0]],
            [event["initial_position_m"][1]],
            color=colors[uav - 1],
            marker="o",
        )
        ax.scatter(
            [event["release_point_m"][0]],
            [event["release_point_m"][1]],
            color=colors[uav - 1],
            marker="x",
        )
        ax.scatter(
            [event["smoke_center_m"][0]],
            [event["smoke_center_m"][1]],
            color=colors[uav - 1],
            marker="s",
        )
    ax.set_aspect("equal", adjustable="datalim")
    ax.set_xlabel("x / m")
    ax.set_ylabel("y / m")
    ax.set_title("Q3 P2 trajectories (SYNTHETIC_SCENARIO_ONLY)")
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(figures / "q3_p2_trajectories.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.6, 4.4))
    ax.plot(
        [row["d_safe_m"] for row in safety_rows],
        [row["combined_perturbation_retention_rate"] for row in safety_rows],
        color="#2563eb",
        marker="o",
        markersize=3,
    )
    ax.axvline(nominal_limit, color="#dc2626", linestyle="--", label="nominal P2 limit")
    ax.set_xlabel("required safety distance / m")
    ax.set_ylabel("combined-perturbation retention rate")
    ax.set_ylim(-0.02, 1.02)
    ax.set_title("Q3 P2 safety sensitivity (SYNTHETIC_SCENARIO_ONLY)")
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(figures / "q3_p2_safety_sensitivity.png", dpi=180)
    plt.close(fig)

    elapsed = time.perf_counter() - started
    summary = {
        "schema_version": 1,
        "question": "Q3",
        "round": "round3",
        "round_label": "p2_formal_sensitivity",
        "scenario_label": "SYNTHETIC_SCENARIO_ONLY",
        "implementation_target": "python",
        "random_seed": 2026,
        "approved_decision_ids": [
            "q3_method_choice",
            "q3_result_adjust_pretask",
            "q3_representative_choice_p2",
        ],
        "selected_method": "Q3-A",
        "selected_candidate": "A-00217",
        "retained_alternatives": ["A-00017", "A-00033", "Q3-B B-3"],
        "metrics_summary": {
            "common_warning_lead_s": analysis["selected"]["lead_required_s"],
            "d_safe_max_m": nominal_limit,
            "minimum_pair_distance": analysis["minimum_pair_distance"],
            "n_minus_one_success_rate": analysis[
                "selected_exact_failure_metrics"
            ]["n_minus_one_success_rate"],
            "worst_failure_continuous_cover_s": analysis[
                "selected_exact_failure_metrics"
            ]["worst_failure_continuous_cover_s"],
            "double_cover_time_ratio": analysis[
                "selected_exact_failure_metrics"
            ]["double_cover_time_ratio"],
            "sensitivity": analysis["sensitivity_summary"],
        },
        "continuous_validation_pass": analysis["continuous_validation"][
            "validators_agree"
        ],
        "fallback_trigger": {
            "fallback_id": "P1_A-00017_recomparison",
            "observed": analysis["sensitivity_summary"][
                "fallback_p1_recomparison_required"
            ],
        },
        "freeze_status": "BLOCKED_FALLBACK_RECOMPARISON"
        if analysis["sensitivity_summary"]["fallback_p1_recomparison_required"]
        else "WAITING_HUMAN_PACKAGE_SIGNOFF",
        "outputs": [
            "results/Q3/experiments/round3/metrics/q3_p2_formal_plan.json",
            "results/Q3/experiments/round3/metrics/q3_p2_sensitivity.json",
            "results/Q3/experiments/round3/metrics/q3_p2_failure_details.json",
            "results/Q3/experiments/round3/metrics/q3_p2_combined_perturbations.json",
            "results/Q3/experiments/round3/tables/q3_p2_events.csv",
            "results/Q3/experiments/round3/tables/q3_p2_trajectory.csv",
            "results/Q3/experiments/round3/tables/q3_p2_bearing_sensitivity.csv",
            "results/Q3/experiments/round3/tables/q3_p2_position_sensitivity.csv",
            "results/Q3/experiments/round3/tables/q3_p2_heading_sensitivity.csv",
            "results/Q3/experiments/round3/tables/q3_p2_safety_sensitivity.csv",
            "results/Q3/experiments/round3/tables/q3_p2_comparison.csv",
            "results/Q3/experiments/round3/figures/q3_p2_trajectories.png",
            "results/Q3/experiments/round3/figures/q3_p2_safety_sensitivity.png",
        ],
        "claim_limits": [
            "All coordinates and numerical routes are SYNTHETIC_SCENARIO_ONLY.",
            "The smoke schedule is the selected canonical-collinear candidate A-00217.",
            "Initial-position sensitivity preserves the fixed P2 smoke schedule and UAV assignment.",
            "No minimum turn radius is available; heading perturbations change the reported turn metric but not instantaneous-turn feasibility.",
            "No N-1 impossibility claim is made.",
        ],
        "runtime_seconds": elapsed,
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "numpy": np.__version__,
        },
    }
    write_json(OUT / "run_summary.json", summary)
    print(
        json.dumps(
            {
                "candidate": "A-00217",
                "minimum_pair_distance": analysis["minimum_pair_distance"],
                "sensitivity": analysis["sensitivity_summary"],
                "freeze_status": summary["freeze_status"],
                "runtime_seconds": elapsed,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
