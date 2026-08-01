"""Shared Q3 paths, deterministic I/O, provenance, and runtime contracts."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[2]
CODE_DIR = ROOT / "code" / "Q3"
DATA_DIR = ROOT / "workspace" / "data_clean"
ROUND_DIR = ROOT / "results" / "Q3" / "experiments" / "round3"
METRICS_DIR = ROUND_DIR / "metrics"
TABLES_DIR = ROUND_DIR / "tables"
FIGURES_DIR = ROUND_DIR / "figures"
REVIEWS_DIR = CODE_DIR / "reviews"
ROBUSTNESS_DIR = ROOT / "robustness" / "Q3"
FINAL_MANIFEST_PATH = ROOT / "results" / "Q3" / "q3_final_manifest.json"
SCENARIO_PATH = DATA_DIR / "q3_standardized_scenario.json"
REFERENCE_PATH = DATA_DIR / "q3_reference_plan_p2.json"
PROBLEM_DOC = ROOT / "B题：舰船烟幕遮蔽干扰优化.docx"
WORK_GUIDE_DOC = ROOT / "Q3_编程手与论文手任务清单.docx"
RANDOM_SEED = 2026
SCENARIO_SCOPE = "SYNTHETIC_SCENARIO_ONLY"
FREEZE_STATUS = "unfrozen"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def git_output(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout.strip()


def git_paths_clean(paths: list[str]) -> bool:
    result = subprocess.run(
        ["git", "diff", "--quiet", "--", *paths],
        cwd=ROOT,
        check=False,
    )
    cached = subprocess.run(
        ["git", "diff", "--cached", "--quiet", "--", *paths],
        cwd=ROOT,
        check=False,
    )
    return result.returncode == 0 and cached.returncode == 0


def docx_nonempty_paragraph_count(path: Path) -> int:
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    with zipfile.ZipFile(path) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    return sum(
        bool("".join(node.text or "" for node in paragraph.iter(namespace + "t")).strip())
        for paragraph in root.iter(namespace + "p")
    )


def source_document_metadata() -> dict[str, Any]:
    reference = read_json(REFERENCE_PATH)
    expected_guide_hash = reference["source_sha256"].lower()
    problem_stage = git_output("ls-files", "--stage", "--", PROBLEM_DOC.name)
    problem_blob = problem_stage.split()[1] if problem_stage else None
    problem_hash = sha256_file(PROBLEM_DOC)
    guide_hash = sha256_file(WORK_GUIDE_DOC)
    return {
        "problem": {
            "relative_path": PROBLEM_DOC.name,
            "size_bytes": PROBLEM_DOC.stat().st_size,
            "sha256": problem_hash,
            "git_tracked": bool(problem_stage),
            "git_blob_sha": problem_blob,
            "worktree_modified": not git_paths_clean([PROBLEM_DOC.name]),
            "read_method": "read_only_docx_ooxml",
            "nonempty_paragraph_count": docx_nonempty_paragraph_count(PROBLEM_DOC),
        },
        "q3_work_guide": {
            "relative_path": WORK_GUIDE_DOC.name,
            "size_bytes": WORK_GUIDE_DOC.stat().st_size,
            "sha256": guide_hash,
            "expected_sha256": expected_guide_hash,
            "hash_verified": guide_hash == expected_guide_hash,
            "git_tracked": bool(
                git_output("ls-files", "--", WORK_GUIDE_DOC.name)
            ),
            "read_method": "read_only_docx_ooxml",
            "nonempty_paragraph_count": docx_nonempty_paragraph_count(WORK_GUIDE_DOC),
        },
        "document_visual_render_note": (
            "LibreOffice/soffice unavailable; both DOCX files were read through "
            "read-only OOXML and were not visually re-rendered."
        ),
    }


def dependency_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in ("numpy", "scipy", "pandas", "matplotlib", "mpmath", "pytest"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "not_installed"
    return {
        "python": platform.python_version(),
        **versions,
        "operating_system": platform.platform(),
        "cpu": platform.processor() or os.environ.get("PROCESSOR_IDENTIFIER", "unknown"),
    }


def ensure_output_directories() -> None:
    for path in (
        METRICS_DIR,
        TABLES_DIR,
        FIGURES_DIR,
        REVIEWS_DIR,
        ROBUSTNESS_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)


def clean_runtime_caches() -> list[str]:
    removed: list[str] = []
    for path in ROOT.rglob("__pycache__"):
        if ".git" not in path.parts:
            shutil.rmtree(path)
            removed.append(relative(path))
    for path in ROOT.rglob("*.pyc"):
        if ".git" not in path.parts and path.exists():
            path.unlink()
            removed.append(relative(path))
    return sorted(removed)


def assert_source_contract() -> dict[str, Any]:
    if not PROBLEM_DOC.is_file() or not WORK_GUIDE_DOC.is_file():
        raise FileNotFoundError("Both formal Q3 source documents are required.")
    metadata = source_document_metadata()
    if not metadata["problem"]["git_tracked"]:
        raise ValueError("The formal problem DOCX must be tracked by Git.")
    if metadata["problem"]["worktree_modified"]:
        raise ValueError("The formal problem DOCX has a worktree modification.")
    if not metadata["q3_work_guide"]["hash_verified"]:
        raise ValueError("The Q3 work-guide SHA-256 changed.")
    return metadata


def core_status_fields(
    *,
    result_strength: str,
    coverage_status: str,
    safety_status: str,
    reference_status: str,
    limitations: list[str],
) -> dict[str, Any]:
    return {
        "scenario_scope": SCENARIO_SCOPE,
        "freeze_status": FREEZE_STATUS,
        "execution_status": "completed",
        "input_status": "validated_synthetic_input",
        "coverage_certificate_status": coverage_status,
        "safety_certificate_status": safety_status,
        "reference_comparison_status": reference_status,
        "result_strength": result_strength,
        "global_optimality_status": "not_proved",
        "paper_writing_allowed": False,
        "limitations": limitations,
    }
