#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd


MONITOR_INTERVAL_SEC = 2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a tracked GlossAPI DeepSeek OCR benchmark.")
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--python", dest="python_bin", type=Path, required=True)
    parser.add_argument("--input-dir", type=Path, required=True, help="Directory containing downloaded PDFs.")
    parser.add_argument("--metadata-parquet", type=Path, required=True, help="download_results parquet for Corpus.")
    parser.add_argument("--manifest", type=Path, required=True, help="Rich manifest with page counts and sample buckets.")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--devices", default="0")
    parser.add_argument("--use-gpus", default="single", choices=["single", "multi"])
    parser.add_argument("--workers-per-gpu", type=int, default=1)
    parser.add_argument("--ocr-profile", default="markdown_grounded", choices=["markdown_grounded", "plain_ocr"])
    parser.add_argument("--attn-backend", default="auto", choices=["auto", "flash_attention_2", "sdpa", "eager"])
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--base-size", type=int, default=None)
    parser.add_argument("--image-size", type=int, default=None)
    parser.add_argument("--render-dpi", type=int, default=144)
    parser.add_argument("--max-new-tokens", type=int, default=None)
    parser.add_argument("--repetition-penalty", type=float, default=None)
    parser.add_argument("--no-repeat-ngram-size", type=int, default=None)
    parser.add_argument("--crop-mode", dest="crop_mode", action="store_true")
    parser.add_argument("--no-crop-mode", dest="crop_mode", action="store_false")
    parser.set_defaults(crop_mode=None)
    parser.add_argument("--content-debug", action="store_true")
    parser.add_argument("--label", default="benchmark")
    return parser.parse_args()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _parse_devices(raw: str) -> list[int]:
    devices = [int(piece.strip()) for piece in str(raw).split(",") if piece.strip()]
    if not devices:
        raise ValueError("No GPU devices supplied")
    return devices


def _prepare_output_dir(output_dir: Path, metadata_parquet: Path) -> Path:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    (output_dir / "download_results").mkdir(parents=True, exist_ok=True)
    target_parquet = output_dir / "download_results" / "download_results.parquet"
    shutil.copy2(metadata_parquet, target_parquet)
    return target_parquet


def _start_monitors(log_dir: Path) -> list[subprocess.Popen]:
    log_dir.mkdir(parents=True, exist_ok=True)
    monitors: list[subprocess.Popen] = []
    util_log = log_dir / "gpu_util.csv"
    pmon_log = log_dir / "gpu_pmon.txt"
    util_cmd = [
        "nvidia-smi",
        "--query-gpu=timestamp,index,utilization.gpu,utilization.memory,memory.used,memory.total,power.draw",
        "--format=csv",
        "-l",
        str(MONITOR_INTERVAL_SEC),
    ]
    pmon_cmd = ["nvidia-smi", "pmon", "-s", "um", "-d", str(MONITOR_INTERVAL_SEC)]
    with util_log.open("w", encoding="utf-8") as fh:
        monitors.append(subprocess.Popen(util_cmd, stdout=fh, stderr=subprocess.STDOUT))  # noqa: S603
    with pmon_log.open("w", encoding="utf-8") as fh:
        monitors.append(subprocess.Popen(pmon_cmd, stdout=fh, stderr=subprocess.STDOUT))  # noqa: S603
    return monitors


def _stop_monitors(monitors: list[subprocess.Popen]) -> None:
    for proc in monitors:
        if proc.poll() is None:
            proc.send_signal(signal.SIGTERM)
    deadline = time.time() + 10
    for proc in monitors:
        if proc.poll() is not None:
            continue
        try:
            proc.wait(timeout=max(0.1, deadline - time.time()))
        except subprocess.TimeoutExpired:
            proc.kill()


def _parse_gpu_util(log_path: Path) -> dict[str, dict[str, float]]:
    if not log_path.exists():
        return {}
    rows: dict[str, dict[str, list[float]]] = {}
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("timestamp"):
            continue
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 7:
            continue
        gpu_id = parts[1]
        util_gpu = float(parts[2].rstrip(" %"))
        util_mem = float(parts[3].rstrip(" %"))
        mem_used = float(parts[4].rstrip(" MiB"))
        power_draw = parts[6].replace(" W", "").strip()
        try:
            power_val = float(power_draw)
        except ValueError:
            power_val = 0.0
        bucket = rows.setdefault(gpu_id, {"gpu": [], "mem": [], "mem_used": [], "power": []})
        bucket["gpu"].append(util_gpu)
        bucket["mem"].append(util_mem)
        bucket["mem_used"].append(mem_used)
        bucket["power"].append(power_val)
    summary: dict[str, dict[str, float]] = {}
    for gpu_id, bucket in rows.items():
        summary[gpu_id] = {
            "samples": float(len(bucket["gpu"])),
            "avg_gpu_util": sum(bucket["gpu"]) / max(1, len(bucket["gpu"])),
            "max_gpu_util": max(bucket["gpu"], default=0.0),
            "avg_mem_util": sum(bucket["mem"]) / max(1, len(bucket["mem"])),
            "avg_mem_used_mib": sum(bucket["mem_used"]) / max(1, len(bucket["mem_used"])),
            "max_mem_used_mib": max(bucket["mem_used"], default=0.0),
            "avg_power_w": sum(bucket["power"]) / max(1, len(bucket["power"])),
        }
    return summary


