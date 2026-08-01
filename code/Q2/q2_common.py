"""Q2 single-source parameters, event semantics, source checks, and I/O."""

from __future__ import annotations

import hashlib
import json
import math
import platform
import re
import shutil
import sys
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime
from importlib import metadata
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

MODULE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = MODULE_DIR.parents[1]

PROBLEM_DOC_NAME = "B题：舰船烟幕遮蔽干扰优化.docx"
Q2_GUIDE_DOC_NAME = "Q2_编程手与论文手工作文档.docx"
EXPECTED_SOURCE_HASHES = {
    PROBLEM_DOC_NAME: "e891f635bcb4182517c166d12f1e4f3d05c77e9c18b27a14302c7561f7f2a638",
    Q2_GUIDE_DOC_NAME: "b9cae288150a7a586360982ad11ebb359a3ff8de6679c7deb29e39c49d005631",
}

MODEL_SCOPE = {
    "missile_model": "G1_pure_pursuit_constant_speed",
    "comparison_missile_model": "G2_fixed_heading",
    "smoke_motion_model": "S1_inertial_before_burst_fixed_center_after_burst",
    "coverage_model": "O0_complete_two_dimensional_ship_disk",
    "nominal_drift_model": "U0_no_wind_drift",
    "main_method_name_zh": "共线烟幕圆盘并集连续优化模型",
}


@dataclass(frozen=True)
class Q2Parameters:
    knot_to_mps: float = 0.514
    ship_speed_mps: float = 15.0 * 0.514
    ship_radius_m: float = 80.0
    missile_speed_mps: float = 320.0
    detection_distance_m: float = 8000.0
    fov_half_angle_deg: float = 15.0
    uav_speed_mps: float = 28.0
    uav_operating_radius_m: float = 12000.0
    command_to_release_delay_s: float = 2.0
    minimum_release_interval_s: float = 1.0
    uav_payload_max: int = 3
    smoke_max_radius_m: float = 120.0
    release_to_burst_delay_s: float = 3.5
    smoke_hold_s: float = 18.0
    smoke_decay_s: float = 5.0

    @property
    def smoke_lifetime_s(self) -> float:
        return self.smoke_hold_s + self.smoke_decay_s

    @property
    def inertial_displacement_m(self) -> float:
        return self.uav_speed_mps * self.release_to_burst_delay_s

    @property
    def single_smoke_half_duration_s(self) -> float:
        return (self.smoke_max_radius_m - self.ship_radius_m) / self.ship_speed_mps

    @property
    def single_smoke_max_duration_s(self) -> float:
        return 2.0 * self.single_smoke_half_duration_s

    @property
    def detect_lower_s(self) -> float:
        return (self.detection_distance_m - self.ship_radius_m) / (
            self.missile_speed_mps + self.ship_speed_mps
        )

    @property
    def detect_worst_upper_s(self) -> float:
        return (self.detection_distance_m - self.ship_radius_m) / (
            self.missile_speed_mps - self.ship_speed_mps
        )


PARAMS = Q2Parameters()


@dataclass(frozen=True)
class SmokePlan:
    smoke_id: str
    center_m: float
    t_cmd_s: float

    @property
    def t_d_s(self) -> float:
        return self.t_cmd_s + PARAMS.command_to_release_delay_s

    @property
    def t_b_s(self) -> float:
        return self.t_d_s + PARAMS.release_to_burst_delay_s

    @property
    def pre_lock_mission(self) -> bool:
        return min(self.t_cmd_s, self.t_d_s, self.t_b_s) < 0.0

    def as_event_record(self) -> dict[str, Any]:
        return {
            "smoke_id": self.smoke_id,
            "center_m": self.center_m,
            "t_cmd_s": self.t_cmd_s,
            "t_d_s": self.t_d_s,
            "t_b_s": self.t_b_s,
            "pre_lock_mission": self.pre_lock_mission,
            "event_relations": {
                "t_d": "t_cmd+2",
                "t_b": "t_d+3.5=t_cmd+5.5",
            },
        }

    @classmethod
    def from_burst(
        cls,
        smoke_id: str,
        center_m: float,
        t_b_s: float,
    ) -> "SmokePlan":
        return cls(
            smoke_id=smoke_id,
            center_m=float(center_m),
            t_cmd_s=(
                float(t_b_s)
                - PARAMS.release_to_burst_delay_s
                - PARAMS.command_to_release_delay_s
            ),
        )


