#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import fitz
import pandas as pd


MATH_SYMBOL_RE = re.compile(r"[=+\-*/^_±×÷∑∫√∞≤≥≈∂∈∉∀∃→←↔∧∨∩∪⊂⊆⊕⊗]")
LATEX_RE = re.compile(r"(\\[A-Za-z]+|\$\$|\$|\\begin\{|\\end\{)")
PAGE_SCAN_KEEP_COLUMNS = [
    "source_doc_id",
    "filename",
    "title",
    "collection_slug",
    "bucket",
    "bucket_reason",
    "selection_rank",
    "greek_badness_score",
    "needs_ocr",
    "strict_needs_ocr",
    "polytonic_ratio",
    "contains_math",
    "contains_latex",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Select reference pages from benchmark PDFs and materialize single-page PDFs.")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--downloads-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--min-text-chars", type=int, default=250)
    parser.add_argument("--min-printable-ratio", type=float, default=0.95)
    parser.add_argument("--max-control-ratio", type=float, default=0.02)
    parser.add_argument("--max-pages-per-doc", type=int, default=None)
    return parser.parse_args()


def _is_printable_or_space(char: str) -> bool:
    return char.isprintable() or char in "\n\r\t"


def _is_polytonic_char(char: str) -> bool:
    codepoint = ord(char)
    return 0x1F00 <= codepoint <= 0x1FFF


def _is_greek_char(char: str) -> bool:
    codepoint = ord(char)
    return (0x0370 <= codepoint <= 0x03FF) or (0x1F00 <= codepoint <= 0x1FFF)


def analyze_page_text(text: str, *, min_text_chars: int, min_printable_ratio: float, max_control_ratio: float) -> dict[str, Any]:
    raw = text or ""
    text_chars = len(raw.strip())
    total_chars = len(raw)
    control_chars = sum(1 for char in raw if ord(char) < 32 and char not in "\n\r\t")
    printable_chars = sum(1 for char in raw if _is_printable_or_space(char))
    greek_chars = sum(1 for char in raw if _is_greek_char(char))
    polytonic_chars = sum(1 for char in raw if _is_polytonic_char(char))
    digits = sum(1 for char in raw if char.isdigit())
    math_symbol_hits = len(MATH_SYMBOL_RE.findall(raw))
    latex_hits = len(LATEX_RE.findall(raw))
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    unique_line_ratio = len(set(lines)) / max(1, len(lines))
    repeated_line_max = max((lines.count(line) for line in set(lines)), default=1)
    printable_ratio = printable_chars / max(1, total_chars)
    control_ratio = control_chars / max(1, total_chars)
    math_score = (math_symbol_hits * 2) + (latex_hits * 8) + min(digits, 50)
    good_reference = (
        text_chars >= int(min_text_chars)
        and printable_ratio >= float(min_printable_ratio)
        and control_ratio <= float(max_control_ratio)
    )
    return {
        "text_chars": int(text_chars),
        "total_chars": int(total_chars),
        "control_chars": int(control_chars),
        "control_ratio": float(control_ratio),
        "printable_ratio": float(printable_ratio),
        "greek_chars": int(greek_chars),
        "polytonic_chars": int(polytonic_chars),
        "polytonic_ratio_page": float(polytonic_chars / max(1, greek_chars)),
        "digits": int(digits),
        "math_symbol_hits": int(math_symbol_hits),
        "latex_hits": int(latex_hits),
        "math_score": int(math_score),
        "line_count": int(len(lines)),
        "unique_line_ratio": float(unique_line_ratio),
        "repeated_line_max": int(repeated_line_max),
        "good_reference": bool(good_reference),
    }


def _score_page(row: pd.Series) -> tuple[Any, ...]:
    bucket = str(row.get("bucket") or "")
    good = 1 if bool(row.get("good_reference")) else 0
    control_penalty = -float(row.get("control_ratio", 0.0))
    text_chars = int(row.get("text_chars", 0))
    polytonic_chars = int(row.get("polytonic_chars", 0))
    math_score = int(row.get("math_score", 0))
    unique_line_ratio = float(row.get("unique_line_ratio", 0.0))
    repeated_line_max = int(row.get("repeated_line_max", 0))
    page_number = int(row.get("page_number", 0))
    if bucket == "polytonic_greek":
        return (good, polytonic_chars, text_chars, unique_line_ratio, control_penalty, -repeated_line_max, -page_number)
    if bucket == "math_control":
        return (good, math_score, text_chars, unique_line_ratio, control_penalty, -repeated_line_max, -page_number)
    return (good, text_chars, unique_line_ratio, control_penalty, -repeated_line_max, -page_number)


