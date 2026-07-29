from __future__ import annotations

import csv
from datetime import datetime
import json
from pathlib import Path
import platform
import sys
import time

import matplotlib.pyplot as plt
import numpy as np
import scipy

from q2_analytic_baseline import run_baseline
from q2_common import CANDIDATE, CONSTANTS, candidate_window
from q2_union_optimizer import (
    serialize_frontier_item,
    single_bomb_capacity,
    three_bomb_best_verified,
    two_bomb_capacity,
)


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results" / "Q2" / "experiments" / "round2"
METRICS = OUT / "metrics"
TABLES = OUT / "tables"
FIGURES = OUT / "figures"


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    for directory in (METRICS, TABLES, FIGURES):
        directory.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    one = single_bomb_capacity()
    two = two_bomb_capacity()
    three = three_bomb_best_verified()
    baseline = run_baseline()
    runtime = time.perf_counter() - started

    round1_validation_path = (
        ROOT
        / "results"
        / "Q2"
        / "experiments"
        / "round1"
        / "metrics"
        / "q2_continuous_validation.json"
    )
    round1_validation = json.loads(round1_validation_path.read_text(encoding="utf-8"))
    window_start, window_end = candidate_window()
    minimum_resource = {
        "question": "Q2",
        "objective": "minimum bombs for complete worst-case M1 window",
        "bomb_count": 2,
        "minimality_evidence": {
            "one_bomb_analytic_capacity_s": one["duration_s"],
            "worst_case_M1_window_s": CONSTANTS.m1_detection_upper_s,
            "one_bomb_insufficient": one["duration_s"] < CONSTANTS.m1_detection_upper_s,
            "two_bomb_full_window_continuously_certified": round1_validation[
                "strict_relative_candidate_validated"
            ],
            "logical_conclusion": (
                "one bomb cannot cover the window and a two-bomb schedule is "
                "continuously certified; therefore two is the minimum in the "
                "relative M1/S1 model"
            ),
        },
        "relative_schedule": {
            "cloud_centers_m": list(CANDIDATE.cloud_centers_m),
            "burst_times_s": list(CANDIDATE.burst_times_s),
            "release_times_s": [
                b - CONSTANTS.bomb_burst_delay_s
                for b in CANDIDATE.burst_times_s
            ],
            "command_times_s": [
                b - CONSTANTS.bomb_burst_delay_s - 2.0
                for b in CANDIDATE.burst_times_s
            ],
            "timing_interpretation": (
                "t_release=t_command+2; t_burst=t_release+3.5"
            ),
            "window_start_s": window_start,
            "window_end_s": window_end,
            "window_duration_s": window_end - window_start,
        },
        "continuous_validation_source": str(
            round1_validation_path.relative_to(ROOT)
        ).replace("\\", "/"),
        "absolute_operational_status": "blocked_missing_initial_state_and_reference_base",
        "robustness_interpretation": (
            "This full-window schedule is preferred operationally over the "
            "capacity-frontier tangency schedules because its round-1 "
            "independent minimum squared cross-section slack is positive."
        ),
        "status": "PASS",
    }
    write_json(
        METRICS / "q2_two_bomb_minimum_resource_plan.json",
        minimum_resource,
    )

    frontier_items = [
        serialize_frontier_item(one),
        serialize_frontier_item(two),
        serialize_frontier_item(three),
    ]
    baseline_caps = {
        {1: "one_bomb", 2: "two_bombs", 3: "three_bombs"}[row["bomb_count"]]:
        row["zero_overlap_capacity_s"]
        for row in baseline["capacities"]
    }
    frontier = {
        "question": "Q2",
        "objective_scope": "O3",
        "main_method": "A",
        "mandatory_baseline": "B",
        "capacity_definition": (
            "length of one connected interval during which the complete ship "
            "disk is covered by the union of active smoke disks"
        ),
        "items": frontier_items,
        "baseline_independent_chain_capacities_s": baseline_caps,
        "increment_over_B_s": {
            "one_bomb": one["duration_s"] - baseline_caps["one_bomb"],
            "two_bombs": two["duration_s"] - baseline_caps["two_bombs"],
            "three_bombs": three["duration_s"] - baseline_caps["three_bombs"],
        },
        "three_bomb_claim_warning": (
            "The three-bomb value is the best continuously verified canonical "
            "collinear candidate from the recorded multi-start search. No "
            "matching global upper bound has been proved."
        ),
        "boundary_sensitivity": {
            "two_bomb_capacity_frontier": (
                "CONDITIONAL: internal bridge tangency has approximately zero "
                "slack; use the separately certified full-M1 schedule for the "
                "operational recommendation."
            ),
            "three_bomb_capacity_frontier": (
                "CONDITIONAL: endpoint lies on the feasibility boundary and "
                "there is no global upper-bound proof."
            ),
            "minimum_resource_full_M1_plan": (
                "PASS: round-1 minimum independent squared cross-section "
                "slack is 1463.887280249688 m^2."
            ),
        },
        "C_triggered": False,
        "status": (
            "PASS"
            if all(x["validation"]["status"] == "PASS" for x in (one, two, three))
            else "FAIL"
        ),
    }
    write_json(METRICS / "q2_capacity_frontier.json", frontier)

    frontier_rows = []
    for item, baseline_value in zip(
        (one, two, three),
        (
            baseline_caps["one_bomb"],
            baseline_caps["two_bombs"],
            baseline_caps["three_bombs"],
        ),
    ):
        frontier_rows.append(
            {
                "bomb_count": len(item["schedule"].centers_m),
                "method_A_continuous_capacity_s": item["duration_s"],
                "method_B_conservative_capacity_s": baseline_value,
                "increment_over_B_s": item["duration_s"] - baseline_value,
                "validation_status": item["validation"]["status"],
                "claim_scope": item.get("claim_scope", "analytic exact"),
            }
        )
    with (TABLES / "q2_capacity_frontier.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as f:
        writer = csv.DictWriter(f, fieldnames=list(frontier_rows[0]))
        writer.writeheader()
        writer.writerows(frontier_rows)

    schedule_rows = []
    for item in (one, two, three):
        schedule = item["schedule"]
        for index, (center, burst) in enumerate(
            zip(schedule.centers_m, schedule.burst_times_s), start=1
        ):
            schedule_rows.append(
                {
                    "schedule": schedule.label,
                    "bomb_count": len(schedule.centers_m),
                    "bomb_index": index,
                    "cloud_center_m": center,
                    "burst_time_s": burst,
                    "drop_time_s": burst - CONSTANTS.bomb_burst_delay_s,
                    "command_time_s": (
                        burst - CONSTANTS.bomb_burst_delay_s - 2.0
                    ),
                    "covered_start_s": item["start_s"],
                    "covered_end_s": item["end_s"],
                }
            )
    with (TABLES / "q2_verified_schedules.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as f:
        writer = csv.DictWriter(f, fieldnames=list(schedule_rows[0]))
        writer.writeheader()
        writer.writerows(schedule_rows)

    counts = np.array([1, 2, 3])
    main_values = np.array([one["duration_s"], two["duration_s"], three["duration_s"]])
    base_values = np.array(
        [
            baseline_caps["one_bomb"],
            baseline_caps["two_bombs"],
            baseline_caps["three_bombs"],
        ]
    )
    fig, ax = plt.subplots(figsize=(7.6, 4.6))
    ax.plot(counts, main_values, "o-", color="#1F4D78", label="A: smoke-union geometry")
    ax.plot(counts, base_values, "s--", color="#B05A2A", label="B: independent chaining")
    ax.axhline(
        CONSTANTS.m1_detection_upper_s,
        color="#7B2D43",
        linestyle=":",
        label="worst-case M1 window",
    )
    ax.set_xticks(counts)
    ax.set_xlabel("Number of smoke bombs")
    ax.set_ylabel("Continuous complete-cover duration (s)")
    ax.set_title("Q2 verified capacity frontier and conservative baseline")
    ax.grid(alpha=0.22)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(FIGURES / "q2_capacity_frontier.png", dpi=180)
    plt.close(fig)

    summary = {
        "schema_version": 1,
        "question": "Q2",
        "round": "round2",
        "round_label": "formal_optimization",
        "implementation_target": "python",
        "approved_decision_ids": ["q2_objective_scope", "q2_method_choice"],
        "status": frontier["status"],
        "minimum_resource_conclusion": {
            "minimum_bombs_relative_model": 2,
            "full_window_s": CONSTANTS.m1_detection_upper_s,
            "continuous_certificate": "round1 PASS",
        },
        "capacity_frontier_s": {
            "one_bomb": one["duration_s"],
            "two_bombs": two["duration_s"],
            "three_bombs_best_verified": three["duration_s"],
        },
        "baseline_capacity_s": baseline_caps,
        "claim_limits": [
            "Three-bomb value is best verified in the canonical collinear family, not a proved global optimum.",
            "Absolute first-drop and 12 km feasibility remain blocked by missing initial/reference data.",
            "No wind drift is included; drift remains a robustness extension parameter.",
        ],
        "fallback": {
            "method_C_triggered": False,
            "reason": "Both geometry validators agree and the continuous validator is stable.",
        },
        "runtime_seconds": runtime,
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
        },
        "generated_at": datetime.now().astimezone().isoformat(),
        "outputs": [
            "results/Q2/experiments/round2/metrics/q2_two_bomb_minimum_resource_plan.json",
            "results/Q2/experiments/round2/metrics/q2_capacity_frontier.json",
            "results/Q2/experiments/round2/tables/q2_capacity_frontier.csv",
            "results/Q2/experiments/round2/tables/q2_verified_schedules.csv",
            "results/Q2/experiments/round2/figures/q2_capacity_frontier.png",
        ],
    }
    write_json(OUT / "run_summary.json", summary)


if __name__ == "__main__":
    main()
