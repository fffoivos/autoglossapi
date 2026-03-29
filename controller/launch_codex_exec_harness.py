#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from controller.route_next_action import decide_next_action
from controller.stage_definitions import STAGES, StageSpec
from controller.validate_stage_report import validate_report_payload


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COLLECTIONS_FILE = PROJECT_ROOT / "config" / "collections" / "all_strict_target_collections.json"
DEFAULT_SCHEMA_FILE = PROJECT_ROOT / "schemas" / "stage_report.schema.json"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "runs"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare or launch a staged Codex-exec harness for direct repository scraping research."
    )
    parser.add_argument("--stage", choices=sorted(STAGES), required=True)
    parser.add_argument("--collections-file", type=Path, default=DEFAULT_COLLECTIONS_FILE)
    parser.add_argument("--schema-file", type=Path, default=DEFAULT_SCHEMA_FILE)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--workdir", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--previous-run-dir", type=Path, default=None)
    parser.add_argument("--codex-bin", default="codex")
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument("--reasoning-effort", default="xhigh")
    parser.add_argument("--sandbox-mode", default="danger-full-access")
    parser.add_argument("--max-parallel", type=int, default=10)
    parser.add_argument("--collection-slugs", nargs="*", default=None)
    parser.add_argument("--disable-search", action="store_true")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually launch codex exec jobs. Default is dry-run manifest generation only.",
    )
    return parser.parse_args()


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_collections(path: Path, slugs: list[str] | None) -> list[dict[str, Any]]:
    payload = read_json(path)
    if not isinstance(payload, list):
        raise ValueError(f"expected a list in {path}")
    collections = [item for item in payload if isinstance(item, dict)]
    if slugs:
        wanted = set(slugs)
        collections = [item for item in collections if item.get("collection_slug") in wanted]
    if not collections:
        raise ValueError("no collections selected")
    return collections


def make_run_dir(output_root: Path, stage: str) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = output_root / f"{stamp}_{stage}"
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "jobs").mkdir(parents=True, exist_ok=False)
    return run_dir


def previous_report_path(previous_run_dir: Path | None, collection_slug: str) -> Path | None:
    if previous_run_dir is None:
        return None
    candidate = previous_run_dir / "jobs" / collection_slug / "final.json"
    return candidate if candidate.exists() else None


def render_prompt(
    collection: dict[str, Any],
    stage_spec: StageSpec,
    stage: str,
    job_dir: Path,
    schema_file: Path,
    previous_report: Path | None,
) -> str:
    checklist_lines = "\n".join(
        f"- `{item_id}`: {label}" for item_id, label in stage_spec.checklist
    )
    previous_block = ""
    if previous_report is not None:
        previous_block = (
            "\nPrevious stage report:\n"
            f"- path: `{previous_report}`\n"
            "- read it before doing new work and preserve any correct findings.\n"
        )
    sample_block = ""
    if stage_spec.sample_limit:
        sample_block = (
            f"\nSample limit:\n- download at most `{stage_spec.sample_limit}` PDFs for this stage.\n"
        )
    return f"""You are working on direct upstream repository scraping research for GlossAPI.

Goal:
- collection_slug: `{collection['collection_slug']}`
- stage: `{stage}`
- repository host hint: `{collection['repo_host']}`
- repository URL hint: `{collection['repo_url_hint']}`
- sample item URL hint: `{collection.get('sample_item_url_hint', '')}`
- platform hint: `{collection['platform_hint']}`
- priority kind: `{collection['priority_kind']}`
- tapped strict-language rows already extracted: `{collection['tapped_target_rows']}`
- untapped strict-language rows: `{collection['untapped_target_rows']}`
- content priority: `{collection.get('content_priority', '')}`
- extraction ease: `{collection.get('extraction_ease', '')}`
- dominant target types: `{collection.get('dominant_target_types', [])}`
- search query hint: `{collection.get('search_query_hint', '')}`
- notes: `{collection['notes']}`

Stage objective:
- {stage_spec.description}
{previous_block}
Hard constraints:
- Work directly against the upstream repository, not `openarchives.gr`, except to use the provided host hint.
- Do not launch a bulk crawl.
- Be conservative about rate and volume.
- If you need Python locally, use `python3`, not `python`.
- Save any local notes or helper outputs under `{job_dir}`.
- The final response must be JSON only and must satisfy `{schema_file}`.

Focus:
- Prioritize Greek-language content or collections that plausibly center Greek content.
- Prioritize high-quality, academically meaningful, easy-to-extract material.
- Deprioritize content that is likely to extract poorly or be low value, such as handwritten scans, image-only artifacts, repository notices, and attachment stubs.
- Pay close attention to website levels: repo home, collection page, listing page, item page, and PDF access path.
- Explicitly record any stated total-count claims and per-collection count claims, and distinguish website claims from API-reported counts and scraper-observed counts.
- Explore any public API or machine-readable endpoint that can improve metadata enumeration, file discovery, or count reconciliation.
- Probe request tolerance conservatively. If you see temporary 429s or similar throttling, stop escalating and record the apparent safe request pattern instead of forcing retries.
- If you hit a blocker, explicitly record failed checklist items, tried hypotheses, alternative hypotheses, the best next hypothesis, and whether you think the lineage is exhausted.

Required checklist:
{checklist_lines}
{sample_block}
Expected useful fields in the final JSON:
- `repo_root_url`
- `available_subcollections`
- `website_levels`
- `relevant_collection_urls`
- `platform_guess`
- `content_type_summary`
- `claimed_item_count`
- `observed_item_count`
- `count_evidence`
- `pagination_strategy`
- `pdf_detection_strategy`
- `metadata_richness_note`
- `metadata_fields`
- `priority_assessment`
- `sample_documents`
- `checklist`
- `artifacts`
- `risks`
- `failed_checklist_ids`
- `tried_hypotheses`
- `alternative_hypotheses`
- `best_next_hypothesis`
- `stuck_reason`
- `blocked_on`
- `exhausted_paths`
- `confidence`
- `recommended_next_step`

The repository-specific proof matters more than polished prose. Use the checklist evidence fields to make the handoff auditable.
"""


