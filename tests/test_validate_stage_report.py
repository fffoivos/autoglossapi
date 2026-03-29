from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from controller.validate_stage_report import validate_report_payload


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "schemas" / "stage_report.schema.json"


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


class ValidateStageReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.schema = load_schema()

    def _discover_report(self, status: str = "success") -> dict:
        checklist_ids = [
            "website",
            "collections_available",
            "entry_path",
            "website_levels",
            "platform",
            "api_surface",
            "count_claims",
            "content_types",
            "priority_scope",
            "request_capacity",
            "priority_assessment",
        ]
        return {
            "collection_slug": "pyxida",
            "stage": "discover",
            "status": status,
            "repo_root_url": "https://pyxida.aueb.gr/",
            "repo_host": "pyxida.aueb.gr",
            "platform_guess": "dspace7",
            "summary": "Discover stage succeeded.",
            "available_subcollections": [],
            "website_levels": {
                "repo_home": "https://pyxida.aueb.gr/",
                "collection_entry": "https://pyxida.aueb.gr/collections/example",
                "list_pages": "listing pages exist",
                "pagination": "next-page links",
                "item_page": "item pages exist",
                "pdf_access": "bitstream download",
            },
            "relevant_collection_urls": [
                "https://pyxida.aueb.gr/collections/example"
            ],
            "content_type_summary": ["theses"],
            "claimed_item_count": 100,
            "observed_item_count": 100,
            "count_evidence": {
                "repository_claimed_total": 100,
                "repository_claim_unit": "items",
                "repository_claim_source": "home page",
                "api_reported_total": 100,
                "api_report_unit": "items",
                "scraper_observed_total": 100,
                "scraper_observed_unit": "items",
                "collection_count_comparison": [
                    {
                        "name": "Example collection",
                        "url": "https://pyxida.aueb.gr/collections/example",
                        "website_claimed_count": 100,
                        "website_claim_unit": "items",
                        "claim_source": "collection page",
                        "api_reported_count": 100,
                        "api_report_unit": "items",
                        "scraper_observed_count": 100,
                        "scraper_observed_unit": "items",
                        "note": "counts agree",
                    }
                ],
                "discrepancy_note": None,
            },
            "pagination_strategy": "follow next-page links",
            "pdf_detection_strategy": "look for PDF bitstream links",
            "metadata_richness_note": "title, author, date, abstract",
            "metadata_fields": ["title", "author", "date"],
            "priority_assessment": {
                "language_fit": "high",
                "content_quality_fit": "high",
                "extraction_ease": "high",
                "overall_priority": "high",
            },
            "sample_documents": [],
            "failed_checklist_ids": [],
            "tried_hypotheses": ["collection entry via navigation"],
            "alternative_hypotheses": [],
            "best_next_hypothesis": None,
            "stuck_reason": None,
            "blocked_on": [],
            "exhausted_paths": [],
            "confidence": "high",
            "needs_human_input": False,
            "checklist": [
                {
                    "id": item_id,
                    "label": item_id,
                    "status": "done",
                    "evidence": "verified",
                }
                for item_id in checklist_ids
            ],
            "artifacts": [],
            "risks": [],
            "recommended_next_step": "Advance to feasibility.",
        }

    def test_successful_report_is_promotable(self) -> None:
        report = self._discover_report()
        summary = validate_report_payload(report, self.schema)
        self.assertTrue(summary["schema_valid"])
        self.assertEqual(summary["failure_class"], "success")
        self.assertTrue(summary["promotable"])

    def test_partial_report_is_not_promotable(self) -> None:
        report = self._discover_report(status="partial")
        report["checklist"][0]["status"] = "partial"
        summary = validate_report_payload(report, self.schema)
        self.assertEqual(summary["failure_class"], "partial")
        self.assertFalse(summary["promotable"])
        self.assertIn("website", summary["non_done_checklist_ids"])

    def test_missing_artifact_is_evidence_failed(self) -> None:
        report = self._discover_report()
        report["artifacts"] = [
            {
                "kind": "html_capture",
                "path_or_url": "captures/missing.html",
                "note": "not actually present",
            }
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            summary = validate_report_payload(report, self.schema, job_dir=Path(tmpdir))
        self.assertEqual(summary["failure_class"], "evidence_failed")
        self.assertFalse(summary["promotable"])


if __name__ == "__main__":
    unittest.main()
