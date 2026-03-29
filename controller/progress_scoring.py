#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_SUCCESS_THRESHOLD = 80.0
DEFAULT_MAX_ATTEMPTS = 4
QUALITY_SCORES = {
    "very_high": 100.0,
    "high": 100.0,
    "medium": 70.0,
    "moderate": 70.0,
    "low": 30.0,
    "very_low": 15.0,
    "unknown": 50.0,
    "n/a": 50.0,
    "na": 50.0,
}
CHECKLIST_STATUS_SCORES = {
    "done": 100.0,
    "not_applicable": 100.0,
    "partial": 50.0,
    "blocked": 0.0,
    "todo": 0.0,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score a stage attempt with exact completeness and ETA percentages."
    )
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--attempt-index", type=int, default=1)
    parser.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    parser.add_argument("--success-threshold", type=float, default=DEFAULT_SUCCESS_THRESHOLD)
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _round(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 2)


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _quality_score(value: Any) -> float:
    if value is None:
        return QUALITY_SCORES["unknown"]
    lowered = str(value).strip().lower()
    if not lowered:
        return QUALITY_SCORES["unknown"]
    return QUALITY_SCORES.get(lowered, QUALITY_SCORES["unknown"])


def _label_status(percent: float) -> str:
    if percent >= 100.0:
        return "complete"
    if percent >= 80.0:
        return "strong"
    if percent >= 50.0:
        return "partial"
    return "weak"


def _checklist_scores(report: dict[str, Any]) -> tuple[list[dict[str, Any]], float]:
    checklist_scores: list[dict[str, Any]] = []
    checklist = report.get("checklist") or []
    if not checklist:
        return checklist_scores, 0.0
    total = 0.0
    for item in checklist:
        item_id = str(item.get("id") or "")
        label = str(item.get("label") or item_id)
        status = str(item.get("status") or "todo")
        score = CHECKLIST_STATUS_SCORES.get(status, 0.0)
        total += score
        checklist_scores.append(
            {
                "id": item_id,
                "label": label,
                "status": status,
                "percent": _round(score),
                "note": item.get("evidence"),
            }
        )
    return checklist_scores, total / len(checklist)


