from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from controller.human_decision import (
    load_human_decision,
    prepare_resume_state,
    synthesize_review_plan_from_human_decision,
)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class HumanDecisionTests(unittest.TestCase):
    def test_load_human_decision_validates_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            decision_path = root / "decision.json"
            write_json(
                decision_path,
                {
                    "decision_id": "pyxida_discover_1",
                    "collection_slug": "pyxida",
                    "stage": "discover",
                    "decision": "retry_same_stage",
                    "decision_reason": "Authorize one more discover retry.",
                    "instructions": ["Probe a safer file cadence."],
                    "approved_by": "foivos",
                    "approved_at": "2026-03-29T16:00:00Z",
                    "approved_eta_ceiling_hours": 72.0,
                    "target_progress_percent": 100.0,
                    "scope_override": None,
                    "notes": None,
                },
            )
            loaded = load_human_decision(decision_path)
            self.assertEqual(loaded["decision"], "retry_same_stage")

    def test_prepare_resume_state_for_retry_same_stage(self) -> None:
        manifest = {
            "collection_slug": "pyxida",
            "final_state": "decision_pending_user",
            "history": [
                {
                    "stage": "discover",
                    "attempt_index": 1,
                    "run_dir": "/tmp/runs/20260329T151206Z_discover",
                    "improvement": {
                        "failure_class": "partial",
                        "overall_progress_percent": 96.68,
                    },
                }
            ],
        }
        decision = {
            "decision_id": "pyxida_discover_1",
            "collection_slug": "pyxida",
            "stage": "discover",
            "decision": "retry_same_stage",
            "decision_reason": "Retry discover.",
            "instructions": ["Probe more slowly."],
            "approved_by": "foivos",
            "approved_at": "2026-03-29T16:00:00Z",
        }
        resume = prepare_resume_state(manifest=manifest, decision=decision, collection_slug="pyxida")
        self.assertEqual(resume["current_stage"], "discover")
        self.assertEqual(resume["attempt_index"], 2)
        self.assertEqual(str(resume["previous_run_dir"]), "/tmp/runs/20260329T151206Z_discover")

    def test_synthesize_review_plan_from_human_decision(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output_path = root / "review_plan.json"
            path = synthesize_review_plan_from_human_decision(
                decision={
                    "decision_id": "pyxida_discover_1",
                    "collection_slug": "pyxida",
                    "stage": "discover",
                    "decision": "retry_same_stage",
                    "decision_reason": "Retry discover with lower file cadence.",
                    "instructions": [
                        "Probe file downloads with much longer gaps.",
                        "Recompute ETA from the safe cadence.",
                    ],
                    "approved_by": "foivos",
                    "approved_at": "2026-03-29T16:00:00Z",
                    "approved_eta_ceiling_hours": 72.0,
                },
                previous_improvement={
                    "failure_class": "partial",
                    "overall_progress_percent": 96.68,
                    "stage_completion_percent": 95.83,
                    "count_completeness_percent": 100.0,
                    "eta_health_percent": 91.72,
                    "quality_fit_percent": 100.0,
                    "success_threshold_percent": 80.0,
                    "issue_labels": ["eta_health:91.72%:strong"],
                    "problem_tags": ["checklist:request_capacity"],
                    "matched_solution_ids": ["dspace_429_backoff"],
                    "knowledge_refs": ["/tmp/example.md"],
                    "target_progress_percent": 100.0,
                },
                output_path=output_path,
            )
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["decision"], "retry_same_stage")
            self.assertIn("decision:human_override", payload["problem_tags"])
            self.assertEqual(payload["changes_to_try"][0], "Probe file downloads with much longer gaps.")


if __name__ == "__main__":
    unittest.main()