def ship_center_m(t_s: float, ship_speed_mps: float | None = None) -> float:
    speed = PARAMS.ship_speed_mps if ship_speed_mps is None else float(ship_speed_mps)
    return speed * float(t_s)


def smoke_radius_from_age(
    age_s: float,
    *,
    max_radius_m: float | None = None,
) -> float:
    radius = PARAMS.smoke_max_radius_m if max_radius_m is None else float(max_radius_m)
    age = float(age_s)
    if age < 0.0:
        return 0.0
    if age <= PARAMS.smoke_hold_s:
        return radius
    if age <= PARAMS.smoke_lifetime_s:
        return radius * (PARAMS.smoke_lifetime_s - age) / PARAMS.smoke_decay_s
    return 0.0


def smoke_radius(
    t_s: float,
    t_b_s: float,
    *,
    max_radius_m: float | None = None,
) -> float:
    return smoke_radius_from_age(float(t_s) - float(t_b_s), max_radius_m=max_radius_m)


def smoke_radius_derivative(
    t_s: float,
    t_b_s: float,
    *,
    max_radius_m: float | None = None,
) -> float:
    radius = PARAMS.smoke_max_radius_m if max_radius_m is None else float(max_radius_m)
    age = float(t_s) - float(t_b_s)
    if PARAMS.smoke_hold_s < age < PARAMS.smoke_lifetime_s:
        return -radius / PARAMS.smoke_decay_s
    return 0.0


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def locate_source_documents() -> dict[str, Path]:
    documents = {
        "problem": PROJECT_ROOT / PROBLEM_DOC_NAME,
        "q2_work_guide": PROJECT_ROOT / Q2_GUIDE_DOC_NAME,
    }
    missing = [str(path) for path in documents.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing Q2 source documents: {missing}")
    return documents


def read_docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        xml_data = archive.read("word/document.xml")
    root = ET.fromstring(xml_data)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs = []
    for paragraph in root.findall(".//w:p", ns):
        text = "".join(node.text or "" for node in paragraph.findall(".//w:t", ns))
        if text.strip():
            paragraphs.append(text)
    return "\n".join(paragraphs)


def standalone_numeric_reference_records_from_q2_guide() -> list[dict[str, Any]]:
    guide_path = PROJECT_ROOT / Q2_GUIDE_DOC_NAME
    if not guide_path.is_file():
        return []
    text = read_docx_text(guide_path)
    values: list[dict[str, Any]] = []
    for line in text.splitlines():
        match = re.fullmatch(
            r"\s*([0-9]+(?:\.[0-9]+)?)\s*",
            line,
        )
        if match is not None:
            literal = match.group(1)
            values.append(
                {
                    "value": float(literal),
                    "literal": literal,
                    "precision_digits": (
                        len(literal.split(".", maxsplit=1)[1])
                        if "." in literal
                        else 0
                    ),
                    "source_document": Q2_GUIDE_DOC_NAME,
                    "read_method": "read_only_docx_ooxml",
                }
            )
    return values


def source_document_metadata() -> dict[str, Any]:
    metadata_rows: dict[str, Any] = {}
    document_paths = {
        "problem": PROJECT_ROOT / PROBLEM_DOC_NAME,
        "q2_work_guide": PROJECT_ROOT / Q2_GUIDE_DOC_NAME,
    }
    for role, path in document_paths.items():
        if not path.is_file():
            metadata_rows[role] = {
                "relative_path": path.relative_to(PROJECT_ROOT).as_posix(),
                "availability": "not_available",
                "sha256": None,
                "expected_sha256": EXPECTED_SOURCE_HASHES[path.name],
                "hash_verified": None,
                "size_bytes": None,
                "nonempty_paragraph_count": None,
                "read_method": "not_available",
                "read_only_policy": True,
            }
            continue
        observed_hash = sha256_file(path)
        text = read_docx_text(path)
        metadata_rows[role] = {
            "relative_path": path.relative_to(PROJECT_ROOT).as_posix(),
            "availability": "available",
            "sha256": observed_hash,
            "expected_sha256": EXPECTED_SOURCE_HASHES[path.name],
            "hash_verified": observed_hash == EXPECTED_SOURCE_HASHES[path.name],
            "size_bytes": path.stat().st_size,
            "nonempty_paragraph_count": len(text.splitlines()),
            "read_method": "read_only_docx_ooxml",
            "read_only_policy": True,
        }
    return metadata_rows


def parameter_payload() -> dict[str, Any]:
    payload = asdict(PARAMS)
    payload.update(
        {
            "smoke_lifetime_s": PARAMS.smoke_lifetime_s,
            "inertial_displacement_m": PARAMS.inertial_displacement_m,
            "single_smoke_half_duration_s": PARAMS.single_smoke_half_duration_s,
            "single_smoke_max_duration_s": PARAMS.single_smoke_max_duration_s,
            "detect_lower_s": PARAMS.detect_lower_s,
            "detect_worst_upper_s": PARAMS.detect_worst_upper_s,
            "units": {
                "length": "m",
                "time": "s",
                "speed": "m/s",
                "area": "m^2",
                "angle": "degree",
            },
        }
    )
    return payload


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
        ("mpmath", "mpmath"),
        ("pytest", "pytest"),
    ):
        try:
            versions[label] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[label] = "not_installed"
    return versions


