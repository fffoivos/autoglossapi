#!/usr/bin/env python3

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from runtime.investigation import (  # noqa: E402
    CodexExecRuntimeInvestigationLauncher,
    GlossAPIRuntimeInvestigationPayload,
    RuntimeIssue,
)
from runtime.ocr.deepseek_runtime_fit import (  # noqa: E402
    DeepSeekRuntimeFacts,
    assess_deepseek_runtime_fit,
)


BASE_REQUIRED_COMMANDS = {
    "git": "required to clone and update GlossAPI",
    "gcc": "required for Python/Rust native builds",
}

OPTIONAL_COMMANDS = {
    "uv": "recommended because GlossAPI DeepSeek setup uses uv-managed environments",
    "nvidia-smi": "required on GPU hosts for OCR benchmarking and readiness checks",
}

REQUIRED_REPO_PATHS = (
    "dependency_setup/setup_deepseek_uv.sh",
    "rust/glossapi_rs_cleaner/Cargo.toml",
    "rust/glossapi_rs_noise/Cargo.toml",
    "src/glossapi",
)

DEEPSEEK_PYTHON_MODULES = (
    "fitz",
    "torch",
    "transformers",
)

OPTIONAL_PYTHON_MODULES = (
    "pandas",
    "pytest",
)

CLEANER_PYTHON_MODULES = (
    "glossapi_rs_cleaner",
    "glossapi_rs_noise",
)


@dataclass
class CheckResult:
    check_id: str
    status: str
    detail: str
    suggestion: str | None = None
    data: dict[str, Any] | None = None

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check whether a host is ready to run GlossAPI.")
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--python", dest="python_bin", type=Path, default=None)
    parser.add_argument("--expect-gpu", action="store_true")
    parser.add_argument("--needs-rust", action="store_true")
    parser.add_argument("--needs-cleaner", action="store_true")
    parser.add_argument("--needs-deepseek-ocr", action="store_true")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--launch-investigation", action="store_true")
    parser.add_argument("--artifact-dir", type=Path, default=None)
    parser.add_argument("--workdir", type=Path, default=Path.cwd())
    return parser.parse_args()


def _run_command(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout,
    )


def _check_commands(*, expect_gpu: bool, needs_rust: bool, needs_deepseek_ocr: bool) -> list[CheckResult]:
    results: list[CheckResult] = []
    required_commands = dict(BASE_REQUIRED_COMMANDS)
    if needs_rust:
        required_commands.update(
            {
                "rustc": "required because Corpus.clean()/OCR flows may build rust extensions",
                "cargo": "required to build glossapi_rs_cleaner and glossapi_rs_noise",
            }
        )
    for name, detail in required_commands.items():
        found = shutil.which(name)
        if found:
            results.append(CheckResult(check_id=f"command:{name}", status="pass", detail=f"{detail}: {found}"))
        else:
            results.append(
                CheckResult(
                    check_id=f"command:{name}",
                    status="fail",
                    detail=f"missing required command `{name}`",
                    suggestion=f"install `{name}` before running GlossAPI setup",
                )
            )
    for name, detail in OPTIONAL_COMMANDS.items():
        found = shutil.which(name)
        if found:
            results.append(CheckResult(check_id=f"command:{name}", status="pass", detail=f"{detail}: {found}"))
        else:
            status = "warn"
            if expect_gpu and name == "nvidia-smi":
                status = "fail"
            elif needs_deepseek_ocr and name == "uv":
                status = "fail"
            results.append(
                CheckResult(
                    check_id=f"command:{name}",
                    status=status,
                    detail=f"missing optional command `{name}`",
                    suggestion=f"install `{name}` if this host should run the related workflow",
                )
            )
    return results


