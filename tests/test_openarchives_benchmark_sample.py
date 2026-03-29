from __future__ import annotations

import importlib.util
import unittest

PANDAS_AVAILABLE = importlib.util.find_spec("pandas") is not None
if PANDAS_AVAILABLE:
    import pandas as pd
    from runtime.ocr.openarchives_benchmark_sample import select_benchmark_sample


@unittest.skipUnless(PANDAS_AVAILABLE, "pandas is required for the benchmark sample test")
class OpenArchivesBenchmarkSampleTests(unittest.TestCase):
    def test_select_benchmark_sample_assigns_expected_bucket_counts(self) -> None:
        rows: list[dict] = []
        for idx in range(1, 7):
            rows.append(
                {
                    "source_doc_id": f"poly_ref_{idx}",
                    "title": f"Poly Ref {idx}",
                    "author": "A",
                    "collection_slug": f"poly_{idx % 3}",
                    "collection_for_sampling": f"poly_{idx % 3}",
                    "language_code": "ELL",
                    "doc_type": "book",
                    "pdf_url": f"https://example.com/poly_ref_{idx}.pdf",
                    "filename": f"poly_ref_{idx}.pdf",
                    "needs_ocr": False,
                    "strict_needs_ocr": False,
                    "greek_badness_score": float(idx),
                    "mojibake_badness_score": 0.0,
                    "contains_math": False,
                    "contains_latex": False,
                    "is_historical_or_polytonic": True,
                    "polytonic_ratio": 0.2,
                    "polytonic_candidate": True,
                    "table_ratio": 0.0,
                    "filter": "ok",
                    "text_chars": 2000,
                }
            )
        for idx in range(1, 7):
            rows.append(
                {
                    "source_doc_id": f"poly_strict_{idx}",
                    "title": f"Poly Strict {idx}",
                    "author": "A",
                    "collection_slug": f"poly_s_{idx % 3}",
                    "collection_for_sampling": f"poly_s_{idx % 3}",
                    "language_code": "ELL",
                    "doc_type": "book",
                    "pdf_url": f"https://example.com/poly_strict_{idx}.pdf",
                    "filename": f"poly_strict_{idx}.pdf",
                    "needs_ocr": True,
                    "strict_needs_ocr": True,
                    "greek_badness_score": float(50 + idx),
                    "mojibake_badness_score": 0.0,
                    "contains_math": False,
                    "contains_latex": False,
                    "is_historical_or_polytonic": True,
                    "polytonic_ratio": 0.3,
                    "polytonic_candidate": True,
                    "table_ratio": 0.0,
                    "filter": "bad",
                    "text_chars": 2200,
                }
            )
        for idx in range(1, 7):
            rows.append(
                {
                    "source_doc_id": f"math_{idx}",
                    "title": f"Math {idx}",
                    "author": "B",
                    "collection_slug": f"math_{idx % 3}",
                    "collection_for_sampling": f"math_{idx % 3}",
                    "language_code": "ELL",
                    "doc_type": "thesis",
                    "pdf_url": f"https://example.com/math_{idx}.pdf",
                    "filename": f"math_{idx}.pdf",
                    "needs_ocr": False,
                    "strict_needs_ocr": False,
                    "greek_badness_score": float(idx),
                    "mojibake_badness_score": 0.0,
                    "contains_math": True,
                    "contains_latex": True,
                    "is_historical_or_polytonic": False,
                    "polytonic_ratio": 0.0,
                    "polytonic_candidate": False,
                    "table_ratio": 0.0,
                    "filter": "ok",
                    "text_chars": 4000,
                }
            )
        for idx in range(1, 7):
            rows.append(
                {
                    "source_doc_id": f"strict_{idx}",
                    "title": f"Strict {idx}",
                    "author": "C",
                    "collection_slug": f"strict_{idx % 3}",
                    "collection_for_sampling": f"strict_{idx % 3}",
                    "language_code": "ELL",
                    "doc_type": "article",
                    "pdf_url": f"https://example.com/strict_{idx}.pdf",
                    "filename": f"strict_{idx}.pdf",
                    "needs_ocr": True,
                    "strict_needs_ocr": True,
                    "greek_badness_score": float(70 + idx),
                    "mojibake_badness_score": 0.0,
                    "contains_math": False,
                    "contains_latex": False,
                    "is_historical_or_polytonic": False,
                    "polytonic_ratio": 0.0,
                    "polytonic_candidate": False,
                    "table_ratio": 0.0,
                    "filter": "bad",
                    "text_chars": 3000,
                }
            )
        for idx in range(1, 7):
            rows.append(
                {
                    "source_doc_id": f"long_{idx}",
                    "title": f"Long {idx}",
                    "author": "D",
                    "collection_slug": f"long_{idx % 3}",
                    "collection_for_sampling": f"long_{idx % 3}",
                    "language_code": "ELL",
                    "doc_type": "book",
                    "pdf_url": f"https://example.com/long_{idx}.pdf",
                    "filename": f"long_{idx}.pdf",
                    "needs_ocr": False,
                    "strict_needs_ocr": False,
                    "greek_badness_score": 5.0,
                    "mojibake_badness_score": 0.0,
                    "contains_math": False,
                    "contains_latex": False,
                    "is_historical_or_polytonic": False,
                    "polytonic_ratio": 0.0,
                    "polytonic_candidate": False,
                    "table_ratio": 0.4,
                    "filter": "ok",
                    "text_chars": 9000 + idx,
                }
            )

        frame = pd.DataFrame(rows)
        sample = select_benchmark_sample(
            frame,
            polytonic_count=4,
            math_count=4,
            strict_count=4,
            long_count=2,
            min_polytonic_text_chars=500,
            min_math_text_chars=500,
        )

        self.assertEqual(len(sample), 14)
        self.assertEqual(sample["source_doc_id"].nunique(), 14)
        self.assertEqual((sample["bucket"] == "polytonic_greek").sum(), 4)
        self.assertEqual((sample["bucket"] == "math_control").sum(), 4)
        self.assertEqual((sample["bucket"] == "strict_bad_extraction").sum(), 4)
        self.assertEqual((sample["bucket"] == "long_output_risk").sum(), 2)


if __name__ == "__main__":
    unittest.main()
