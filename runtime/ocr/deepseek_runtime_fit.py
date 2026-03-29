from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any


def _parse_major_minor(value: str | None) -> tuple[int, int] | None:
    if not value:
        return None
    match = re.search(r"(\d+)\.(\d+)", value)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _driver_major(value: str | None) -> int | None:
    if not value:
        return None
    match = re.match(r"(\d+)", value.strip())
    if not match:
        return None
    return int(match.group(1))


def _arch_from_capability(capability: str | None) -> str | None:
    parsed = _parse_major_minor(capability)
    if parsed is None:
        return None
    major, minor = parsed
    return f"sm_{major}{minor}"


def _gpu_generation(model: str | None, arch_tag: str | None) -> str | None:
    model_text = (model or "").lower()
    if "blackwell" in model_text or arch_tag == "sm_120":
        return "blackwell"
    if "hopper" in model_text or "h100" in model_text or "h200" in model_text:
        return "hopper"
    if "ampere" in model_text or "a100" in model_text or "a10" in model_text:
        return "ampere"
    return None


@dataclass
class RuntimeFitFinding:
    check_id: str
    status: str
    detail: str
    suggestion: str | None = None
    data: dict[str, Any] | None = None

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DeepSeekRuntimeFacts:
    gpu_model: str | None = None
    gpu_compute_capability: str | None = None
    driver_version: str | None = None
    torch_version: str | None = None
    torch_cuda_version: str | None = None
    torch_arch_list: list[str] = field(default_factory=list)
    torch_cuda_available: bool | None = None
    allocation_ok: bool | None = None
    allocation_error: str | None = None
    flash_attn_available: bool | None = None
    attention_fallback: str | None = None
    ocr_mode: str | None = None
    base_torch_reference: str | None = None


def assess_deepseek_runtime_fit(facts: DeepSeekRuntimeFacts) -> list[RuntimeFitFinding]:
    findings: list[RuntimeFitFinding] = []
    arch_tag = _arch_from_capability(facts.gpu_compute_capability)
    generation = _gpu_generation(facts.gpu_model, arch_tag)

    findings.append(
        RuntimeFitFinding(
            check_id="deepseek_fit:gpu_generation",
            status="pass" if generation else "warn",
            detail=f"detected GPU generation `{generation or 'unknown'}`",
            data={
                "gpu_model": facts.gpu_model,
                "gpu_compute_capability": facts.gpu_compute_capability,
                "arch_tag": arch_tag,
            },
        )
    )

    if facts.torch_cuda_available is False:
        findings.append(
            RuntimeFitFinding(
                check_id="deepseek_fit:cuda_available",
                status="fail",
                detail="selected runtime reports torch.cuda.is_available() = False",
                suggestion="repair the NVIDIA, CUDA, and PyTorch runtime stack before OCR benchmarking",
            )
        )

    if facts.allocation_ok is False:
        findings.append(
            RuntimeFitFinding(
                check_id="deepseek_fit:cuda_allocation",
                status="fail",
                detail=f"runtime could not allocate on CUDA: {facts.allocation_error or 'unknown CUDA allocation failure'}",
                suggestion="treat this as a runtime-stack mismatch first; do not benchmark workers_per_gpu until a basic CUDA allocation succeeds",
            )
        )

    runtime_cuda = _parse_major_minor(facts.torch_cuda_version)
    if generation == "blackwell":
        if runtime_cuda is None:
            findings.append(
                RuntimeFitFinding(
                    check_id="deepseek_fit:blackwell_cuda_runtime",
                    status="fail",
                    detail="Blackwell GPU detected but the selected runtime does not report a usable CUDA build",
                    suggestion="use a Blackwell-compatible Torch/CUDA stack, preferably CUDA 12.8+ or 13.0",
                )
            )
        elif runtime_cuda < (12, 8):
            findings.append(
                RuntimeFitFinding(
                    check_id="deepseek_fit:blackwell_cuda_runtime",
                    status="fail",
                    detail=(
                        f"Blackwell GPU detected but the selected runtime uses CUDA {facts.torch_cuda_version}; "
                        "that is too old for a safe DeepSeek OCR stack on this generation"
                    ),
                    suggestion="move the DeepSeek runtime to a newer Torch build on CUDA 12.8+ or 13.0 before benchmarking or tuning workers_per_gpu",
                )
            )
        driver_major = _driver_major(facts.driver_version)
        if driver_major is not None and driver_major < 570:
            findings.append(
                RuntimeFitFinding(
                    check_id="deepseek_fit:blackwell_driver",
                    status="warn",
                    detail=f"Blackwell GPU detected with driver {facts.driver_version}",
                    suggestion="validate that the host uses a recent Blackwell-capable NVIDIA driver before relying on OCR throughput results",
                )
            )

    if arch_tag and facts.torch_arch_list:
        if arch_tag not in facts.torch_arch_list:
            findings.append(
                RuntimeFitFinding(
                    check_id="deepseek_fit:torch_arch_list",
                    status="fail",
                    detail=f"selected Torch build does not include `{arch_tag}` in its compiled CUDA arch list",
                    suggestion="replace the runtime Torch build with one that targets the actual GPU architecture",
                    data={"torch_arch_list": facts.torch_arch_list},
                )
            )
        else:
            findings.append(
                RuntimeFitFinding(
                    check_id="deepseek_fit:torch_arch_list",
                    status="pass",
                    detail=f"selected Torch build includes `{arch_tag}`",
                    data={"torch_arch_list": facts.torch_arch_list},
                )
            )

    if facts.flash_attn_available is False and facts.attention_fallback == "eager":
        findings.append(
            RuntimeFitFinding(
                check_id="deepseek_fit:attention_backend",
                status="warn",
                detail="DeepSeek runtime falls back from flash_attention_2 to eager attention",
                suggestion="prefer `sdpa` as the no-flash fallback on modern PyTorch, or install and validate flash-attn on the chosen stack",
            )
        )
    elif facts.flash_attn_available is False and facts.attention_fallback == "sdpa":
        findings.append(
            RuntimeFitFinding(
                check_id="deepseek_fit:attention_backend",
                status="pass",
                detail="DeepSeek runtime falls back to sdpa when flash-attn is missing",
            )
        )
    elif facts.flash_attn_available:
        findings.append(
            RuntimeFitFinding(
                check_id="deepseek_fit:attention_backend",
                status="pass",
                detail="flash-attn is importable in the selected runtime",
            )
        )

    if facts.ocr_mode == "grounded_markdown_heavy":
        findings.append(
            RuntimeFitFinding(
                check_id="deepseek_fit:ocr_mode",
                status="warn",
                detail="current OCR path appears to use the heavier grounding markdown mode",
                suggestion="if layout-preserving markdown is not required, benchmark a lighter plain/free OCR mode before scaling the job estimate",
            )
        )

    if facts.base_torch_reference:
        findings.append(
            RuntimeFitFinding(
                check_id="deepseek_fit:base_torch_reference",
                status="pass",
                detail=f"host reference stack: {facts.base_torch_reference}",
            )
        )

    return findings
