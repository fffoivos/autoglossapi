#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile
import tempfile
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from runtime.aws.task_execution import (  # noqa: E402
    default_ssh_user,
    derive_execution_plan,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ROOT = PROJECT_ROOT / "runtime"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Execute a resolved runtime task against a remote host.")
    parser.add_argument("--resolved-task", type=Path, required=True)
    parser.add_argument("--ssh-key-path", type=Path, default=None)
    parser.add_argument("--ssh-user", default=None)
    parser.add_argument("--remote-root", default="/tmp/automated-glossapi-runtime")
    parser.add_argument("--artifacts-dir", type=Path, required=True)
    parser.add_argument("--skip-smoke-test", action="store_true")
    parser.add_argument("--smoke-device", type=int, default=0)
    parser.add_argument("--strict-host-key-checking", action="store_true")
    return parser.parse_args()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _ssh_base_args(*, target: str, key_path: Path | None, strict_host_key_checking: bool) -> list[str]:
    args = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        f"StrictHostKeyChecking={'yes' if strict_host_key_checking else 'no'}",
    ]
    if key_path is not None:
        args.extend(["-i", str(key_path)])
    args.append(target)
    return args


def _run_command(cmd: list[str], *, input_bytes: bytes | None = None, log_path: Path | None = None) -> subprocess.CompletedProcess[bytes]:
    proc = subprocess.run(cmd, input=input_bytes, capture_output=True, check=False)
    if log_path is not None:
        payload = proc.stdout + (b"\n--- STDERR ---\n" if proc.stderr else b"") + proc.stderr
        log_path.write_bytes(payload)
    return proc


