"""Thin entry point for the Q1 A/B/C global certificate."""

from __future__ import annotations

import json

from q1_certificates import build_global_certificate
from q1_common import write_json
from q1_outputs import ROUND2


def main() -> int:
    result = build_global_certificate(locked_at_8000m=True)
    write_json(ROUND2, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["certificate_status"] == "verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
