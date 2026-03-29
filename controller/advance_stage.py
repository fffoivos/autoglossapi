#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from controller.launch_codex_exec_harness import (
    DEFAULT_COLLECTIONS_FILE,
    DEFAULT_OUTPUT_ROOT,
    PROJECT_ROOT,
)
from controller.stage_definitions import STAGES


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Advance promotable collection lineages from a previous run into their next stage."
    )
    parser.add_argument("--previous-run-dir", type=Path, required=True)
    parser.add_argument("--stage", choices=sorted(STAGES), default=None)
    parser.add_argument("--collections-file", type=Path, default=None)
    parser.add_argument("--collection-slugs", nargs="*", default=None)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--workdir", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--codex-bin", default="codex")
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument("--reasoning-effort", default="xhigh")
    parser.add_argument("--sandbox-mode", default="danger-full-access")
    parser.add_argument("--max-parallel", type=int, default=10)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually launch the next-stage jobs. Default is dry-run manifest generation only.",
    )
    return parser.parse_args()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_json_if_exists(path: Path) -> Any | None:
    if not path.exists():
        return None
    return read_json(path)


def resolve_manifest_path(path_or_value: str | None, base_dir: Path) -> Path:
    if not path_or_value:
        return DEFAULT_COLLECTIONS_FILE
    candidate = Path(path_or_value)
    if candidate.is_absolute():
        return candidate
    return (base_dir / candidate).resolve()


def resolve_collections_file(args: argparse.Namespace, manifest: dict[str, Any]) -> Path:
    if args.collections_file is not None:
        return args.collections_file
    base_dir = Path(str(manifest.get("workdir") or PROJECT_ROOT))
    return resolve_manifest_path(manifest.get("collections_file"), base_dir)


def load_job_state(previous_run_dir: Path, job: dict[str, Any]) -> dict[str, Any]:
    slug = str(job["collection_slug"])
    job_dir = previous_run_dir / "jobs" / slug
    validation = job.get("validation")
    if not isinstance(validation, dict):
        validation = read_json_if_exists(job_dir / "validation.json") or {}
    next_action = job.get("next_action")
    if not isinstance(next_action, dict):
        next_action = read_json_if_exists(job_dir / "next_action.json") or {}
    return {
        "collection_slug": slug,
        "validation": validation,
        "next_action": next_action,
    }


def select_jobs(
    previous_run_dir: Path,
    manifest: dict[str, Any],
    requested_stage: str | None,
    requested_slugs: list[str] | None,
) -> tuple[str, list[str]]:
    jobs = manifest.get("jobs")
    if not isinstance(jobs, list):
        raise ValueError(f"`{previous_run_dir}` does not contain a valid job list")

    wanted = set(requested_slugs or [])
    states: list[dict[str, Any]] = []
    for job in jobs:
        if not isinstance(job, dict) or "collection_slug" not in job:
            continue
        slug = str(job["collection_slug"])
        if wanted and slug not in wanted:
            continue
        states.append(load_job_state(previous_run_dir, job))

    if requested_slugs:
        found_slugs = {state["collection_slug"] for state in states}
        missing = sorted(wanted - found_slugs)
        if missing:
            raise ValueError(f"requested collection slugs not found in previous run: {', '.join(missing)}")

    promotable: list[dict[str, Any]] = []
    for state in states:
        validation = state["validation"]
        next_action = state["next_action"]
        if validation.get("promotable") is not True:
            continue
        if next_action.get("decision") != "advance":
            continue
        next_stage = next_action.get("next_stage")
        if not isinstance(next_stage, str) or not next_stage:
            continue
        if requested_stage is not None and next_stage != requested_stage:
            continue
        promotable.append(state)

    if not promotable:
        raise ValueError("no promotable collection lineages matched the selection")

    target_stages = sorted({str(state["next_action"]["next_stage"]) for state in promotable})
    if requested_stage is None:
        if len(target_stages) != 1:
            raise ValueError(
                "selected promotable jobs do not agree on a unique next stage; pass --stage explicitly"
            )
        target_stage = target_stages[0]
    else:
        target_stage = requested_stage

    selected_slugs = [state["collection_slug"] for state in promotable]
    return target_stage, selected_slugs


def build_command(args: argparse.Namespace, stage: str, slugs: list[str], collections_file: Path) -> list[str]:
    command = [
        "python3",
        str(PROJECT_ROOT / "controller" / "launch_codex_exec_harness.py"),
        "--stage",
        stage,
        "--previous-run-dir",
        str(args.previous_run_dir),
        "--collections-file",
        str(collections_file),
        "--output-root",
        str(args.output_root),
        "--workdir",
        str(args.workdir),
        "--codex-bin",
        args.codex_bin,
        "--model",
        args.model,
        "--reasoning-effort",
        args.reasoning_effort,
        "--sandbox-mode",
        args.sandbox_mode,
        "--max-parallel",
        str(args.max_parallel),
        "--collection-slugs",
        *slugs,
    ]
    if args.apply:
        command.append("--apply")
    return command


def main() -> None:
    args = parse_args()
    manifest = read_json(args.previous_run_dir / "run_manifest.json")
    collections_file = resolve_collections_file(args, manifest)
    try:
        stage, slugs = select_jobs(
            previous_run_dir=args.previous_run_dir,
            manifest=manifest,
            requested_stage=args.stage,
            requested_slugs=args.collection_slugs,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    command = build_command(args=args, stage=stage, slugs=slugs, collections_file=collections_file)
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        cwd=args.workdir,
    )
    print(result.stdout.strip())


if __name__ == "__main__":
    main()
