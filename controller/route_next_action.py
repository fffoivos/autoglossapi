#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from controller.stage_definitions import next_stage_name


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Route the next action for a collection lineage.")
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def decide_next_action(validation: dict[str, Any]) -> dict[str, Any]:
    stage = str(validation.get("stage") or "")
    failure_class = str(validation.get("failure_class") or "")
    next_stage = next_stage_name(stage) if failure_class == "success" else None
    decision = {
        "collection_slug": validation.get("collection_slug"),
        "current_stage": stage,
        "failure_class": failure_class,
        "decision": "retry_same_stage",
        "next_stage": next_stage,
        "retry_prompt_mode": None,
        "reason": "",
    }

    if failure_class == "success":
        decision["decision"] = "advance"
        decision["reason"] = "stage is promotable"
        return decision
    if failure_class == "runtime_failed":
        decision["decision"] = "retry_same_stage"
        decision["retry_prompt_mode"] = "runtime_repair"
        decision["reason"] = "worker process failed before producing a valid stage report"
        return decision
    if failure_class == "schema_failed":
        decision["decision"] = "retry_same_stage"
        decision["retry_prompt_mode"] = "schema_repair"
        decision["reason"] = "stage output did not satisfy the report schema"
        return decision
    if failure_class == "evidence_failed":
        decision["decision"] = "retry_same_stage"
        decision["retry_prompt_mode"] = "missing_evidence"
        decision["reason"] = "required evidence for the checklist is still missing"
        return decision
    if failure_class == "partial":
        decision["decision"] = "retry_same_stage"
        decision["retry_prompt_mode"] = "unresolved_checklist"
        decision["reason"] = "stage completed only partially"
        return decision
    if failure_class == "blocked":
        decision["decision"] = "retry_same_stage"
        decision["retry_prompt_mode"] = "alternative_hypotheses"
        decision["reason"] = "agent reported blockers and should explore alternatives"
        return decision
    if failure_class == "exhausted":
        decision["decision"] = "escalate"
        decision["reason"] = "agent exhausted the reasonable paths it knew about"
        return decision

    decision["decision"] = "manual_review"
    decision["reason"] = f"unknown failure class: {failure_class}"
    return decision


def main() -> None:
    args = parse_args()
    validation = read_json(args.validation)
    decision = decide_next_action(validation)
    if args.output:
        write_json(args.output, decision)
    else:
        print(json.dumps(decision, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
