from __future__ import annotations

from collections import Counter, deque
from dataclasses import asdict, dataclass, field
import json
import math
from pathlib import Path
import subprocess
import time
from typing import Any, Protocol


SECONDS_PER_HOUR = 3600.0


@dataclass
class DownloadEvent:
    timestamp: float
    kind: str
    url: str
    ok: bool
    duration_seconds: float
    bytes_received: int = 0
    status_code: int | None = None
    item_id: str | None = None
    collection_slug: str | None = None
    response_headers: dict[str, str] = field(default_factory=dict)
    response_excerpt: str | None = None
    error: str | None = None
    attempt: int = 1
    note: str | None = None

    def to_json(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["timestamp_iso"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.timestamp))
        return payload


@dataclass
class CodexInvestigationPayload:
    collection_slug: str
    total_expected_items: int | None
    completed_items: int
    remaining_items: int | None
    recent_window_seconds: float
    recent_file_rate_per_hour: float | None
    recent_bytes_per_second: float | None
    recent_metadata_rps: float | None
    estimated_eta_hours: float | None
    target_eta_hours: float
    suggested_parallel_downloads: int | None
    status_counts_recent: dict[str, int]
    recent_errors: list[dict[str, Any]]
    notes: list[str]

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


class InvestigationLauncher(Protocol):
    def launch(self, payload: CodexInvestigationPayload) -> dict[str, Any]:
        ...


def build_codex_investigation_prompt(payload: CodexInvestigationPayload, context_path: Path) -> str:
    status_counts = ", ".join(f"{code}:{count}" for code, count in sorted(payload.status_counts_recent.items())) or "none"
    recent_errors = json.dumps(payload.recent_errors, ensure_ascii=False, indent=2)
    return f"""You are investigating a slow or unstable direct-repository download run for GlossAPI.

Context JSON:
- `{context_path}`

Collection:
- `{payload.collection_slug}`

Current throughput snapshot:
- total_expected_items: `{payload.total_expected_items}`
- completed_items: `{payload.completed_items}`
- remaining_items: `{payload.remaining_items}`
- recent_window_seconds: `{payload.recent_window_seconds}`
- recent_file_rate_per_hour: `{payload.recent_file_rate_per_hour}`
- recent_bytes_per_second: `{payload.recent_bytes_per_second}`
- recent_metadata_rps: `{payload.recent_metadata_rps}`
- estimated_eta_hours: `{payload.estimated_eta_hours}`
- target_eta_hours: `{payload.target_eta_hours}`
- suggested_parallel_downloads: `{payload.suggested_parallel_downloads}`
- recent_status_counts: `{status_counts}`

Recent errors:
```json
{recent_errors}
```

Notes:
{chr(10).join(f"- {note}" for note in payload.notes) if payload.notes else "- none"}

Task:
- analyze whether the bottleneck is likely API pacing, file-serving speed, parallelism, throttling, access restrictions, or implementation overhead
- suggest the next concrete debugging steps
- suggest safe changes to concurrency, retry policy, pacing, or endpoint choice
- keep the answer concise and operational
"""


