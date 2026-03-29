#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import jsonschema

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from controller.stage_definitions import STAGES


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a stage report against schema and stage evidence requirements.")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--schema", type=Path, default=Path(__file__).resolve().parents[1] / "schemas" / "stage_report.schema.json")
    parser.add_argument("--job-dir", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _artifact_issue(job_dir: Path | None, artifact: dict[str, Any]) -> str | None:
    path_or_url = str(artifact.get("path_or_url") or "").strip()
    if not path_or_url:
        return "artifact has empty path_or_url"
    parsed = urlparse(path_or_url)
    if parsed.scheme in {"http", "https", "s3"}:
        return None
    if job_dir is None:
        return None
    candidate = Path(path_or_url)
    if not candidate.is_absolute():
        candidate = job_dir / candidate
    if candidate.exists():
        return None
    return f"artifact missing: {path_or_url}"


def validate_report_payload(report: dict[str, Any], schema: dict[str, Any], job_dir: Path | None = None) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "collection_slug": report.get("collection_slug"),
        "stage": report.get("stage"),
        "schema_valid": False,
        "failure_class": "schema_failed",
        "promotable": False,
        "missing_checklist_ids": [],
        "non_done_checklist_ids": [],
        "artifact_issues": [],
        "notes": [],
    }

    try:
        jsonschema.validate(report, schema)
    except jsonschema.ValidationError as exc:
        summary["notes"].append(f"schema validation failed: {exc.message}")
        return summary

    stage_name = str(report["stage"])
    stage_spec = STAGES.get(stage_name)
    if stage_spec is None:
        summary["notes"].append(f"unknown stage: {stage_name}")
        return summary

    summary["schema_valid"] = True
    checklist = {item["id"]: item for item in report.get("checklist", [])}
    required_ids = [item_id for item_id, _ in stage_spec.checklist]
    missing_ids = [item_id for item_id in required_ids if item_id not in checklist]
    summary["missing_checklist_ids"] = missing_ids
    if missing_ids:
        summary["failure_class"] = "evidence_failed"
        summary["notes"].append("missing required checklist items")
        return summary

    non_done = [
        item_id
        for item_id in required_ids
        if checklist[item_id]["status"] not in {"done", "not_applicable"}
    ]
    summary["non_done_checklist_ids"] = non_done

    artifact_issues = []
    for artifact in report.get("artifacts", []):
        issue = _artifact_issue(job_dir, artifact)
        if issue:
            artifact_issues.append(issue)
    summary["artifact_issues"] = artifact_issues

    status = str(report["status"])
    if status == "success" and not non_done and not artifact_issues:
        summary["failure_class"] = "success"
        summary["promotable"] = True
        return summary

    if status == "exhausted":
        summary["failure_class"] = "exhausted"
        summary["notes"].append("agent marked the lineage exhausted")
        return summary

    if status == "blocked":
        summary["failure_class"] = "blocked"
        return summary

    if artifact_issues:
        summary["failure_class"] = "evidence_failed"
        summary["notes"].append("artifact references are incomplete")
        return summary

    if non_done or status == "partial":
        summary["failure_class"] = "partial"
        return summary

    summary["failure_class"] = "evidence_failed"
    summary["notes"].append(f"unrecognized state for status={status}")
    return summary


def main() -> None:
    args = parse_args()
    report = read_json(args.report)
    schema = read_json(args.schema)
    job_dir = args.job_dir or args.report.parent
    result = validate_report_payload(report=report, schema=schema, job_dir=job_dir)
    if args.output:
        write_json(args.output, result)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