def write_json(path: Path, payload: Any) -> None:
    def json_default(value: Any) -> Any:
        if hasattr(value, "item"):
            return value.item()
        if hasattr(value, "tolist"):
            return value.tolist()
        raise TypeError(
            f"Object of type {value.__class__.__name__} is not JSON serializable"
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
            default=json_default,
        )
        + "\n",
        encoding="utf-8",
    )


def runtime_timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def clean_runtime_caches() -> list[str]:
    removed: list[str] = []
    for path in sorted(PROJECT_ROOT.rglob("__pycache__"), reverse=True):
        if path.is_dir():
            shutil.rmtree(path)
            removed.append(path.relative_to(PROJECT_ROOT).as_posix() + "/")
    for name in (".pytest_cache", ".mypy_cache", ".ruff_cache"):
        path = PROJECT_ROOT / name
        if path.is_dir():
            shutil.rmtree(path)
            removed.append(name + "/")
    for path in PROJECT_ROOT.rglob("*.pyc"):
        if path.is_file():
            path.unlink()
            removed.append(path.relative_to(PROJECT_ROOT).as_posix())
    return sorted(set(removed))


def assert_parameter_contract() -> None:
    expected = {
        "ship_speed_mps": 7.71,
        "single_smoke_max_duration_s": 10.376134889753567,
        "detect_lower_s": 24.167709255134113,
        "detect_worst_upper_s": 25.36104262064107,
        "inertial_displacement_m": 98.0,
    }
    observed = {
        "ship_speed_mps": PARAMS.ship_speed_mps,
        "single_smoke_max_duration_s": PARAMS.single_smoke_max_duration_s,
        "detect_lower_s": PARAMS.detect_lower_s,
        "detect_worst_upper_s": PARAMS.detect_worst_upper_s,
        "inertial_displacement_m": PARAMS.inertial_displacement_m,
    }
    for key, value in observed.items():
        if not math.isclose(value, expected[key], rel_tol=0.0, abs_tol=2e-13):
            raise RuntimeError(f"Q2 parameter mismatch for {key}: {value}")
    metadata_rows = source_document_metadata()
    if metadata_rows["problem"]["hash_verified"] is not True:
        raise RuntimeError("The tracked Q2 problem document hash changed.")
    guide_hash_status = metadata_rows["q2_work_guide"]["hash_verified"]
    if guide_hash_status is False:
        raise RuntimeError("The available Q2 work-guide document hash changed.")
