from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from scrapers.common.download_telemetry import (
    CodexExecInvestigationLauncher,
    DownloadEvent,
    RollingDownloadConfig,
    RollingDownloadMonitor,
    build_codex_investigation_prompt,
)


class FakeLauncher:
    def __init__(self) -> None:
        self.payloads = []

    def launch(self, payload):
        self.payloads.append(payload)
        return {"pid": 12345, "launched": True}


class DownloadTelemetryTests(unittest.TestCase):
    def test_monitor_computes_rolling_eta_and_logs_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config = RollingDownloadConfig(
                collection_slug="pyxida",
                total_expected_items=10,
                rolling_window_seconds=600.0,
                target_eta_hours=48.0,
                event_log_path=root / "download_events.jsonl",
                snapshot_path=root / "download_snapshot.json",
                investigation_log_path=root / "investigations.jsonl",
            )
            monitor = RollingDownloadMonitor(config)
            base = time.time()
            for index in range(4):
                snapshot = monitor.record_event(
                    DownloadEvent(
                        timestamp=base + index * 10.0,
                        kind="file",
                        url=f"https://example.org/file-{index}.pdf",
                        ok=True,
                        duration_seconds=5.0,
                        bytes_received=5_000_000,
                        status_code=200,
                    )
                )

            self.assertEqual(snapshot["completed_items"], 4)
            self.assertFalse(snapshot["threshold_breach"])
            self.assertGreater(snapshot["recent_files"]["bytes_per_second"], 0.0)
            self.assertTrue((root / "download_events.jsonl").exists())
            self.assertTrue((root / "download_snapshot.json").exists())
            logged = (root / "download_events.jsonl").read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(logged), 4)

    def test_slow_eta_triggers_investigation_launcher(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            launcher = FakeLauncher()
            config = RollingDownloadConfig(
                collection_slug="slow_repo",
                total_expected_items=5_000,
                rolling_window_seconds=600.0,
                target_eta_hours=48.0,
                min_file_events_for_eta=3,
                event_log_path=root / "download_events.jsonl",
                snapshot_path=root / "download_snapshot.json",
                investigation_log_path=root / "investigations.jsonl",
            )
            monitor = RollingDownloadMonitor(config, investigation_launcher=launcher)
            base = time.time()
            for index in range(3):
                snapshot = monitor.record_event(
                    DownloadEvent(
                        timestamp=base + index * 120.0,
                        kind="file",
                        url=f"https://example.org/slow-{index}.pdf",
                        ok=True,
                        duration_seconds=100.0,
                        bytes_received=500_000,
                        status_code=200,
                    )
                )

            self.assertTrue(snapshot["threshold_breach"])
            self.assertEqual(len(launcher.payloads), 1)
            self.assertTrue((root / "investigations.jsonl").exists())

    def test_codex_launcher_writes_context_and_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            launcher = CodexExecInvestigationLauncher(
                workdir=root,
                artifact_dir=root / "artifacts",
                codex_bin="codex",
            )
            payload = FakeLauncher()
            with patch("scrapers.common.download_telemetry.subprocess.Popen") as mock_popen:
                process = MagicMock()
                process.pid = 999
                process.stdin = MagicMock()
                mock_popen.return_value = process
                from scrapers.common.download_telemetry import CodexInvestigationPayload

                result = launcher.launch(
                    CodexInvestigationPayload(
                        collection_slug="pyxida",
                        total_expected_items=100,
                        completed_items=10,
                        remaining_items=90,
                        recent_window_seconds=600.0,
                        recent_file_rate_per_hour=5.0,
                        recent_bytes_per_second=2048.0,
                        recent_metadata_rps=2.0,
                        estimated_eta_hours=18.0,
                        target_eta_hours=48.0,
                        suggested_parallel_downloads=4,
                        status_counts_recent={"200": 10},
                        recent_errors=[],
                        notes=["all good"],
                    )
                )
            self.assertEqual(result["pid"], 999)
            self.assertTrue(Path(result["context_path"]).exists())
            self.assertTrue(Path(result["prompt_path"]).exists())
            context = json.loads(Path(result["context_path"]).read_text(encoding="utf-8"))
            self.assertEqual(context["collection_slug"], "pyxida")
            process.stdin.write.assert_called()
            process.stdin.close.assert_called_once()

    def test_prompt_mentions_threshold_and_context(self) -> None:
        from scrapers.common.download_telemetry import CodexInvestigationPayload

        prompt = build_codex_investigation_prompt(
            CodexInvestigationPayload(
                collection_slug="pyxida",
                total_expected_items=100,
                completed_items=10,
                remaining_items=90,
                recent_window_seconds=600.0,
                recent_file_rate_per_hour=5.0,
                recent_bytes_per_second=2048.0,
                recent_metadata_rps=2.0,
                estimated_eta_hours=72.0,
                target_eta_hours=48.0,
                suggested_parallel_downloads=4,
                status_counts_recent={"200": 10, "429": 2},
                recent_errors=[{"status_code": 429, "url": "https://example.org/file.pdf"}],
                notes=["slow download detected"],
            ),
            Path("/tmp/context.json"),
        )
        self.assertIn("target_eta_hours", prompt)
        self.assertIn("429", prompt)
        self.assertIn("slow download detected", prompt)


if __name__ == "__main__":
    unittest.main()
