from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import subprocess
import time
from typing import Any


@dataclass
class RuntimeIssue:
    issue_id: str
    severity: str
    component: str
    summary: str
    evidence: list[str] = field(default_factory=list)
    suggested_actions: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GlossAPIRuntimeInvestigationPayload:
    target_name: str
    runtime_kind: str
    objective: str
    issue_summary: str
    readiness_report_path: str | None = None
    benchmark_artifact_paths: list[str] = field(default_factory=list)
    issues: list[RuntimeIssue] = field(default_factory=list)
    known_facts: list[str] = field(default_factory=list)
    requested_outcomes: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["issues"] = [issue.to_json() for issue in self.issues]
        return payload


def build_runtime_investigation_prompt(
    payload: GlossAPIRuntimeInvestigationPayload,
    context_path: Path,
) -> str:
    issue_block = "\n".join(
        [
            f"- [{issue.severity}] `{issue.issue_id}` `{issue.component}`: {issue.summary}"
            for issue in payload.issues
        ]
    ) or "- none"
    facts_block = "\n".join(f"- {fact}" for fact in payload.known_facts) or "- none"
    outcomes_block = "\n".join(f"- {item}" for item in payload.requested_outcomes) or "- none"
    artifacts_block = "\n".join(f"- `{path}`" for path in payload.benchmark_artifact_paths) or "- none"

    return f"""You are investigating a GlossAPI runtime or performance failure for the automation harness.

Context JSON:
- `{context_path}`

Target:
- target_name: `{payload.target_name}`
- runtime_kind: `{payload.runtime_kind}`
- objective: `{payload.objective}`

Issue summary:
- {payload.issue_summary}

Readiness report:
- `{payload.readiness_report_path or 'none'}`

Benchmark artifacts:
{artifacts_block}

Known issues:
{issue_block}

Known facts:
{facts_block}

Requested outcomes:
{outcomes_block}

Task:
- classify the likely root causes
- identify missing dependencies, environment drift, performance bottlenecks, and probable GlossAPI library bugs
- propose the shortest safe repair plan
- propose one or more upstream harness or library improvements that would make the failure less likely next time
- recommend the next validation step after the repair
- keep the answer concise, operational, and evidence-driven
"""


@dataclass
class CodexExecRuntimeInvestigationLauncher:
    workdir: Path
    artifact_dir: Path
    codex_bin: str = "codex"
    model: str = "gpt-5.4"
    reasoning_effort: str = "xhigh"
    sandbox_mode: str = "danger-full-access"

    def launch(self, payload: GlossAPIRuntimeInvestigationPayload) -> dict[str, Any]:
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        base = f"runtime_investigation_{payload.target_name}_{stamp}"
        context_path = self.artifact_dir / f"{base}.json"
        prompt_path = self.artifact_dir / f"{base}.txt"
        output_path = self.artifact_dir / f"{base}.jsonl"

        context_path.write_text(
            json.dumps(payload.to_json(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        prompt = build_runtime_investigation_prompt(payload, context_path)
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
