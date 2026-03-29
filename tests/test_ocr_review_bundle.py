from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

PANDAS_AVAILABLE = importlib.util.find_spec("pandas") is not None
if PANDAS_AVAILABLE:
    import pandas as pd

    from runtime.ocr.build_ocr_review_bundle import build_review_bundle, write_outputs


@unittest.skipUnless(PANDAS_AVAILABLE, "pandas is required for the OCR review bundle tests")
class OcrReviewBundleTests(unittest.TestCase):
    def test_build_review_bundle_creates_case_files_without_similarity_scoring(self) -> None:
        with self.subTest("bundle"):
            import tempfile

            with tempfile.TemporaryDirectory() as tmp_dir:
                root = Path(tmp_dir)
                markdown_dir = root / "ocr_output" / "markdown"
                markdown_dir.mkdir(parents=True, exist_ok=True)
                (markdown_dir / "doc__p0001.md").write_text(
                    "γραμμή\nΕΠΑΝΑΛΗΨΗ\nΕΠΑΝΑΛΗΨΗ\nΕΠΑΝΑΛΗΨΗ\n",
                    encoding="utf-8",
                )
                selected = pd.DataFrame(
                    [
                        {
                            "source_doc_id": "doc",
                            "filename": "doc__p0001.pdf",
                            "page_number": 1,
                            "bucket": "polytonic_greek",
                            "collection_slug": "hellanicus",
                            "page_text": "Ἡ ἀρετὴ τοῦ λόγου.",
                            "selected_pdf_path": str(root / "pdfs" / "doc__p0001.pdf"),
                        }
                    ]
                )

                output_dir = root / "review_bundle"
                report = build_review_bundle(selected, markdown_dir=markdown_dir, output_dir=output_dir)
                write_outputs(output_dir, report)

                self.assertEqual(len(report), 1)
                self.assertNotIn("similarity", report.columns)
                self.assertTrue(bool(report.loc[0, "repeat_flag"]))
                self.assertTrue((output_dir / "cases" / "doc__p0001" / "reference.txt").exists())
                self.assertTrue((output_dir / "cases" / "doc__p0001" / "ocr.md").exists())

                summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
                self.assertEqual(summary["docs"], 1)
                self.assertEqual(summary["repeat_flags"], 1)
                self.assertTrue((output_dir / "review_queue.csv").exists())


if __name__ == "__main__":
    unittest.main()
