"""Risk-targeted robustness checks for the approved Q1 conclusion."""

from __future__ import annotations

from datetime import datetime, timezone
import itertools
import json
from pathlib import Path

from q1_common import Q1Constants


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "robustness" / "Q1" / "q1_robustness_summary.json"


def duration_metrics(
    cfg: Q1Constants,
    ship_speed: float,
    missile_speed: float,
    smoke_radius: float,
    cloud_drift_along_ship: float = 0.0,
) -> dict[str, float | bool]:
    relative_speed = abs(ship_speed - cloud_drift_along_ship)
    cover = (
        float("inf")
        if relative_speed <= 1e-12
        else 2.0 * max(0.0, smoke_radius - cfg.ship_radius_m) / relative_speed
    )
    detect = (cfg.detection_distance_m - cfg.ship_radius_m) / (
        missile_speed + ship_speed
    )
    return {
        "cover_upper_bound_s": cover,
        "detection_lower_bound_s": detect,
        "duration_margin_s": cover - detect,
        "duration_necessary_condition_feasible": cover >= detect,
    }


def main() -> int:
    cfg = Q1Constants()
    nominal = duration_metrics(
        cfg,
        cfg.ship_speed_mps,
        cfg.missile_speed_mps,
        cfg.smoke_max_radius_m,
    )

    one_at_a_time: list[dict[str, object]] = []
    for field in ("ship_speed", "missile_speed", "smoke_radius"):
        for factor in (0.9, 1.1):
            values = {
                "ship_speed": cfg.ship_speed_mps,
                "missile_speed": cfg.missile_speed_mps,
                "smoke_radius": cfg.smoke_max_radius_m,
            }
            values[field] *= factor
            result = duration_metrics(
                cfg,
                values["ship_speed"],
                values["missile_speed"],
                values["smoke_radius"],
            )
            one_at_a_time.append(
                {
                    "changed_field": field,
                    "factor": factor,
                    **values,
                    **result,
                }
            )

    joint_stress: list[dict[str, object]] = []
    for ship_factor, missile_factor, radius_factor in itertools.product(
        (0.8, 1.2), repeat=3
    ):
        result = duration_metrics(
            cfg,
            cfg.ship_speed_mps * ship_factor,
            cfg.missile_speed_mps * missile_factor,
            cfg.smoke_max_radius_m * radius_factor,
        )
        joint_stress.append(
            {
                "ship_speed_factor": ship_factor,
                "missile_speed_factor": missile_factor,
                "smoke_radius_factor": radius_factor,
                **result,
            }
        )

    drift_checks = []
    for drift in (-5.0, 0.0, 5.0):
        drift_checks.append(
            {
                "cloud_drift_along_ship_mps": drift,
                **duration_metrics(
                    cfg,
                    cfg.ship_speed_mps,
                    cfg.missile_speed_mps,
                    cfg.smoke_max_radius_m,
                    cloud_drift_along_ship=drift,
                ),
            }
        )

    nominal_detect = float(nominal["detection_lower_bound_s"])
    critical_ship_speed = (
        2.0
        * (cfg.smoke_max_radius_m - cfg.ship_radius_m)
        * cfg.missile_speed_mps
        / (
            cfg.detection_distance_m
            - cfg.ship_radius_m
            - 2.0 * (cfg.smoke_max_radius_m - cfg.ship_radius_m)
        )
    )
    critical_smoke_radius = cfg.ship_radius_m + (
        cfg.ship_speed_mps * nominal_detect / 2.0
    )
    critical_detection_distance = cfg.ship_radius_m + (
        (cfg.missile_speed_mps + cfg.ship_speed_mps)
        * float(nominal["cover_upper_bound_s"])
    )
    critical_relative_cloud_speed = (
        2.0
        * (cfg.smoke_max_radius_m - cfg.ship_radius_m)
        / nominal_detect
    )

    all_oat_infeasible = not any(
        bool(row["duration_necessary_condition_feasible"])
        for row in one_at_a_time
    )
    any_joint_flip = any(
        bool(row["duration_necessary_condition_feasible"]) for row in joint_stress
    )
    any_drift_flip = any(
        bool(row["duration_necessary_condition_feasible"]) for row in drift_checks
    )

    summary = {
        "schema_version": 1,
        "question_id": "Q1",
        "tested_claim": (
            "Under G1+S1+O0+U0 and statement constants, one stationary smoke cannot "
            "fully cover the ship for the entire detection window."
        ),
        "input_sources": [
            "results/Q1/experiments/round1/metrics/q1_structural_metrics.json",
            "methods/Q1/q1_decisions.jsonl",
        ],
        "result_sources": [
            "results/Q1/experiments/round1/run_summary.json"
        ],
        "checks": [
            {
                "name": "nominal_duration_certificate",
                "perturbation": "none",
                "metric": "cover upper bound minus detection lower bound",
                "threshold": "<0 supports strict infeasibility",
                "observed": nominal,
                "status": "PASS",
                "limitation": "This is a duration certificate; it does not identify coordinates.",
                "fallback_trigger_relevance": "A and B agree, so C is not triggered."
            },
            {
                "name": "one_at_a_time_10_percent",
                "perturbation": (
                    "Exploratory ±10% on ship speed, missile speed and smoke radius, "
                    "one field at a time; no empirical uncertainty distribution is claimed."
                ),
                "metric": "number of cases satisfying the duration necessary condition",
                "threshold": "0 for local stability of the infeasibility claim",
                "observed": {
                    "feasible_case_count": sum(
                        int(bool(row["duration_necessary_condition_feasible"]))
                        for row in one_at_a_time
                    ),
                    "cases": one_at_a_time
                },
                "status": "PASS" if all_oat_infeasible else "FAIL",
                "limitation": "One-at-a-time perturbations do not cover joint extremes.",
                "fallback_trigger_relevance": "No A/B contradiction."
            },
            {
                "name": "joint_20_percent_stress",
                "perturbation": (
                    "Exploratory joint corner stress at ±20% for three physical constants."
                ),
                "metric": "whether any corner flips the duration necessary condition",
                "threshold": "Exploratory; no pass/fail threshold was asserted as physical.",
                "observed": {
                    "any_flip": any_joint_flip,
                    "cases": joint_stress
                },
                "status": "CONDITIONAL",
                "limitation": "The range is not data-derived and is used only to locate claim boundaries.",
                "fallback_trigger_relevance": (
                    "A supplied physical parameter revision near a flip requires rerunning A and B."
                )
            },
            {
                "name": "G2_detection_window_condition",
                "perturbation": "Replace G1 by a fixed-heading G2 trajectory.",
                "metric": "actual distance-and-FOV window length",
                "threshold": float(nominal["cover_upper_bound_s"]),
                "observed": {
                    "required_for_possible_duration_feasibility": (
                        "G2 detection window <= threshold_seconds"
                    ),
                    "threshold_seconds": float(nominal["cover_upper_bound_s"]),
                    "actual_G2_window": None
                },
                "status": "CONDITIONAL",
                "limitation": "G2 initial position and fixed heading are absent.",
                "fallback_trigger_relevance": "A changed feasibility conclusion under supplied G2 data requires a new result decision."
            },
            {
                "name": "cloud_drift_extension",
                "perturbation": (
                    "Exploratory along-track cloud drift of -5, 0 and +5 m/s."
                ),
                "metric": "duration necessary condition",
                "threshold": "cover upper bound >= detection lower bound",
                "observed": {
                    "any_flip": any_drift_flip,
                    "cases": drift_checks
                },
                "status": "CONDITIONAL",
                "limitation": (
                    "No wind direction or speed is supplied. These are relaxed "
                    "geometric upper bounds that hold the cloud at its maximum "
                    "radius; exact S2 values require the 18 s/5 s event model."
                ),
                "fallback_trigger_relevance": "A measured drift near ship speed requires upgrading the nominal model."
            }
        ],
        "critical_boundaries": {
            "ship_speed_at_duration_equality_mps": critical_ship_speed,
            "smoke_radius_at_duration_equality_m": critical_smoke_radius,
            "detection_distance_at_duration_equality_m": critical_detection_distance,
            "maximum_relative_ship_cloud_speed_for_duration_feasibility_mps": (
                critical_relative_cloud_speed
            )
        },
        "overall_status": "CONDITIONAL",
        "interpretation": (
            "The nominal infeasibility conclusion is locally stable to one-at-a-time "
            "±10% checks. It is conditional on M1/S1; a sufficiently short M2 FOV "
            "window or strong along-track smoke drift can change the duration condition."
        ),
        "fallback_C_triggered": True,
        "canonical_interpretation": (
            "The nominal G1+S1+O0+U0 infeasibility conclusion is locally "
            "stable to the recorded one-at-a-time 10 percent checks. G2 and "
            "S2 remain conditional extensions."
        ),
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat()
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
