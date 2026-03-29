#!/usr/bin/env python3

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

import aiohttp
import fitz
import pandas as pd


USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) GlossAPI-Benchmark/1.0"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download benchmark PDFs and prepare a GlossAPI-ready corpus root.")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--concurrency", type=int, default=24)
    parser.add_argument("--conn-limit", type=int, default=48)
    parser.add_argument("--conn-limit-per-host", type=int, default=12)
    parser.add_argument("--timeout-total", type=int, default=180)
    parser.add_argument("--timeout-connect", type=int, default=20)
    parser.add_argument("--timeout-sock-read", type=int, default=180)
    return parser.parse_args()


def _safe_page_count(path: Path) -> int | None:
    try:
        doc = fitz.open(path)
        try:
            return int(doc.page_count)
        finally:
            doc.close()
    except Exception:
        return None


async def _download_one(
    session: aiohttp.ClientSession,
    sem: asyncio.Semaphore,
    rec: dict[str, Any],
    downloads_dir: Path,
) -> dict[str, Any]:
    filename = str(rec["filename"])
    pdf_url = str(rec["pdf_url"])
    output_path = downloads_dir / filename
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.exists() and output_path.stat().st_size > 0:
        result = dict(rec)
        result.update(
            {
                "download_ok": True,
                "status": 200,
                "bytes": int(output_path.stat().st_size),
                "path": str(output_path),
                "ssl_verify": True,
                "existing": True,
                "page_count": _safe_page_count(output_path),
            }
        )
        return result

    async with sem:
        last_error = None
        for verify_ssl in (True, False):
            try:
                ssl_arg = None if verify_ssl else False
                async with session.get(
                    pdf_url,
                    headers={"User-Agent": USER_AGENT},
                    allow_redirects=True,
                    ssl=ssl_arg,
                ) as resp:
                    payload = await resp.read()
                    ok = resp.status == 200 and payload.startswith(b"%PDF")
                    if ok:
                        output_path.write_bytes(payload)
                        result = dict(rec)
                        result.update(
                            {
                                "download_ok": True,
                                "status": int(resp.status),
                                "bytes": len(payload),
                                "path": str(output_path),
                                "ssl_verify": verify_ssl,
                                "existing": False,
                                "page_count": _safe_page_count(output_path),
                            }
                        )
                        return result
                    last_error = (
                        f"status={resp.status} bytes={len(payload)} "
                        f"prefix={payload[:16]!r}"
                    )
            except Exception as exc:  # pragma: no cover - network/runtime variability
                last_error = repr(exc)

    result = dict(rec)
    result.update(
        {
            "download_ok": False,
            "status": None,
            "bytes": 0,
            "path": str(output_path),
            "error": last_error,
            "page_count": None,
        }
    )
    return result


async def _run_downloads(
    records: list[dict[str, Any]],
    downloads_dir: Path,
    *,
    concurrency: int,
    conn_limit: int,
    conn_limit_per_host: int,
    timeout_total: int,
    timeout_connect: int,
    timeout_sock_read: int,
) -> list[dict[str, Any]]:
    sem = asyncio.Semaphore(concurrency)
    timeout = aiohttp.ClientTimeout(
        total=timeout_total,
        connect=timeout_connect,
        sock_read=timeout_sock_read,
    )
    connector = aiohttp.TCPConnector(
        limit=conn_limit,
        limit_per_host=conn_limit_per_host,
        ttl_dns_cache=300,
    )
    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        tasks = [_download_one(session, sem, rec, downloads_dir) for rec in records]
        return await asyncio.gather(*tasks)


def main() -> int:
    args = parse_args()
    manifest_path = args.manifest.resolve()
    output_root = args.output_root.resolve()
    downloads_dir = output_root / "downloads"
    meta_dir = output_root / "download_results"
    downloads_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_parquet(manifest_path).copy()
    if "filename" not in df.columns or "pdf_url" not in df.columns:
        raise ValueError("Manifest must contain filename and pdf_url columns")
    df["needs_ocr"] = True
    df["ocr_success"] = False
    records = df.to_dict(orient="records")

    results = asyncio.run(
        _run_downloads(
            records,
            downloads_dir,
            concurrency=args.concurrency,
            conn_limit=args.conn_limit,
            conn_limit_per_host=args.conn_limit_per_host,
            timeout_total=args.timeout_total,
            timeout_connect=args.timeout_connect,
            timeout_sock_read=args.timeout_sock_read,
        )
    )
    results_df = pd.DataFrame(results)
    results_df.to_parquet(meta_dir / "sample_manifest_with_downloads.parquet", index=False)

    ready = results_df.loc[results_df["download_ok"] == True].copy()  # noqa: E712
    ready_for_corpus = ready[["filename"]].copy()
    ready_for_corpus["url"] = ready["pdf_url"]
    ready_for_corpus["needs_ocr"] = True
    ready_for_corpus["ocr_success"] = False
    ready_for_corpus.to_parquet(meta_dir / "download_results.parquet", index=False)

    summary = {
        "requested_docs": int(len(results_df)),
        "download_ok_docs": int(ready.shape[0]),
        "download_failed_docs": int((~results_df["download_ok"].fillna(False).astype(bool)).sum()),
        "download_ok_pages": int(ready["page_count"].fillna(0).sum()),
        "bucket_counts": ready.get("bucket", pd.Series(dtype=str)).value_counts().to_dict(),
        "collection_counts": ready.get("collection_slug", pd.Series(dtype=str)).fillna("unknown").value_counts().to_dict(),
    }
    (output_root / "download_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    failed = results_df.loc[~results_df["download_ok"].fillna(False).astype(bool), ["filename", "pdf_url", "error"]]
    if not failed.empty:
        print("\nFAILED:")
        print(failed.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
