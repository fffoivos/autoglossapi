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

    def _report_for_stage(self, stage: str, checklist_ids: list[str], status: str = "success") -> dict:
        return {
            "collection_slug": "pyxida",
            "stage": stage,
            "status": status,
            "repo_root_url": "https://pyxida.aueb.gr/",
            "repo_host": "pyxida.aueb.gr",
            "platform_guess": "dspace7",
            "summary": f"{stage} stage succeeded.",
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
            "throughput_evidence": {
                "metadata_probe_requests": 20,
                "metadata_probe_window_seconds": 10.0,
                "metadata_probe_rps": 2.0,
                "metadata_probe_note": "API tolerated 2 rps during the probe.",
                "file_probe_downloads": 4,
                "file_probe_total_bytes": 12000000,
                "file_probe_window_seconds": 40.0,
                "file_probe_bytes_per_second": 300000.0,
                "file_probe_files_per_hour": 360.0,
                "suggested_parallel_downloads": 4,
                "estimated_total_items": 100,
                "estimated_total_bytes": 300000000,
                "estimated_eta_hours": 0.28,
                "eta_basis_note": "Estimated from four sample PDFs and the claimed collection size.",
                "slow_eta_threshold_hours": 48.0,
                "threshold_breach": False,
                "investigation_trigger_recommendation": None,
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

    def _discover_report(self, status: str = "success") -> dict:
        checklist_ids = [
            "website",
            "collections_available",
            "entry_path",
            "website_levels",
            "platform",
            "api_surface",
            "count_claims",
            "throughput_surfaces",
            "content_types",
            "priority_scope",
            "request_capacity",
            "priority_assessment",
        ]
        return self._report_for_stage("discover", checklist_ids, status=status)

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

    def test_sample_validation_success_requires_sample_documents(self) -> None:
        report = self._report_for_stage(
            "sample_validation",
            [
                "sample_download",
                "first_page_extract",
                "academic_work_check",
                "duplicate_notice_check",
                "pdf_metadata_check",
                "metadata_capture",
            ],
        )
        summary = validate_report_payload(report, self.schema)
        self.assertEqual(summary["failure_class"], "evidence_failed")
        self.assertIn("sample_validation success requires non-empty sample_documents", summary["notes"])

    def test_bulk_run_success_requires_snapshot_manifest_artifact(self) -> None:
        report = self._report_for_stage(
            "bulk_run_scraper",
            [
                "launch_downloader",
                "resume_state",
                "request_budget",
                "throughput_monitoring",
                "download_coverage",
                "integrity_evidence",
                "snapshot_manifest",
                "run_summary",
            ],
        )
        summary = validate_report_payload(report, self.schema)
        self.assertEqual(summary["failure_class"], "evidence_failed")
        self.assertIn("bulk_run_scraper success requires a snapshot_manifest artifact", summary["notes"])

    def test_bulk_run_success_with_snapshot_manifest_is_promotable(self) -> None:
        report = self._report_for_stage(
            "bulk_run_scraper",
            [
                "launch_downloader",
                "resume_state",
                "request_budget",
                "throughput_monitoring",
                "download_coverage",
                "integrity_evidence",
                "snapshot_manifest",
                "run_summary",
            ],
        )
        report["artifacts"] = [
            {
                "kind": "snapshot_manifest",
                "path_or_url": "manifests/pyxida_snapshot.json",
                "note": "bulk run snapshot manifest",
            }
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "manifests" / "pyxida_snapshot.json"
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text("{}", encoding="utf-8")
            summary = validate_report_payload(report, self.schema, job_dir=Path(tmpdir))
        self.assertEqual(summary["failure_class"], "success")
        self.assertTrue(summary["promotable"])


if __name__ == "__main__":
    unittest.main()