def _load_manifest_stats(manifest_path: Path, metadata_path: Path, max_pages: int | None) -> dict[str, Any]:
    manifest = pd.read_parquet(manifest_path).copy()
    metadata = pd.read_parquet(metadata_path).copy()
    filenames = set(metadata["filename"].astype(str))
    manifest["filename"] = manifest["filename"].astype(str)
    selected = manifest.loc[manifest["filename"].isin(filenames)].copy()
    if "page_count" in selected.columns:
        page_counts = selected["page_count"].fillna(0).astype(int)
    elif "page_count_source" in selected.columns:
        page_counts = selected["page_count_source"].fillna(0).astype(int)
    else:
        fallback_pages = int(max_pages) if max_pages is not None else 0
        page_counts = pd.Series([fallback_pages] * len(selected), index=selected.index)
    if max_pages is not None:
        page_counts = page_counts.clip(upper=max_pages)
    selected["effective_pages"] = page_counts
    return {
        "docs": int(selected.shape[0]),
        "pages": int(selected["effective_pages"].sum()),
        "bucket_counts": selected.get("bucket", pd.Series(dtype=str)).value_counts().to_dict(),
        "collection_counts": selected.get("collection_slug", pd.Series(dtype=str)).fillna("unknown").value_counts().to_dict(),
    }


def main() -> int:
    args = parse_args()
    repo = args.repo.resolve()
    output_dir = args.output_dir.resolve()
    input_dir = args.input_dir.resolve()
    metadata_parquet = args.metadata_parquet.resolve()
    manifest_path = args.manifest.resolve()
    python_bin = args.python_bin.resolve()
    devices = _parse_devices(args.devices)
    metadata_copy = _prepare_output_dir(output_dir, metadata_parquet)
    log_dir = output_dir / "logs"

    sys.path.insert(0, str(repo / "src"))
    import torch  # type: ignore
    from glossapi import Corpus  # type: ignore

    stats_before = _load_manifest_stats(manifest_path, metadata_copy, args.max_pages)
    config = {
        "label": args.label,
        "devices": devices,
        "use_gpus": args.use_gpus,
        "workers_per_gpu": int(args.workers_per_gpu),
        "ocr_profile": args.ocr_profile,
        "attn_backend": args.attn_backend,
        "max_pages": args.max_pages,
        "base_size": args.base_size,
        "image_size": args.image_size,
        "render_dpi": args.render_dpi,
        "max_new_tokens": args.max_new_tokens,
        "repetition_penalty": args.repetition_penalty,
        "no_repeat_ngram_size": args.no_repeat_ngram_size,
        "crop_mode": args.crop_mode,
        "content_debug": bool(args.content_debug),
        "input_dir": str(input_dir),
        "metadata_parquet": str(metadata_copy),
        "repo": str(repo),
        "python": str(python_bin),
    }
    _write_json(output_dir / "benchmark_config.json", config)

    monitors = _start_monitors(log_dir)
    start = time.time()
    failure: str | None = None
    try:
        corpus = Corpus(
            input_dir=input_dir,
            output_dir=output_dir,
        )
        corpus.ocr(
            mode="ocr_bad",
            backend="deepseek",
            use_gpus=args.use_gpus,
            devices=devices,
            workers_per_gpu=int(args.workers_per_gpu),
            max_pages=args.max_pages,
            ocr_profile=args.ocr_profile,
            attn_backend=args.attn_backend,
            base_size=args.base_size,
            image_size=args.image_size,
            crop_mode=args.crop_mode,
            render_dpi=args.render_dpi,
            max_new_tokens=args.max_new_tokens,
            repetition_penalty=args.repetition_penalty,
            no_repeat_ngram_size=args.no_repeat_ngram_size,
            content_debug=bool(args.content_debug),
            math_enhance=False,
        )
    except Exception as exc:
        failure = repr(exc)
    finally:
        _stop_monitors(monitors)
    wall_time = time.time() - start

    metadata_after = pd.read_parquet(metadata_copy)
    success_count = int(metadata_after.get("ocr_success", pd.Series(dtype=bool)).fillna(False).astype(bool).sum())
    needs_remaining = int(metadata_after.get("needs_ocr", pd.Series(dtype=bool)).fillna(False).astype(bool).sum())
    markdown_dir = output_dir / "markdown"
    markdown_docs = len(list(markdown_dir.glob("*.md"))) if markdown_dir.exists() else 0
    gpu_util_summary = _parse_gpu_util(log_dir / "gpu_util.csv")
    torch_info = {
        "torch": torch.__version__,
        "cuda": torch.version.cuda,
        "cuda_available": bool(torch.cuda.is_available()),
        "device_count": int(torch.cuda.device_count()),
        "arch_list": list(torch.cuda.get_arch_list()) if torch.cuda.is_available() else [],
    }

    summary = {
        "status": "fail" if failure else "pass",
        "failure": failure,
        "config": config,
        "wall_time_sec": wall_time,
        "docs": stats_before["docs"],
        "pages": stats_before["pages"],
        "seconds_per_page": wall_time / max(1, stats_before["pages"]),
        "pages_per_sec": stats_before["pages"] / max(1e-9, wall_time),
        "pages_per_min": stats_before["pages"] * 60.0 / max(1e-9, wall_time),
        "bucket_counts": stats_before["bucket_counts"],
        "collection_counts": stats_before["collection_counts"],
        "ocr_success_docs": success_count,
        "needs_ocr_remaining_docs": needs_remaining,
        "markdown_docs": markdown_docs,
        "gpu_util_summary": gpu_util_summary,
        "torch_info": torch_info,
    }
    _write_json(output_dir / "benchmark_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if failure else 0


if __name__ == "__main__":
    raise SystemExit(main())