def scan_manifest_pages(
    manifest: pd.DataFrame,
    *,
    downloads_dir: Path,
    min_text_chars: int,
    min_printable_ratio: float,
    max_control_ratio: float,
    max_pages_per_doc: int | None,
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    subset_cols = [column for column in PAGE_SCAN_KEEP_COLUMNS if column in manifest.columns]
    manifest_rows = manifest[subset_cols].to_dict(orient="records")
    for row in manifest_rows:
        filename = str(row["filename"])
        pdf_path = downloads_dir / filename
        if not pdf_path.exists():
            continue
        with fitz.open(pdf_path) as doc:
            page_limit = doc.page_count if max_pages_per_doc is None else min(doc.page_count, max_pages_per_doc)
            for page_index in range(page_limit):
                page = doc.load_page(page_index)
                metrics = analyze_page_text(
                    page.get_text("text"),
                    min_text_chars=min_text_chars,
                    min_printable_ratio=min_printable_ratio,
                    max_control_ratio=max_control_ratio,
                )
                records.append(
                    {
                        **row,
                        "pdf_path": str(pdf_path),
                        "page_index": int(page_index),
                        "page_number": int(page_index + 1),
                        **metrics,
                    }
                )
    return pd.DataFrame.from_records(records)


def select_reference_pages(page_frame: pd.DataFrame) -> pd.DataFrame:
    if page_frame.empty:
        return page_frame.copy()
    selected_rows: list[pd.Series] = []
    for _source_doc_id, group in page_frame.groupby("source_doc_id", sort=False):
        ranked = group.copy()
        ranked["_score"] = ranked.apply(_score_page, axis=1)
        ranked = ranked.sort_values("_score", ascending=False, kind="stable")
        selected_rows.append(ranked.iloc[0].drop(labels=["_score"]))
    selected = pd.DataFrame(selected_rows).reset_index(drop=True)
    return selected


def materialize_single_page_pdfs(selected: pd.DataFrame, *, output_dir: Path) -> pd.DataFrame:
    output_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    for row in selected.to_dict(orient="records"):
        source_doc_id = str(row["source_doc_id"])
        page_number = int(row["page_number"])
        source_pdf = Path(str(row["pdf_path"]))
        target_name = f"{source_doc_id}__p{page_number:04d}.pdf"
        target_path = output_dir / target_name
        with fitz.open(source_pdf) as src:
            page_text = src.load_page(page_number - 1).get_text("text")
            new_doc = fitz.open()
            new_doc.insert_pdf(src, from_page=page_number - 1, to_page=page_number - 1)
            new_doc.save(target_path)
            new_doc.close()
        out = dict(row)
        out["page_text"] = page_text
        out["source_filename"] = row["filename"]
        out["filename"] = target_name
        out["selected_pdf_path"] = str(target_path)
        out["selected_page_number"] = page_number
        records.append(out)
    return pd.DataFrame.from_records(records)


def build_single_page_metadata(selected: pd.DataFrame) -> pd.DataFrame:
    metadata = selected.copy()
    metadata["needs_ocr"] = True
    metadata["ocr_success"] = False
    metadata["page_count"] = 1
    return metadata


def write_outputs(output_dir: Path, *, page_stats: pd.DataFrame, selected_pages: pd.DataFrame, single_page_metadata: pd.DataFrame) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    page_stats.to_parquet(output_dir / "page_stats.parquet", index=False)
    selected_pages.to_parquet(output_dir / "selected_pages.parquet", index=False)
    selected_pages.to_csv(output_dir / "selected_pages.csv", index=False)
    single_page_metadata.to_parquet(output_dir / "selected_page_manifest.parquet", index=False)
    summary = {
        "docs": int(selected_pages["source_doc_id"].nunique()) if not selected_pages.empty else 0,
        "bucket_counts": selected_pages.get("bucket", pd.Series(dtype=str)).value_counts().to_dict(),
        "good_reference_docs": int(selected_pages.get("good_reference", pd.Series(dtype=bool)).fillna(False).astype(bool).sum()),
        "polytonic_docs": int((selected_pages.get("polytonic_chars", pd.Series(dtype=int)).fillna(0).astype(int) > 0).sum()),
        "math_docs": int((selected_pages.get("math_score", pd.Series(dtype=int)).fillna(0).astype(int) > 0).sum()),
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    manifest = pd.read_parquet(args.manifest.resolve()).copy()
    page_stats = scan_manifest_pages(
        manifest,
        downloads_dir=args.downloads_dir.resolve(),
        min_text_chars=args.min_text_chars,
        min_printable_ratio=args.min_printable_ratio,
        max_control_ratio=args.max_control_ratio,
        max_pages_per_doc=args.max_pages_per_doc,
    )
    selected = select_reference_pages(page_stats)
    single_page_dir = args.output_dir.resolve() / "single_page_pdfs"
    selected_pages = materialize_single_page_pdfs(selected, output_dir=single_page_dir)
    single_page_metadata = build_single_page_metadata(selected_pages)
    write_outputs(args.output_dir.resolve(), page_stats=page_stats, selected_pages=selected_pages, single_page_metadata=single_page_metadata)
    print(json.dumps({"docs": int(len(selected_pages)), "output_dir": str(args.output_dir.resolve())}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
