from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def make_collections_file(root: Path) -> Path:
    collections_file = root / "collections.json"
    write_json(
        collections_file,
        [
            {
                "agent_id": "agent011_pyxida",
                "collection_slug": "pyxida",
                "repo_host": "pyxida.aueb.gr",
                "repo_url_hint": "https://pyxida.aueb.gr/",
                "sample_item_url_hint": "https://pyxida.aueb.gr/handle/123456789/3707",
                "platform_hint": "dspace7",
                "priority_kind": "whole_collection",
                "tapped_target_rows": 0,
                "untapped_target_rows": 11622,
                "content_priority": "high",
                "extraction_ease": "easy",
                "dominant_target_types": [{"type": "text", "count": 11450}],
                "search_query_hint": "ΠΥΞΙΔΑ Οικονομικό Πανεπιστήμιο Αθηνών pyxida",
                "notes": "test fixture",
            }
        ],
    )
    return collections_file


def make_previous_run(
    root: Path,
    *,
    stage: str,
    failure_class: str,
    promotable: bool,
    decision: str,
    next_stage: str | None,
    retry_prompt_mode: str | None = None,
) -> Path:
    previous_run_dir = root / f"previous_{stage}"
    job_dir = previous_run_dir / "jobs" / "pyxida"
    write_json(
        previous_run_dir / "run_manifest.json",
        {
            "stage": stage,
            "workdir": str(REPO_ROOT),
            "collections_file": "config/collections/wave1_high_quality_easy.json",
            "jobs": [
                {
                    "collection_slug": "pyxida",
                    "job_dir": str(job_dir),
                }
            ],
        },
    )
    write_json(
        job_dir / "final.json",
        {
            "collection_slug": "pyxida",
            "stage": stage,
            "status": "success" if promotable else "partial",
        },
    )
    write_json(
        job_dir / "validation.json",
        {
            "collection_slug": "pyxida",
            "stage": stage,
            "schema_valid": True,
            "failure_class": failure_class,
            "promotable": promotable,
            "missing_checklist_ids": ["pdf_presence"] if not promotable else [],
            "non_done_checklist_ids": ["pdf_presence"] if not promotable else [],
            "artifact_issues": [],
            "notes": ["fixture validation"],
        },
    )
    write_json(
        job_dir / "next_action.json",
        {
            "collection_slug": "pyxida",
            "current_stage": stage,
            "failure_class": failure_class,
            "decision": decision,
            "next_stage": next_stage,
            "retry_prompt_mode": retry_prompt_mode,
            "reason": "fixture route",
        },
    )
    return previous_run_dir


