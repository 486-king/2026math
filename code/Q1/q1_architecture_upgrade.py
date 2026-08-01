"""Thin entry point for the complete Q1 architecture artifact set."""

from __future__ import annotations

import json

from q1_outputs import ROUND4, finalize_production_run, generate_core_outputs


def main() -> int:
    context = generate_core_outputs()
    finalize_production_run(context)
    print(json.dumps(json.loads(ROUND4.read_text(encoding="utf-8")), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
