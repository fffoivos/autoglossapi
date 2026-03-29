from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class RuntimeHarnessDryRunTests(unittest.TestCase):
    def test_runtime_dry_run_generates_bundle_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [
                    "python3",
                    str(REPO_ROOT / "controller" / "launch_runtime_task.py"),
                    "--task-file",
                    str(REPO_ROOT / "runtime" / "examples" / "repair_existing_ocr_host.json"),
                    "--output-root",
                    tmpdir,
                ],
                check=True,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
            )
            run_dir = Path(result.stdout.strip())
            manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "prepared")
            self.assertTrue(Path(manifest["resolved_task_path"]).exists())
            self.assertTrue(Path(manifest["prompt_path"]).exists())
            self.assertTrue((run_dir / "task_spec.json").exists())
            resolved = json.loads(Path(manifest["resolved_task_path"]).read_text(encoding="utf-8"))
            self.assertEqual(resolved["execution_plan"]["bootstrap_mode"], "repair")
            self.assertTrue(resolved["execution_plan"]["run_ocr_smoke_test"])


if __name__ == "__main__":
    unittest.main()
