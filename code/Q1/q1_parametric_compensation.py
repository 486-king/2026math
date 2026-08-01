"""Thin entry point for the Q1 maximum continuous coverage family."""

from __future__ import annotations

import json

from q1_common import T_DETECT_LOWER, write_json
from q1_compensation import compensation_family, release_point_relation
from q1_outputs import ROUND3


def main() -> int:
    result = compensation_family(
        0.0,
        T_DETECT_LOWER,
        input_status="blocked_missing_scenario",
        executable_value="not_evaluated",
    )
    result["release_point_relation"] = release_point_relation()
    write_json(ROUND3, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
