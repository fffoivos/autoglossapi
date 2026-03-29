from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class HarnessDryRunTests(unittest.TestCase):
    def test_wave1_discover_dry_run_generates_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [
                    "python3",
                    str(REPO_ROOT / "controller" / "launch_codex_exec_harness.py"),
                    "--stage",
                    "discover",
                    "--collections-file",
                    str(REPO_ROOT / "config" / "collections" / "wave1_high_quality_easy.json"),
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
            jobs = manifest["jobs"]
            self.assertEqual(len(jobs), 4)
            slugs = {job["collection_slug"] for job in jobs}
            self.assertEqual(slugs, {"uth_rep", "psepheda", "ntua", "pyxida"})
            for job in jobs:
                self.assertTrue(Path(job["prompt_path"]).exists())
                self.assertEqual(job["status"], "prepared")


if __name__ == "__main__":
    unittest.main()
