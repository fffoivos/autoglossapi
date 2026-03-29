#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from controller.launch_codex_exec_harness import DEFAULT_COLLECTIONS_FILE, PROJECT_ROOT
from controller.stage_definitions import STAGE_ORDER, next_stage_name


DEFAULT_LINEAGES_ROOT = PROJECT_ROOT / "lineages"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a persistent stage/review lineage loop for one collection."
    )
    parser.add_argument("--collection-slug", required=True)
    parser.add_argument("--collections-file", type=Path, default=DEFAULT_COLLECTIONS_FILE)
    parser.add_argument("--lineages-root", type=Path, default=DEFAULT_LINEAGES_ROOT)
    parser.add_argument("--runs-root", type=Path, default=PROJECT_ROOT / "runs")
    parser.add_argument("--start-stage", choices=sorted(STAGE_ORDER), default="discover")
    parser.add_argument("--through-stage", choices=sorted(STAGE_ORDER), default=STAGE_ORDER[-1])
    parser.add_argument("--initial-previous-run-dir", type=Path, default=None)
    parser.add_argument("--max-attempts-per-stage", type=int, default=4)
    parser.add_argument("--success-threshold", type=float, default=80.0)
    parser.add_argument("--codex-bin", default="codex")
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument("--reasoning-effort", default="xhigh")
    parser.add_argument("--sandbox-mode", default="danger-full-access")
    return parser.parse_args()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _stage_index(stage: str) -> int:
    return STAGE_ORDER.index(stage)


def ensure_stage_sequence(start_stage: str, through_stage: str) -> None:
    if _stage_index(through_stage) < _stage_index(start_stage):
        raise SystemExit(
            f"`--through-stage` ({through_stage}) must not come before `--start-stage` ({start_stage})"
        )


def make_lineage_dir(root: Path, slug: str) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    lineage_dir = root / f"{stamp}_{slug}"
    lineage_dir.mkdir(parents=True, exist_ok=False)
    return lineage_dir


def run_command(command: list[str], *, cwd: Path) -> str:
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    return result.stdout.strip()


def ensure_report(job_dir: Path, *, collection_slug: str, stage: str) -> Path:
    report_path = job_dir / "final.json"
    if report_path.exists():
        return report_path
    synthetic_report = {
        "collection_slug": collection_slug,
        "stage": stage,
        "status": "partial",
        "repo_root_url": None,
        "repo_host": None,
        "platform_guess": "unknown",
        "summary": "Synthetic placeholder report created because the worker did not emit final.json.",
        "available_subcollections": [],
        "website_levels": {
            "repo_home": None,
            "collection_entry": None,
            "list_pages": None,
            "pagination": None,
            "item_page": None,
            "pdf_access": None,
        },
        "relevant_collection_urls": [],
        "content_type_summary": [],
        "claimed_item_count": None,
        "observed_item_count": None,
        "count_evidence": {
            "repository_claimed_total": None,
            "repository_claim_unit": None,
            "repository_claim_source": None,
            "api_reported_total": None,
            "api_report_unit": None,
            "scraper_observed_total": None,
            "scraper_observed_unit": None,
            "collection_count_comparison": [],
            "discrepancy_note": "Synthetic placeholder report because the worker did not emit final.json.",
        },
        "throughput_evidence": {
            "metadata_probe_requests": 0,
            "metadata_probe_window_seconds": 0.0,
            "metadata_probe_rps": None,
            "metadata_probe_note": "No probe completed.",
            "file_probe_downloads": 0,
            "file_probe_total_bytes": 0,
            "file_probe_window_seconds": 0.0,
            "file_probe_bytes_per_second": None,
            "file_probe_files_per_hour": None,
            "suggested_parallel_downloads": None,
            "estimated_total_items": None,
            "estimated_total_bytes": None,
            "estimated_eta_hours": None,
            "eta_basis_note": "No probe completed.",
            "slow_eta_threshold_hours": 48.0,
            "threshold_breach": False,
            "investigation_trigger_recommendation": None,
        },
        "pagination_strategy": "unknown",
        "pdf_detection_strategy": "unknown",
        "metadata_richness_note": "unknown",
        "metadata_fields": [],
        "priority_assessment": {
            "language_fit": "unknown",
            "content_quality_fit": "unknown",
            "extraction_ease": "unknown",
            "overall_priority": "unknown",
        },
        "sample_documents": [],
        "failed_checklist_ids": [],
        "tried_hypotheses": [],
        "alternative_hypotheses": [],
        "best_next_hypothesis": None,
        "stuck_reason": "Worker failed before producing a report.",
        "blocked_on": [],
        "exhausted_paths": [],
        "confidence": "low",
        "needs_human_input": False,
        "checklist": [],
        "artifacts": [],
        "risks": [],
        "recommended_next_step": "Inspect the runtime failure and retry with a repair prompt.",
    }
    report_path = job_dir / "synthetic_final.json"
    write_json(report_path, synthetic_report)
    return report_path