def _check_repo(repo: Path) -> list[CheckResult]:
    results: list[CheckResult] = []
    if not repo.exists():
        return [
            CheckResult(
                check_id="repo:exists",
                status="fail",
                detail=f"repo path does not exist: {repo}",
                suggestion="clone the GlossAPI repo before running the readiness check",
            )
        ]

    results.append(CheckResult(check_id="repo:exists", status="pass", detail=f"repo path exists: {repo}"))

    for relative in REQUIRED_REPO_PATHS:
        candidate = repo / relative
        if candidate.exists():
            results.append(
                CheckResult(check_id=f"repo:{relative}", status="pass", detail=f"found `{relative}`")
            )
        else:
            results.append(
                CheckResult(
                    check_id=f"repo:{relative}",
                    status="fail",
                    detail=f"missing required repo path `{relative}`",
                    suggestion="ensure the GlossAPI checkout is complete and on the expected branch",
                )
            )

    git_dir = repo / ".git"
    if git_dir.exists():
        branch_proc = _run_command(["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD"])
        commit_proc = _run_command(["git", "-C", str(repo), "rev-parse", "HEAD"])
        if branch_proc.returncode == 0 and commit_proc.returncode == 0:
            results.append(
                CheckResult(
                    check_id="repo:git",
                    status="pass",
                    detail="git metadata available",
                    data={
                        "branch": branch_proc.stdout.strip(),
                        "commit": commit_proc.stdout.strip(),
                    },
                )
            )
        else:
            results.append(
                CheckResult(
                    check_id="repo:git",
                    status="warn",
                    detail="repo exists but git metadata could not be read",
                )
            )
    else:
        results.append(
            CheckResult(
                check_id="repo:git",
                status="warn",
                detail="repo path is not a git checkout",
                suggestion="prefer a real clone so agents can update the branch cleanly",
            )
        )
    return results


def _check_platform() -> list[CheckResult]:
    os_release = Path("/etc/os-release")
    if not os_release.exists():
        return [
            CheckResult(
                check_id="platform:os_release",
                status="warn",
                detail="`/etc/os-release` is missing",
            )
        ]
    data: dict[str, str] = {}
    for line in os_release.read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key] = value.strip().strip('"')
    pretty = data.get("PRETTY_NAME") or data.get("NAME") or "unknown"
    return [
        CheckResult(
            check_id="platform:os_release",
            status="pass",
            detail=f"os release: {pretty}",
            data={
                "pretty_name": pretty,
                "id": data.get("ID"),
                "version_id": data.get("VERSION_ID"),
            },
        )
    ]


def _check_cargo_repo_compatibility(repo: Path, *, needs_cleaner: bool) -> list[CheckResult]:
    if not needs_cleaner:
        return []
    cargo_bin = shutil.which("cargo")
    if cargo_bin is None:
        return []

    manifests = [
        repo / "rust" / "glossapi_rs_cleaner" / "Cargo.toml",
        repo / "rust" / "glossapi_rs_noise" / "Cargo.toml",
    ]
    results: list[CheckResult] = []
    for manifest in manifests:
        if not manifest.exists():
            continue
        proc = _run_command(
            [
                cargo_bin,
                "metadata",
                "--format-version",
                "1",
                "--manifest-path",
                str(manifest),
            ],
            timeout=60.0,
        )
        crate_name = manifest.parent.name
        if proc.returncode == 0:
            results.append(
                CheckResult(
                    check_id=f"cargo:{crate_name}",
                    status="pass",
                    detail=f"`cargo metadata` succeeded for `{crate_name}`",
                )
            )
        else:
            error_text = (proc.stderr.strip() or proc.stdout.strip() or "cargo metadata failed").replace("\n", " ")
            results.append(
                CheckResult(
                    check_id=f"cargo:{crate_name}",
                    status="fail",
                    detail=f"`cargo metadata` failed for `{crate_name}`: {error_text}",
                    suggestion="upgrade the Rust toolchain so the repo's Cargo manifests and lockfiles are supported",
                )
            )
    return results


