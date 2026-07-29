"""Shared constants, event semantics, source-document checks, and utilities."""

from __future__ import annotations

import hashlib
import json
import math
import platform
import re
import sys
import zipfile
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree as ET

MODULE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = (
    MODULE_DIR.parents[1]
    if MODULE_DIR.name == "Q1" and MODULE_DIR.parent.name == "code"
    else MODULE_DIR.parent
)
PROBLEM_DOC_CANDIDATES = (
    "B题：舰船烟幕遮蔽干扰优化(4).docx",
    "B题：舰船烟幕遮蔽干扰优化.docx",
)
GUIDE_DOC_NAME = "Q1_编程手与论文手分工.docx"

EXPECTED_SOURCE_HASHES = {
    "B题：舰船烟幕遮蔽干扰优化.docx": (
        "374a3a91f82fdd2475859258ca4e73902e6706e620920eedab16121ee85e4bfa"
    ),
    GUIDE_DOC_NAME: (
        "578aec2867cbdf32fbb2e5a64d06698fa0896eb1e5d5429a70e2f0df20fdffe5"
    ),
}

KNOT_TO_MPS = 0.514
V_S = 15.0 * KNOT_TO_MPS
R_S = 80.0
V_U = 28.0
R_U_MAX = 12000.0
UAV_PAYLOAD_MAX = 3
TAU_RESPONSE = 2.0
MIN_DROP_INTERVAL = 1.0
TAU_BURST = 3.5
R_C = 120.0
TAU_HOLD = 18.0
TAU_DECAY = 5.0
SMOKE_LIFETIME = TAU_HOLD + TAU_DECAY
V_M = 320.0
D_MAX = 8000.0
FOV_HALF_ANGLE_DEG = 15.0
INERTIAL_DISPLACEMENT = V_U * TAU_BURST

h = (R_C - R_S) / V_S
T_STRUCTURAL_MAX = 2.0 * h
T_DETECT_LOWER = (D_MAX - R_S) / (V_M + V_S)
T_NAKED_LOWER = T_DETECT_LOWER - T_STRUCTURAL_MAX
BURST_INTERVAL_WIDTH = TAU_HOLD - T_STRUCTURAL_MAX

STATUS_SEMANTICS = {
    "execution_status": ["completed", "failed"],
    "input_status": [
        "complete",
        "blocked_missing_scenario",
        "blocked_missing_fields",
        "blocked_ambiguous_interpretation",
    ],
    "feasibility_status": [
        "full_window_structurally_infeasible",
        "executable_feasible",
        "executable_infeasible",
        "not_evaluated",
    ],
    "certificate_status": ["verified", "conditional", "failed", "not_evaluated"],
}


@dataclass(frozen=True)
class ParameterRecord:
    name: str
    value: float | int | str
    unit: str
    source_type: str
    source_file: str
    note: str = ""


