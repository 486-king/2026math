"""One-click production entry point for Q1.

The production runner intentionally has no pytest or tests-directory dependency.
Formal tests are executed separately before release and summarized in
code/Q1/reviews/q1_final_validation.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from q1_outputs import finalize_production_run, generate_core_outputs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate and validate all Q1 production artifacts.")
    parser.add_argument("--all", action="store_true", help="Generate all Q1 production artifacts.")
    parser.add_argument("--scenario", type=Path, help="Optional complete scenario JSON.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        context = generate_core_outputs(args.scenario)
        result = finalize_production_run(context)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"Q1 production run failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