def _run_remote_bash(
    ssh_args: list[str],
    script: str,
    *,
    log_path: Path,
    input_bytes: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    remote_command = f"bash -lc {shlex.quote(script)}"
    return _run_command(ssh_args + [remote_command], input_bytes=input_bytes, log_path=log_path)


def _copy_runtime_to_remote(ssh_args: list[str], remote_root: str, *, log_path: Path) -> subprocess.CompletedProcess[bytes]:
    with tempfile.TemporaryDirectory() as tmpdir:
        tar_path = Path(tmpdir) / "runtime.tgz"
        with tarfile.open(tar_path, "w:gz") as tar:
            tar.add(RUNTIME_ROOT, arcname="runtime")
        payload = tar_path.read_bytes()
    script = f"rm -rf {shlex.quote(remote_root)} && mkdir -p {shlex.quote(remote_root)} && tar xzf - -C {shlex.quote(remote_root)}"
    return _run_remote_bash(ssh_args, script, log_path=log_path, input_bytes=payload)


def _fetch_remote_file(ssh_args: list[str], remote_path: str, *, local_path: Path) -> bool:
    proc = _run_command(ssh_args + [f"bash -lc {shlex.quote(f'cat {shlex.quote(remote_path)}')}"])
    if proc.returncode != 0:
        return False
    local_path.write_bytes(proc.stdout)
    return True


def _runtime_python_resolution_shell(candidates: list[str]) -> str:
    quoted_candidates = " ".join(shlex.quote(candidate) for candidate in candidates)
    return (
        "RUNTIME_PY=''; "
        f"for candidate in {quoted_candidates}; do "
        "if [ -x \"$candidate\" ]; then RUNTIME_PY=\"$candidate\"; break; fi; "
        "done; "
        "if [ -z \"$RUNTIME_PY\" ]; then echo 'runtime python not found' >&2; exit 1; fi"
    )


def _readiness_script(task: dict[str, Any], *, remote_root: str, output_path: str, strict: bool) -> str:
    plan = derive_execution_plan(task)
    target_dir = plan["target_dir"]
    if not target_dir:
        raise ValueError("resolved task is missing a target_dir")
    flags = " ".join(plan["readiness_flags"])
    strict_flag = "--strict" if strict else ""
    resolve_python = _runtime_python_resolution_shell(plan["runtime_python_candidates"])
    return " && ".join(
        [
            "set -euo pipefail",
            "export PATH=\"$HOME/.cargo/bin:/usr/local/bin:$PATH\"",
            f"mkdir -p {shlex.quote(str(Path(output_path).parent))}",
            resolve_python,
            (
                f"python3 {shlex.quote(str(Path(remote_root) / 'runtime' / 'aws' / 'check_glossapi_runtime.py'))} "
                f"--repo {shlex.quote(str(target_dir))} "
                f"--python \"$RUNTIME_PY\" {flags} {strict_flag} "
                f"--output {shlex.quote(output_path)}"
            ).strip(),
        ]
    )


def _bootstrap_script(task: dict[str, Any], *, remote_root: str) -> str:
    plan = derive_execution_plan(task)
    target_dir = plan["target_dir"]
    if not target_dir:
        raise ValueError("resolved task is missing a target_dir")
    env = {
        "TARGET_DIR": str(target_dir),
        "TARGET_BRANCH": str(task.get("glossapi_branch", "development")),
        "EXPECT_GPU": "1" if task.get("requirements", {}).get("expect_gpu") else "0",
        "NEEDS_RUST": "1" if task.get("requirements", {}).get("needs_rust") else "0",
        "NEEDS_CLEANER": "1" if task.get("requirements", {}).get("needs_cleaner") else "0",
        "NEEDS_DEEPSEEK_OCR": "1" if task.get("requirements", {}).get("needs_deepseek_ocr") else "0",
        "DOWNLOAD_DEEPSEEK_MODEL": "1" if task.get("requirements", {}).get("needs_deepseek_ocr") else "0",
        "BOOTSTRAP_MODE": str(plan["bootstrap_mode"]),
        "UPDATE_REPO": "1" if plan["update_repo"] else "0",
    }
    env_block = " ".join(f"{key}={shlex.quote(value)}" for key, value in env.items())
    return " && ".join(
        [
            "set -euo pipefail",
            "export PATH=\"$HOME/.cargo/bin:/usr/local/bin:$PATH\"",
            f"cd {shlex.quote(remote_root)}",
            f"{env_block} bash runtime/aws/bootstrap_glossapi_aws.sh",
        ]
    )


def _smoke_test_script(task: dict[str, Any], *, remote_root: str, smoke_device: int) -> str:
    plan = derive_execution_plan(task)
    target_dir = plan["target_dir"]
    if not target_dir:
        raise ValueError("resolved task is missing a target_dir")
    smoke_dir = str(Path(remote_root) / "artifacts" / "smoke_test")
    resolve_python = _runtime_python_resolution_shell(plan["runtime_python_candidates"])
    return " && ".join(
        [
            "set -euo pipefail",
            "export PATH=\"$HOME/.cargo/bin:/usr/local/bin:$PATH\"",
            resolve_python,
            f"mkdir -p {shlex.quote(smoke_dir)}",
            (
                f"\"$RUNTIME_PY\" {shlex.quote(str(Path(remote_root) / 'runtime' / 'aws' / 'smoke_test_glossapi_runtime.py'))} "
                f"--repo {shlex.quote(str(target_dir))} "
                f"--python \"$RUNTIME_PY\" "
                f"--output-dir {shlex.quote(smoke_dir)} "
                f"--device {smoke_device}"
            ),
        ]
    )


def main() -> int:
    args = parse_args()
    resolved_task = _read_json(args.resolved_task)
    artifacts_dir = args.artifacts_dir.resolve()
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    plan = derive_execution_plan(resolved_task)
    existing_host = resolved_task.get("existing_host", {}) or {}
    public_ip = existing_host.get("public_ip")
    if not public_ip:
        raise ValueError("resolved task is missing existing_host.public_ip")

    ssh_user = args.ssh_user or plan["default_ssh_user"] or default_ssh_user(resolved_task.get("provider"))
    if not ssh_user:
        raise ValueError("could not infer ssh user; pass --ssh-user explicitly")

    ssh_target = f"{ssh_user}@{public_ip}"
    ssh_args = _ssh_base_args(
        target=ssh_target,
        key_path=args.ssh_key_path.resolve() if args.ssh_key_path else None,
        strict_host_key_checking=args.strict_host_key_checking,
    )

    summary: dict[str, Any] = {
        "target": ssh_target,
        "remote_root": args.remote_root,
        "execution_plan": plan,
        "steps": [],
    }

    copy_log = artifacts_dir / "copy_runtime.log"
    copy_proc = _copy_runtime_to_remote(ssh_args, args.remote_root, log_path=copy_log)
    summary["steps"].append({"step": "copy_runtime", "returncode": copy_proc.returncode, "log": str(copy_log)})
    if copy_proc.returncode != 0:
        _write_json(artifacts_dir / "execution_summary.json", summary)
        return copy_proc.returncode

    if resolved_task["task_type"] == "repair_glossapi_host":
        before_remote = str(Path(args.remote_root) / "artifacts" / "readiness_before.json")
        before_log = artifacts_dir / "readiness_before.log"
        before_proc = _run_remote_bash(
            ssh_args,
            _readiness_script(resolved_task, remote_root=args.remote_root, output_path=before_remote, strict=False),
            log_path=before_log,
        )
        before_local = artifacts_dir / "readiness_before.json"
        _fetch_remote_file(ssh_args, before_remote, local_path=before_local)
        summary["steps"].append(
            {
                "step": "readiness_before",
                "returncode": before_proc.returncode,
                "log": str(before_log),
                "report": str(before_local),
            }
        )

    bootstrap_log = artifacts_dir / "bootstrap.log"
    bootstrap_proc = _run_remote_bash(
        ssh_args,
        _bootstrap_script(resolved_task, remote_root=args.remote_root),
        log_path=bootstrap_log,
    )
    summary["steps"].append({"step": "bootstrap", "returncode": bootstrap_proc.returncode, "log": str(bootstrap_log)})
    if bootstrap_proc.returncode != 0:
        _write_json(artifacts_dir / "execution_summary.json", summary)
        return bootstrap_proc.returncode

    after_remote = str(Path(args.remote_root) / "artifacts" / "readiness_after.json")
    after_log = artifacts_dir / "readiness_after.log"
    after_proc = _run_remote_bash(
        ssh_args,
        _readiness_script(resolved_task, remote_root=args.remote_root, output_path=after_remote, strict=True),
        log_path=after_log,
    )
    after_local = artifacts_dir / "readiness_after.json"
    _fetch_remote_file(ssh_args, after_remote, local_path=after_local)
    summary["steps"].append(
        {
            "step": "readiness_after",
            "returncode": after_proc.returncode,
            "log": str(after_log),
            "report": str(after_local),
        }
    )
    if after_proc.returncode != 0:
        _write_json(artifacts_dir / "execution_summary.json", summary)
        return after_proc.returncode

    if plan["run_ocr_smoke_test"] and not args.skip_smoke_test:
        smoke_log = artifacts_dir / "smoke_test.log"
        smoke_proc = _run_remote_bash(
            ssh_args,
            _smoke_test_script(resolved_task, remote_root=args.remote_root, smoke_device=args.smoke_device),
            log_path=smoke_log,
        )
        smoke_remote = str(Path(args.remote_root) / "artifacts" / "smoke_test" / "smoke_test_report.json")
        smoke_local = artifacts_dir / "smoke_test_report.json"
        _fetch_remote_file(ssh_args, smoke_remote, local_path=smoke_local)
        summary["steps"].append(
            {
                "step": "smoke_test",
                "returncode": smoke_proc.returncode,
                "log": str(smoke_log),
                "report": str(smoke_local),
            }
        )
        if smoke_proc.returncode != 0:
            _write_json(artifacts_dir / "execution_summary.json", summary)
            return smoke_proc.returncode

    _write_json(artifacts_dir / "execution_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
