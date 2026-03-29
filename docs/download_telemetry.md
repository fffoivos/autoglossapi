# Download Telemetry

Deterministic scrapers should use the shared rolling download monitor in [scrapers/common/download_telemetry.py](/home/foivos/Projects/automated-glossapi/scrapers/common/download_telemetry.py).

The goal is to make throughput evidence operational rather than anecdotal:

- log every metadata and file request
- compute rolling recent throughput
- estimate ETA for the remaining corpus
- trigger a Codex investigation if recent throughput projects past the slow threshold

Minimal usage pattern:

```python
from pathlib import Path
import time

from scrapers.common.download_telemetry import (
    CodexExecInvestigationLauncher,
    DownloadEvent,
    RollingDownloadConfig,
    RollingDownloadMonitor,
)

telemetry = RollingDownloadMonitor(
    RollingDownloadConfig(
        collection_slug="pyxida",
        total_expected_items=12265,
        rolling_window_seconds=900.0,
        target_eta_hours=48.0,
        suggested_parallel_downloads=4,
        event_log_path=Path("logs/download_events.jsonl"),
        snapshot_path=Path("logs/download_snapshot.json"),
        investigation_log_path=Path("logs/investigations.jsonl"),
    ),
    investigation_launcher=CodexExecInvestigationLauncher(
        workdir=Path("."),
        artifact_dir=Path("logs/codex_investigations"),
    ),
)

snapshot = telemetry.record_event(
    DownloadEvent(
        timestamp=time.time(),
        kind="file",
        url="https://example.org/file.pdf",
        ok=True,
        duration_seconds=4.2,
        bytes_received=4_800_000,
        status_code=200,
    )
)
```

The rolling snapshot is suitable for status printing in a downloader and for periodic persistence to a metrics file.