def _count_completeness(report: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    count_evidence = report.get("count_evidence") or {}
    claimed = (
        count_evidence.get("api_reported_total")
        or count_evidence.get("repository_claimed_total")
        or report.get("claimed_item_count")
    )
    observed = count_evidence.get("scraper_observed_total") or report.get("observed_item_count")
    claimed_value = _as_float(claimed)
    observed_value = _as_float(observed)
    percent = 0.0
    if claimed_value and claimed_value > 0 and observed_value is not None:
        percent = min(100.0, (observed_value / claimed_value) * 100.0)
    elif observed_value and observed_value > 0:
        percent = 100.0
    return percent, {
        "claimed_total": claimed_value,
        "observed_total": observed_value,
        "claim_unit": count_evidence.get("api_report_unit")
        or count_evidence.get("repository_claim_unit")
        or "items",
    }


def _eta_health(report: dict[str, Any]) -> tuple[float, dict[str, Any], bool]:
    throughput = report.get("throughput_evidence") or {}
    eta_hours = _as_float(throughput.get("estimated_eta_hours"))
    threshold_hours = _as_float(throughput.get("slow_eta_threshold_hours")) or 48.0
    threshold_breach = bool(throughput.get("threshold_breach"))
    if eta_hours is None:
        return 0.0, {"eta_hours": None, "threshold_hours": threshold_hours}, False
    if eta_hours <= 0:
        return 100.0, {"eta_hours": eta_hours, "threshold_hours": threshold_hours}, threshold_breach
    percent = 100.0 if eta_hours <= threshold_hours else max(0.0, (threshold_hours / eta_hours) * 100.0)
    return percent, {"eta_hours": eta_hours, "threshold_hours": threshold_hours}, threshold_breach


def _quality_fit(report: dict[str, Any]) -> float:
    priority = report.get("priority_assessment") or {}
    scores = [
        _quality_score(priority.get("language_fit")),
        _quality_score(priority.get("content_quality_fit")),
        _quality_score(priority.get("extraction_ease")),
        _quality_score(priority.get("overall_priority")),
    ]
    return sum(scores) / len(scores)


def _issue_labels(
    stage_completion_percent: float,
    count_completeness_percent: float,
    eta_health_percent: float,
    quality_fit_percent: float,
    overall_progress_percent: float,
) -> list[dict[str, Any]]:
    issues = [
        ("stage_completion", stage_completion_percent, "Progress against the stage checklist."),
        ("count_completeness", count_completeness_percent, "Observed coverage relative to reported counts."),
        ("eta_health", eta_health_percent, "Download ETA health versus the 48-hour target."),
        ("quality_fit", quality_fit_percent, "Greek fit, content quality, and extraction ease."),
        ("overall_progress", overall_progress_percent, "Weighted summary of current stage health."),
    ]
    return [
        {
            "label": label,
            "percent": _round(percent),
            "status": _label_status(percent),
            "note": note,
        }
        for label, percent, note in issues
    ]


def score_progress(
    report: dict[str, Any],
    validation: dict[str, Any],
    *,
    attempt_index: int,
    max_attempts: int,
    success_threshold: float,
) -> dict[str, Any]:
    checklist_scores, stage_completion_percent = _checklist_scores(report)
    count_completeness_percent, count_numbers = _count_completeness(report)
    eta_health_percent, eta_numbers, threshold_breach = _eta_health(report)
    quality_fit_percent = _quality_fit(report)
    overall_progress_percent = (
        0.40 * stage_completion_percent
        + 0.25 * count_completeness_percent
        + 0.20 * eta_health_percent
        + 0.15 * quality_fit_percent
    )
    failure_class = str(validation.get("failure_class") or "unknown")
    needs_human_input = bool(report.get("needs_human_input"))
    user_decision_pending = any(
        [
            needs_human_input,
            threshold_breach,
            failure_class == "exhausted",
            attempt_index >= max_attempts and overall_progress_percent < success_threshold,
        ]
    )
    user_decision_reason = None
    if needs_human_input:
        user_decision_reason = "worker explicitly requested human input"
    elif threshold_breach:
        user_decision_reason = "recent ETA exceeds the 48-hour target"
    elif failure_class == "exhausted":
        user_decision_reason = "lineage is marked exhausted"
    elif attempt_index >= max_attempts and overall_progress_percent < success_threshold:
        user_decision_reason = "attempt budget exhausted before reaching the success threshold"

    can_advance = failure_class == "success" and overall_progress_percent >= success_threshold and not user_decision_pending
    should_retry = (
        not can_advance
        and not user_decision_pending
        and attempt_index < max_attempts
        and failure_class not in {"exhausted"}
    )
    issue_labels = _issue_labels(
        stage_completion_percent=stage_completion_percent,
        count_completeness_percent=count_completeness_percent,
        eta_health_percent=eta_health_percent,
        quality_fit_percent=quality_fit_percent,
        overall_progress_percent=overall_progress_percent,
    )
    throughput = report.get("throughput_evidence") or {}

    return {
        "collection_slug": report.get("collection_slug"),
        "stage": report.get("stage"),
        "attempt_index": attempt_index,
        "max_attempts": max_attempts,
        "failure_class": failure_class,
        "success_threshold_percent": _round(success_threshold),
        "checklist_scores": checklist_scores,
        "stage_completion_percent": _round(stage_completion_percent),
        "count_completeness_percent": _round(count_completeness_percent),
        "eta_health_percent": _round(eta_health_percent),
        "quality_fit_percent": _round(quality_fit_percent),
        "overall_progress_percent": _round(overall_progress_percent),
        "issue_labels": issue_labels,
        "user_decision_pending": user_decision_pending,
        "user_decision_reason": user_decision_reason,
        "can_advance": can_advance,
        "should_retry": should_retry,
        "exact_numbers": {
            "claimed_total": count_numbers["claimed_total"],
            "observed_total": count_numbers["observed_total"],
            "count_unit": count_numbers["claim_unit"],
            "estimated_eta_hours": eta_numbers["eta_hours"],
            "slow_eta_threshold_hours": eta_numbers["threshold_hours"],
            "metadata_probe_rps": _as_float(throughput.get("metadata_probe_rps")),
            "file_probe_bytes_per_second": _as_float(throughput.get("file_probe_bytes_per_second")),
            "suggested_parallel_downloads": throughput.get("suggested_parallel_downloads"),
            "threshold_breach": threshold_breach,
        },
    }


def main() -> None:
    args = parse_args()
    report = read_json(args.report)
    validation = read_json(args.validation)
    scored = score_progress(
        report=report,
        validation=validation,
        attempt_index=args.attempt_index,
        max_attempts=args.max_attempts,
        success_threshold=args.success_threshold,
    )
    if args.output:
        write_json(args.output, scored)
    else:
        print(json.dumps(scored, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
