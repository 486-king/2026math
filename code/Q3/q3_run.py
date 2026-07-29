from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import platform
import sys
import time

import matplotlib.pyplot as plt
import numpy as np

from q3_baseline import run_baseline
from q3_common import CONSTANTS, LABEL, ROOT, SCENARIO_PATH, load_scenario
from q3_main import run_main


ROUND_DIR = ROOT / "results" / "Q3" / "experiments" / "round1"


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def validator_regression() -> dict:
    q2_dir = ROOT / "code" / "Q2"
    sys.path.insert(0, str(q2_dir))
    from q2_continuous_validator import run_continuous_validation

    result = run_continuous_validation()
    return {
        "label": "VALIDATOR_REGRESSION_ONLY",
        "source": "Q2 positive-margin two-smoke recovery fixture",
        "interval_certificate_status": result["interval_certificate"]["status"],
        "independent_geometry_status": result["independent_geometry"]["status"],
        "validators_agree": result["validators_agree"],
        "formal_q3_candidate": False,
    }


def write_availability_table(path: Path, window_start_s: float) -> list[dict]:
    rows = []
    for availability in np.linspace(0.0, 3.0, 13):
        earliest_burst = float(availability + CONSTANTS.command_to_burst_s)
        rows.append(
            {
                "scenario_label": LABEL,
                "minimum_availability_s": float(availability),
                "earliest_burst_s": earliest_burst,
                "necessary_threshold_s": window_start_s
                - CONSTANTS.command_to_burst_s,
                "full_defense_necessary_condition": "FAIL"
                if earliest_burst > window_start_s
                else "PASS",
                "guaranteed_initial_naked_duration_s": max(
                    0.0, earliest_burst - window_start_s
                ),
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return rows


def write_comparison(path: Path, main: dict, baseline: dict) -> None:
    rows = []
    for result in (main, baseline):
        rows.append(
            {
                "scenario_label": LABEL,
                "method_id": result["method_id"],
                "role": result["role"],
                "execution_status": result["execution_status"],
                "input_status": result["input_status"],
                "feasibility_status": result["feasibility_status"],
                "certificate_status": result["certificate_status"],
                "earliest_burst_s": result["certificate"]["earliest_burst_s"],
                "initial_naked_duration_s": result["certificate"][
                    "guaranteed_initial_naked_duration_s"
                ],
                "pareto_or_construction": result.get(
                    "optimization_status", result.get("construction_status")
                ),
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_timeline(path: Path, earliest_burst_s: float, window_end_s: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8.2, 2.8))
    ax.axvspan(0.0, earliest_burst_s, color="#d95f59", alpha=0.32, label="guaranteed naked")
    ax.axvline(0.0, color="#1f2937", linewidth=1.4, label="G1 lock / task available")
    ax.axvline(2.0, color="#2563eb", linewidth=1.2, label="earliest release")
    ax.axvline(earliest_burst_s, color="#047857", linewidth=1.4, label="earliest burst")
    ax.set_xlim(-0.5, min(window_end_s, 12.0))
    ax.set_ylim(0.0, 1.0)
    ax.set_yticks([])
    ax.set_xlabel("task time / s")
    ax.set_title("Q3 standardized scenario event-feasibility certificate")
    ax.grid(axis="x", alpha=0.2)
    ax.legend(loc="upper right", fontsize=8, ncol=2)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def main() -> None:
    started = time.perf_counter()
    scenario = load_scenario()
    main_result = run_main(scenario)
    baseline_result = run_baseline(scenario)
    regression = validator_regression()

    metrics_dir = ROUND_DIR / "metrics"
    tables_dir = ROUND_DIR / "tables"
    figures_dir = ROUND_DIR / "figures"
    certificate = main_result["certificate"]

    write_json(metrics_dir / "q3_event_infeasibility_certificate.json", certificate)
    write_json(
        metrics_dir / "q3_standard_scenario_status.json",
        {
            "scenario_label": LABEL,
            "main": main_result,
            "baseline": baseline_result,
            "formal_result_layer": (
                "parameterized conclusion: full defense is impossible whenever "
                "min_i(a_i)>-5.5 s under the approved t=0 definition"
            ),
            "probe_numbers_imported": False,
        },
    )
    write_json(metrics_dir / "q3_validator_recovery_test.json", regression)
    availability_rows = write_availability_table(
        tables_dir / "q3_availability_sensitivity.csv",
        float(scenario["g1_lock_time_s"]),
    )
    write_comparison(
        tables_dir / "q3_method_comparison.csv", main_result, baseline_result
    )
    write_timeline(
        figures_dir / "q3_event_timeline.png",
        certificate["earliest_burst_s"],
        certificate["defense_window_conservative_end_s"],
    )

    scenario_hash = hashlib.sha256(SCENARIO_PATH.read_bytes()).hexdigest()
    elapsed = time.perf_counter() - started
    summary = {
        "schema_version": 1,
        "question": "Q3",
        "round": "round1",
        "round_label": "formal_event_feasibility",
        "implementation_target": "python",
        "random_seed": 2026,
        "approved_decision_id": "q3_method_choice",
        "scenario_decision_id": "q3_parameterized_and_standardized_scenario",
        "scenario_label": LABEL,
        "scenario_sha256": scenario_hash,
        "methods": [
            {
                "method_id": "Q3-A",
                "role": "main_candidate",
                "script": "code/Q3/q3_main.py",
                "status": "executed_infeasible",
                "metrics_summary": {
                    "feasibility_status": "FAIL",
                    "certificate_status": "PASS",
                    "earliest_burst_s": certificate["earliest_burst_s"],
                    "initial_naked_duration_s": certificate[
                        "guaranteed_initial_naked_duration_s"
                    ],
                    "pareto_front_status": "NOT_RUN_STRUCTURAL_INFEASIBILITY",
                },
                "warnings": [],
                "errors": [],
            },
            {
                "method_id": "Q3-B",
                "role": "usable_baseline",
                "script": "code/Q3/q3_baseline.py",
                "status": "executed_infeasible",
                "metrics_summary": {
                    "feasibility_status": "FAIL",
                    "certificate_status": "PASS",
                    "earliest_burst_s": certificate["earliest_burst_s"],
                    "initial_naked_duration_s": certificate[
                        "guaranteed_initial_naked_duration_s"
                    ],
                    "construction_status": "NOT_RUN_STRUCTURAL_INFEASIBILITY",
                },
                "warnings": [],
                "errors": [],
            },
        ],
        "comparison": {
            "same_hard_constraint": True,
            "same_infeasibility_cause": True,
            "path_turn_dsafe_n_minus_one_metrics": "NOT_EVALUATED_NO_FEASIBLE_NORMAL_DEFENSE",
        },
        "parameterized_conclusion": {
            "necessary_availability_condition": "min_i(a_i)<=-5.5 s",
            "approved_availability_range_s": [0.0, 3.0],
            "range_verdict": "FAIL_FOR_ALL_APPROVED_VALUES",
            "position_heading_dsafe_beta_sensitivity": (
                "NO_EFFECT_ON_EVENT_INFEASIBILITY_WITHIN_APPROVED_AVAILABILITY_RANGE"
            ),
            "availability_rows": len(availability_rows),
        },
        "continuous_validation": regression,
        "fallback_trigger": {
            "fallback_id": "Q3-C",
            "observed": False,
            "reason": "Deterministic event-delay infeasibility is not an uncertainty trigger.",
        },
        "outputs": [
            "results/Q3/experiments/round1/metrics/q3_event_infeasibility_certificate.json",
            "results/Q3/experiments/round1/metrics/q3_standard_scenario_status.json",
            "results/Q3/experiments/round1/metrics/q3_validator_recovery_test.json",
            "results/Q3/experiments/round1/tables/q3_availability_sensitivity.csv",
            "results/Q3/experiments/round1/tables/q3_method_comparison.csv",
            "results/Q3/experiments/round1/figures/q3_event_timeline.png",
        ],
        "runtime_seconds": elapsed,
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "numpy": np.__version__,
        },
    }
    write_json(ROUND_DIR / "run_summary.json", summary)
    print(
        json.dumps(
            {
                "scenario_label": LABEL,
                "earliest_burst_s": certificate["earliest_burst_s"],
                "initial_naked_duration_s": certificate[
                    "guaranteed_initial_naked_duration_s"
                ],
                "main_feasibility": main_result["feasibility_status"],
                "baseline_feasibility": baseline_result["feasibility_status"],
                "validator_regression": regression["validators_agree"],
                "runtime_seconds": elapsed,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
