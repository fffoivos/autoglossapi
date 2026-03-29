from __future__ import annotations

import json
import unittest
from pathlib import Path

import jsonschema


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "schemas" / "snapshot_manifest.schema.json"


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


class SnapshotManifestSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.schema = load_schema()

    def test_valid_bulk_snapshot_manifest_passes(self) -> None:
        payload = {
            "snapshot_id": "pyxida_20260329T160000Z",
            "collection_slug": "pyxida",
            "stage": "bulk_run_scraper",
            "created_at": "2026-03-29T16:00:00Z",
            "scraper_version": "pyxida-v1",
            "agent_run_id": "20260329T160000Z_bulk_run_scraper",
            "source_run_dir": "/srv/glossapi/runs/20260329T160000Z_bulk_run_scraper",
            "storage_backend": "s3",
            "storage_prefix": "s3://example-bucket/openarchives-direct-recovery/raw-pdfs/pyxida/20260329T160000Z",
            "sha256_manifest_path": "s3://example-bucket/openarchives-direct-recovery/manifests/pyxida/20260329T160000Z.sha256",
            "download_log_path": "s3://example-bucket/openarchives-direct-recovery/logs/20260329T160000Z/download.jsonl",
            "telemetry_snapshot_path": "s3://example-bucket/openarchives-direct-recovery/logs/20260329T160000Z/snapshot.json",
            "document_count": 12265,
            "pdf_file_count": 12265,
            "total_bytes": 987654321,
            "failed_items": [
                {
                    "item_id": "123456789/42",
                    "reason": "temporary 429 after max retries",
                }
            ],
            "notes": "Initial pyxida bulk acquisition snapshot.",
        }
        jsonschema.validate(payload, self.schema)

    def test_invalid_stage_is_rejected(self) -> None:
        payload = {
            "snapshot_id": "bad",
            "collection_slug": "pyxida",
            "stage": "discover",
            "created_at": "2026-03-29T16:00:00Z",
            "scraper_version": "pyxida-v1",
            "storage_backend": "s3",
            "storage_prefix": "s3://example-bucket/openarchives-direct-recovery/raw-pdfs/pyxida/bad",
            "document_count": 1,
            "pdf_file_count": 1,
            "total_bytes": 1,
            "notes": "bad stage",
        }
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(payload, self.schema)


if __name__ == "__main__":
    unittest.main()
