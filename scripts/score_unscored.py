#!/usr/bin/env python3
"""Standalone script to score unscored opportunities via Claude API.

Usage:
    python scripts/score_unscored.py
    python scripts/score_unscored.py --dry-run
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scorer import batch_score_unscored


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Score unscored Notion opportunities via Claude API."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be scored without writing to Notion",
    )
    args = parser.parse_args()

    print("Fetching unscored opportunities...")
    stats = batch_score_unscored(dry_run=args.dry_run)

    print(f"\n=== Scoring Complete ===")
    print(f"Scored:  {stats['scored']}")
    print(f"Skipped: {stats['skipped']}")
    print(f"Errors:  {stats['errors']}")


if __name__ == "__main__":
    main()