def _check_python(
    python_bin: Path | None,
    repo: Path,
    *,
    needs_cleaner: bool = False,
    needs_deepseek_ocr: bool = False,
) -> list[CheckResult]:
    results: list[CheckResult] = []
    if python_bin is None:
        results.append(
            CheckResult(
                check_id="python:selected",
                status="warn",
                detail="no explicit Python interpreter provided",
                suggestion="pass the GlossAPI runtime interpreter with `--python`",
            )
        )
        return results

    if not python_bin.exists():
        return [
            CheckResult(
                check_id="python:selected",
                status="fail",
                detail=f"python interpreter does not exist: {python_bin}",
                suggestion="point `--python` at the real GlossAPI runtime interpreter",
            )
        ]

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{repo / 'src'}:{env.get('PYTHONPATH', '')}"
    required_modules: list[str] = []
    optional_modules = list(OPTIONAL_PYTHON_MODULES)
    if needs_deepseek_ocr:
        required_modules.extend(DEEPSEEK_PYTHON_MODULES)
    else:
        optional_modules.extend(DEEPSEEK_PYTHON_MODULES)
    if needs_cleaner:
        required_modules.extend(CLEANER_PYTHON_MODULES)
    else:
        optional_modules.extend(CLEANER_PYTHON_MODULES)
    module_script = """
import importlib.util, json, sys
modules = {}
for name in sys.argv[1:]:
    modules[name] = importlib.util.find_spec(name) is not None
print(json.dumps(modules))
"""
    proc = _run_command(
        [str(python_bin), "-c", module_script, *required_modules, *optional_modules],
        env=env,
    )
    version_proc = _run_command([str(python_bin), "--version"], env=env)

    if version_proc.returncode == 0:
        results.append(
            CheckResult(
                check_id="python:version",
                status="pass",
                detail=version_proc.stdout.strip() or version_proc.stderr.strip(),
                data={"python_bin": str(python_bin)},
            )
        )
    else:
        results.append(
            CheckResult(
                check_id="python:version",
                status="fail",
                detail=f"could not execute python: {python_bin}",
                suggestion="repair or recreate the GlossAPI runtime environment",
            )
        )
        return results

    if proc.returncode != 0:
        results.append(
            CheckResult(
                check_id="python:imports",
                status="fail",
                detail=f"module check failed: {proc.stderr.strip() or proc.stdout.strip()}",
                suggestion="repair the Python environment before running OCR or cleaning",
            )
        )
        return results

    found = json.loads(proc.stdout)
    for name in required_modules:
        if found.get(name):
            results.append(CheckResult(check_id=f"python:{name}", status="pass", detail=f"module `{name}` importable"))
        else:
            results.append(
                CheckResult(
                    check_id=f"python:{name}",
                    status="fail",
                    detail=f"required module `{name}` is missing",
                    suggestion=f"install `{name}` into the runtime interpreter",
                )
            )

    for name in optional_modules:
        if found.get(name):
            results.append(CheckResult(check_id=f"python:{name}", status="pass", detail=f"module `{name}` importable"))
        else:
            results.append(
                CheckResult(
                    check_id=f"python:{name}",
                    status="warn",
                    detail=f"optional module `{name}` is missing",
                    suggestion=f"install or build `{name}` if the related workflow depends on it",
                )
            )
    return results


def _check_gpu(expect_gpu: bool) -> list[CheckResult]:
    results: list[CheckResult] = []
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi is None:
        if expect_gpu:
            results.append(
                CheckResult(
                    check_id="gpu:nvidia-smi",
                    status="fail",
                    detail="GPU host expected but `nvidia-smi` is missing",
                    suggestion="install the NVIDIA driver stack and verify GPU access",
                )
            )
        return results

    proc = _run_command(
        [
            nvidia_smi,
            "--query-gpu=index,name,memory.total,driver_version",
            "--format=csv,noheader",
        ]
    )
    if proc.returncode != 0:
        results.append(
            CheckResult(
                check_id="gpu:query",
                status="fail" if expect_gpu else "warn",
                detail=proc.stderr.strip() or "GPU query failed",
                suggestion="repair the NVIDIA runtime before OCR benchmarks",
            )
        )
        return results

    gpus = []
    for line in proc.stdout.splitlines():
        parts = [piece.strip() for piece in line.split(",")]
        if len(parts) >= 4:
            gpus.append(
                {
                    "index": parts[0],
                    "name": parts[1],
                    "memory_total": parts[2],
                    "driver_version": parts[3],
                }
            )
    if not gpus and expect_gpu:
        results.append(
            CheckResult(
                check_id="gpu:count",
                status="fail",
                detail="GPU host expected but no GPUs were reported",
                suggestion="check the instance type, driver, and container/runtime permissions",
            )
        )
    elif gpus:
        results.append(
            CheckResult(
                check_id="gpu:count",
                status="pass",
                detail=f"detected {len(gpus)} GPU(s)",
                data={"gpus": gpus},
            )
        )
    return results


def _inspect_deepseek_source(repo: Path) -> dict[str, Any]:
    path = repo / "src" / "glossapi" / "ocr" / "deepseek" / "run_pdf_ocr_transformers.py"
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    data: dict[str, Any] = {"path": str(path)}
    if '"eager"' in text:
        data["attention_fallback"] = "eager"
    if '"sdpa"' in text and data.get("attention_fallback") is None:
        data["attention_fallback"] = "sdpa"
    heavy_markers = (
        "base_size=1024",
        "image_size=768",
        "crop_mode=True",
    )
    if all(marker in text for marker in heavy_markers):
        data["ocr_mode"] = "grounded_markdown_heavy"
    return data


