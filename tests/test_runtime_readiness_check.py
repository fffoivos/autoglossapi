from __future__ import annotations

import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from runtime.aws import check_glossapi_runtime as readiness


class RuntimeReadinessCheckTests(unittest.TestCase):
    def test_main_preserves_symlink_python_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            repo = tmp_path / "repo"
            repo.mkdir()
            output = tmp_path / "report.json"
            fake_python = tmp_path / "venv" / "bin" / "python"
            fake_python.parent.mkdir(parents=True)
            fake_python.write_text("", encoding="utf-8")

            args = Namespace(
                repo=repo,
                python_bin=fake_python,
                expect_gpu=False,
                output=output,
                strict=False,
                launch_investigation=False,
                artifact_dir=None,
                workdir=tmp_path,
            )

            with (
                patch.object(readiness, "parse_args", return_value=args),
                patch.object(readiness, "_check_commands", return_value=[]),
                patch.object(readiness, "_check_repo", return_value=[]),
                patch.object(readiness, "_check_gpu", return_value=[]),
                patch.object(
                    readiness,
                    "_check_python",
                    return_value=[readiness.CheckResult("python:version", "pass", "ok")],
                ) as check_python,
            ):
                exit_code = readiness.main()

            self.assertEqual(exit_code, 0)
            check_python.assert_called_once_with(fake_python, repo.resolve())
            summary = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(summary["python_bin"], str(fake_python))


if __name__ == "__main__":
    unittest.main()
