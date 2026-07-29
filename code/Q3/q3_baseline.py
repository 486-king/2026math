from __future__ import annotations

from typing import Any

from q3_common import LABEL, event_feasibility_certificate


def run_baseline(scenario: dict[str, Any]) -> dict[str, Any]:
    certificate = event_feasibility_certificate(scenario)
    if certificate["full_window_defense_feasible"] is False:
        return {
            "method_id": "Q3-B",
            "role": "usable_baseline",
            "scenario_label": LABEL,
            "execution_status": "PASS",
            "input_status": "PASS",
            "feasibility_status": "FAIL",
            "certificate_status": "PASS",
            "construction_status": "NOT_RUN_STRUCTURAL_INFEASIBILITY",
            "route_and_event_decisions": None,
            "n_minus_one_metrics": None,
            "reason": "Front-middle-rear construction cannot remove the common command-to-burst delay.",
            "certificate": certificate,
        }
    raise NotImplementedError(
        "A pre-tasked scenario requires the downstream front-middle-rear constructor."
    )
