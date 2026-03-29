#!/usr/bin/env python3

from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
from typing import Any

import jsonschema

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.ocr.worker_planning import WorkerPlanningInputs, recommend_workers_per_gpu  # noqa: E402
from runtime.aws.task_execution import derive_execution_plan  # noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = PROJECT_ROOT / "runtime"
PROMPTS_DIR = RUNTIME_ROOT / "prompts"
PROFILES_DIR = RUNTIME_ROOT / "host_profiles"
KNOWLEDGE_ROOT = RUNTIME_ROOT / "knowledge"
SCHEMA_PATH = PROJECT_ROOT / "schemas" / "runtime_task.schema.json"

PROMPT_BY_TASK_TYPE = {
    "provision_glossapi_host": PROMPTS_DIR / "provision_glossapi_host.md",
    "repair_glossapi_host": PROMPTS_DIR / "repair_glossapi_host.md",
    "benchmark_glossapi_ocr": PROMPTS_DIR / "benchmark_glossapi_ocr.md",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a runtime task bundle for Codex.")
    parser.add_argument("--task-file", type=Path, default=None)
    parser.add_argument("--task-type", choices=sorted(PROMPT_BY_TASK_TYPE), default=None)
    parser.add_argument("--target-name", default=None)
    parser.add_argument("--provider", default=None)
    parser.add_argument("--instance-profile", default=None)
    parser.add_argument("--glossapi-branch", default="development")
    parser.add_argument("--expect-gpu", action="store_true")
    parser.add_argument("--needs-rust", action="store_true")
    parser.add_argument("--needs-cleaner", action="store_true")
    parser.add_argument("--needs-deepseek-ocr", action="store_true")
    parser.add_argument("--benchmark-ocr", action="store_true")
    parser.add_argument("--auto-worker-tuning", action="store_true")
    parser.add_argument("--minimum-gpu-count", type=int, default=None)
    parser.add_argument("--minimum-gpu-memory-gib", type=float, default=None)
    parser.add_argument("--preferred-gpu-model", default=None)
    parser.add_argument("--minimum-vcpu", type=int, default=None)
    parser.add_argument("--minimum-ram-gib", type=float, default=None)
    parser.add_argument("--public-ip", default=None)
    parser.add_argument("--instance-id", default=None)
    parser.add_argument("--repo-path", default=None)
    parser.add_argument("--runtime-python", default=None)
    parser.add_argument("--peak-worker-memory-gib", type=float, default=None)
    parser.add_argument("--single-worker-utilization", type=float, default=None)
    parser.add_argument("--cpu-cores-per-gpu", type=float, default=None)
    parser.add_argument("--cpu-cores-per-worker", type=float, default=None)
    parser.add_argument("--headroom-gib", type=float, default=None)
    parser.add_argument("--target-utilization", type=float, default=None)
    parser.add_argument("--hard-max-workers", type=int, default=None)
    parser.add_argument("--note", action="append", default=[])
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _task_from_args(args: argparse.Namespace) -> dict[str, Any]:
    if not args.task_type or not args.target_name:
        raise ValueError("either --task-file or both --task-type and --target-name are required")
    task: dict[str, Any] = {
        "task_type": args.task_type,
        "target_name": args.target_name,
        "glossapi_branch": args.glossapi_branch,
        "requirements": {},
    }
    if args.provider:
        task["provider"] = args.provider
    if args.instance_profile:
        task["instance_profile"] = args.instance_profile
    requirements = task["requirements"]
    for key, value in (
        ("expect_gpu", args.expect_gpu),
        ("needs_rust", args.needs_rust),
        ("needs_cleaner", args.needs_cleaner),
        ("needs_deepseek_ocr", args.needs_deepseek_ocr),
        ("benchmark_ocr", args.benchmark_ocr),
        ("auto_worker_tuning", args.auto_worker_tuning),
        ("minimum_gpu_count", args.minimum_gpu_count),
        ("minimum_gpu_memory_gib", args.minimum_gpu_memory_gib),
        ("preferred_gpu_model", args.preferred_gpu_model),
        ("minimum_vcpu", args.minimum_vcpu),
        ("minimum_ram_gib", args.minimum_ram_gib),
    ):
        if value not in (None, False):
            requirements[key] = value
    existing_host = {
        key: value
        for key, value in (
            ("public_ip", args.public_ip),
            ("instance_id", args.instance_id),
            ("repo_path", args.repo_path),
            ("runtime_python", args.runtime_python),
        )
        if value is not None
    }
    if existing_host:
        task["existing_host"] = existing_host
    benchmark_inputs = {
        key: value
        for key, value in (
            ("peak_worker_memory_gib", args.peak_worker_memory_gib),
            ("single_worker_utilization", args.single_worker_utilization),
            ("cpu_cores_per_gpu", args.cpu_cores_per_gpu),
            ("cpu_cores_per_worker", args.cpu_cores_per_worker),
            ("headroom_gib", args.headroom_gib),
            ("target_utilization", args.target_utilization),
            ("hard_max_workers", args.hard_max_workers),
        )
        if value is not None
    }
    if benchmark_inputs:
        task["benchmark_inputs"] = benchmark_inputs
    if args.note:
        task["notes"] = list(args.note)
    return task


def _validate_task(task: dict[str, Any]) -> None:
    schema = _read_json(SCHEMA_PATH)
    jsonschema.validate(task, schema)


def _load_profile(profile_id: str | None) -> dict[str, Any] | None:
    if not profile_id:
        return None
    path = PROFILES_DIR / f"{profile_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"unknown host profile: {profile_id}")
    profile = _read_json(path)
    profile["_path"] = str(path)
    return profile


def _merge_profile_defaults(task: dict[str, Any], profile: dict[str, Any] | None) -> dict[str, Any]:
    resolved = deepcopy(task)
    if not profile:
        return resolved

    resolved.setdefault("provider", profile.get("provider"))
    resolved.setdefault("instance_profile", profile.get("profile_id"))
    resolved.setdefault("glossapi_branch", profile.get("runtime_defaults", {}).get("glossapi_branch", "development"))
    requirements = resolved.setdefault("requirements", {})
    for key, value in profile.get("runtime_defaults", {}).items():
        if key in {"glossapi_branch", "target_dir"}:
            continue
        requirements.setdefault(key, value)
    target_dir = profile.get("runtime_defaults", {}).get("target_dir")
    if target_dir:
        resolved.setdefault("resolved_runtime_defaults", {})
        resolved["resolved_runtime_defaults"].setdefault("target_dir", target_dir)
    if "benchmark_inputs" not in resolved and profile.get("benchmark_inputs"):
        resolved["benchmark_inputs"] = deepcopy(profile["benchmark_inputs"])
    return resolved


def _derive_truth_conditions(task: dict[str, Any], profile: dict[str, Any] | None) -> list[str]:
    requirements = task.get("requirements", {})
    conditions = [
        "GlossAPI checkout exists and is on the requested branch.",
        "A readiness check passes against the actual runtime interpreter.",
    ]
    if requirements.get("needs_rust") or requirements.get("needs_cleaner"):
        conditions.append("Rust and Cargo are installed so rust extensions can build cleanly.")
    if requirements.get("expect_gpu"):
        conditions.append("nvidia-smi works and reports the expected GPU hardware.")
    if requirements.get("needs_deepseek_ocr"):
        conditions.append("DeepSeek OCR runtime modules and model assets are present.")
        conditions.append("The selected Torch/CUDA/attention stack fits the host GPU generation and can execute a basic CUDA allocation.")
    if requirements.get("benchmark_ocr"):
        conditions.append("A bounded OCR benchmark has been run and artifacts were captured.")
    if requirements.get("auto_worker_tuning"):
        conditions.append("A workers_per_gpu recommendation has been computed and validated with a small sweep.")
    if profile and profile.get("runtime_defaults", {}).get("target_dir"):
        conditions.append(f"GlossAPI target directory matches or intentionally overrides `{profile['runtime_defaults']['target_dir']}`.")
    return conditions


def _derive_workflow_steps(task: dict[str, Any]) -> list[str]:
    requirements = task.get("requirements", {})
    task_type = task["task_type"]
    steps = []
    if task_type == "provision_glossapi_host":
        steps.extend(
            [
                "Bootstrap the host with runtime/aws/bootstrap_glossapi_aws.sh.",
                "Run runtime/aws/check_glossapi_runtime.py against the resolved runtime interpreter.",
            ]
        )
    elif task_type == "repair_glossapi_host":
        steps.extend(
            [
                "Inspect the existing host state before changing anything.",
                "Run runtime/aws/check_glossapi_runtime.py to identify missing dependencies and drift.",
                "Apply the smallest repair set needed to satisfy the readiness checks.",
            ]
        )
    else:
        steps.extend(
            [
                "Run the readiness check first.",
                "Compute the initial OCR worker guess.",
                "Run a bounded benchmark sweep to validate the worker choice.",
            ]
        )
    if requirements.get("auto_worker_tuning"):
        steps.append("Use runtime/ocr/worker_planning.py to choose the initial workers_per_gpu guess.")
    if requirements.get("needs_deepseek_ocr"):
        steps.append("Review OS, driver, Torch, CUDA, arch support, attention backend, and OCR mode before benchmarking OCR throughput.")
        steps.append("Prefer CUDA_VISIBLE_DEVICES isolation for multi-worker DeepSeek OCR.")
    if requirements.get("needs_deepseek_ocr"):
        steps.append("Run the runtime OCR smoke test after setup so OCR plus cleaner refresh is verified end to end.")
    return steps


def _recommend_ocr_parameters(task: dict[str, Any], profile: dict[str, Any] | None) -> dict[str, Any] | None:
    requirements = task.get("requirements", {})
    if not (requirements.get("benchmark_ocr") or requirements.get("auto_worker_tuning") or requirements.get("needs_deepseek_ocr")):
        return None
    benchmark_inputs = task.get("benchmark_inputs") or {}
    gpu_memory = None
    if profile:
        gpu_memory = profile.get("hardware", {}).get("gpu_memory_gib")
    if gpu_memory is None or not benchmark_inputs.get("peak_worker_memory_gib"):
        return None

    recommendation = recommend_workers_per_gpu(
        WorkerPlanningInputs(
            gpu_memory_gib=float(gpu_memory),
            peak_worker_memory_gib=float(benchmark_inputs["peak_worker_memory_gib"]),
            headroom_gib=float(benchmark_inputs.get("headroom_gib", 15.0)),
            target_utilization=float(benchmark_inputs.get("target_utilization", 0.80)),
            single_worker_utilization=benchmark_inputs.get("single_worker_utilization"),
            cpu_cores_per_gpu=benchmark_inputs.get("cpu_cores_per_gpu"),
            cpu_cores_per_worker=benchmark_inputs.get("cpu_cores_per_worker"),
            hard_max_workers=benchmark_inputs.get("hard_max_workers"),
        )
    )
    return recommendation.to_json()


def _resolve_knowledge_paths(profile: dict[str, Any] | None) -> list[Path]:
    if not profile:
        return []
    paths = []
    for relative in profile.get("knowledge_refs", []):
        candidate = PROJECT_ROOT / relative
        if candidate.exists():
            paths.append(candidate)
    return paths


def _format_prompt(
    task: dict[str, Any],
    resolved_task_path: Path,
    output_dir: Path,
    host_profile_path: Path | None,
    knowledge_paths: list[Path],
) -> str:
    prompt_template = PROMPT_BY_TASK_TYPE[task["task_type"]].read_text(encoding="utf-8")
    knowledge_block = "\n".join(f"- `{path}`" for path in knowledge_paths)
    if knowledge_block:
        knowledge_block = "Additional stored knowledge:\n" + knowledge_block
    else:
        knowledge_block = "Additional stored knowledge:\n- none"
    return prompt_template.format(
        resolved_task_path=str(resolved_task_path),
        host_profile_path=str(host_profile_path) if host_profile_path else "none",
        aws_runtime_doc_path=str(PROJECT_ROOT / "docs" / "aws_runtime.md"),
        stack_fit_doc_path=str(PROJECT_ROOT / "docs" / "runtime_stack_fit.md"),
        runtime_readme_path=str(RUNTIME_ROOT / "README.md"),
        bootstrap_script_path=str(RUNTIME_ROOT / "aws" / "bootstrap_glossapi_aws.sh"),
        readiness_check_path=str(RUNTIME_ROOT / "aws" / "check_glossapi_runtime.py"),
        worker_planning_path=str(RUNTIME_ROOT / "ocr" / "worker_planning.py"),
        knowledge_paths_block=knowledge_block,
        output_dir=str(output_dir),
    )


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    task = _read_json(args.task_file) if args.task_file else _task_from_args(args)
    _validate_task(task)
    profile = _load_profile(task.get("instance_profile"))
    resolved_task = _merge_profile_defaults(task, profile)

    host_profile_path = Path(profile["_path"]) if profile else None
    knowledge_paths = _resolve_knowledge_paths(profile)
    resolved_task["what_must_be_true"] = _derive_truth_conditions(resolved_task, profile)
    resolved_task["workflow_steps"] = _derive_workflow_steps(resolved_task)
    resolved_task["execution_plan"] = derive_execution_plan(resolved_task)
    resolved_task["relevant_paths"] = {
        "runtime_readme": str(RUNTIME_ROOT / "README.md"),
        "aws_runtime_doc": str(PROJECT_ROOT / "docs" / "aws_runtime.md"),
        "runtime_stack_fit_doc": str(PROJECT_ROOT / "docs" / "runtime_stack_fit.md"),
        "runtime_execution_spec": str(PROJECT_ROOT / "docs" / "runtime_execution_spec.md"),
        "bootstrap_script": str(RUNTIME_ROOT / "aws" / "bootstrap_glossapi_aws.sh"),
        "readiness_check": str(RUNTIME_ROOT / "aws" / "check_glossapi_runtime.py"),
        "runtime_executor": str(RUNTIME_ROOT / "aws" / "execute_runtime_task.py"),
        "runtime_smoke_test": str(RUNTIME_ROOT / "aws" / "smoke_test_glossapi_runtime.py"),
        "ocr_worker_planning": str(RUNTIME_ROOT / "ocr" / "worker_planning.py"),
        "runtime_investigation": str(RUNTIME_ROOT / "investigation.py"),
        "host_profile": str(host_profile_path) if host_profile_path else None,
        "knowledge_refs": [str(path) for path in knowledge_paths],
    }
    resolved_task["recommended_parameters"] = {
        "ocr": _recommend_ocr_parameters(resolved_task, profile)
    }

    resolved_task_path = output_dir / "resolved_task.json"
    prompt_path = output_dir / "codex_prompt.txt"
    _write_json(resolved_task_path, resolved_task)
    prompt_text = _format_prompt(
        resolved_task,
        resolved_task_path=resolved_task_path,
        output_dir=output_dir,
        host_profile_path=host_profile_path,
        knowledge_paths=knowledge_paths,
    )
    prompt_path.write_text(prompt_text, encoding="utf-8")

    manifest = {
        "task_type": resolved_task["task_type"],
        "target_name": resolved_task["target_name"],
        "resolved_task_path": str(resolved_task_path),
        "prompt_path": str(prompt_path),
        "host_profile_path": str(host_profile_path) if host_profile_path else None,
        "knowledge_paths": [str(path) for path in knowledge_paths],
        "suggested_codex_command": [
            "codex",
            "exec",
            "--skip-git-repo-check",
            "--cd",
            str(PROJECT_ROOT),
            "--json",
            "-",
        ],
    }
    _write_json(output_dir / "bundle_manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
