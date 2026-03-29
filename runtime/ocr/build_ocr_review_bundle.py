#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd


REVIEW_PROMPT = """# OCR Review Prompt

Review these OCR cases manually or with Codex. Do not use code-level text-similarity scoring.

For each case:
1. Open the single-page PDF in `selected_pdf_path`.
2. Read `reference.txt` only as context from the original extraction.
3. Read `ocr.md` as the DeepSeek OCR output under review.
4. Judge the OCR qualitatively on:
   - Greek fidelity, especially polytonic Greek
   - math fidelity and symbol preservation
   - repeated output, looping, or obvious nonsense
   - truncation or token-limit failure
   - reading order and obvious structural breakage
   - wrong script or transliteration-like corruption

Suggested outcome labels:
- `pass`
- `soft_fail`
- `hard_fail`
- `needs_followup`

Record short notes in each case directory or in a separate review sheet.
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a manual/Codex OCR review bundle without code-level OCR/reference matching."
    )
    parser.add_argument("--selected-pages", type=Path, required=True)
    parser.add_argument("--ocr-output-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def _line_stats(text: str) -> dict[str, Any]:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    if not lines:
        return {"unique_line_ratio": 1.0, "repeated_line_max": 0}
    repeated_line_max = max((lines.count(line) for line in set(lines)), default=1)
    return {
        "unique_line_ratio": len(set(lines)) / max(1, len(lines)),
        "repeated_line_max": int(repeated_line_max),
    }


def _load_markdown(markdown_dir: Path, filename: str) -> str:
    markdown_path = markdown_dir / f"{Path(filename).stem}.md"
    if not markdown_path.exists():
        return ""
    return markdown_path.read_text(encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build_review_bundle(
    selected_pages: pd.DataFrame,
    *,
    markdown_dir: Path,
    output_dir: Path,
) -> pd.DataFrame:
    cases_dir = output_dir / "cases"
    records: list[dict[str, Any]] = []
    for row in selected_pages.to_dict(orient="records"):
        filename = str(row["filename"])
        case_id = Path(filename).stem
        case_dir = cases_dir / case_id
        case_dir.mkdir(parents=True, exist_ok=True)

        reference_text = str(row.get("page_text") or "")
        ocr_text = _load_markdown(markdown_dir, filename)
        ocr_line_stats = _line_stats(ocr_text)
        repeat_flag = bool(
            float(ocr_line_stats["unique_line_ratio"]) < 0.5 or int(ocr_line_stats["repeated_line_max"]) >= 3
        )
        empty_ocr_flag = bool(len(ocr_text.strip()) == 0)

        reference_path = case_dir / "reference.txt"
        ocr_path = case_dir / "ocr.md"
        metadata_path = case_dir / "metadata.json"
        notes_path = case_dir / "review_notes.md"

        _write_text(reference_path, reference_text)
        _write_text(ocr_path, ocr_text)
        _write_text(
            notes_path,
            (
                "# Review Notes\n\n"
                f"- case_id: `{case_id}`\n"
                f"- bucket: `{row.get('bucket', '')}`\n"
                f"- collection: `{row.get('collection_slug', '')}`\n"
                "- outcome: \n"
                "- notes: \n"
            ),
        )

        metadata_payload = {
            key: value
            for key, value in row.items()
            if key not in {"page_text"}
        }
        metadata_payload.update(
            {
                "case_id": case_id,
                "reference_path": str(reference_path),
                "ocr_markdown_path": str(ocr_path),
                "review_notes_path": str(notes_path),
                "repeat_flag": repeat_flag,
                "empty_ocr_flag": empty_ocr_flag,
                "ocr_unique_line_ratio": float(ocr_line_stats["unique_line_ratio"]),
                "ocr_repeated_line_max": int(ocr_line_stats["repeated_line_max"]),
            }
        )
        metadata_path.write_text(json.dumps(metadata_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        records.append(
            {
                **row,
                "case_id": case_id,
                "case_dir": str(case_dir),
                "reference_text_path": str(reference_path),
                "ocr_markdown_path": str(ocr_path),
                "review_notes_path": str(notes_path),
                "ocr_chars": int(len(ocr_text.strip())),
                "reference_chars": int(len(reference_text.strip())),
                "ocr_unique_line_ratio": float(ocr_line_stats["unique_line_ratio"]),
                "ocr_repeated_line_max": int(ocr_line_stats["repeated_line_max"]),
                "repeat_flag": repeat_flag,
                "empty_ocr_flag": empty_ocr_flag,
                "ocr_preview": ocr_text[:500],
                "reference_preview": reference_text[:500],
            }
        )
    return pd.DataFrame.from_records(records)


def write_outputs(output_dir: Path, report: pd.DataFrame) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    report.to_parquet(output_dir / "review_report.parquet", index=False)
    report.to_csv(output_dir / "review_report.csv", index=False)
    review_queue = report.sort_values(
        by=["empty_ocr_flag", "repeat_flag", "bucket", "collection_slug", "page_number"],
        ascending=[False, False, True, True, True],
        kind="stable",
    )
    review_queue.to_csv(output_dir / "review_queue.csv", index=False)
    prompt_path = output_dir / "review_prompt.md"
    prompt_path.write_text(REVIEW_PROMPT, encoding="utf-8")
    summary = {
        "docs": int(len(report)),
        "bucket_counts": report.get("bucket", pd.Series(dtype=str)).value_counts().to_dict(),
        "repeat_flags": int(report.get("repeat_flag", pd.Series(dtype=bool)).fillna(False).astype(bool).sum()),
        "empty_ocr_flags": int(report.get("empty_ocr_flag", pd.Series(dtype=bool)).fillna(False).astype(bool).sum()),
        "review_prompt_path": str(prompt_path),
        "review_queue_path": str(output_dir / "review_queue.csv"),
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    selected_pages = pd.read_parquet(args.selected_pages.resolve()).copy()
    markdown_dir = args.ocr_output_dir.resolve() / "markdown"
    report = build_review_bundle(
        selected_pages,
        markdown_dir=markdown_dir,
        output_dir=args.output_dir.resolve(),
    )
    write_outputs(args.output_dir.resolve(), report)
    print(json.dumps({"docs": int(len(report)), "output_dir": str(args.output_dir.resolve())}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
