#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORK_ROOT = Path(os.environ.get("GLOSSAPI_WORK_ROOT", "/home/foivos/data/glossapi_work"))
DEFAULT_RAW_ROOT = Path(os.environ.get("GLOSSAPI_RAW_ROOT", "/home/foivos/data/glossapi_raw"))
DEFAULT_COLLECTION_SUMMARY = (
    DEFAULT_WORK_ROOT
    / "analysis"
    / "openarchives_collection_coverage"
    / "runs"
    / "strict_lang_coverage_20260329T122854Z"
    / "collection_summary.csv"
)
DEFAULT_EXTERNAL_PDFS = DEFAULT_RAW_ROOT / "hf" / "openarchives.gr" / "data" / "external_pdfs.parquet"
DEFAULT_RAW_METADATA = DEFAULT_RAW_ROOT / "hf" / "openarchives.gr" / "data" / "edm_metadata_labeled.parquet"
DEFAULT_CONFIG_DIR = PROJECT_ROOT / "config" / "collections"

FAVORABLE_TYPES = {
    "thesis",
    "doctoral",
    "article",
    "paper",
    "book",
    "text",
    "journal",
    "report",
    "εργασία",
    "άρθρο",
    "διατριβή",
    "διδακτορική",
    "βιβλίο",
    "κεφάλαιο",
    "συνέδριο",
    "συνέδριο/αναφορά",
    "έγγραφο",
    "διάλεξη",
    "νοταριακό",
}
LOW_PRIORITY_TYPES = {
    "image",
    "video",
    "access",
    "archive",
    "review",
    "exhibition",
    "συλλογή/εκλογές",
}
OVERLAP_MAP = {
    "phdtheses": "covered_by_standalone_greek_phd",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build master OpenArchives direct-repo collection manifests.")
    parser.add_argument("--collection-summary", type=Path, default=DEFAULT_COLLECTION_SUMMARY)
    parser.add_argument("--external-pdfs", type=Path, default=DEFAULT_EXTERNAL_PDFS)
    parser.add_argument("--raw-metadata", type=Path, default=DEFAULT_RAW_METADATA)
    parser.add_argument("--config-dir", type=Path, default=DEFAULT_CONFIG_DIR)
    return parser.parse_args()


def normalize_type(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "NA"
    text = str(value).strip()
    return text if text else "NA"


def platform_hint_from_url(host: str, sample_url: str) -> str:
    if not host:
        return "unknown"
    text = f"{host} {sample_url}".lower()
    if "/server/api/" in text or host in {"repository.ihu.gr", "pyxida.aueb.gr"}:
        return "dspace7"
    if "/xmlui/" in text:
        return "dspace_xmlui"
    if "/jspui/" in text:
        return "dspace_jspui"
    if "/handle/" in text:
        return "dspace_handle_repository"
    if host == "pergamos.lib.uoa.gr":
        return "custom_object_repository"
    if host in {"ikee.lib.auth.gr", "repository.kallipos.gr"}:
        return "custom_ekt_repository"
    return "custom_or_unknown"


def content_priority(favorable_share: float, low_priority_share: float) -> str:
    if favorable_share >= 0.7 and low_priority_share <= 0.1:
        return "high"
    if favorable_share >= 0.4 and low_priority_share <= 0.3:
        return "medium"
    return "low"


def extraction_ease(platform_hint: str, direct_repo_hint_available: bool, pdf_hit_rate: float | None) -> str:
    if not direct_repo_hint_available:
        return "discovery_only"
    dspace_platforms = {"dspace7", "dspace_xmlui", "dspace_jspui", "dspace_handle_repository"}
    if platform_hint in dspace_platforms and (pdf_hit_rate is None or pdf_hit_rate >= 0.3):
        return "easy"
    if platform_hint in dspace_platforms:
        return "medium"
    if pdf_hit_rate is not None and pdf_hit_rate >= 0.3:
        return "medium"
    return "hard"


def suggested_wave(
    overlap: str,
    direct_repo_hint_available: bool,
    content_priority_label: str,
    extraction_ease_label: str,
    untapped_target_rows: int,
) -> str:
    if overlap:
        return "overlap_defer"
    if not direct_repo_hint_available:
        return "discovery_backlog"
    if untapped_target_rows >= 10000 and content_priority_label == "high" and extraction_ease_label == "easy":
        return "wave1_high_quality_easy"
    if untapped_target_rows >= 5000 and content_priority_label in {"high", "medium"} and extraction_ease_label in {"easy", "medium"}:
        return "wave2_medium"
    return "wave3_hard_or_small"


def build_type_stats(raw_metadata_path: Path, target_slugs: set[str]) -> dict[str, Counter[str]]:
    raw = pd.read_parquet(raw_metadata_path, columns=["collection_slug", "language_code", "type"])
    raw["collection_slug"] = raw["collection_slug"].fillna("").astype(str)
    raw["language_code"] = raw["language_code"].fillna("").astype(str)
    raw = raw[(raw["collection_slug"].isin(target_slugs)) & (raw["language_code"].isin({"ELL", "NONE"}))]
    stats: dict[str, Counter[str]] = {}
    for slug, sub in raw.groupby("collection_slug", dropna=False):
        stats[slug] = Counter(normalize_type(value) for value in sub["type"])
    return stats


def build_external_stats(external_pdfs_path: Path, target_slugs: set[str]) -> dict[str, dict[str, Any]]:
    external = pd.read_parquet(
        external_pdfs_path,
        columns=[
            "collection_slug",
            "external_link",
            "pdf_links_count",
            "refined_pdf_links_count",
        ],
    )
    external["collection_slug"] = external["collection_slug"].fillna("").astype(str)
    external = external[external["collection_slug"].isin(target_slugs)].copy()
    if external.empty:
        return {}

    external["external_link"] = external["external_link"].fillna("").astype(str)
    external["host"] = external["external_link"].map(lambda x: urlparse(x).netloc or "")
    external["any_pdf"] = (
        external["refined_pdf_links_count"].fillna(0).astype(float).gt(0)
        | external["pdf_links_count"].fillna(0).astype(float).gt(0)
    )

    stats: dict[str, dict[str, Any]] = {}
    for slug, sub in external.groupby("collection_slug", dropna=False):
        host_counts = Counter(host for host in sub["host"] if host)
        top_host = host_counts.most_common(1)[0][0] if host_counts else ""
        sample_url = ""
        if top_host:
            first = sub[sub["host"] == top_host]["external_link"]
            if not first.empty:
                sample_url = str(first.iloc[0])
        pdf_hit_rate = float(sub["any_pdf"].mean()) if len(sub) else None
        root_hint = ""
        if sample_url:
            parsed = urlparse(sample_url)
            root_hint = f"{parsed.scheme}://{parsed.netloc}/"
        stats[slug] = {
            "repo_host": top_host,
            "sample_item_url_hint": sample_url,
            "repo_url_hint": root_hint,
            "pdf_hit_rate": pdf_hit_rate,
            "external_rows": int(len(sub)),
        }
    return stats


def build_manifest_items(
    summary: pd.DataFrame,
    type_stats: dict[str, Counter[str]],
    external_stats: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    ordered = summary.sort_values(
        by=["untapped_target_rows", "raw_target_rows", "collection_slug"],
        ascending=[False, False, True],
    ).reset_index(drop=True)

    for index, row in ordered.iterrows():
        slug = str(row["collection_slug"])
        external = external_stats.get(slug, {})
        repo_host = str(external.get("repo_host") or "")
        sample_item_url_hint = str(external.get("sample_item_url_hint") or "")
        repo_url_hint = str(external.get("repo_url_hint") or "")
        pdf_hit_rate = external.get("pdf_hit_rate")
        direct_repo_hint_available = bool(repo_host)
        platform_hint = platform_hint_from_url(repo_host, sample_item_url_hint)

        counts = type_stats.get(slug, Counter())
        total_types = sum(counts.values())
        favorable_rows = sum(count for key, count in counts.items() if key in FAVORABLE_TYPES)
        low_priority_rows = sum(count for key, count in counts.items() if key in LOW_PRIORITY_TYPES)
        favorable_share = (favorable_rows / total_types) if total_types else 0.0
        low_priority_share = (low_priority_rows / total_types) if total_types else 0.0
        content_priority_label = content_priority(favorable_share, low_priority_share)
        extraction_ease_label = extraction_ease(platform_hint, direct_repo_hint_available, pdf_hit_rate)
        overlap = OVERLAP_MAP.get(slug, "")
        wave = suggested_wave(
            overlap=overlap,
            direct_repo_hint_available=direct_repo_hint_available,
            content_priority_label=content_priority_label,
            extraction_ease_label=extraction_ease_label,
            untapped_target_rows=int(row["untapped_target_rows"]),
        )

        top_types = [
            {"type": type_name, "count": count}
            for type_name, count in counts.most_common(5)
        ]
        notes_parts = [
            f"strict-language untapped rows={int(row['untapped_target_rows'])}",
            f"content_priority={content_priority_label}",
            f"extraction_ease={extraction_ease_label}",
        ]
        if overlap:
            notes_parts.append(f"overlap={overlap}")
        if not direct_repo_hint_available:
            notes_parts.append("no direct host hint yet from external_pdfs")
        item = {
            "agent_id": f"agent{index + 1:03d}_{slug}",
            "collection_slug": slug,
            "top_repository_name": str(row.get("top_repository_name") or ""),
            "top_provider": str(row.get("top_provider") or ""),
            "repo_host": repo_host,
            "repo_url_hint": repo_url_hint,
            "sample_item_url_hint": sample_item_url_hint,
            "platform_hint": platform_hint,
            "priority_kind": "whole_collection" if bool(row.get("whole_collection_target")) else "row_filtered",
            "tapped_target_rows": int(row["extracted_target_rows"]),
            "untapped_target_rows": int(row["untapped_target_rows"]),
            "raw_target_rows": int(row["raw_target_rows"]),
            "language_priority": "strict_ELL_NONE",
            "content_priority": content_priority_label,
            "extraction_ease": extraction_ease_label,
            "known_overlap_source": overlap,
            "direct_repo_hint_available": direct_repo_hint_available,
            "pdf_hit_rate": float(pdf_hit_rate) if pdf_hit_rate is not None else None,
            "dominant_target_types": top_types,
            "search_query_hint": " ".join(part for part in [str(row.get("top_repository_name") or "").strip(), str(row.get("top_provider") or "").strip(), slug] if part),
            "suggested_wave": wave,
            "notes": "; ".join(notes_parts),
        }
        items.append(item)
    return items


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    args.config_dir.mkdir(parents=True, exist_ok=True)

    summary = pd.read_csv(args.collection_summary)
    summary = summary[summary["raw_target_rows"] > 0].copy()
    target_slugs = set(summary["collection_slug"].astype(str))

    type_stats = build_type_stats(args.raw_metadata, target_slugs)
    external_stats = build_external_stats(args.external_pdfs, target_slugs)
    items = build_manifest_items(summary, type_stats, external_stats)

    all_path = args.config_dir / "all_strict_target_collections.json"
    known_hosts_path = args.config_dir / "all_known_host_collections.json"
    wave1_path = args.config_dir / "wave1_high_quality_easy.json"

    write_json(all_path, items)
    write_json(known_hosts_path, [item for item in items if item["direct_repo_hint_available"]])
    write_json(wave1_path, [item for item in items if item["suggested_wave"] == "wave1_high_quality_easy"])

    print(all_path)
    print(known_hosts_path)
    print(wave1_path)


if __name__ == "__main__":
    main()
