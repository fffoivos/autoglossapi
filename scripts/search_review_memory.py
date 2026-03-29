#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
TRACKING_DIR = REPO_ROOT / "tracking"
GENERATED_DIR = TRACKING_DIR / "generated"
MANUAL_DIR = TRACKING_DIR / "manual"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search reviewer knowledge, indexed solutions, and recovery statistics."
    )
    parser.add_argument("query")
    parser.add_argument("--limit", type=int, default=15)
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of a human-readable summary.")
    return parser.parse_args()


def load_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def row_text(row: dict[str, Any]) -> str:
    return " ".join(str(value or "") for value in row.values()).lower()


def search_rows(rows: list[dict[str, Any]], pattern: re.Pattern[str], source: str) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for row in rows:
        if pattern.search(row_text(row)):
            matches.append({"source": source, **row})
    return matches


def main() -> None:
    args = parse_args()
    pattern = re.compile(re.escape(args.query.lower()))
    sources = {
        "manual_solution_index": load_csv(MANUAL_DIR / "problem_solution_index.csv"),
        "generated_solution_index": load_csv(GENERATED_DIR / "reviewer_problem_solution_index.csv"),
        "recovery_cases": load_csv(GENERATED_DIR / "reviewer_recovery_cases.csv"),
        "recovery_stats": load_csv(GENERATED_DIR / "reviewer_recovery_stats.csv"),
    }

    matches: list[dict[str, Any]] = []
    for source_name, rows in sources.items():
        matches.extend(search_rows(rows, pattern, source_name))
    matches = matches[: args.limit]

    if args.json:
        print(json.dumps({"query": args.query, "matches": matches}, ensure_ascii=False, indent=2))
        return

    print(f"Query: {args.query}")
    print(f"Matches: {len(matches)}")
    for index, match in enumerate(matches, start=1):
        print(f"\n[{index}] source={match['source']}")
        for key, value in match.items():
            if key == "source" or value in {"", None}:
                continue
            print(f"{key}: {value}")


if __name__ == "__main__":
    main()
