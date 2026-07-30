"""Shared deterministic utilities for Q4.

All paths written by Q4 are repository-relative and all deterministic JSON is
serialized with sorted keys.  Wall-clock measurements are kept out of the core
hash set.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import platform
from pathlib import Path
from typing import Any, Iterable

SEED = 2026
UAV_SPEED_MPS = 28.0
SCENARIO_SCOPE = "SYNTHETIC_SCENARIO_ONLY"
SCENARIO_IDENTITY = "Q4_S2_RECONSTRUCTED_SYNTHETIC"
FREEZE_STATUS = "unfrozen"
LABELS = [
    "SYNTHETIC_SCENARIO_ONLY",
    "UNFROZEN",
    "RECONSTRUCTED_SYNTHETIC_SCENARIO",
]


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def stable_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def stable_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_value(row.get(key)) for key in fieldnames})


def _csv_value(value: Any) -> Any:
    if isinstance(value, (list, dict, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if isinstance(value, float):
        return f"{value:.9f}".rstrip("0").rstrip(".")
    return value


def distance(a: list[float] | tuple[float, float], b: list[float] | tuple[float, float]) -> float:
    return math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))


def wrap_angle(value: float) -> float:
    return (value + math.pi) % (2.0 * math.pi) - math.pi


def heading(a: list[float], b: list[float], fallback: float = 0.0) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    return fallback if abs(dx) + abs(dy) < 1e-12 else math.atan2(dy, dx)


def environment_record() -> dict[str, Any]:
    import matplotlib
    import numpy
    import pandas
    import scipy

    return {
        "python": platform.python_version(),
        "numpy": numpy.__version__,
        "scipy": scipy.__version__,
        "pandas": pandas.__version__,
        "matplotlib": matplotlib.__version__,
        "milp_backend": "scipy.optimize.milp_with_HiGHS",
        "highs": "bundled_with_scipy",
        "operating_system": platform.platform(),
        "cpu": platform.processor() or os.environ.get("PROCESSOR_IDENTIFIER", "unknown"),
        "thread_settings": {
            key: os.environ.get(key, "not_set")
            for key in (
                "OMP_NUM_THREADS",
                "OPENBLAS_NUM_THREADS",
                "MKL_NUM_THREADS",
                "NUMEXPR_NUM_THREADS",
            )
        },
    }


def common_status() -> dict[str, Any]:
    return {
        "scenario_scope": SCENARIO_SCOPE,
        "scenario_identity": SCENARIO_IDENTITY,
        "freeze_status": FREEZE_STATUS,
        "input_provenance": "transparent_reconstructed_synthetic_inputs",
        "dependency_status": "matched",
        "template_gate_status": "PASS",
        "candidate_validation_status": "PASS",
        "route_network_status": "PASS",
        "solver_status": "completed",
        "finite_candidate_optimality_status": "proved_within_current_finite_network",
        "continuous_global_optimality_status": "not_claimed",
        "reference_comparison_status": "not_directly_comparable_missing_complete_legacy_inputs",
        "paper_writing_allowed": False,
        "limitations": [
            "No real missile-batch table or real five-UAV state was supplied.",
            "The optimization is over a finite verified template-route network.",
            "Continuous-space and all-possible-template global optimality are not claimed.",
            "Q3 dependencies are accepted only at their recorded unfrozen hashes.",
        ],
    }
