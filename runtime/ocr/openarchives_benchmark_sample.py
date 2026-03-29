#!/usr/bin/env python3

from __future__ import annotations

import argparse
from collections import Counter
import html
import json
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds
import pyarrow.parquet as pq


SELECTION_COLUMNS = [
    "source_doc_id",
    "title",
    "author",
    "text",
    "source_metadata_json",
    "is_historical_or_polytonic",
    "contains_math",
    "contains_latex",
    "polytonic_ratio",
    "table_ratio",
    "greek_badness_score",
    "mojibake_badness_score",
    "needs_ocr",
    "filter",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the OpenArchives OCR benchmark sample manifest.")
    parser.add_argument("--release-parquet", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--polytonic-count", type=int, default=15)
    parser.add_argument("--math-count", type=int, default=15)
    parser.add_argument("--strict-count", type=int, default=15)
    parser.add_argument("--long-count", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=2048)
    parser.add_argument("--min-polytonic-text-chars", type=int, default=800)
    parser.add_argument("--min-math-text-chars", type=int, default=1000)
    return parser.parse_args()


def _metadata_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return {}
    text = str(value).strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _first_pdf_url(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, list):
        for item in value:
            resolved = _first_pdf_url(item)
            if resolved:
                return resolved
        return None
    if isinstance(value, dict):
        for key in ("url", "href", "download_url", "pdf_url", "link"):
            if key in value:
                resolved = _first_pdf_url(value[key])
                if resolved:
                    return resolved
        return None
    text = html.unescape(str(value).strip())
    if not text:
        return None
    if text.startswith("[") or text.startswith("{"):
        try:
            return _first_pdf_url(json.loads(text))
        except json.JSONDecodeError:
            return text
    return text


def _clean_bool(series: pd.Series) -> pd.Series:
    return series.fillna(False).astype(bool)


def _text_lengths(array: pa.Array) -> list[int]:
    values = pc.fill_null(array, "")
    try:
        lengths = pc.utf8_length(values)
    except (pa.ArrowInvalid, pa.ArrowNotImplementedError):
        lengths = pc.binary_length(values.cast(pa.binary()))
    return lengths.to_pylist()


def _normalize_batch(frame: pd.DataFrame, *, text_chars: list[int]) -> pd.DataFrame:
    meta = frame["source_metadata_json"].apply(_metadata_dict)
    out = frame.copy()
    out["collection_slug"] = meta.apply(lambda item: item.get("collection_slug"))
    out["language_code"] = meta.apply(lambda item: item.get("language_code"))
    out["doc_type"] = meta.apply(lambda item: item.get("type"))
    out["pdf_url"] = meta.apply(lambda item: _first_pdf_url(item.get("pdf_links_json")))
    out["text_chars"] = text_chars
    out["strict_needs_ocr"] = _clean_bool(out["needs_ocr"]) | (out["greek_badness_score"].fillna(0) > 10)
    out["polytonic_candidate"] = _clean_bool(out["is_historical_or_polytonic"]) | (out["polytonic_ratio"].fillna(0.0) > 0)
    out["filename"] = out["source_doc_id"].astype(str) + ".pdf"
    out["collection_for_sampling"] = out["collection_slug"].fillna("unknown")
    return out


def load_selection_frame(path: Path, *, batch_size: int) -> pd.DataFrame:
    parquet = pq.ParquetFile(path)
    batches: list[pd.DataFrame] = []
    for batch in parquet.iter_batches(batch_size=batch_size, columns=SELECTION_COLUMNS):
        text_chars = _text_lengths(batch.column("text"))
        batch = batch.drop_columns(["text"])
        frame = batch.to_pandas(types_mapper=None)
        normalized = _normalize_batch(frame, text_chars=text_chars)
        normalized = normalized[normalized["pdf_url"].notna()].copy()
        batches.append(normalized)
    if not batches:
        return pd.DataFrame()
    combined = pd.concat(batches, ignore_index=True)
    combined = combined.drop_duplicates(subset=["source_doc_id"], keep="first").reset_index(drop=True)
    return combined


def _take_round_robin(frame: pd.DataFrame, *, count: int, group_col: str, sort_cols: list[str], ascending: list[bool]) -> pd.DataFrame:
    if count <= 0 or frame.empty:
        return frame.iloc[0:0].copy()
    ordered = frame.sort_values(sort_cols, ascending=ascending, kind="stable").reset_index(drop=True)
    groups: dict[str, list[int]] = {}
    for idx, group_value in enumerate(ordered[group_col].fillna("unknown").astype(str)):
        groups.setdefault(group_value, []).append(idx)
    group_order = sorted(groups, key=lambda key: (-len(groups[key]), key))
    selected: list[int] = []
    while len(selected) < count and group_order:
        next_round: list[str] = []
        for key in group_order:
            indices = groups[key]
            if indices:
                selected.append(indices.pop(0))
                if len(selected) >= count:
                    break
            if indices:
                next_round.append(key)
        group_order = next_round
    return ordered.iloc[selected].copy()


def _tag_bucket(frame: pd.DataFrame, *, bucket: str, reason: str) -> pd.DataFrame:
    tagged = frame.copy()
    tagged["bucket"] = bucket
    tagged["bucket_reason"] = reason
    tagged["selection_rank"] = range(1, len(tagged) + 1)
    return tagged


def _select_polytonic(frame: pd.DataFrame, *, count: int, min_text_chars: int) -> pd.DataFrame:
    candidates = frame[
        frame["polytonic_candidate"]
        & (frame["text_chars"] >= min_text_chars)
    ].copy()
    readable = candidates[~candidates["strict_needs_ocr"]].copy()
    strict = candidates[candidates["strict_needs_ocr"]].copy()
    readable_take = min(len(readable), (count + 1) // 2)
    strict_take = min(len(strict), count - readable_take)
    selected = [
        _take_round_robin(
            readable,
            count=readable_take,
            group_col="collection_slug",
            sort_cols=["greek_badness_score", "text_chars"],
            ascending=[True, False],
        ),
        _take_round_robin(
            strict,
            count=strict_take,
            group_col="collection_slug",
            sort_cols=["greek_badness_score", "text_chars"],
            ascending=[False, False],
        ),
    ]
    combined = pd.concat(selected, ignore_index=True)
    if len(combined) < count:
        remaining = candidates[~candidates["source_doc_id"].isin(combined["source_doc_id"])].copy()
        fill = _take_round_robin(
            remaining,
            count=count - len(combined),
            group_col="collection_slug",
            sort_cols=["greek_badness_score", "text_chars"],
            ascending=[True, False],
        )
        combined = pd.concat([combined, fill], ignore_index=True)
    return _tag_bucket(combined.head(count), bucket="polytonic_greek", reason="polytonic reference and bug probe")


def _select_math(frame: pd.DataFrame, *, count: int, min_text_chars: int) -> pd.DataFrame:
    candidates = frame[
        _clean_bool(frame["contains_math"])
        & ~frame["strict_needs_ocr"]
        & (frame["text_chars"] >= min_text_chars)
    ].copy()
    selected = _take_round_robin(
        candidates,
        count=count,
        group_col="collection_slug",
        sort_cols=["greek_badness_score", "text_chars"],
        ascending=[True, False],
    )
    return _tag_bucket(selected, bucket="math_control", reason="low-badness math benchmark")


def _select_strict_bad(frame: pd.DataFrame, *, count: int) -> pd.DataFrame:
    candidates = frame[frame["strict_needs_ocr"]].copy()
    candidates["needs_ocr_rank"] = _clean_bool(candidates["needs_ocr"]).astype(int) * -1
    selected = _take_round_robin(
        candidates,
        count=count,
        group_col="collection_slug",
        sort_cols=["needs_ocr_rank", "greek_badness_score", "text_chars"],
        ascending=[True, False, False],
    )
    return _tag_bucket(selected, bucket="strict_bad_extraction", reason="needs OCR or greek badness over 10")


def _select_long_risk(frame: pd.DataFrame, *, count: int) -> pd.DataFrame:
    candidates = frame.copy()
    candidates["long_rank"] = candidates["text_chars"].fillna(0) + (candidates["table_ratio"].fillna(0) * 10000)
    selected = _take_round_robin(
        candidates,
        count=count,
        group_col="collection_slug",
        sort_cols=["long_rank", "text_chars", "greek_badness_score"],
        ascending=[False, False, False],
    )
    return _tag_bucket(selected, bucket="long_output_risk", reason="dense output and truncation risk")


def select_benchmark_sample(
    frame: pd.DataFrame,
    *,
    polytonic_count: int,
    math_count: int,
    strict_count: int,
    long_count: int,
    min_polytonic_text_chars: int,
    min_math_text_chars: int,
) -> pd.DataFrame:
    selected_parts: list[pd.DataFrame] = []

    poly = _select_polytonic(frame, count=polytonic_count, min_text_chars=min_polytonic_text_chars)
    selected_parts.append(poly)

    remaining = frame[~frame["source_doc_id"].isin(poly["source_doc_id"])].copy()
    math = _select_math(remaining, count=math_count, min_text_chars=min_math_text_chars)
    selected_parts.append(math)

    remaining = remaining[~remaining["source_doc_id"].isin(math["source_doc_id"])].copy()
    strict = _select_strict_bad(remaining, count=strict_count)
    selected_parts.append(strict)

    remaining = remaining[~remaining["source_doc_id"].isin(strict["source_doc_id"])].copy()
    long = _select_long_risk(remaining, count=long_count)
    selected_parts.append(long)

    combined = pd.concat(selected_parts, ignore_index=True)
    combined = combined.drop_duplicates(subset=["source_doc_id"], keep="first").reset_index(drop=True)
    return combined


def attach_reference_text(path: Path, selected: pd.DataFrame) -> pd.DataFrame:
    selected_ids = selected["source_doc_id"].astype(str).tolist()
    if not selected_ids:
        return selected
    dataset = ds.dataset(path, format="parquet")
    table = dataset.to_table(
        columns=["source_doc_id", "text"],
        filter=ds.field("source_doc_id").isin(selected_ids),
    )
    text_frame = table.to_pandas()
    text_frame["source_doc_id"] = text_frame["source_doc_id"].astype(str)
    text_frame = text_frame.rename(columns={"text": "reference_text"})
    merged = selected.copy()
    merged["source_doc_id"] = merged["source_doc_id"].astype(str)
    return merged.merge(text_frame, on="source_doc_id", how="left")


def write_outputs(output_dir: Path, sample: pd.DataFrame) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    sample.to_parquet(output_dir / "benchmark_sample.parquet", index=False)
    sample.to_csv(output_dir / "benchmark_sample.csv", index=False)
    summary = {
        "rows": int(len(sample)),
        "bucket_counts": Counter(sample["bucket"]).most_common(),
        "collection_counts": Counter(sample["collection_slug"].fillna("unknown")).most_common(),
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    release_path = args.release_parquet.resolve()
    frame = load_selection_frame(release_path, batch_size=args.batch_size)
    sample = select_benchmark_sample(
        frame,
        polytonic_count=args.polytonic_count,
        math_count=args.math_count,
        strict_count=args.strict_count,
        long_count=args.long_count,
        min_polytonic_text_chars=args.min_polytonic_text_chars,
        min_math_text_chars=args.min_math_text_chars,
    )
    sample = attach_reference_text(release_path, sample)
    write_outputs(args.output_dir.resolve(), sample)
    print(json.dumps({"rows": int(len(sample)), "output_dir": str(args.output_dir.resolve())}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
