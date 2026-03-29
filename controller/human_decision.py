#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from controller.reviewer_memory import knowledge_ref_strings
from controller.stage_definitions import next_stage_name


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = PROJECT_ROOT / "schemas" / "human_decision.schema.json"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_human_decision(path: Path, *, schema_path: Path = DEFAULT_SCHEMA) -> dict[str, Any]:
    payload = read_json(path)
    schema = read_json(schema_path)
    jsonschema.validate(payload, schema)
    if not isinstance(payload, dict):
        raise ValueError("human decision payload must be an object")
    return payload


def prepare_resume_state(
    *,
    manifest: dict[str, Any],
    decision: dict[str, Any],
    collection_slug: str,
) -> dict[str, Any]:
    history = manifest.get("history")
    if not isinstance(history, list) or not history:
        raise ValueError("resume lineage manifest has no history")
    last = history[-1]
    last_stage = str(last.get("stage") or "")
    last_run_dir = str(last.get("run_dir") or "")
    last_attempt_index = int(last.get("attempt_index") or 1)
    final_state = str(manifest.get("final_state") or "")
    if final_state not in {"decision_pending_user", "manual_review"}:
        raise ValueError(f"resume requires a stopped lineage, found final_state={final_state or 'unknown'}")
    if decision.get("collection_slug") != collection_slug:
        raise ValueError("human decision collection does not match the lineage")
    if decision.get("stage") != last_stage:
        raise ValueError("human decision stage does not match the lineage stop stage")
    if not last_run_dir:
        raise ValueError("resume lineage manifest is missing the previous run directory")

    requested = str(decision.get("decision") or "")
    if requested == "retry_same_stage":
        current_stage = last_stage
        attempt_index = last_attempt_index + 1
    elif requested == "advance":
        current_stage = next_stage_name(last_stage)
        if current_stage is None:
            raise ValueError(f"cannot advance beyond terminal stage `{last_stage}`")
        attempt_index = 1
    elif requested == "stop_exhausted":
        current_stage = last_stage
        attempt_index = last_attempt_index
    else:
        raise ValueError(f"unsupported human decision `{requested}`")

    return {
        "current_stage": current_stage,
        "previous_run_dir": Path(last_run_dir),
        "attempt_index": attempt_index,
        "previous_improvement": last.get("improvement") if isinstance(last.get("improvement"), dict) else {},
        "requested_decision": requested,
    }


def synthesize_review_plan_from_human_decision(
    *,
    decision: dict[str, Any],
    previous_improvement: dict[str, Any] | None,
    output_path: Path,
) -> Path:
    previous = previous_improvement or {}
    stage = str(decision["stage"])
    instructions = list(decision.get("instructions") or [])
    plan = {
        "collection_slug": decision["collection_slug"],
        "stage": stage,
        "failure_class": str(previous.get("failure_class") or "decision_pending_user"),
        "overall_progress_percent": float(previous.get("overall_progress_percent") or 0.0),
        "stage_completion_percent": float(previous.get("stage_completion_percent") or 0.0),
        "count_completeness_percent": float(previous.get("count_completeness_percent") or 0.0),
        "eta_health_percent": float(previous.get("eta_health_percent") or 0.0),
        "quality_fit_percent": float(previous.get("quality_fit_percent") or 0.0),
        "success_threshold_percent": float(previous.get("success_threshold_percent") or 80.0),
        "issue_labels": list(previous.get("issue_labels") or []),
        "decision": decision["decision"],
        "decision_reason": decision["decision_reason"],
        "problem_tags": list(previous.get("problem_tags") or []) + ["decision:human_override"],
        "matched_solution_ids": list(previous.get("matched_solution_ids") or []),
        "knowledge_refs": list(previous.get("knowledge_refs") or knowledge_ref_strings(stage)),
        "improvement_hypotheses": instructions,
        "changes_to_try": instructions,
        "expected_gain_percent": 0.0,
        "target_progress_percent": float(
            decision.get("target_progress_percent")
            or previous.get("target_progress_percent")
            or previous.get("success_threshold_percent")
            or 80.0
        ),
        "user_decision_required": False,
        "user_decision_question": None,
        "confidence": "high",
    }
    eta_ceiling = decision.get("approved_eta_ceiling_hours")
    if eta_ceiling not in {None, ""}:
        plan["decision_reason"] = (
            f"{plan['decision_reason']} User-approved ETA ceiling for this branch: {eta_ceiling} hours."
        )
    scope_override = decision.get("scope_override")
    if scope_override:
        plan["decision_reason"] = f"{plan['decision_reason']} Scope override: {scope_override}."
    notes = decision.get("notes")
    if notes:
        plan["decision_reason"] = f"{plan['decision_reason']} Notes: {notes}."
    write_json(output_path, plan)
    return output_path