PROBLEM_SOURCE = "B题：舰船烟幕遮蔽干扰优化.docx"
GUIDE_SOURCE = GUIDE_DOC_NAME
PARAMETER_RECORDS = (
    ParameterRecord("ship_speed_knots", 15.0, "kn", "problem_fact", PROBLEM_SOURCE),
    ParameterRecord("knot_conversion", KNOT_TO_MPS, "m/s per kn", "problem_fact", PROBLEM_SOURCE),
    ParameterRecord("V_s", V_S, "m/s", "derived_quantity", PROBLEM_SOURCE, "15×0.514"),
    ParameterRecord("R_s", R_S, "m", "problem_fact", PROBLEM_SOURCE),
    ParameterRecord("V_u", V_U, "m/s", "problem_fact", PROBLEM_SOURCE),
    ParameterRecord("R_u_max", R_U_MAX, "m", "problem_fact", PROBLEM_SOURCE),
    ParameterRecord("uav_payload_max", UAV_PAYLOAD_MAX, "round", "problem_fact", PROBLEM_SOURCE),
    ParameterRecord("tau_response", TAU_RESPONSE, "s", "adopted_interpretation", GUIDE_SOURCE, "command to actual release"),
    ParameterRecord("minimum_same_uav_release_interval", MIN_DROP_INTERVAL, "s", "problem_fact", PROBLEM_SOURCE),
    ParameterRecord("tau_burst", TAU_BURST, "s", "problem_fact", PROBLEM_SOURCE),
    ParameterRecord("R_c", R_C, "m", "problem_fact", PROBLEM_SOURCE),
    ParameterRecord("tau_hold", TAU_HOLD, "s", "problem_fact", PROBLEM_SOURCE),
    ParameterRecord("tau_decay", TAU_DECAY, "s", "problem_fact", PROBLEM_SOURCE),
    ParameterRecord("smoke_lifetime", SMOKE_LIFETIME, "s", "derived_quantity", PROBLEM_SOURCE),
    ParameterRecord("V_m", V_M, "m/s", "problem_fact", PROBLEM_SOURCE),
    ParameterRecord("D_max", D_MAX, "m", "problem_fact", PROBLEM_SOURCE),
    ParameterRecord("fov_half_angle", FOV_HALF_ANGLE_DEG, "degree", "problem_fact", PROBLEM_SOURCE),
    ParameterRecord(
        "inertial_displacement",
        INERTIAL_DISPLACEMENT,
        "m",
        "derived_quantity",
        GUIDE_SOURCE,
        "under S1 inertial-flight assumption: V_u×tau_burst",
    ),
    ParameterRecord(
        "operating_radius_interpretation",
        "distance from UAV initial launch reference point",
        "text",
        "adopted_interpretation",
        GUIDE_SOURCE,
    ),
    ParameterRecord(
        "turning_radius",
        "not_provided",
        "m",
        "missing_input",
        PROBLEM_SOURCE,
    ),
    ParameterRecord(
        "absolute_initial_states",
        "not_provided",
        "mixed",
        "missing_input",
        PROBLEM_SOURCE,
    ),
)


def locate_source_documents(
    root: Path = PROJECT_ROOT,
    *,
    required: bool = True,
) -> dict[str, Path]:
    problem = next((root / n for n in PROBLEM_DOC_CANDIDATES if (root / n).is_file()), None)
    guide = root / GUIDE_DOC_NAME
    if problem is None and required:
        raise FileNotFoundError(f"None of the problem documents exists: {PROBLEM_DOC_CANDIDATES}")
    if not guide.is_file() and required:
        raise FileNotFoundError(f"Missing guide document: {GUIDE_DOC_NAME}")
    result: dict[str, Path] = {}
    if problem is not None:
        result["problem"] = problem
    if guide.is_file():
        result["guide"] = guide
    return result


<<<<<<< HEAD
def single_smoke_margin(
    ship_center_m: np.ndarray | tuple[float, float],
    smoke_center_m: np.ndarray | tuple[float, float],
    smoke_radius_m: float,
    ship_radius_m: float,
) -> float:
    """Exact complete-cover margin for one circular smoke cloud.

    Positive is safe, zero is tangent, and negative means that some part of
    the ship disk is exposed.
    """
    ship = np.asarray(ship_center_m, dtype=float)
    smoke = np.asarray(smoke_center_m, dtype=float)
    return float(
        smoke_radius_m
        - ship_radius_m
        - np.linalg.norm(ship - smoke)
    )


def coverage_defect(
    ship_center_m: np.ndarray | tuple[float, float],
    smoke_centers_m: np.ndarray,
    smoke_radii_m: np.ndarray,
    ship_radius_m: float,
) -> float:
    """Unified coverage-defect interface, exact for the Q1 single-smoke case.

    The mathematical cross-question definition is

        Delta(t) = max_{x in D_ship(t)} min_j (||x-c_j||-r_j).

    Q1 contains exactly one active smoke cloud, for which the expression has
    the closed form ||s-c||+R_s-r.  Multi-smoke callers must use the certified
    Q2 union-geometry kernel rather than silently replacing the maximization
    with a finite grid.
    """
    centers = np.asarray(smoke_centers_m, dtype=float)
    radii = np.asarray(smoke_radii_m, dtype=float)
    if centers.ndim != 2 or centers.shape[1] != 2:
        raise ValueError("smoke_centers_m must have shape (n,2)")
    if radii.shape != (centers.shape[0],):
        raise ValueError("smoke_radii_m must have shape (n,)")
    if centers.shape[0] != 1:
        raise NotImplementedError(
            "Q1 coverage_defect is exact only for one smoke; "
            "use code/Q2/q2_union_optimizer.py for certified multi-smoke geometry"
        )
    return float(
        np.linalg.norm(np.asarray(ship_center_m, dtype=float) - centers[0])
        + ship_radius_m
        - radii[0]
    )


