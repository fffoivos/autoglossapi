from __future__ import annotations

import unittest
from pathlib import Path

from runtime.investigation import (
    GlossAPIRuntimeInvestigationPayload,
    RuntimeIssue,
    build_runtime_investigation_prompt,
)


class RuntimeInvestigationPromptTests(unittest.TestCase):
    def test_prompt_includes_issue_summary_and_requested_outcomes(self) -> None:
        payload = GlossAPIRuntimeInvestigationPayload(
            target_name="glossAPI",
            runtime_kind="aws_or_remote_host",
            objective="prepare a host for OCR",
            issue_summary="runtime readiness returned fail",
            readiness_report_path="runs/runtime_check.json",
            benchmark_artifact_paths=["runs/bench.json"],
            issues=[
                RuntimeIssue(
                    issue_id="command:rustc",
                    severity="fail",
                    component="command",
                    summary="missing required command `rustc`",
                )
            ],
            known_facts=["Rust is required for cleaner builds."],
            requested_outcomes=["repair the runtime", "recommend the next validation step"],
        )

        prompt = build_runtime_investigation_prompt(payload, Path("context.json"))

        self.assertIn("runtime readiness returned fail", prompt)
        self.assertIn("missing required command `rustc`", prompt)
        self.assertIn("repair the runtime", prompt)
        self.assertIn("recommend the next validation step", prompt)
        self.assertIn("context.json", prompt)


if __name__ == "__main__":
    unittest.main()
