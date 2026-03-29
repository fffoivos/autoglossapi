#!/usr/bin/env python3

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from controller.human_decision import write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a structured human decision for a stopped lineage.")
    parser.add_argument("--collection-slug", required=True)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--decision", choices=["retry_same_stage", "advance", "stop_exhausted"], required=True)
    parser.add_argument("--decision-reason", required=True)
    parser.add_argument("--instruction", action="append", default=[])
    parser.add_argument("--approved-by", default="foivos")
    parser.add_argument("--approved-eta-ceiling-hours", type=float, default=None)
    parser.add_argument("--target-progress-percent", type=float, default=None)
    parser.add_argument("--scope-override", default=None)
    parser.add_argument("--notes", default=None)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    decision_id = f"{args.collection_slug}_{args.stage}_{stamp}"
    payload = {
        "decision_id": decision_id,
        "collection_slug": args.collection_slug,
        "stage": args.stage,
        "decision": args.decision,
        "decision_reason": args.decision_reason,
        "instructions": list(args.instruction),
        "approved_by": args.approved_by,
        "approved_at": datetime.now(UTC).isoformat(),
        "approved_eta_ceiling_hours": args.approved_eta_ceiling_hours,
        "target_progress_percent": args.target_progress_percent,
        "scope_override": args.scope_override,
        "notes": args.notes,
    }
    write_json(args.output, payload)
    print(args.output)


if __name__ == "__main__":
    main()
