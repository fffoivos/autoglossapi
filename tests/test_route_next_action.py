from __future__ import annotations

import unittest

from controller.route_next_action import decide_next_action


class RouteNextActionTests(unittest.TestCase):
    def test_success_advances_stage(self) -> None:
        decision = decide_next_action(
            {
                "collection_slug": "pyxida",
                "stage": "discover",
                "failure_class": "success",
            }
        )
        self.assertEqual(decision["decision"], "advance")
        self.assertEqual(decision["next_stage"], "feasibility")

    def test_schema_failure_uses_repair_mode(self) -> None:
        decision = decide_next_action(
            {
                "collection_slug": "pyxida",
                "stage": "discover",
                "failure_class": "schema_failed",
            }
        )
        self.assertEqual(decision["decision"], "retry_same_stage")
        self.assertEqual(decision["retry_prompt_mode"], "schema_repair")

    def test_exhausted_escalates(self) -> None:
        decision = decide_next_action(
            {
                "collection_slug": "pyxida",
                "stage": "feasibility",
                "failure_class": "exhausted",
            }
        )
        self.assertEqual(decision["decision"], "escalate")
        self.assertIsNone(decision["next_stage"])

    def test_smoke_test_success_advances_to_bulk_run(self) -> None:
        decision = decide_next_action(
            {
                "collection_slug": "pyxida",
                "stage": "smoke_test_scraper",
                "failure_class": "success",
            }
        )
        self.assertEqual(decision["decision"], "advance")
        self.assertEqual(decision["next_stage"], "bulk_run_scraper")


if __name__ == "__main__":
    unittest.main()