def _check_deepseek_runtime_fit(
    python_bin: Path | None,
    repo: Path,
    *,
    needs_deepseek_ocr: bool,
) -> list[CheckResult]:
    if not needs_deepseek_ocr or python_bin is None or not python_bin.exists():
        return []

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{repo / 'src'}:{env.get('PYTHONPATH', '')}"
    script = """
import importlib.util, json, sys
payload = {
    "flash_attn_available": importlib.util.find_spec("flash_attn") is not None,
    "python_executable": sys.executable,
}
try:
    import torch
    payload["torch_version"] = getattr(torch, "__version__", None)
    payload["torch_cuda_version"] = getattr(getattr(torch, "version", None), "cuda", None)
    payload["torch_arch_list"] = list(getattr(torch.cuda, "get_arch_list", lambda: [])())
    payload["torch_cuda_available"] = bool(torch.cuda.is_available())
    if payload["torch_cuda_available"]:
        payload["device_count"] = torch.cuda.device_count()
        if payload["device_count"]:
            payload["gpu_model"] = torch.cuda.get_device_name(0)
            capability = torch.cuda.get_device_capability(0)
            payload["gpu_compute_capability"] = f"{capability[0]}.{capability[1]}"
            try:
                torch.zeros(1, device="cuda")
                payload["allocation_ok"] = True
            except Exception as exc:
                payload["allocation_ok"] = False
                payload["allocation_error"] = str(exc)
except Exception as exc:
    payload["torch_error"] = str(exc)
print(json.dumps(payload))
"""
    proc = _run_command([str(python_bin), "-c", script], env=env, timeout=60.0)
    if proc.returncode != 0:
        return [
            CheckResult(
                check_id="deepseek_fit:introspection",
                status="fail",
                detail=f"could not inspect DeepSeek runtime: {proc.stderr.strip() or proc.stdout.strip()}",
                suggestion="repair the runtime interpreter before benchmarking OCR",
            )
        ]
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return [
            CheckResult(
                check_id="deepseek_fit:introspection",
                status="fail",
                detail="could not parse DeepSeek runtime introspection output",
                suggestion="repair the runtime interpreter before benchmarking OCR",
            )
        ]

    if payload.get("torch_error"):
        return [
            CheckResult(
                check_id="deepseek_fit:introspection",
                status="fail",
                detail=f"runtime torch import failed: {payload['torch_error']}",
                suggestion="repair or replace the selected OCR runtime before benchmarking",
            )
        ]

    gpu_proc = _run_command(
        [
            "nvidia-smi",
            "--query-gpu=name,driver_version",
            "--format=csv,noheader",
        ]
    )
    gpu_model = payload.get("gpu_model")
    driver_version = None
    if gpu_proc.returncode == 0 and gpu_proc.stdout.strip():
        first = gpu_proc.stdout.splitlines()[0]
        parts = [piece.strip() for piece in first.split(",")]
        if len(parts) >= 2:
            gpu_model = gpu_model or parts[0]
            driver_version = parts[1]

    source_facts = _inspect_deepseek_source(repo)
    facts = DeepSeekRuntimeFacts(
        gpu_model=gpu_model,
        gpu_compute_capability=payload.get("gpu_compute_capability"),
        driver_version=driver_version,
        torch_version=payload.get("torch_version"),
        torch_cuda_version=payload.get("torch_cuda_version"),
        torch_arch_list=list(payload.get("torch_arch_list") or []),
        torch_cuda_available=payload.get("torch_cuda_available"),
        allocation_ok=payload.get("allocation_ok"),
        allocation_error=payload.get("allocation_error"),
        flash_attn_available=payload.get("flash_attn_available"),
        attention_fallback=source_facts.get("attention_fallback"),
        ocr_mode=source_facts.get("ocr_mode"),
    )
    return [
        CheckResult(
            check_id=finding.check_id,
            status=finding.status,
            detail=finding.detail,
            suggestion=finding.suggestion,
            data=finding.data,
        )
        for finding in assess_deepseek_runtime_fit(facts)
    ]


def summarize_results(results: list[CheckResult]) -> dict[str, Any]:
    fail_count = sum(1 for result in results if result.status == "fail")
    warn_count = sum(1 for result in results if result.status == "warn")
    status = "fail" if fail_count else "warn" if warn_count else "pass"
    return {
        "status": status,
        "fail_count": fail_count,
        "warn_count": warn_count,
        "brainstorm_recommended": status != "pass",
        "checks": [result.to_json() for result in results],
    }


