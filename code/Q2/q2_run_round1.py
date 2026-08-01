"""Run the canonical two-bomb validation and print its gate result."""

from __future__ import annotations

import json

from q2_two_bomb_plan import broken_plan_gate, validate_canonical_two_bomb_plan


def main() -> int:
    validation = validate_canonical_two_bomb_plan()
    broken = broken_plan_gate()
    payload = {
        "canonical_certificate_status": validation["certificate_status"],
        "canonical_box_count": validation["continuous_certificate"][
            "canonical_box_count"
        ],
        "broken_plan_gate_passed": broken["false_positive_gate_passed"],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if all(
        (
            validation["certificate_status"] == "verified",
            broken["false_positive_gate_passed"],
        )
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