class StageProgressionTests(unittest.TestCase):
    def test_feasibility_dry_run_uses_previous_discover_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            collections_file = make_collections_file(root)
            previous_run_dir = make_previous_run(
                root,
                stage="discover",
                failure_class="success",
                promotable=True,
                decision="advance",
                next_stage="feasibility",
            )
            result = subprocess.run(
                [
                    "python3",
                    str(REPO_ROOT / "controller" / "launch_codex_exec_harness.py"),
                    "--stage",
                    "feasibility",
                    "--previous-run-dir",
                    str(previous_run_dir),
                    "--collections-file",
                    str(collections_file),
                    "--output-root",
                    str(root / "runs"),
                ],
                check=True,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
            )
            run_dir = Path(result.stdout.strip())
            manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
            job = manifest["jobs"][0]
            self.assertEqual(job["previous_stage"], "discover")
            self.assertEqual(
                job["previous_report"],
                str(previous_run_dir / "jobs" / "pyxida" / "final.json"),
            )
            prompt_text = Path(job["prompt_path"]).read_text(encoding="utf-8")
            self.assertIn("Treat the previous discover report as baseline context", prompt_text)
            self.assertIn("previous_stage: `discover`", prompt_text)

    def test_same_stage_retry_uses_retry_prompt_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            collections_file = make_collections_file(root)
            previous_run_dir = make_previous_run(
                root,
                stage="feasibility",
                failure_class="partial",
                promotable=False,
                decision="retry_same_stage",
                next_stage=None,
                retry_prompt_mode="unresolved_checklist",
            )
            result = subprocess.run(
                [
                    "python3",
                    str(REPO_ROOT / "controller" / "launch_codex_exec_harness.py"),
                    "--stage",
                    "feasibility",
                    "--previous-run-dir",
                    str(previous_run_dir),
                    "--collections-file",
                    str(collections_file),
                    "--output-root",
                    str(root / "runs"),
                ],
                check=True,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
            )
            run_dir = Path(result.stdout.strip())
            manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
            job = manifest["jobs"][0]
            self.assertEqual(job["retry_prompt_mode"], "unresolved_checklist")
            prompt_text = Path(job["prompt_path"]).read_text(encoding="utf-8")
            self.assertIn("retry_prompt_mode: `unresolved_checklist`", prompt_text)
            self.assertIn("Focus on checklist items still marked partial or unresolved.", prompt_text)

    def test_review_plan_path_is_carried_into_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            collections_file = make_collections_file(root)
            previous_run_dir = make_previous_run(
                root,
                stage="discover",
                failure_class="success",
                promotable=True,
                decision="advance",
                next_stage="feasibility",
            )
            review_plan_path = root / "review_plan.json"
            write_json(
                review_plan_path,
                {
                    "collection_slug": "pyxida",
                    "stage": "discover",
                    "decision": "retry_same_stage",
                    "decision_reason": "fixture review",
                },
            )
            result = subprocess.run(
                [
                    "python3",
                    str(REPO_ROOT / "controller" / "launch_codex_exec_harness.py"),
                    "--stage",
                    "feasibility",
                    "--previous-run-dir",
                    str(previous_run_dir),
                    "--review-plan-path",
                    str(review_plan_path),
                    "--collections-file",
                    str(collections_file),
                    "--output-root",
                    str(root / "runs"),
                ],
                check=True,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
            )
            run_dir = Path(result.stdout.strip())
            manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
            job = manifest["jobs"][0]
            self.assertEqual(job["review_plan_path"], str(review_plan_path))
            prompt_text = Path(job["prompt_path"]).read_text(encoding="utf-8")
            self.assertIn("Latest improvement review:", prompt_text)
            self.assertIn(str(review_plan_path), prompt_text)

    def test_review_plan_can_override_partial_stage_for_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            collections_file = make_collections_file(root)
            previous_run_dir = make_previous_run(
                root,
                stage="discover",
                failure_class="partial",
                promotable=False,
                decision="retry_same_stage",
                next_stage=None,
                retry_prompt_mode="unresolved_checklist",
            )
            review_plan_path = root / "review_plan.json"
            write_json(
                review_plan_path,
                {
                    "collection_slug": "pyxida",
                    "stage": "discover",
                    "failure_class": "partial",
                    "overall_progress_percent": 98.0,
                    "stage_completion_percent": 95.0,
                    "count_completeness_percent": 100.0,
                    "eta_health_percent": 100.0,
                    "quality_fit_percent": 100.0,
                    "success_threshold_percent": 80.0,
                    "issue_labels": ["overall_progress:98.0%:strong"],
                    "decision": "advance",
                    "decision_reason": "Good enough to promote.",
                    "improvement_hypotheses": [],
                    "changes_to_try": [],
                    "expected_gain_percent": 5.0,
                    "user_decision_required": False,
                    "user_decision_question": None,
                    "confidence": "medium",
                },
            )
            result = subprocess.run(
                [
                    "python3",
                    str(REPO_ROOT / "controller" / "launch_codex_exec_harness.py"),
                    "--stage",
                    "feasibility",
                    "--previous-run-dir",
                    str(previous_run_dir),
                    "--review-plan-path",
                    str(review_plan_path),
                    "--collections-file",
                    str(collections_file),
                    "--output-root",
                    str(root / "runs"),
                ],
                check=True,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
            )
            run_dir = Path(result.stdout.strip())
            manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["jobs"][0]["previous_stage"], "discover")

    def test_later_stage_cannot_skip_required_previous_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            collections_file = make_collections_file(root)
            previous_run_dir = make_previous_run(
                root,
                stage="discover",
                failure_class="success",
                promotable=True,
                decision="advance",
                next_stage="feasibility",
            )
            result = subprocess.run(
                [
                    "python3",
                    str(REPO_ROOT / "controller" / "launch_codex_exec_harness.py"),
                    "--stage",
                    "sample_validation",
                    "--previous-run-dir",
                    str(previous_run_dir),
                    "--collections-file",
                    str(collections_file),
                    "--output-root",
                    str(root / "runs"),
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "expects previous stage `feasibility`, but found `discover`",
                result.stderr,
            )

    def test_advance_stage_promotes_promotable_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            collections_file = make_collections_file(root)
            previous_run_dir = make_previous_run(
                root,
                stage="discover",
                failure_class="success",
                promotable=True,
                decision="advance",
                next_stage="feasibility",
            )
            result = subprocess.run(
                [
                    "python3",
                    str(REPO_ROOT / "controller" / "advance_stage.py"),
                    "--previous-run-dir",
                    str(previous_run_dir),
                    "--collections-file",
                    str(collections_file),
                    "--output-root",
                    str(root / "runs"),
                ],
                check=True,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
            )
            run_dir = Path(result.stdout.strip())
            manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["stage"], "feasibility")
            self.assertEqual([job["collection_slug"] for job in manifest["jobs"]], ["pyxida"])


if __name__ == "__main__":
    unittest.main()
