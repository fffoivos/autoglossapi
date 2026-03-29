from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from controller.review_stage_outcome import build_prompt, fallback_review_plan
from scripts.generate_tracking_backlogs import generate_review_memory_outputs


class ReviewerMemoryTests(unittest.TestCase):
    def test_fallback_review_plan_emits_problem_tags_and_knowledge_refs(self) -> None:
        report = {
            "collection_slug": "pyxida",
            "stage": "discover",
            "failed_checklist_ids": ["request_capacity"],
            "alternative_hypotheses": ["probe a slower file cadence"],
            "tried_hypotheses": ["light probe"],
        }
        validation = {
            "collection_slug": "pyxida",
            "stage": "discover",
            "failure_class": "partial",
            "non_done_checklist_ids": ["request_capacity"],
        }
        progress = {
            "overall_progress_percent": 92.0,
            "stage_completion_percent": 95.0,
            "count_completeness_percent": 100.0,
            "eta_health_percent": 100.0,
            "quality_fit_percent": 100.0,
            "success_threshold_percent": 80.0,
            "issue_labels": [{"label": "eta_health", "percent": 100.0, "status": "complete"}],
            "user_decision_pending": False,
        }
        plan = fallback_review_plan(report=report, validation=validation, progress=progress)
        self.assertEqual(plan["decision"], "advance")
        self.assertIn("failure:partial", plan["problem_tags"])
        self.assertIn("checklist:request_capacity", plan["problem_tags"])
        self.assertIn("request_capacity", plan["matched_solution_ids"])
        self.assertTrue(any(ref.endswith("/knowledge/reviewer/stages/discover.md") for ref in plan["knowledge_refs"]))
        self.assertEqual(plan["target_progress_percent"], 80.0)

    def test_build_prompt_mentions_reviewer_knowledge_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            report_path = root / "report.json"
            validation_path = root / "validation.json"
            progress_path = root / "progress.json"
            report_path.write_text('{"collection_slug":"pyxida","stage":"discover"}\n', encoding="utf-8")
            validation_path.write_text('{"collection_slug":"pyxida","stage":"discover"}\n', encoding="utf-8")
            progress_path.write_text('{"collection_slug":"pyxida","stage":"discover"}\n', encoding="utf-8")
            prompt = build_prompt(
                report_path=report_path,
                validation_path=validation_path,
                progress_path=progress_path,
                events_path=None,
                schema_path=Path("/tmp/schema.json"),
            )
            self.assertIn("Reviewer knowledge assets:", prompt)
            self.assertIn("knowledge/reviewer/stages/discover.md", prompt)

    def test_generate_review_memory_outputs_tracks_recovery_delta(self) -> None:
        history = {
            "pyxida": [
                {
                    "run_id": "20260329T100000Z_discover",
                    "job_dir": "/tmp/pyxida_a",
                    "stage": "discover",
                    "progress": {
                        "overall_progress_percent": 20.0,
                        "issue_labels": [{"label": "stage_completion", "percent": 20.0, "status": "weak"}],
                    },
                    "validation": {"failure_class": "partial", "promotable": False},
                    "improvement": {
                        "decision": "retry_same_stage",
                        "problem_tags": ["checklist:request_capacity"],
                        "changes_to_try": ["reduce file frequency"],
                        "improvement_hypotheses": ["respect reset window"],
                        "target_progress_percent": 80.0,
                    },
                },
                {
                    "run_id": "20260329T110000Z_discover",
                    "job_dir": "/tmp/pyxida_b",
                    "stage": "discover",
                    "progress": {
                        "overall_progress_percent": 50.0,
                        "issue_labels": [{"label": "stage_completion", "percent": 50.0, "status": "partial"}],
                    },
                    "validation": {"failure_class": "partial", "promotable": False},
                    "improvement": {},
                },
            ]
        }
        generated_rows, recovery_cases, recovery_stats, _summary = generate_review_memory_outputs(history)
        self.assertEqual(len(generated_rows), 1)
        self.assertEqual(recovery_cases[0]["delta_progress_percent"], 30.0)
        stat_row = recovery_stats[0]
        self.assertEqual(stat_row["problem_tag"], "checklist:request_capacity")
        self.assertEqual(stat_row["avg_delta_progress_percent"], 30.0)


if __name__ == "__main__":
    unittest.main()