def build_command(
    args: argparse.Namespace,
    schema_file: Path,
    final_path: Path,
    job_dir: Path,
) -> list[str]:
    command = [
        args.codex_bin,
        "exec",
        "--skip-git-repo-check",
        "--cd",
        str(args.workdir),
        "--model",
        args.model,
        "-c",
        f'model_reasoning_effort="{args.reasoning_effort}"',
        "-c",
        'approval_policy="never"',
        "-s",
        args.sandbox_mode,
        "--add-dir",
        str(job_dir),
    ]
    command.extend(
        [
            "--output-schema",
            str(schema_file),
            "-o",
            str(final_path),
            "--json",
            "-",
        ]
    )
    return command


def runtime_failure_validation(job: dict[str, Any], note: str) -> dict[str, Any]:
    return {
        "collection_slug": job["collection_slug"],
        "stage": job["stage"],
        "schema_valid": False,
        "failure_class": "runtime_failed",
        "promotable": False,
        "missing_checklist_ids": [],
        "non_done_checklist_ids": [],
        "artifact_issues": [],
        "notes": [note],
    }


def finalize_job(job: dict[str, Any], schema: dict[str, Any]) -> None:
    final_path = Path(job["final_path"])
    validation_path = Path(job["validation_path"])
    next_action_path = Path(job["next_action_path"])
    lineage_state_path = Path(job["lineage_state_path"])

    if job["returncode"] != 0:
        validation = runtime_failure_validation(job, f"codex exec exited with return code {job['returncode']}")
    elif not final_path.exists():
        validation = runtime_failure_validation(job, "codex exec exited cleanly but did not produce final.json")
    else:
        try:
            report = read_json(final_path)
        except json.JSONDecodeError as exc:
            validation = {
                "collection_slug": job["collection_slug"],
                "stage": job["stage"],
                "schema_valid": False,
                "failure_class": "schema_failed",
                "promotable": False,
                "missing_checklist_ids": [],
                "non_done_checklist_ids": [],
                "artifact_issues": [],
                "notes": [f"final.json is not valid JSON: {exc}"],
            }
        else:
            validation = validate_report_payload(report=report, schema=schema, job_dir=final_path.parent)

    decision = decide_next_action(validation)
    write_json(validation_path, validation)
    write_json(next_action_path, decision)
    write_json(
        lineage_state_path,
        {
            "collection_slug": job["collection_slug"],
            "stage": job["stage"],
            "job_dir": job["job_dir"],
            "previous_report": job.get("previous_report"),
            "validation": validation,
            "next_action": decision,
        },
    )
    job["validation"] = validation
    job["next_action"] = decision


