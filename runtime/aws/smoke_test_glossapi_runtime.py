#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys
from typing import Any

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a minimal GlossAPI OCR smoke test.")
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--python", dest="python_bin", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--device", type=int, default=0)
    return parser.parse_args()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    repo = args.repo.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(repo / "src"))

    import fitz  # type: ignore
    from glossapi import Corpus  # type: ignore

    downloads_dir = output_dir / "downloads"
    results_dir = output_dir / "download_results"
    downloads_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)

    pdf_path = downloads_dir / "runtime_smoke.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (72, 72),
        "GlossAPI runtime OCR smoke test.\nThis file validates OCR plus the Rust cleaner refresh path.",
        fontsize=12,
    )
    doc.save(pdf_path)
    doc.close()

    parquet_path = results_dir / "download_results.parquet"
    pd.DataFrame(
        [
            {
                "filename": pdf_path.name,
                "url": "",
                "needs_ocr": True,
                "ocr_success": False,
            }
        ]
    ).to_parquet(parquet_path, index=False)

    corpus = Corpus(
        input_dir=downloads_dir,
        output_dir=output_dir,
        log_level=logging.INFO,
    )
    corpus.ocr(
        mode="ocr_bad",
        backend="deepseek",
        use_gpus="single",
        devices=[args.device],
        workers_per_gpu=1,
        max_pages=1,
        math_enhance=False,
    )

    markdown_path = output_dir / "markdown" / "runtime_smoke.md"
    clean_markdown_path = output_dir / "clean_markdown" / "runtime_smoke.md"
    df = pd.read_parquet(parquet_path)
    row = df.iloc[0].to_dict()
    report = {
        "status": "pass",
        "pdf_path": str(pdf_path),
        "markdown_path": str(markdown_path),
        "clean_markdown_path": str(clean_markdown_path),
        "metadata_row": row,
    }

    if not markdown_path.exists() or not markdown_path.read_text(encoding="utf-8").strip():
        report["status"] = "fail"
        report["failure"] = "missing or empty markdown output"
    elif not clean_markdown_path.exists() or not clean_markdown_path.read_text(encoding="utf-8").strip():
        report["status"] = "fail"
        report["failure"] = "missing or empty clean_markdown output"
    elif not bool(row.get("ocr_success")):
        report["status"] = "fail"
        report["failure"] = "ocr_success was not set to true"
    elif row.get("mojibake_badness_score") is None:
        report["status"] = "fail"
        report["failure"] = "cleaner metrics were not written back to the parquet"

    report_path = output_dir / "smoke_test_report.json"
    _write_json(report_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
