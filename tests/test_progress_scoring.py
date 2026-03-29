from __future__ import annotations

import unittest

from controller.progress_scoring import score_progress


class ProgressScoringTests(unittest.TestCase):
    def _report(self) -> dict:
        checklist = [
            {"id": "website", "label": "website", "status": "done", "evidence": "ok"},
            {"id": "api_surface", "label": "api_surface", "status": "partial", "evidence": "partial"},
            {"id": "count_claims", "label": "count_claims", "status": "blocked", "evidence": "blocked"},
        ]
        return {
            "collection_slug": "pyxida",
            "stage": "discover",
            "checklist": checklist,
            "count_evidence": {
                "repository_claimed_total": 100,
                "api_reported_total": 100,
                "scraper_observed_total": 80,
            },
            "throughput_evidence": {
                "metadata_probe_rps": 3.0,
                "file_probe_bytes_per_second": 500000.0,
                "suggested_parallel_downloads": 4,
                "estimated_eta_hours": 24.0,
                "slow_eta_threshold_hours": 48.0,
                "threshold_breach": False,
            },
            "priority_assessment": {
                "language_fit": "high",
                "content_quality_fit": "high",
                "extraction_ease": "medium",
                "overall_priority": "high",
            },
            "needs_human_input": False,
        }

    def test_score_progress_uses_exact_percentages(self) -> None:
        report = self._report()
        validation = {"collection_slug": "pyxida", "stage": "discover", "failure_class": "partial"}
        progress = score_progress(
            report=report,
            validation=validation,
            attempt_index=1,
            max_attempts=4,
            success_threshold=80.0,
        )
        self.assertEqual(progress["stage_completion_percent"], 50.0)
        self.assertEqual(progress["count_completeness_percent"], 80.0)
        self.assertEqual(progress["eta_health_percent"], 100.0)
        self.assertEqual(progress["quality_fit_percent"], 92.5)
        self.assertFalse(progress["can_advance"])
        self.assertTrue(progress["should_retry"])

    def test_eta_breach_marks_user_decision_pending(self) -> None:
        report = self._report()
        report["throughput_evidence"]["estimated_eta_hours"] = 96.0
        report["throughput_evidence"]["threshold_breach"] = True
        validation = {"collection_slug": "pyxida", "stage": "discover", "failure_class": "partial"}
        progress = score_progress(
            report=report,
            validation=validation,
            attempt_index=2,
            max_attempts=4,
            success_threshold=80.0,
        )
        self.assertTrue(progress["user_decision_pending"])
        self.assertEqual(progress["user_decision_reason"], "recent ETA exceeds the 48-hour target")

    def test_attempt_budget_exhaustion_marks_user_decision_pending(self) -> None:
        report = self._report()
        validation = {"collection_slug": "pyxida", "stage": "discover", "failure_class": "partial"}
        progress = score_progress(
            report=report,
            validation=validation,
            attempt_index=4,
            max_attempts=4,
            success_threshold=95.0,
        )
        self.assertTrue(progress["user_decision_pending"])
        self.assertIn("attempt budget exhausted", progress["user_decision_reason"])


if __name__ == "__main__":
    unittest.main()