def launch_jobs(run_dir: Path, job_specs: list[dict[str, Any]], max_parallel: int, schema: dict[str, Any]) -> None:
    pending = list(job_specs)
    running: list[dict[str, Any]] = []

    while pending or running:
        while pending and len(running) < max_parallel:
            job = pending.pop(0)
            prompt_handle = open(job["prompt_path"], "r", encoding="utf-8")
            event_handle = open(job["events_path"], "w", encoding="utf-8")
            process = subprocess.Popen(
                job["command"],
                stdin=prompt_handle,
                stdout=event_handle,
                stderr=subprocess.STDOUT,
                text=True,
            )
            job["pid"] = process.pid
            job["started_at"] = datetime.now(UTC).isoformat()
            job["status"] = "running"
            running.append(
                {
                    "process": process,
                    "job": job,
                    "prompt_handle": prompt_handle,
                    "event_handle": event_handle,
                }
            )

        still_running: list[dict[str, Any]] = []
        for running_job in running:
            process = running_job["process"]
            job = running_job["job"]
            returncode = process.poll()
            if returncode is None:
                still_running.append(running_job)
                continue
            job["returncode"] = returncode
            job["finished_at"] = datetime.now(UTC).isoformat()
            job["status"] = "completed" if returncode == 0 else "failed"
            running_job["prompt_handle"].close()
            running_job["event_handle"].close()
            finalize_job(job, schema=schema)
        running = still_running
        write_json(run_dir / "run_manifest.json", {"jobs": job_specs})
        if running:
            time.sleep(2.0)


def main() -> None:
    args = parse_args()
    stage_spec = STAGES[args.stage]
    collections = load_collections(args.collections_file, args.collection_slugs)
    if args.stage != "discover" and args.previous_run_dir is None:
        raise SystemExit(f"`--previous-run-dir` is required for stage `{args.stage}`")

    schema = read_json(args.schema_file)
    run_dir = make_run_dir(args.output_root, args.stage)
    manifest: list[dict[str, Any]] = []

    for collection in collections:
        slug = str(collection["collection_slug"])
        job_dir = run_dir / "jobs" / slug
        job_dir.mkdir(parents=True, exist_ok=False)
        previous_report = previous_report_path(args.previous_run_dir, slug)
        prompt_text = render_prompt(
            collection=collection,
            stage_spec=stage_spec,
            stage=args.stage,
            job_dir=job_dir,
            schema_file=args.schema_file,
            previous_report=previous_report,
        )
        prompt_path = job_dir / "prompt.txt"
        final_path = job_dir / "final.json"
        events_path = job_dir / "events.jsonl"
        validation_path = job_dir / "validation.json"
        next_action_path = job_dir / "next_action.json"
        lineage_state_path = job_dir / "lineage_state.json"
        write_json(job_dir / "collection_context.json", collection)
        prompt_path.write_text(prompt_text, encoding="utf-8")
        command = build_command(args=args, schema_file=args.schema_file, final_path=final_path, job_dir=job_dir)
        manifest.append(
            {
                "collection_slug": slug,
                "agent_id": collection["agent_id"],
                "stage": args.stage,
                "job_dir": str(job_dir),
                "prompt_path": str(prompt_path),
                "final_path": str(final_path),
                "events_path": str(events_path),
                "validation_path": str(validation_path),
                "next_action_path": str(next_action_path),
                "lineage_state_path": str(lineage_state_path),
                "previous_report": str(previous_report) if previous_report else None,
                "command": command,
                "command_shell": " ".join(shlex.quote(part) for part in command) + f" < {shlex.quote(str(prompt_path))}",
                "status": "pending" if args.apply else "prepared",
            }
        )

    run_summary = {
        "generated_at": datetime.now(UTC).isoformat(),
        "stage": args.stage,
        "apply": args.apply,
        "model": args.model,
        "reasoning_effort": args.reasoning_effort,
        "workdir": str(args.workdir),
        "schema_file": str(args.schema_file),
        "max_parallel": args.max_parallel,
        "collections_file": str(args.collections_file),
        "previous_run_dir": str(args.previous_run_dir) if args.previous_run_dir else None,
        "jobs": manifest,
    }
    write_json(run_dir / "run_manifest.json", run_summary)

    if args.apply:
        launch_jobs(run_dir, manifest, max_parallel=args.max_parallel, schema=schema)
        run_summary["completed_at"] = datetime.now(UTC).isoformat()
        write_json(run_dir / "run_manifest.json", run_summary | {"jobs": manifest})

    print(run_dir)


if __name__ == "__main__":
    main()
