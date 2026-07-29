from __future__ import annotations

from typing import Any

from q3_common import LABEL, event_feasibility_certificate


def run_main(scenario: dict[str, Any]) -> dict[str, Any]:
    certificate = event_feasibility_certificate(scenario)
    if certificate["full_window_defense_feasible"] is False:
        return {
            "method_id": "Q3-A",
            "role": "main_candidate",
            "scenario_label": LABEL,
            "execution_status": "PASS",
            "input_status": "PASS",
            "feasibility_status": "FAIL",
            "certificate_status": "PASS",
            "optimization_status": "NOT_RUN_STRUCTURAL_INFEASIBILITY",
            "pareto_front": None,
            "representative_solution": None,
            "d_safe_feasible_interval_m": None,
            "route_and_event_decisions": None,
            "n_minus_one_metrics": None,
            "reason": "The continuous initial naked interval violates the hard defense constraint before any smoke can exist.",
            "certificate": certificate,
        }
    raise NotImplementedError(
        "The approved standard scenario reaches only the event gate. "
        "A pre-tasked scenario requires the downstream Pareto engine."
    )
