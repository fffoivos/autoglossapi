#!/usr/bin/env python3

from __future__ import annotations

import csv
import json
import re
import subprocess
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
COLLECTIONS_DIR = REPO_ROOT / "config" / "collections"
RUNS_DIR = REPO_ROOT / "runs"
TRACKING_DIR = REPO_ROOT / "tracking"
GENERATED_DIR = TRACKING_DIR / "generated"
MANUAL_DIR = TRACKING_DIR / "manual"


TEXT_KEYWORDS = {
    "thesis",
    "article",
    "εργασία",
    "text",
    "άρθρο",
    "book",
    "συνέδριο",
    "doctoral",
    "συνέδριο/αναφορά",
    "άλλο",
    "other",
    "έγγραφο",
    "διατριβή",
    "βιβλίο",
    "paper",
    "νοταριακό",
    "διάλεξη",
    "τεύχος",
    "παρουσίαση",
    "περιοδικό",
    "δικαστική απόφαση",
    "επετηρίδα",
    "journal",
    "επιστημονική δημοσίευση",
    "access",
    "εκδήλωση",
    "dissertation",
    "folder",
    "learning",
    "archive",
    "report",
    "software",
    "bibliographic",
    "dataset",
    "συλλογή/εκλογές",
    "οδηγός",
    "review",
    "event",
    "μονογραφία",
    "διδακτορική",
    "chapter",
    "ψήφισμα",
    "κεφάλαιο",
    "χάρτης",
    "na",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def ensure_manual_overlay(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    if path.exists():
        return
    write_csv(path, rows, fieldnames)


def modality_bucket(type_name: str) -> str:
    lowered = (type_name or "").strip().lower()
    if not lowered:
        return "other"
    if any(token in lowered for token in ("video", "ταιν", "film")):
        return "video"
    if any(token in lowered for token in ("sound", "audio", "record", "tape", "ηχ")):
        return "sound"
    if any(token in lowered for token in ("image", "εικόνα", "photo", "φωτο")):
        return "image"
    if lowered in TEXT_KEYWORDS:
        return "text"
    return "text"


def summarize_target_types(entries: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for entry in entries or []:
        type_name = entry.get("type")
        count = entry.get("count")
        parts.append(f"{type_name}:{count}")
    return "; ".join(parts)


def modality_counts(entries: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"text": 0, "image": 0, "sound": 0, "video": 0, "other": 0}
    for entry in entries or []:
        bucket = modality_bucket(str(entry.get("type") or ""))
        count = int(entry.get("count") or 0)
        counts[bucket] += count
    return counts


def bool_string(value: bool) -> str:
    return "yes" if value else "no"


def slug_map(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {row["collection_slug"]: row for row in rows}


def running_job_dirs() -> set[str]:
    result = subprocess.run(
        ["bash", "-lc", "ps -ef | grep '[c]odex exec'"],
        capture_output=True,
        text=True,
        check=False,
    )
    paths: set[str] = set()
    for line in result.stdout.splitlines():
        match = re.search(r"--add-dir (\S+)", line)
        if match:
            paths.add(match.group(1))
    return paths


def parse_run_history() -> dict[str, list[dict[str, Any]]]:
    running_paths = running_job_dirs()
    history: dict[str, list[dict[str, Any]]] = {}
    for run_dir in sorted(RUNS_DIR.glob("*_*")):
        jobs_dir = run_dir / "jobs"
        if not jobs_dir.exists():
            continue
        run_id = run_dir.name
        stage = run_id.split("_", 1)[1]
        for job_dir in sorted(jobs_dir.iterdir()):
            if not job_dir.is_dir():
                continue
            final_path = job_dir / "final.json"
            validation_path = job_dir / "validation.json"
            next_action_path = job_dir / "next_action.json"
            progress_path = job_dir / "progress_evaluation.json"
            improvement_path = job_dir / "improvement_plan.json"
            final = load_json(final_path) if final_path.exists() else None
            validation = load_json(validation_path) if validation_path.exists() else None
            next_action = load_json(next_action_path) if next_action_path.exists() else None
            progress = load_json(progress_path) if progress_path.exists() else None
            improvement = load_json(improvement_path) if improvement_path.exists() else None
            active = str(job_dir) in running_paths
            if active:
                run_state = "in_progress"
            elif validation and validation.get("promotable"):
                run_state = "completed_promotable"
            elif final_path.exists():
                run_state = "completed"
            else:
                run_state = "incomplete"
            record = {
                "run_id": run_id,
                "job_dir": str(job_dir),
                "stage": (final or {}).get("stage", stage),
                "active": active,
                "run_state": run_state,
                "final": final,
                "validation": validation,
                "next_action": next_action,
                "claimed_item_count": (final or {}).get("claimed_item_count"),
                "observed_item_count": (final or {}).get("observed_item_count"),
                "available_subcollections_count": len((final or {}).get("available_subcollections", [])),
                "summary": (final or {}).get("summary"),
                "content_type_summary": " | ".join((final or {}).get("content_type_summary", [])),
                "priority_assessment": (final or {}).get("priority_assessment", {}),
                "count_evidence": (final or {}).get("count_evidence") if final else None,
                "throughput_evidence": (final or {}).get("throughput_evidence") if final else None,
                "progress": progress if isinstance(progress, dict) else None,
                "improvement": improvement if isinstance(improvement, dict) else None,
            }
            history.setdefault(job_dir.name, []).append(record)
    for records in history.values():
        records.sort(key=lambda item: item["run_id"])
    return history


def latest_run(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    return records[-1] if records else None


def best_promotable_run(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    promotable = [record for record in records if (record.get("validation") or {}).get("promotable")]
    if promotable:
        return promotable[-1]
    completed = [record for record in records if record["final"]]
    return completed[-1] if completed else None


def backlog_bucket(row: dict[str, Any], wave1_slugs: set[str], started_slugs: set[str]) -> str:
    slug = row["collection_slug"]
    if slug in wave1_slugs:
        return "wave1_active"
    if slug in started_slugs:
        return "research_started"
    if row.get("direct_repo_hint_available"):
        return "known_host_backlog"
    return "discovery_backlog"


def active_status(slug: str, latest: dict[str, Any] | None, wave1_slugs: set[str]) -> str:
    if latest:
        stage = latest["stage"]
        if latest["run_state"] == "in_progress":
            return f"{stage}_running"
        if latest["run_state"] == "completed_promotable":
            return f"{stage}_completed_promotable"
        if latest["run_state"] == "completed":
            return f"{stage}_completed_not_promotable"
        return f"{stage}_{latest['run_state']}"
    if slug in wave1_slugs:
        return "queued_wave1"
    return "tracked_no_run"


def count_evidence_fields(record: dict[str, Any] | None) -> dict[str, Any]:
    count_evidence = (record or {}).get("count_evidence") or {}
    return {
        "repository_claimed_total": count_evidence.get("repository_claimed_total"),
        "api_reported_total": count_evidence.get("api_reported_total"),
        "scraper_observed_total": count_evidence.get("scraper_observed_total"),
        "count_discrepancy_note": count_evidence.get("discrepancy_note"),
        "repo_claimed_collection_count": (record or {}).get("available_subcollections_count"),
    }


def throughput_fields(record: dict[str, Any] | None) -> dict[str, Any]:
    throughput = (record or {}).get("throughput_evidence") or {}
    return {
        "metadata_probe_rps": throughput.get("metadata_probe_rps"),
        "file_probe_bytes_per_second": throughput.get("file_probe_bytes_per_second"),
        "suggested_parallel_downloads": throughput.get("suggested_parallel_downloads"),
        "estimated_eta_hours": throughput.get("estimated_eta_hours"),
        "slow_eta_threshold_hours": throughput.get("slow_eta_threshold_hours"),
        "throughput_threshold_breach": throughput.get("threshold_breach"),
    }


def progress_fields(record: dict[str, Any] | None) -> dict[str, Any]:
    progress = (record or {}).get("progress") or {}
    return {
        "overall_progress_percent": progress.get("overall_progress_percent"),
        "stage_completion_percent": progress.get("stage_completion_percent"),
        "count_completeness_percent": progress.get("count_completeness_percent"),
        "eta_health_percent": progress.get("eta_health_percent"),
        "quality_fit_percent": progress.get("quality_fit_percent"),
        "user_decision_pending": progress.get("user_decision_pending"),
        "user_decision_reason": progress.get("user_decision_reason"),
    }


def improvement_fields(record: dict[str, Any] | None) -> dict[str, Any]:
    improvement = (record or {}).get("improvement") or {}
    return {
        "review_decision": improvement.get("decision"),
        "review_decision_reason": improvement.get("decision_reason"),
        "review_expected_gain_percent": improvement.get("expected_gain_percent"),
        "review_confidence": improvement.get("confidence"),
        "review_user_decision_required": improvement.get("user_decision_required"),
    }


def generate() -> None:
    all_rows = load_json(COLLECTIONS_DIR / "all_strict_target_collections.json")
    wave1_rows = load_json(COLLECTIONS_DIR / "wave1_high_quality_easy.json")
    all_by_slug = slug_map(all_rows)
    wave1_slugs = {row["collection_slug"] for row in wave1_rows}
    history = parse_run_history()
    started_slugs = set(history)

    potential_rows: list[dict[str, Any]] = []
    for row in sorted(all_rows, key=lambda item: (-int(item.get("untapped_target_rows") or 0), item["collection_slug"])):
        counts = modality_counts(row.get("dominant_target_types", []))
        bucket = backlog_bucket(row, wave1_slugs, started_slugs)
        latest = latest_run(history.get(row["collection_slug"], []))
        best = best_promotable_run(history.get(row["collection_slug"], []))
        row_data = {
            "collection_slug": row["collection_slug"],
            "backlog_bucket": bucket,
            "top_repository_name": row.get("top_repository_name"),
            "top_provider": row.get("top_provider"),
            "repo_host": row.get("repo_host"),
            "repo_url_hint": row.get("repo_url_hint"),
            "platform_hint": row.get("platform_hint"),
            "priority_kind": row.get("priority_kind"),
            "suggested_wave": row.get("suggested_wave"),
            "direct_repo_hint_available": bool_string(bool(row.get("direct_repo_hint_available"))),
            "content_priority": row.get("content_priority"),
            "extraction_ease": row.get("extraction_ease"),
            "language_priority": row.get("language_priority"),
            "pdf_hit_rate": row.get("pdf_hit_rate"),
            "raw_target_rows": row.get("raw_target_rows"),
            "tapped_target_rows": row.get("tapped_target_rows"),
            "untapped_target_rows": row.get("untapped_target_rows"),
            "known_overlap_source": row.get("known_overlap_source"),
            "dominant_target_types_summary": summarize_target_types(row.get("dominant_target_types", [])),
            "has_text": bool_string(counts["text"] > 0 or (row.get("raw_target_rows") or 0) > 0),
            "has_image": bool_string(counts["image"] > 0),
            "has_sound": bool_string(counts["sound"] > 0),
            "has_video": bool_string(counts["video"] > 0),
            "estimated_text_items": counts["text"],
            "estimated_image_items": counts["image"],
            "estimated_sound_items": counts["sound"],
            "estimated_video_items": counts["video"],
            "latest_run_id": (latest or {}).get("run_id"),
            "latest_run_state": (latest or {}).get("run_state"),
            "best_completed_run_id": (best or {}).get("run_id"),
            "notes": row.get("notes"),
            "manual_priority": "",
            "manual_repo_status": "",
            "manual_notes": "",
        }
        potential_rows.append(row_data)

    active_source_slugs = sorted(wave1_slugs | started_slugs)
    active_rows: list[dict[str, Any]] = []
    for slug in active_source_slugs:
        base = all_by_slug.get(slug)
        if not base:
            continue
        counts = modality_counts(base.get("dominant_target_types", []))
        records = history.get(slug, [])
        latest = latest_run(records)
        best = best_promotable_run(records)
        count_fields = count_evidence_fields(best)
        speed_fields = throughput_fields(best)
        progress = progress_fields(latest or best)
        improvement = improvement_fields(latest or best)
        active_rows.append(
            {
                "collection_slug": slug,
                "active_group": "wave1_high_quality_easy" if slug in wave1_slugs else "run_history_only",
                "top_repository_name": base.get("top_repository_name"),
                "top_provider": base.get("top_provider"),
                "repo_host": base.get("repo_host"),
                "repo_url_hint": base.get("repo_url_hint"),
                "platform_hint": base.get("platform_hint"),
                "content_priority": base.get("content_priority"),
                "extraction_ease": base.get("extraction_ease"),
                "untapped_target_rows": base.get("untapped_target_rows"),
                "raw_target_rows": base.get("raw_target_rows"),
                "has_text": bool_string(counts["text"] > 0 or (base.get("raw_target_rows") or 0) > 0),
                "has_image": bool_string(counts["image"] > 0),
                "has_sound": bool_string(counts["sound"] > 0),
                "has_video": bool_string(counts["video"] > 0),
                "dominant_target_types_summary": summarize_target_types(base.get("dominant_target_types", [])),
                "latest_run_id": (latest or {}).get("run_id"),
                "latest_stage": (latest or {}).get("stage"),
                "latest_status": active_status(slug, latest, wave1_slugs),
                "latest_failure_class": ((latest or {}).get("validation") or {}).get("failure_class"),
                "latest_promotable": ((latest or {}).get("validation") or {}).get("promotable"),
                "latest_next_stage": ((latest or {}).get("next_action") or {}).get("next_stage"),
                "best_completed_run_id": (best or {}).get("run_id"),
                "best_completed_stage": (best or {}).get("stage"),
                "repo_claimed_collection_count": count_fields["repo_claimed_collection_count"],
                "repo_claimed_total_items": count_fields["repository_claimed_total"] if count_fields["repository_claimed_total"] is not None else (best or {}).get("claimed_item_count"),
                "api_reported_total_items": count_fields["api_reported_total"],
                "scraper_observed_total_items": count_fields["scraper_observed_total"] if count_fields["scraper_observed_total"] is not None else (best or {}).get("observed_item_count"),
                "count_discrepancy_note": count_fields["count_discrepancy_note"],
                "metadata_probe_rps": speed_fields["metadata_probe_rps"],
                "file_probe_bytes_per_second": speed_fields["file_probe_bytes_per_second"],
                "suggested_parallel_downloads": speed_fields["suggested_parallel_downloads"],
                "estimated_eta_hours": speed_fields["estimated_eta_hours"],
                "slow_eta_threshold_hours": speed_fields["slow_eta_threshold_hours"],
                "throughput_threshold_breach": speed_fields["throughput_threshold_breach"],
                "overall_progress_percent": progress["overall_progress_percent"],
                "stage_completion_percent": progress["stage_completion_percent"],
                "count_completeness_percent": progress["count_completeness_percent"],
                "eta_health_percent": progress["eta_health_percent"],
                "quality_fit_percent": progress["quality_fit_percent"],
                "user_decision_pending": progress["user_decision_pending"],
                "user_decision_reason": progress["user_decision_reason"],
                "review_decision": improvement["review_decision"],
                "review_decision_reason": improvement["review_decision_reason"],
                "review_expected_gain_percent": improvement["review_expected_gain_percent"],
                "review_confidence": improvement["review_confidence"],
                "review_user_decision_required": improvement["review_user_decision_required"],
                "content_type_summary": (best or {}).get("content_type_summary"),
                "latest_summary": (best or {}).get("summary"),
                "manual_owner": "",
                "manual_next_action": "",
                "manual_decision": "",
                "manual_notes": "",
            }
        )

    potential_fieldnames = [
        "collection_slug",
        "backlog_bucket",
        "top_repository_name",
        "top_provider",
        "repo_host",
        "repo_url_hint",
        "platform_hint",
        "priority_kind",
        "suggested_wave",
        "direct_repo_hint_available",
        "content_priority",
        "extraction_ease",
        "language_priority",
        "pdf_hit_rate",
        "raw_target_rows",
        "tapped_target_rows",
        "untapped_target_rows",
        "known_overlap_source",
        "dominant_target_types_summary",
        "has_text",
        "has_image",
        "has_sound",
        "has_video",
        "estimated_text_items",
        "estimated_image_items",
        "estimated_sound_items",
        "estimated_video_items",
        "latest_run_id",
        "latest_run_state",
        "best_completed_run_id",
        "notes",
        "manual_priority",
        "manual_repo_status",
        "manual_notes",
    ]
    active_fieldnames = [
        "collection_slug",
        "active_group",
        "top_repository_name",
        "top_provider",
        "repo_host",
        "repo_url_hint",
        "platform_hint",
        "content_priority",
        "extraction_ease",
        "untapped_target_rows",
        "raw_target_rows",
        "has_text",
        "has_image",
        "has_sound",
        "has_video",
        "dominant_target_types_summary",
        "latest_run_id",
        "latest_stage",
        "latest_status",
        "latest_failure_class",
        "latest_promotable",
        "latest_next_stage",
        "best_completed_run_id",
        "best_completed_stage",
        "repo_claimed_collection_count",
        "repo_claimed_total_items",
        "api_reported_total_items",
        "scraper_observed_total_items",
        "count_discrepancy_note",
        "metadata_probe_rps",
        "file_probe_bytes_per_second",
        "suggested_parallel_downloads",
        "estimated_eta_hours",
        "slow_eta_threshold_hours",
        "throughput_threshold_breach",
        "overall_progress_percent",
        "stage_completion_percent",
        "count_completeness_percent",
        "eta_health_percent",
        "quality_fit_percent",
        "user_decision_pending",
        "user_decision_reason",
        "review_decision",
        "review_decision_reason",
        "review_expected_gain_percent",
        "review_confidence",
        "review_user_decision_required",
        "content_type_summary",
        "latest_summary",
        "manual_owner",
        "manual_next_action",
        "manual_decision",
        "manual_notes",
    ]

    write_csv(GENERATED_DIR / "potential_sources.csv", potential_rows, potential_fieldnames)
    write_csv(GENERATED_DIR / "active_sources.csv", active_rows, active_fieldnames)

    ensure_manual_overlay(
        MANUAL_DIR / "potential_sources_enrichment.csv",
        [
            {
                "collection_slug": row["collection_slug"],
                "manual_priority": "",
                "manual_repo_status": "",
                "manual_notes": "",
            }
            for row in potential_rows
        ],
        ["collection_slug", "manual_priority", "manual_repo_status", "manual_notes"],
    )
    ensure_manual_overlay(
        MANUAL_DIR / "active_sources_enrichment.csv",
        [
            {
                "collection_slug": row["collection_slug"],
                "manual_owner": "",
                "manual_next_action": "",
                "manual_decision": "",
                "manual_notes": "",
            }
            for row in active_rows
        ],
        ["collection_slug", "manual_owner", "manual_next_action", "manual_decision", "manual_notes"],
    )

    summary_lines = [
        "# Source Backlog Summary",
        "",
        f"- Potential sources tracked: `{len(potential_rows)}`",
        f"- Active sources tracked: `{len(active_rows)}`",
        f"- Known-host backlog candidates: `{sum(1 for row in potential_rows if row['backlog_bucket'] == 'known_host_backlog')}`",
        f"- Discovery-needed backlog candidates: `{sum(1 for row in potential_rows if row['backlog_bucket'] == 'discovery_backlog')}`",
        "",
        "## Top Untapped Potential",
        "",
        "| Collection | Untapped | Host | Platform | Modalities | Bucket |",
        "| --- | ---: | --- | --- | --- | --- |",
    ]
    for row in potential_rows[:15]:
        modalities = ",".join(
            name
            for name in ("text", "image", "sound", "video")
            if row[f"has_{name}"] == "yes"
        )
        summary_lines.append(
            f"| {row['collection_slug']} | {row['untapped_target_rows']} | {row['repo_host'] or ''} | {row['platform_hint'] or ''} | {modalities or 'unknown'} | {row['backlog_bucket']} |"
        )
    summary_lines.extend(
        [
            "",
            "## Active Sources",
            "",
            "| Collection | Status | Latest Stage | Progress % | Repo Items | ETA h | Review | Next Stage |",
            "| --- | --- | --- | ---: | ---: | ---: | --- | --- |",
        ]
    )
    for row in active_rows:
        summary_lines.append(
            f"| {row['collection_slug']} | {row['latest_status']} | {row['latest_stage'] or ''} | {row['overall_progress_percent'] or ''} | {row['repo_claimed_total_items'] or ''} | {row['estimated_eta_hours'] or ''} | {row['review_decision'] or ''} | {row['latest_next_stage'] or ''} |"
        )
    write_text(GENERATED_DIR / "backlog_summary.md", "\n".join(summary_lines) + "\n")


if __name__ == "__main__":
    generate()