@dataclass
class CodexExecInvestigationLauncher:
    workdir: Path
    artifact_dir: Path
    codex_bin: str = "codex"
    model: str = "gpt-5.4"
    reasoning_effort: str = "xhigh"
    sandbox_mode: str = "danger-full-access"

    def launch(self, payload: CodexInvestigationPayload) -> dict[str, Any]:
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        context_path = self.artifact_dir / f"codex_investigation_{payload.collection_slug}_{stamp}.json"
        prompt_path = self.artifact_dir / f"codex_investigation_{payload.collection_slug}_{stamp}.txt"
        output_path = self.artifact_dir / f"codex_investigation_{payload.collection_slug}_{stamp}.jsonl"
        context_path.write_text(json.dumps(payload.to_json(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        prompt = build_codex_investigation_prompt(payload, context_path)
        prompt_path.write_text(prompt, encoding="utf-8")

        command = [
            self.codex_bin,
            "exec",
            "--skip-git-repo-check",
            "--cd",
            str(self.workdir),
            "--model",
            self.model,
            "-c",
            f'model_reasoning_effort="{self.reasoning_effort}"',
            "-c",
            'approval_policy="never"',
            "-s",
            self.sandbox_mode,
            "--add-dir",
            str(self.artifact_dir),
            "--json",
            "-",
        ]

        output_handle = output_path.open("w", encoding="utf-8")
        process = subprocess.Popen(
            command,
            cwd=str(self.workdir),
            stdin=subprocess.PIPE,
            stdout=output_handle,
            stderr=subprocess.STDOUT,
            text=True,
        )
        assert process.stdin is not None
        process.stdin.write(prompt)
        process.stdin.close()
        output_handle.close()
        return {
            "pid": process.pid,
            "command": command,
            "context_path": str(context_path),
            "prompt_path": str(prompt_path),
            "output_path": str(output_path),
            "launched_at": stamp,
        }


@dataclass
class RollingDownloadConfig:
    collection_slug: str
    total_expected_items: int | None = None
    already_completed_items: int = 0
    rolling_window_seconds: float = 900.0
    target_eta_hours: float = 48.0
    min_file_events_for_eta: int = 3
    min_metadata_events_for_rate: int = 3
    suggested_parallel_downloads: int | None = None
    investigation_cooldown_seconds: float = 1800.0
    event_log_path: Path | None = None
    snapshot_path: Path | None = None
    investigation_log_path: Path | None = None


class RollingDownloadMonitor:
    def __init__(
        self,
        config: RollingDownloadConfig,
        investigation_launcher: InvestigationLauncher | None = None,
    ) -> None:
        self.config = config
        self.investigation_launcher = investigation_launcher
        self.events: deque[DownloadEvent] = deque()
        self.total_events = 0
        self.total_file_successes = 0
        self.total_metadata_successes = 0
        self.total_bytes = 0
        self.last_trigger_time: float | None = None

    def record_event(self, event: DownloadEvent) -> dict[str, Any]:
        self.total_events += 1
        if event.ok:
            if event.kind == "file":
                self.total_file_successes += 1
                self.total_bytes += max(int(event.bytes_received), 0)
            elif event.kind == "metadata":
                self.total_metadata_successes += 1
        self.events.append(event)
        self._prune(event.timestamp)
        self._append_event_log(event)
        snapshot = self.snapshot(now=event.timestamp)
        self._write_snapshot(snapshot)
        launch_info = self.maybe_trigger_investigation(snapshot)
        if launch_info is not None:
            snapshot["investigation_launch"] = launch_info
            self._write_snapshot(snapshot)
        return snapshot

    def _prune(self, now: float) -> None:
        cutoff = now - self.config.rolling_window_seconds
        while self.events:
            earliest = self.events[0]
            earliest_start = earliest.timestamp - max(earliest.duration_seconds, 0.0)
            if earliest_start >= cutoff:
                break
            self.events.popleft()

    def _append_event_log(self, event: DownloadEvent) -> None:
        if self.config.event_log_path is None:
            return
        self.config.event_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.config.event_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.to_json(), ensure_ascii=False) + "\n")

    def _write_snapshot(self, snapshot: dict[str, Any]) -> None:
        if self.config.snapshot_path is None:
            return
        self.config.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        self.config.snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _recent_stats(self, kind: str, now: float) -> dict[str, Any]:
        relevant = [event for event in self.events if event.kind == kind]
        if not relevant:
            return {
                "event_count": 0,
                "ok_count": 0,
                "window_seconds": 0.0,
                "requests_per_second": None,
                "items_per_hour": None,
                "bytes_per_second": None,
                "status_counts": {},
            }
        earliest_start = min(event.timestamp - max(event.duration_seconds, 0.0) for event in relevant)
        window_seconds = max(now - earliest_start, 1e-9)
        ok_events = [event for event in relevant if event.ok]
        status_counts = Counter(str(event.status_code) if event.status_code is not None else "none" for event in relevant)
        bytes_per_second = None
        if kind == "file" and ok_events:
            bytes_per_second = sum(max(int(event.bytes_received), 0) for event in ok_events) / window_seconds
        requests_per_second = len(relevant) / window_seconds
        items_per_hour = len(ok_events) * SECONDS_PER_HOUR / window_seconds if ok_events else None
        return {
            "event_count": len(relevant),
            "ok_count": len(ok_events),
            "window_seconds": window_seconds,
            "requests_per_second": requests_per_second,
            "items_per_hour": items_per_hour,
            "bytes_per_second": bytes_per_second,
            "status_counts": dict(status_counts),
        }

    def snapshot(self, now: float | None = None) -> dict[str, Any]:
        current_time = now or time.time()
        metadata_stats = self._recent_stats("metadata", current_time)
        file_stats = self._recent_stats("file", current_time)
        completed_items = self.config.already_completed_items + self.total_file_successes
        remaining_items = None
        estimated_eta_hours = None
        threshold_breach = None
        if self.config.total_expected_items is not None:
            remaining_items = max(self.config.total_expected_items - completed_items, 0)
            if file_stats["items_per_hour"]:
                estimated_eta_hours = remaining_items / file_stats["items_per_hour"]
                threshold_breach = estimated_eta_hours > self.config.target_eta_hours
            elif remaining_items > 0:
                estimated_eta_hours = math.inf
                threshold_breach = True
            else:
                estimated_eta_hours = 0.0
                threshold_breach = False

        recent_errors = [
            {
                "timestamp": event.timestamp,
                "kind": event.kind,
                "url": event.url,
                "status_code": event.status_code,
                "error": event.error,
                "note": event.note,
            }
            for event in list(self.events)[-10:]
            if not event.ok or (event.status_code is not None and event.status_code >= 400)
        ]

        return {
            "collection_slug": self.config.collection_slug,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(current_time)),
            "total_expected_items": self.config.total_expected_items,
            "completed_items": completed_items,
            "remaining_items": remaining_items,
            "rolling_window_seconds": self.config.rolling_window_seconds,
            "target_eta_hours": self.config.target_eta_hours,
            "suggested_parallel_downloads": self.config.suggested_parallel_downloads,
            "recent_metadata": metadata_stats,
            "recent_files": file_stats,
            "estimated_eta_hours": estimated_eta_hours,
            "threshold_breach": threshold_breach,
            "recent_errors": recent_errors,
        }

    def maybe_trigger_investigation(self, snapshot: dict[str, Any]) -> dict[str, Any] | None:
        if self.investigation_launcher is None:
            return None
        if snapshot["threshold_breach"] is not True:
            return None
        recent_files = snapshot["recent_files"]
        recent_metadata = snapshot["recent_metadata"]
        if recent_files["ok_count"] < self.config.min_file_events_for_eta:
            return None
        if self.last_trigger_time is not None:
            elapsed = time.time() - self.last_trigger_time
            if elapsed < self.config.investigation_cooldown_seconds:
                return None
        payload = CodexInvestigationPayload(
            collection_slug=self.config.collection_slug,
            total_expected_items=self.config.total_expected_items,
            completed_items=snapshot["completed_items"],
            remaining_items=snapshot["remaining_items"],
            recent_window_seconds=snapshot["rolling_window_seconds"],
            recent_file_rate_per_hour=recent_files["items_per_hour"],
            recent_bytes_per_second=recent_files["bytes_per_second"],
            recent_metadata_rps=recent_metadata["requests_per_second"],
            estimated_eta_hours=snapshot["estimated_eta_hours"],
            target_eta_hours=self.config.target_eta_hours,
            suggested_parallel_downloads=self.config.suggested_parallel_downloads,
            status_counts_recent=recent_files["status_counts"] | recent_metadata["status_counts"],
            recent_errors=snapshot["recent_errors"],
            notes=[
                "Recent projected ETA exceeds the target threshold.",
                "Investigate whether the bottleneck is server-side throttling, client-side pacing, low parallelism, or a bad route choice.",
            ],
        )
        launch_info = self.investigation_launcher.launch(payload)
        self.last_trigger_time = time.time()
        self._append_investigation_log(payload, launch_info)
        return launch_info

    def _append_investigation_log(self, payload: CodexInvestigationPayload, launch_info: dict[str, Any]) -> None:
        if self.config.investigation_log_path is None:
            return
        self.config.investigation_log_path.parent.mkdir(parents=True, exist_ok=True)
        log_record = {
            "payload": payload.to_json(),
            "launch_info": launch_info,
            "logged_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        with self.config.investigation_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(log_record, ensure_ascii=False) + "\n")
