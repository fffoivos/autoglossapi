from __future__ import annotations

import importlib.util
import unittest

PANDAS_AVAILABLE = importlib.util.find_spec("pandas") is not None
if PANDAS_AVAILABLE:
    import pandas as pd

    from runtime.ocr.select_reference_pages import analyze_page_text, select_reference_pages


@unittest.skipUnless(PANDAS_AVAILABLE, "pandas is required for the reference-page selection tests")
class ReferencePageSelectionTests(unittest.TestCase):
    def test_analyze_page_text_marks_good_reference_and_scores_polytonic(self) -> None:
        text = "Ἡ ἀρετὴ τοῦ λόγου.\n" * 30
        metrics = analyze_page_text(
            text,
            min_text_chars=100,
            min_printable_ratio=0.95,
            max_control_ratio=0.02,
        )
        self.assertTrue(metrics["good_reference"])
        self.assertGreater(metrics["polytonic_chars"], 0)
        self.assertGreater(metrics["polytonic_ratio_page"], 0.0)

    def test_select_reference_pages_prefers_bucket_specific_signal(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "source_doc_id": "poly_doc",
                    "bucket": "polytonic_greek",
                    "page_number": 1,
                    "text_chars": 600,
                    "good_reference": True,
                    "polytonic_chars": 5,
                    "math_score": 0,
                    "control_ratio": 0.0,
                    "unique_line_ratio": 1.0,
                    "repeated_line_max": 1,
                },
                {
                    "source_doc_id": "poly_doc",
                    "bucket": "polytonic_greek",
                    "page_number": 2,
                    "text_chars": 500,
                    "good_reference": True,
                    "polytonic_chars": 20,
                    "math_score": 0,
                    "control_ratio": 0.0,
                    "unique_line_ratio": 1.0,
                    "repeated_line_max": 1,
                },
                {
                    "source_doc_id": "math_doc",
                    "bucket": "math_control",
                    "page_number": 1,
                    "text_chars": 700,
                    "good_reference": True,
                    "polytonic_chars": 0,
                    "math_score": 3,
                    "control_ratio": 0.0,
                    "unique_line_ratio": 1.0,
                    "repeated_line_max": 1,
                },
                {
                    "source_doc_id": "math_doc",
                    "bucket": "math_control",
                    "page_number": 3,
                    "text_chars": 650,
                    "good_reference": True,
                    "polytonic_chars": 0,
                    "math_score": 15,
                    "control_ratio": 0.0,
                    "unique_line_ratio": 1.0,
                    "repeated_line_max": 1,
                },
            ]
        )

        selected = select_reference_pages(frame)
        self.assertEqual(len(selected), 2)
        selected = selected.set_index("source_doc_id")
        self.assertEqual(int(selected.loc["poly_doc", "page_number"]), 2)
        self.assertEqual(int(selected.loc["math_doc", "page_number"]), 3)


if __name__ == "__main__":
    unittest.main()