def launch_stage_run(
    *,
    collection_slug: str,
    collections_file: Path,
    runs_root: Path,
    stage: str,
    previous_run_dir: Path | None,
    review_plan_path: Path | None,
    args: argparse.Namespace,
) -> Path:
    command = [
        "python3",
        str(PROJECT_ROOT / "controller" / "launch_codex_exec_harness.py"),
        "--stage",
        stage,
        "--collections-file",
        str(collections_file),
        "--output-root",
        str(runs_root),
        "--workdir",
        str(PROJECT_ROOT),
        "--codex-bin",
        args.codex_bin,
        "--model",
        args.model,
        "--reasoning-effort",
        args.reasoning_effort,
        "--sandbox-mode",
        args.sandbox_mode,
        "--max-parallel",
        "1",
        "--collection-slugs",
        collection_slug,
        "--apply",
    ]
    if previous_run_dir is not None:
        command.extend(["--previous-run-dir", str(previous_run_dir)])
    if review_plan_path is not None:
        command.extend(["--review-plan-path", str(review_plan_path)])
    run_dir_text = run_command(command, cwd=PROJECT_ROOT)
    return Path(run_dir_text)


def score_stage_attempt(
    *,
    report_path: Path,
    validation_path: Path,
    job_dir: Path,
    attempt_index: int,
    max_attempts: int,
    success_threshold: float,
) -> Path:
    output_path = job_dir / "progress_evaluation.json"
    command = [
        "python3",
        str(PROJECT_ROOT / "controller" / "progress_scoring.py"),
        "--report",
        str(report_path),
        "--validation",
        str(validation_path),
        "--attempt-index",
        str(attempt_index),
        "--max-attempts",
        str(max_attempts),
        "--success-threshold",
        str(success_threshold),
        "--output",
        str(output_path),
    ]
    run_command(command, cwd=PROJECT_ROOT)
    return output_path


def review_stage_attempt(
    *,
    report_path: Path,
    validation_path: Path,
    progress_path: Path,
    events_path: Path | None,
    job_dir: Path,
    args: argparse.Namespace,
) -> Path:
    output_path = job_dir / "improvement_plan.json"
    command = [
        "python3",
        str(PROJECT_ROOT / "controller" / "review_stage_outcome.py"),
        "--report",
        str(report_path),
        "--validation",
        str(validation_path),
        "--progress",
        str(progress_path),
        "--output",
        str(output_path),
        "--events-output",
        str(job_dir / "review_events.jsonl"),
        "--codex-bin",
        args.codex_bin,
        "--model",
        args.model,
        "--reasoning-effort",
        args.reasoning_effort,
        "--sandbox-mode",
        args.sandbox_mode,
    ]
    if events_path is not None and events_path.exists():
        command.extend(["--events", str(events_path)])
    run_command(command, cwd=PROJECT_ROOT)
    return output_path