def command_release_burst_times(
    command_time_s: float,
    cfg: Q1Constants,
) -> dict[str, float]:
    """Primary interpretation of the statement's 2 s response delay.

    This timing semantics is human-approved in
    q1_teammate_review_integration; the statement supplies the 2 s constant
    but does not explicitly name its two endpoint events.
    """
    release = command_time_s + cfg.response_delay_s
    burst = release + cfg.bomb_burst_delay_s
    return {
        "command_time_s": float(command_time_s),
        "release_time_s": float(release),
        "burst_time_s": float(burst),
    }


def structural_bounds(cfg: Q1Constants) -> dict[str, Any]:
    """Scenario-independent necessary bounds for G1/S1/O0/U0."""
    cover_margin_m = cfg.smoke_max_radius_m - cfg.ship_radius_m
    if cover_margin_m < 0:
        stationary_cover_s = 0.0
    else:
        stationary_cover_s = 2.0 * cover_margin_m / cfg.ship_speed_mps
=======
def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
>>>>>>> 05b4caca0369d310133e03bd82ba235ad075b5d3


def source_hashes(root: Path = PROJECT_ROOT, *, required: bool = True) -> dict[str, str]:
    return {
<<<<<<< HEAD
        "model_scope": (
            "G1 pure pursuit + S1 stationary smoke + O0 complete-disk "
            "coverage + U0 nominal deterministic assumptions"
        ),
        "cover_margin_at_max_radius_m": cover_margin_m,
        "stationary_smoke_max_continuous_full_cover_s": stationary_cover_s,
        "comoving_smoke_relaxation_upper_bound_s": comoving_relaxation_s,
        "m1_detection_window_lower_bound_s": min_detection_s,
        "m1_detection_window_upper_bound_s": max_detection_s,
        "strict_full_window_feasible_by_duration_necessary_condition": (
            stationary_cover_s >= min_detection_s
        ),
        "minimum_naked_time_lower_bound_s": naked_lower_bound_s,
        "unique_coordinate_identifiable": False,
        "proof_notes": [
            "For a fixed smoke center, complete cover implies the ship center stays within "
            "R_c-R_s=40 m of that center. A line moving at V_s can remain in this disk for "
            "at most 2(R_c-R_s)/V_s.",
            "Under pure pursuit, range rate is V_s*cos(phi)-V_m and is no smaller in "
            "magnitude than V_m-V_s and no larger than V_m+V_s. The shortest possible "
            "8000 m-to-contact window uses V_m+V_s. This window is active only under "
            "the explicit standard-scenario premise that lock has already been acquired "
            "at 8000 m; G1 then keeps the line-of-sight offset equal to zero.",
            "Because the maximum cover upper bound is shorter than the minimum detection "
            "window, strict full-window cover is impossible before UAV reachability is considered.",
        ],
=======
        p.name: sha256_file(p)
        for p in locate_source_documents(root, required=required).values()
>>>>>>> 05b4caca0369d310133e03bd82ba235ad075b5d3
    }


def source_hashes_match_expected(root: Path = PROJECT_ROOT) -> bool:
    observed = source_hashes(root)
    return observed == EXPECTED_SOURCE_HASHES


