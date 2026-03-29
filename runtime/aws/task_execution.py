from __future__ import annotations

from pathlib import Path
from typing import Any


def default_ssh_user(provider: str | None) -> str | None:
    if provider == "aws":
        return "ubuntu"
    if provider == "hetzner":
        return "foivos"
    return None


def bootstrap_mode_for_task(task_type: str) -> str:
    return "repair" if task_type == "repair_glossapi_host" else "provision"


def should_update_repo(task_type: str) -> bool:
    return task_type != "repair_glossapi_host"


def should_run_ocr_smoke_test(task: dict[str, Any]) -> bool:
    requirements = task.get("requirements", {})
    return bool(requirements.get("needs_deepseek_ocr"))


def should_review_stack_fit(task: dict[str, Any]) -> bool:
    requirements = task.get("requirements", {})
    return bool(requirements.get("needs_deepseek_ocr") or requirements.get("benchmark_ocr"))


def derive_target_dir(task: dict[str, Any]) -> str | None:
    existing = task.get("existing_host", {}) or {}
    if existing.get("repo_path"):
        return str(existing["repo_path"])
    defaults = task.get("resolved_runtime_defaults", {}) or {}
    if defaults.get("target_dir"):
        return str(defaults["target_dir"])
    return None


def derive_runtime_python_candidates(task: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    existing = task.get("existing_host", {}) or {}
    explicit = existing.get("runtime_python")
    if explicit:
        candidates.append(str(explicit))
    target_dir = derive_target_dir(task)
    if target_dir:
        candidates.extend(
            [
                str(Path(target_dir) / "dependency_setup" / "deepseek_uv" / "dependency_setup" / ".venvs" / "deepseek" / "bin" / "python"),
                str(Path(target_dir) / "dependency_setup" / ".venvs" / "deepseek" / "bin" / "python"),
            ]
        )
    seen: set[str] = set()
    unique_candidates: list[str] = []
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        unique_candidates.append(candidate)
    return unique_candidates


def readiness_flags(task: dict[str, Any]) -> list[str]:
    requirements = task.get("requirements", {}) or {}
    flags: list[str] = []
    if requirements.get("expect_gpu"):
        flags.append("--expect-gpu")
    if requirements.get("needs_rust"):
        flags.append("--needs-rust")
    if requirements.get("needs_cleaner"):
        flags.append("--needs-cleaner")
    if requirements.get("needs_deepseek_ocr"):
        flags.append("--needs-deepseek-ocr")
    return flags


def derive_execution_plan(task: dict[str, Any]) -> dict[str, Any]:
    provider = task.get("provider")
    return {
        "executor": "runtime/aws/execute_runtime_task.py",
        "bootstrap_mode": bootstrap_mode_for_task(task["task_type"]),
        "update_repo": should_update_repo(task["task_type"]),
        "default_ssh_user": default_ssh_user(provider),
        "target_dir": derive_target_dir(task),
        "runtime_python_candidates": derive_runtime_python_candidates(task),
        "readiness_flags": readiness_flags(task),
        "review_stack_fit": should_review_stack_fit(task),
        "run_ocr_smoke_test": should_run_ocr_smoke_test(task),
        "smoke_test_script": "runtime/aws/smoke_test_glossapi_runtime.py",
        "requires_clean_repo_for_update": should_update_repo(task["task_type"]),
    }