def main() -> None:
    args = parse_args()
    ensure_stage_sequence(args.start_stage, args.through_stage)
    if args.start_stage != "discover" and args.initial_previous_run_dir is None:
        raise SystemExit("`--initial-previous-run-dir` is required when starting after `discover`")
    lineage_dir = make_lineage_dir(args.lineages_root, args.collection_slug)
    runs_root = args.runs_root
    history: list[dict[str, Any]] = []
    current_stage = args.start_stage
    previous_run_dir = args.initial_previous_run_dir
    review_plan_path: Path | None = None
    attempt_index = 1
    final_state = "running"
    final_reason = None

    manifest_path = lineage_dir / "loop_manifest.json"

    while True:
        run_dir = launch_stage_run(
            collection_slug=args.collection_slug,
            collections_file=args.collections_file,
            runs_root=runs_root,
            stage=current_stage,
            previous_run_dir=previous_run_dir,
            review_plan_path=review_plan_path,
            args=args,
        )
        job_dir = run_dir / "jobs" / args.collection_slug
        validation_path = job_dir / "validation.json"
        next_action_path = job_dir / "next_action.json"
        events_path = job_dir / "events.jsonl"
        report_path = ensure_report(job_dir, collection_slug=args.collection_slug, stage=current_stage)
        progress_path = score_stage_attempt(
            report_path=report_path,
            validation_path=validation_path,
            job_dir=job_dir,
            attempt_index=attempt_index,
            max_attempts=args.max_attempts_per_stage,
            success_threshold=args.success_threshold,
        )
        improvement_path = review_stage_attempt(
            report_path=report_path,
            validation_path=validation_path,
            progress_path=progress_path,
            events_path=events_path if events_path.exists() else None,
            job_dir=job_dir,
            args=args,
        )

        validation = read_json(validation_path)
        next_action = read_json(next_action_path) if next_action_path.exists() else None
        progress = read_json(progress_path)
        improvement = read_json(improvement_path)
        history.append(
            {
                "collection_slug": args.collection_slug,
                "stage": current_stage,
                "attempt_index": attempt_index,
                "run_dir": str(run_dir),
                "job_dir": str(job_dir),
                "report_path": str(report_path),
                "validation_path": str(validation_path),
                "next_action_path": str(next_action_path) if next_action_path.exists() else None,
                "progress_path": str(progress_path),
                "improvement_plan_path": str(improvement_path),
                "validation": validation,
                "next_action": next_action,
                "progress": progress,
                "improvement": improvement,
            }
        )

        decision = str(improvement.get("decision") or "")
        write_json(
            manifest_path,
            {
                "collection_slug": args.collection_slug,
                "lineage_dir": str(lineage_dir),
                "start_stage": args.start_stage,
                "through_stage": args.through_stage,
                "current_stage": current_stage,
                "attempt_index": attempt_index,
                "history": history,
                "final_state": final_state,
                "final_reason": final_reason,
            },
        )

        if decision == "decision_pending_user":
            final_state = "decision_pending_user"
            final_reason = improvement.get("decision_reason")
            break

        if decision == "stop_exhausted":
            final_state = "stop_exhausted"
            final_reason = improvement.get("decision_reason")
            break

        if decision == "advance":
            if current_stage == args.through_stage or next_stage_name(current_stage) is None:
                final_state = "completed"
                final_reason = improvement.get("decision_reason")
                break
            previous_run_dir = run_dir
            review_plan_path = improvement_path
            current_stage = str(next_stage_name(current_stage))
            attempt_index = 1
            continue

        if decision == "retry_same_stage":
            if attempt_index >= args.max_attempts_per_stage:
                final_state = "decision_pending_user"
                final_reason = (
                    "Review asked for another retry, but the max attempts per stage were already used. "
                    "User review is required."
                )
                break
            previous_run_dir = run_dir
            review_plan_path = improvement_path
            attempt_index += 1
            continue

        final_state = "manual_review"
        final_reason = f"Unexpected improvement-plan decision: {decision or 'missing'}"
        break

    write_json(
        manifest_path,
        {
            "collection_slug": args.collection_slug,
            "lineage_dir": str(lineage_dir),
            "start_stage": args.start_stage,
            "through_stage": args.through_stage,
            "current_stage": current_stage,
            "attempt_index": attempt_index,
            "history": history,
            "final_state": final_state,
            "final_reason": final_reason,
        },
    )
    print(lineage_dir)


if __name__ == "__main__":
    main()