def read_docx_text(path: Path) -> str:
    """Read paragraphs directly from OOXML without modifying the Word file."""
    with zipfile.ZipFile(path) as archive:
        xml_data = archive.read("word/document.xml")
    root = ET.fromstring(xml_data)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs = []
    for paragraph in root.findall(".//w:p", ns):
        text = "".join(node.text or "" for node in paragraph.findall(".//w:t", ns))
        if text:
            paragraphs.append(text)
    return "\n".join(paragraphs)


def source_document_metadata(
    root: Path = PROJECT_ROOT,
    *,
    required: bool = True,
) -> dict[str, Any]:
    docs = locate_source_documents(root, required=required)
    result: dict[str, Any] = {}
    for role, path in docs.items():
        text = read_docx_text(path)
        result[role] = {
            "filename": path.name,
            "sha256": sha256_file(path),
            "character_count": len(text),
            "nonempty_paragraph_count": len(text.splitlines()),
            "title": text.splitlines()[0] if text else "",
            "read_method": "read_only_docx_ooxml",
        }
    return result


def command_to_release(t_cmd: float) -> float:
    return float(t_cmd) + TAU_RESPONSE


def release_to_burst(t_d: float) -> float:
    return float(t_d) + TAU_BURST


def command_to_burst(t_cmd: float) -> float:
    return release_to_burst(command_to_release(t_cmd))


def burst_to_release(t_b: float) -> float:
    return float(t_b) - TAU_BURST


def burst_to_command(t_b: float) -> float:
    return burst_to_release(t_b) - TAU_RESPONSE


def legacy_release_alias(t_d: float) -> dict[str, Any]:
    return {
        "drop_time": float(t_d),
        "semantic": "deprecated legacy alias of release time t_d",
    }


def smoke_radius_from_age(age: float) -> float:
    age = float(age)
    if age < 0.0:
        return 0.0
    if age <= TAU_HOLD:
        return R_C
    if age <= SMOKE_LIFETIME:
        return R_C * (SMOKE_LIFETIME - age) / TAU_DECAY
    return 0.0


def smoke_radius(t: float, t_b: float) -> float:
    return smoke_radius_from_age(float(t) - float(t_b))


def parameter_dict() -> dict[str, Any]:
    return {
        item.name: {
            "value": item.value,
            "unit": item.unit,
            "source_type": item.source_type,
            "source_file": item.source_file,
            "note": item.note,
        }
        for item in PARAMETER_RECORDS
    }


def dependency_versions() -> dict[str, str]:
    versions = {
        "python": sys.version.split()[0],
        "operating_system": platform.platform(),
    }
    for label, package in (
        ("numpy", "numpy"),
        ("scipy", "scipy"),
        ("pandas", "pandas"),
        ("matplotlib", "matplotlib"),
        ("pytest", "pytest"),
        ("python_docx", "python-docx"),
    ):
        try:
            versions[label] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[label] = "not_installed"
    return versions


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def relative_posix(path: Path, root: Path = PROJECT_ROOT) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def official_text_files(root: Path = PROJECT_ROOT) -> Iterable[Path]:
    suffixes = {".py", ".json", ".csv", ".md", ".txt"}
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in suffixes:
            if any(part.startswith(".") for part in path.relative_to(root).parts):
                continue
            yield path


def contains_personal_absolute_path(text: str) -> bool:
    return bool(re.search(r"[A-Za-z]:\\Users\\\d+", text, re.IGNORECASE))


def assert_core_constants() -> None:
    expected = {
        "h": 5.188067444876784,
        "T_structural_max": 10.376134889753567,
        "T_detect_lower": 24.167709255134113,
        "T_naked_lower": 13.791574365380546,
        "burst_interval_width": 7.623865110246433,
    }
    observed = {
        "h": h,
        "T_structural_max": T_STRUCTURAL_MAX,
        "T_detect_lower": T_DETECT_LOWER,
        "T_naked_lower": T_NAKED_LOWER,
        "burst_interval_width": BURST_INTERVAL_WIDTH,
    }
    for key, value in observed.items():
        if not math.isclose(value, expected[key], rel_tol=0.0, abs_tol=2e-14):
            raise RuntimeError(f"Core constant mismatch for {key}: {value} vs {expected[key]}")
