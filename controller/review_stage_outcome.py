#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

import jsonschema

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = PROJECT_ROOT / "schemas" / "improvement_plan.schema.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a second-pass Codex review over a stage outcome and emit an improvement plan."
    )
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--progress", type=Path, required=True)
    parser.add_argument("--events", type=Path, default=None)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--events-output", type=Path, default=None)
    parser.add_argument("--codex-bin", default="codex")
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument("--reasoning-effort", default="xhigh")
    parser.add_argument("--sandbox-mode", default="danger-full-access")
    return parser.parse_args()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _issue_label_strings(progress: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    for entry in progress.get("issue_labels", []):
        if not isinstance(entry, dict):
            continue
        label = str(entry.get("label") or "issue")
        percent = entry.get("percent")
        status = str(entry.get("status") or "")
        labels.append(f"{label}:{percent}%:{status}")
    return labels


def fallback_review_plan(report: dict[str, Any], validation: dict[str, Any], progress: dict[str, Any]) -> dict[str, Any]:
    failure_class = str(validation.get("failure_class") or "unknown")
    overall = float(progress.get("overall_progress_percent") or 0.0)
    stage_completion = float(progress.get("stage_completion_percent") or 0.0)
    count_completion = float(progress.get("count_completeness_percent") or 0.0)
    eta_health = float(progress.get("eta_health_percent") or 0.0)
    quality_fit = float(progress.get("quality_fit_percent") or 0.0)
    success_threshold = float(progress.get("success_threshold_percent") or 80.0)
    user_decision_pending = bool(progress.get("user_decision_pending"))
    user_decision_reason = progress.get("user_decision_reason")

    decision = "retry_same_stage"
    decision_reason = "Another bounded retry should improve completeness."
    expected_gain = 10.0
    user_decision_required = False
    user_decision_question = None
    if user_decision_pending:
        decision = "decision_pending_user"
        decision_reason = str(user_decision_reason or "The run reached a condition that requires user review.")
        expected_gain = 0.0
        user_decision_required = True
        user_decision_question = (
            "ETA, completeness, or repository constraints need a non-routine decision. "
            "Should the lineage keep pushing, accept partial coverage, or change strategy?"
        )
    elif failure_class == "success" and overall >= success_threshold:
        decision = "advance"
        decision_reason = "The stage cleared the success threshold with no forced user-decision stop."
        expected_gain = 5.0
    elif failure_class == "exhausted":
        decision = "decision_pending_user"
        decision_reason = "The lineage appears exhausted and needs user review of the remaining options."
        expected_gain = 0.0
        user_decision_required = True
        user_decision_question = "The lineage is exhausted. Review whether to stop, narrow scope, or change tactics."
    elif overall < 50.0 and progress.get("attempt_index", 1) >= progress.get("max_attempts", 4):
        decision = "decision_pending_user"
        decision_reason = "Progress stayed weak across the allowed attempts."
        expected_gain = 0.0
        user_decision_required = True
        user_decision_question = "Progress remains weak after repeated attempts. Choose whether to continue or pause."

    return {
        "collection_slug": report.get("collection_slug"),
        "stage": report.get("stage"),
        "failure_class": failure_class,
        "overall_progress_percent": round(overall, 2),
        "stage_completion_percent": round(stage_completion, 2),
        "count_completeness_percent": round(count_completion, 2),
        "eta_health_percent": round(eta_health, 2),
        "quality_fit_percent": round(quality_fit, 2),
        "success_threshold_percent": round(success_threshold, 2),
        "issue_labels": _issue_label_strings(progress),
        "decision": decision,
        "decision_reason": decision_reason,
        "improvement_hypotheses": list(report.get("alternative_hypotheses") or report.get("tried_hypotheses") or []),
        "changes_to_try": list(report.get("failed_checklist_ids") or validation.get("non_done_checklist_ids") or []),
        "expected_gain_percent": round(expected_gain, 2),
        "user_decision_required": user_decision_required,
        "user_decision_question": user_decision_question,
        "confidence": "medium",
    }


def build_prompt(
    *,
    report_path: Path,
    validation_path: Path,
    progress_path: Path,
    events_path: Path | None,
    schema_path: Path,
) -> str:
    events_line = f"- events_path: `{events_path}`\n" if events_path else ""
    return f"""You are the stage-review agent for automated GlossAPI upstream recovery.

Mission:
- Maximize large quantities of high-quality Greek text and other useful Greek artifacts, including images when they add real value.
- Push toward complete coverage whenever feasible.
- Prefer plans that can complete the full download in roughly 48 hours or less.
- If ETA exceeds that target or the next move requires a non-routine tradeoff, choose `decision_pending_user`.
- Use exact numbers from the supplied artifacts whenever possible.

Read these artifacts before deciding:
- report_path: `{report_path}`
- validation_path: `{validation_path}`
- progress_path: `{progress_path}`
{events_line}Decision rules:
- Choose `advance` only if the current stage is already good enough, typically at or above the success threshold, and the likely incremental gain from more retries is small.
- Choose `retry_same_stage` only if there is a concrete, bounded set of improvements that should materially increase completeness or confidence.
- Choose `decision_pending_user` for ETA breaches, hard repository constraints, exhausted paths, or any tradeoff that should be reviewed by the user.
- Choose `stop_exhausted` only if nothing meaningful remains and there is no real user decision left to make.

Output must be JSON only and must satisfy `{schema_path}`.
"""


def validate_plan(plan: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    jsonschema.validate(plan, schema)
    return plan


def main() -> None:
    args = parse_args()
    report = read_json(args.report)
    validation = read_json(args.validation)
    progress = read_json(args.progress)
    schema = read_json(args.schema)
    prompt = build_prompt(
        report_path=args.report,
        validation_path=args.validation,
        progress_path=args.progress,
        events_path=args.events,
        schema_path=args.schema,
    )

    prompt_path = args.output.parent / "review_prompt.txt"
    prompt_path.write_text(prompt, encoding="utf-8")

    command = [
        args.codex_bin,
        "exec",
        "--skip-git-repo-check",
        "--cd",
        str(PROJECT_ROOT),
        "--model",
        args.model,
        "-c",
        f'model_reasoning_effort="{args.reasoning_effort}"',
        "-c",
        'approval_policy="never"',
        "-s",
        args.sandbox_mode,
        "--add-dir",
        str(args.report.parent),
        "--output-schema",
        str(args.schema),
        "-o",
        str(args.output),
        "--json",
        "-",
    ]

    review_failed = False
    failure_note = None
    if args.events_output is not None:
        events_handle = args.events_output.open("w", encoding="utf-8")
    else:
        events_handle = None
    prompt_handle = prompt_path.open("r", encoding="utf-8")
    try:
        result = subprocess.run(
            command,
            stdin=prompt_handle,
            stdout=events_handle if events_handle is not None else subprocess.DEVNULL,
            stderr=subprocess.STDOUT if events_handle is not None else subprocess.DEVNULL,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            review_failed = True
            failure_note = f"codex review exited with return code {result.returncode}"
    finally:
        prompt_handle.close()
        if events_handle is not None:
            events_handle.close()

    if not review_failed and args.output.exists():
        try:
            plan = read_json(args.output)
            validate_plan(plan, schema)
        except (json.JSONDecodeError, jsonschema.ValidationError) as exc:
            review_failed = True
            failure_note = f"invalid review plan output: {exc}"

    if review_failed or not args.output.exists():
        fallback = fallback_review_plan(report=report, validation=validation, progress=progress)
        if failure_note:
            fallback["decision_reason"] = f"{fallback['decision_reason']} Fallback used because {failure_note}."
        validate_plan(fallback, schema)
        write_json(args.output, fallback)

    print(args.output)


if __name__ == "__main__":
    main()
