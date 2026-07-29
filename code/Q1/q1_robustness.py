"""Thin entry point for structural-gap sensitivity."""

from __future__ import annotations

import argparse
import json

from q1_common import write_json
from q1_outputs import ROBUSTNESS_PATH
from q1_robustness_core import gap_meaning, robustness_summary, structural_gap


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--R-c", type=float)
    parser.add_argument("--R-s", type=float)
    parser.add_argument("--V-s", type=float)
    parser.add_argument("--V-m", type=float)
    parser.add_argument("--D-max", type=float)
    args = parser.parse_args()
    if any(value is not None for value in vars(args).values()):
        kwargs = {key.replace("_", "-"): value for key, value in vars(args).items() if value is not None}
        mapped = {
            {"R-c": "R_c", "R-s": "R_s", "V-s": "V_s", "V-m": "V_m", "D-max": "D_max"}[key]: value
            for key, value in kwargs.items()
        }
        gap = structural_gap(**mapped)
        result = {
            "exploratory": True,
            "explicit_command_line_parameters": mapped,
            "G_s": gap,
            "meaning": gap_meaning(gap),
        }
    else:
        result = robustness_summary()
    write_json(ROBUSTNESS_PATH, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
