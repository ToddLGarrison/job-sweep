#!/usr/bin/env python3
"""Generate and deliver a pre-interview research brief for a Notion opportunity.

Usage:
    python scripts/research_brief.py "Company Name"
    python scripts/research_brief.py "Company Name" --dry-run
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import notion_api as notion
import research_brief as rb
from config import DIGEST_EMAIL_TO
from digest import send_digest


def _pick_opportunity(matches: list[dict]) -> dict:
    if len(matches) == 1:
        return matches[0]
    print(f"Found {len(matches)} matching opportunities:")
    for i, opp in enumerate(matches, 1):
        print(f"  {i}. {opp['name']} [{opp['stage']}]")
    while True:
        raw = input("Pick one (number): ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(matches):
            return matches[int(raw) - 1]
        print(f"  Enter a number between 1 and {len(matches)}.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a pre-interview research brief for a Notion opportunity."
    )
    parser.add_argument("company", help="Company name to search for in Notion")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate brief but skip Notion write and email send",
    )
    args = parser.parse_args()

    print(f"Searching Notion for opportunities at '{args.company}'...")
    matches = notion.search_opportunities_by_company(args.company)
    if not matches:
        print(f"No active opportunities found for '{args.company}'.")
        sys.exit(1)

    opp = _pick_opportunity(matches)
    company = opp["company_name"]
    title = opp["title"]
    job_url = opp["job_url"]
    page_id = opp["page_id"]

    print(f"\nGenerating research brief for: {opp['name']}")
    print("(This may take 30-60 seconds while Claude searches the web...)\n")

    try:
        brief = rb.generate_brief(company, title, job_url)
    except RuntimeError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    print(brief)
    print()

    subject = f"Research Brief — {company} ({title})"

    if args.dry_run:
        print("[DRY RUN] Would write brief to Notion and send email.")
        print(f"  Subject: {subject}")
        return

    print("Writing brief to Notion...")
    notion.update_research_field(page_id, brief)

    print("Sending email...")
    send_digest(subject, brief)

    print(f"Brief written to Notion and emailed to {DIGEST_EMAIL_TO}")


if __name__ == "__main__":
    main()
