#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "runs" / "runtime_tasks"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare or execute a first-class runtime task run."
    )
    parser.add_argument("--task-file", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--workdir", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--ssh-key-path", type=Path, default=None)
    parser.add_argument("--ssh-user", default=None)
    parser.add_argument("--skip-smoke-test", action="store_true")
    parser.add_argument("--smoke-device", type=int, default=0)
    parser.add_argument("--strict-host-key-checking", action="store_true")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually execute the runtime task against the target host. Default is bundle preparation only.",
    )
    return parser.parse_args()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def make_run_dir(output_root: Path, task: dict[str, Any]) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    task_type = str(task.get("task_type") or "runtime_task")
    target_name = str(task.get("target_name") or "task").replace("/", "_")
    run_dir = output_root / f"{stamp}_{task_type}_{target_name}"
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "bundle").mkdir(parents=True, exist_ok=False)
    (run_dir / "execution").mkdir(parents=True, exist_ok=False)
    return run_dir


def render_runtime_bundle(task_file: Path, bundle_dir: Path) -> dict[str, Any]:
    command = [
        "python3",
        str(PROJECT_ROOT / "runtime" / "render_runtime_task.py"),
        "--task-file",
        str(task_file),
        "--output-dir",
        str(bundle_dir),
    ]
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )
    return json.loads(result.stdout)


def execute_runtime_bundle(
    *,
    resolved_task_path: Path,
    execution_dir: Path,
    ssh_key_path: Path | None,
    ssh_user: str | None,
    skip_smoke_test: bool,
    smoke_device: int,
    strict_host_key_checking: bool,
) -> subprocess.CompletedProcess[str]:
    command = [
        "python3",
        str(PROJECT_ROOT / "runtime" / "aws" / "execute_runtime_task.py"),
        "--resolved-task",
        str(resolved_task_path),
        "--artifacts-dir",
        str(execution_dir),
        "--smoke-device",
        str(smoke_device),
    ]
    if ssh_key_path is not None:
        command.extend(["--ssh-key-path", str(ssh_key_path)])
    if ssh_user is not None:
        command.extend(["--ssh-user", ssh_user])
    if skip_smoke_test:
        command.append("--skip-smoke-test")
    if strict_host_key_checking:
        command.append("--strict-host-key-checking")
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )


def validate_apply_inputs(task: dict[str, Any], ssh_key_path: Path | None) -> None:
    existing_host = task.get("existing_host") or {}
    public_ip = existing_host.get("public_ip")
    if not public_ip:
        raise ValueError(
            "runtime execution currently requires `existing_host.public_ip`; use dry-run for pure provision tasks"
        )
    if ssh_key_path is None:
        raise ValueError("`--apply` requires `--ssh-key-path`")


def main() -> None:
    args = parse_args()
    task_file = args.task_file.resolve()
    task = read_json(task_file)
    run_dir = make_run_dir(args.output_root.resolve(), task)
    copied_task_path = run_dir / "task_spec.json"
    copied_task_path.write_text(task_file.read_text(encoding="utf-8"), encoding="utf-8")

    bundle_dir = run_dir / "bundle"
    bundle_manifest = render_runtime_bundle(task_file, bundle_dir)
    resolved_task_path = Path(bundle_manifest["resolved_task_path"])
    resolved_task = read_json(resolved_task_path)

    manifest: dict[str, Any] = {
        "task_file": str(task_file),
        "task_type": resolved_task["task_type"],
        "target_name": resolved_task["target_name"],
        "run_dir": str(run_dir),
        "bundle_manifest_path": str(bundle_dir / "bundle_manifest.json"),
        "resolved_task_path": str(resolved_task_path),
        "prompt_path": str(bundle_manifest["prompt_path"]),
        "status": "prepared",
        "execution": None,
    }

    if args.apply:
        validate_apply_inputs(resolved_task, args.ssh_key_path.resolve() if args.ssh_key_path else None)
        result = execute_runtime_bundle(
            resolved_task_path=resolved_task_path,
            execution_dir=run_dir / "execution",
            ssh_key_path=args.ssh_key_path.resolve() if args.ssh_key_path else None,
            ssh_user=args.ssh_user,
            skip_smoke_test=args.skip_smoke_test,
            smoke_device=args.smoke_device,
            strict_host_key_checking=args.strict_host_key_checking,
        )
        stdout_path = run_dir / "execution_stdout.log"
        stderr_path = run_dir / "execution_stderr.log"
        stdout_path.write_text(result.stdout, encoding="utf-8")
        stderr_path.write_text(result.stderr, encoding="utf-8")
        manifest["status"] = "completed" if result.returncode == 0 else "failed"
        manifest["execution"] = {
            "returncode": result.returncode,
            "execution_summary_path": str(run_dir / "execution" / "execution_summary.json"),
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
        }
        if result.returncode != 0:
            write_json(run_dir / "run_manifest.json", manifest)
            print(str(run_dir))
            raise SystemExit(result.returncode)

    write_json(run_dir / "run_manifest.json", manifest)
    print(str(run_dir))


if __name__ == "__main__":
    main()