def maybe_launch_investigation(
    summary: dict[str, Any],
    *,
    repo: Path,
    artifact_dir: Path,
    workdir: Path,
    output_path: Path | None,
) -> dict[str, Any] | None:
    if summary["status"] == "pass":
        return None

    issues: list[RuntimeIssue] = []
    for check in summary["checks"]:
        if check["status"] not in {"fail", "warn"}:
            continue
        issues.append(
            RuntimeIssue(
                issue_id=check["check_id"],
                severity=check["status"],
                component=check["check_id"].split(":", 1)[0],
                summary=check["detail"],
                evidence=[check["detail"]],
                suggested_actions=[check["suggestion"]] if check.get("suggestion") else [],
            )
        )

    payload = GlossAPIRuntimeInvestigationPayload(
        target_name=repo.name,
        runtime_kind="aws_or_remote_host",
        objective="prepare a host to run GlossAPI clean/extract/OCR flows reliably",
        issue_summary=f"runtime readiness returned `{summary['status']}`",
        readiness_report_path=str(output_path) if output_path else None,
        issues=issues,
        known_facts=[
            "Rust is required because GlossAPI cleaner/OCR flows may build rust extensions.",
            "DeepSeek multi-GPU workers should be isolated with CUDA_VISIBLE_DEVICES rather than explicit cuda:N.",
            "GPU runtime stack fit must be checked before worker-count tuning; presence checks alone are not enough.",
            "Blackwell GPUs need a newer Torch/CUDA stack than older cu118 DeepSeek environments.",
            "When flash-attn is missing on modern PyTorch, sdpa is a better fallback target than eager attention.",
            "Workers-per-GPU should be measured empirically after a small sweep around the calculated guess.",
        ],
        requested_outcomes=[
            "repair the runtime setup",
            "identify missing dependencies or environment drift",
            "identify candidate GlossAPI library or harness improvements",
            "recommend the next verification step",
        ],
    )
    launcher = CodexExecRuntimeInvestigationLauncher(
        workdir=workdir,
        artifact_dir=artifact_dir,
    )
    return launcher.launch(payload)


def main() -> int:
    args = parse_args()
    repo = args.repo.resolve()
    python_bin = args.python_bin.expanduser() if args.python_bin else None
    expect_gpu = bool(getattr(args, "expect_gpu", False))
    needs_cleaner = bool(getattr(args, "needs_cleaner", False))
    needs_deepseek_ocr = bool(getattr(args, "needs_deepseek_ocr", False))
    needs_rust = bool(getattr(args, "needs_rust", False) or needs_cleaner)
    results = []
    results.extend(_check_platform())
    results.extend(
        _check_commands(
            expect_gpu=expect_gpu,
            needs_rust=needs_rust,
            needs_deepseek_ocr=needs_deepseek_ocr,
        )
    )
    results.extend(_check_repo(repo))
    results.extend(_check_cargo_repo_compatibility(repo, needs_cleaner=needs_cleaner))
    if needs_cleaner or needs_deepseek_ocr:
        results.extend(
            _check_python(
                python_bin,
                repo,
                needs_cleaner=needs_cleaner,
                needs_deepseek_ocr=needs_deepseek_ocr,
            )
        )
    else:
        results.extend(_check_python(python_bin, repo))
    results.extend(_check_gpu(expect_gpu=expect_gpu))
    results.extend(
        _check_deepseek_runtime_fit(
            python_bin,
            repo,
            needs_deepseek_ocr=needs_deepseek_ocr,
        )
    )

    summary = summarize_results(results)
    summary["repo"] = str(repo)
    if python_bin is not None:
        summary["python_bin"] = str(python_bin)
    summary["requirements"] = {
        "expect_gpu": expect_gpu,
        "needs_rust": needs_rust,
        "needs_cleaner": needs_cleaner,
        "needs_deepseek_ocr": needs_deepseek_ocr,
    }

    if args.launch_investigation:
        artifact_dir = args.artifact_dir or (repo / "runtime" / "investigations")
        launch_info = maybe_launch_investigation(
            summary,
            repo=repo,
            artifact_dir=artifact_dir.resolve(),
            workdir=args.workdir.resolve(),
            output_path=args.output.resolve() if args.output else None,
        )
        if launch_info is not None:
            summary["investigation_launch"] = launch_info

    payload = json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")

    if args.strict and summary["status"] != "pass":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
