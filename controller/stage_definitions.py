from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StageSpec:
    name: str
    description: str
    checklist: tuple[tuple[str, str], ...]
    sample_limit: int = 0


STAGES: dict[str, StageSpec] = {
    "discover": StageSpec(
        name="discover",
        description=(
            "Find the upstream repository home, relevant collection landing areas, the platform "
            "shape, and the content types worth prioritizing. Work directly from the repository, "
            "not the OpenArchives aggregator, except as a hint."
        ),
        checklist=(
            ("website", "Find the canonical repository home URL."),
            ("collections_available", "List the collections or subcollections available on the website."),
            ("entry_path", "Show how to enter the relevant collection from the repository home."),
            ("website_levels", "Describe the page levels from repo home to collection to list to item to PDF."),
            ("platform", "Identify the platform or architecture family."),
            ("content_types", "List the dominant content types and low-priority content."),
            ("priority_scope", "Define the subcollections worth crawling first."),
            ("priority_assessment", "Assess Greek fit, content quality, and extraction ease."),
        ),
    ),
    "feasibility": StageSpec(
        name="feasibility",
        description=(
            "Prove that the repository can be scraped deterministically. Demonstrate collection "
            "entry, list-page detection, pagination, claimed-vs-observed counts, PDF detection, "
            "and metadata extraction paths."
        ),
        checklist=(
            ("enter_collection", "Demonstrate entering the target collection."),
            ("detect_lists", "Detect item listing pages or search endpoints."),
            ("pagination", "Explain pagination or batch traversal."),
            ("count_reconciliation", "Compare claimed item counts against observed pages."),
            ("pdf_detection", "Show how to detect true PDFs versus restricted or notice pages."),
            ("pdf_presence", "Show how to tell whether an item has an openly accessible PDF or not."),
            ("metadata_capture", "List the fields that can be scraped for parquet enrichment."),
            ("content_quality_routing", "Identify high-quality easy-to-extract content versus low-priority content."),
        ),
    ),
    "sample_validation": StageSpec(
        name="sample_validation",
        description=(
            "Download a small sample and verify that the outputs are real academic works. Extract "
            "first-page evidence, inspect PDF metadata when available, and reject notice-like or "
            "placeholder attachments."
        ),
        checklist=(
            ("sample_download", "Download a small sample of candidate PDFs."),
            ("first_page_extract", "Extract first-page evidence or equivalent textual proof."),
            ("academic_work_check", "Verify the samples look like real academic works."),
            ("duplicate_notice_check", "Check they are not identical repository notices."),
            ("pdf_metadata_check", "Inspect PDF metadata or file-shape evidence."),
            ("metadata_capture", "Capture the sample metadata needed for downstream parquet rows."),
        ),
        sample_limit=5,
    ),
    "adapter_spec": StageSpec(
        name="adapter_spec",
        description=(
            "Package the deterministic handoff for a non-LLM crawler. Produce the exact crawl "
            "entrypoints, pagination approach, PDF filtering rules, metadata mapping, and failure "
            "cases that the Python downloader should implement."
        ),
        checklist=(
            ("crawl_entrypoints", "Define the crawl entrypoints and relevant collection URLs."),
            ("selectors_or_endpoints", "Name the selectors, URL patterns, or APIs to use."),
            ("website_levels", "Preserve the verified page-level traversal from repo home to PDF."),
            ("download_rules", "Define PDF filtering, file naming, and access checks."),
            ("metadata_mapping", "Map repository fields to parquet columns."),
            ("failure_modes", "List the known repository-specific failure modes."),
        ),
    ),
    "build_scraper": StageSpec(
        name="build_scraper",
        description=(
            "Turn the adapter specification into deterministic scraper code. Keep the logic "
            "repository-specific, bounded, and testable."
        ),
        checklist=(
            ("scraper_module", "Implement the repository-specific scraper module."),
            ("entrypoints", "Wire the crawl entrypoints into code."),
            ("metadata_mapping", "Implement metadata extraction and normalization."),
            ("pdf_rules", "Implement PDF presence and filtering rules."),
            ("tests_or_fixtures", "Add bounded tests or fixtures for the scraper."),
        ),
    ),
    "smoke_test_scraper": StageSpec(
        name="smoke_test_scraper",
        description=(
            "Run a bounded smoke test of the scraper on a handful of items before any bulk work."
        ),
        checklist=(
            ("list_fetch", "Fetch a listing or search page successfully."),
            ("item_parse", "Parse item-level metadata successfully."),
            ("pdf_detection", "Detect PDF presence correctly on sample items."),
            ("sample_outputs", "Produce bounded sample outputs for manual inspection."),
        ),
    ),
}

STAGE_ORDER = tuple(STAGES)


def next_stage_name(stage: str) -> str | None:
    try:
        index = STAGE_ORDER.index(stage)
    except ValueError:
        return None
    next_index = index + 1
    if next_index >= len(STAGE_ORDER):
        return None
    return STAGE_ORDER[next_index]

