from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class RuntimeTaskBundleTests(unittest.TestCase):
    def test_render_example_bundle_includes_worker_recommendation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [
                    "python3",
                    str(REPO_ROOT / "runtime" / "render_runtime_task.py"),
                    "--task-file",
                    str(REPO_ROOT / "runtime" / "examples" / "provision_g7e_deepseek.json"),
                    "--output-dir",
                    tmpdir,
                ],
                check=True,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
            )
            manifest = json.loads(result.stdout)
            resolved = json.loads(Path(manifest["resolved_task_path"]).read_text(encoding="utf-8"))
            self.assertEqual(resolved["task_type"], "provision_glossapi_host")
            self.assertEqual(resolved["recommended_parameters"]["ocr"]["recommended_initial_workers"], 4)
            self.assertIn("Rust and Cargo are installed so rust extensions can build cleanly.", resolved["what_must_be_true"])
            self.assertEqual(resolved["execution_plan"]["bootstrap_mode"], "provision")
            self.assertTrue(resolved["execution_plan"]["update_repo"])
            prompt_text = Path(manifest["prompt_path"]).read_text(encoding="utf-8")
            self.assertIn("bootstrap_glossapi_aws.sh", prompt_text)
            self.assertIn("deepseek_ocr_g7e_20260329.json", prompt_text)

    def test_render_from_cli_flags_for_repair_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(
                [
                    "python3",
                    str(REPO_ROOT / "runtime" / "render_runtime_task.py"),
                    "--task-type",
                    "repair_glossapi_host",
                    "--target-name",
                    "repair-box",
                    "--instance-profile",
                    "aws_g7e_48xlarge",
                    "--expect-gpu",
                    "--needs-rust",
                    "--needs-cleaner",
                    "--needs-deepseek-ocr",
                    "--benchmark-ocr",
                    "--auto-worker-tuning",
                    "--public-ip",
                    "54.224.252.101",
                    "--repo-path",
                    "/opt/dlami/nvme/glossapi/glossAPI",
                    "--runtime-python",
                    "/opt/dlami/nvme/glossapi/glossAPI/dependency_setup/deepseek_uv/dependency_setup/.venvs/deepseek/bin/python",
                    "--output-dir",
                    tmpdir,
                ],
                check=True,
                cwd=REPO_ROOT,
            )
            resolved = json.loads((Path(tmpdir) / "resolved_task.json").read_text(encoding="utf-8"))
            self.assertEqual(resolved["task_type"], "repair_glossapi_host")
            self.assertEqual(resolved["existing_host"]["public_ip"], "54.224.252.101")
            self.assertIn("Inspect the existing host state before changing anything.", resolved["workflow_steps"])
            self.assertEqual(resolved["execution_plan"]["bootstrap_mode"], "repair")
            self.assertFalse(resolved["execution_plan"]["update_repo"])
            self.assertTrue(resolved["execution_plan"]["run_ocr_smoke_test"])


if __name__ == "__main__":
    unittest.main()
