from __future__ import annotations

from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_ROOT = PROJECT_ROOT / "knowledge" / "reviewer"
STAGE_KNOWLEDGE_DIR = KNOWLEDGE_ROOT / "stages"
TRACKING_DIR = PROJECT_ROOT / "tracking"
GENERATED_DIR = TRACKING_DIR / "generated"
MANUAL_DIR = TRACKING_DIR / "manual"

MANUAL_PROBLEM_SOLUTION_INDEX = MANUAL_DIR / "problem_solution_index.csv"
GENERATED_PROBLEM_SOLUTION_INDEX = GENERATED_DIR / "reviewer_problem_solution_index.csv"
GENERATED_RECOVERY_CASES = GENERATED_DIR / "reviewer_recovery_cases.csv"
GENERATED_RECOVERY_STATS = GENERATED_DIR / "reviewer_recovery_stats.csv"
GENERATED_RECOVERY_SUMMARY = GENERATED_DIR / "reviewer_recovery_summary.md"


def stage_knowledge_path(stage: str) -> Path:
    return STAGE_KNOWLEDGE_DIR / f"{stage}.md"


def review_artifact_paths(stage: str) -> list[Path]:
    paths = [
        stage_knowledge_path(stage),
        MANUAL_PROBLEM_SOLUTION_INDEX,
        GENERATED_PROBLEM_SOLUTION_INDEX,
        GENERATED_RECOVERY_CASES,
        GENERATED_RECOVERY_STATS,
        GENERATED_RECOVERY_SUMMARY,
    ]
    return [path for path in paths if path.exists()]


def review_artifact_dirs(stage: str) -> list[Path]:
    seen: set[Path] = set()
    dirs: list[Path] = []
    for path in review_artifact_paths(stage):
        parent = path.parent
        if parent not in seen:
            seen.add(parent)
            dirs.append(parent)
    return dirs


def problem_tags(
    report: dict[str, Any],
    validation: dict[str, Any],
    progress: dict[str, Any],
) -> list[str]:
    tags: set[str] = set()
    failure_class = str(validation.get("failure_class") or "").strip()
    if failure_class:
        tags.add(f"failure:{failure_class}")

    for key in ("failed_checklist_ids",):
        for value in report.get(key) or []:
            if value:
                tags.add(f"checklist:{value}")

    for value in validation.get("non_done_checklist_ids") or []:
        if value:
            tags.add(f"checklist:{value}")

    for issue in progress.get("issue_labels") or []:
        if not isinstance(issue, dict):
            continue
        label = str(issue.get("label") or "").strip()
        status = str(issue.get("status") or "").strip()
        if label:
            tags.add(f"issue:{label}")
        if label and status:
            tags.add(f"issue_status:{label}:{status}")

    if progress.get("user_decision_pending"):
        tags.add("decision:user_pending")

    return sorted(tags)


def knowledge_ref_strings(stage: str) -> list[str]:
    refs = [str(path) for path in review_artifact_paths(stage)]
    return refs
