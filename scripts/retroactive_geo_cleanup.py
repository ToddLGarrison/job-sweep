"""
Audits active Notion Opportunities and closes any that should have been
geo-filtered (non-US title signal or non-US location field).

Usage:
    python scripts/retroactive_geo_cleanup.py [--dry-run] [--verbose]

Flags:
    --dry-run    Print what would be closed without writing to Notion.
    --verbose    Print every record checked, not just flagged ones.
"""
import argparse
import os
import sys

# Allow running as a standalone script from any working directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from notion_client import Client

from config import NOTION_API_KEY, OPPORTUNITIES_DB_ID
from geo_filter import is_title_geo_excluded, is_us_or_remote

_client = Client(auth=NOTION_API_KEY, timeout_ms=120_000)

_ACTIVE_STAGES = ["Qualification", "Prioritized", "Create Resume", "Contacted / Applied"]


def _extract_title(name: str) -> str:
    """Extract role title from 'Company / Title / Year' Name format."""
    parts = name.split(" / ")
    if len(parts) >= 2:
        return parts[1].strip()
    return name.strip()


def _get_location(props: dict) -> str:
    """Read the Location property; returns empty string if absent."""
    loc_prop = props.get("Location", {})
    rich = loc_prop.get("rich_text", [])
    if rich:
        return "".join(t.get("plain_text", "") for t in rich)
    return ""


def _should_geo_close(title: str, location: str) -> tuple[bool, str]:
    """Return (should_close, flag_code). flag_code is 'GEO_TITLE' or 'GEO_LOCATION'."""
    if is_title_geo_excluded(title):
        return True, "GEO_TITLE"
    if location and not is_us_or_remote(location):
        return True, "GEO_LOCATION"
    return False, ""


def _fetch_active_opps(client) -> list[dict]:
    filter_clauses = [
        {"property": "Stage", "select": {"equals": s}} for s in _ACTIVE_STAGES
    ]
    opps = []
    cursor = None
    while True:
        kwargs: dict = {"filter": {"or": filter_clauses}}
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = client.data_sources.query(OPPORTUNITIES_DB_ID, **kwargs)
        for page in resp["results"]:
            props = page["properties"]
            name = "".join(
                t.get("plain_text", "")
                for t in props.get("Name", {}).get("title", [])
            )
            url = props.get("Job URL", {}).get("url", "") or ""
            location = _get_location(props)
            opps.append({
                "page_id": page["id"],
                "name": name,
                "url": url,
                "location": location,
            })
        if not resp.get("has_more"):
            break
        cursor = resp["next_cursor"]
    return opps


def run_cleanup(dry_run: bool = False, verbose: bool = False, client=None) -> dict:
    if client is None:
        client = _client

    opps = _fetch_active_opps(client)

    checked = 0
    closed_title = 0
    closed_location = 0
    skipped = 0

    for opp in opps:
        checked += 1
        name = opp["name"]
        url = opp["url"]
        location = opp["location"]
        page_id = opp["page_id"]

        title = _extract_title(name)
        should_close, flag_code = _should_geo_close(title, location)

        if should_close:
            loc_display = location or "(no location)"
            print(f"[{flag_code}] {name} | {loc_display} | {url}")
            if flag_code == "GEO_TITLE":
                closed_title += 1
            else:
                closed_location += 1
            if not dry_run:
                client.pages.update(
                    page_id=page_id,
                    properties={"Stage": {"select": {"name": "Closed Lost"}}},
                )
        else:
            skipped += 1
            if verbose:
                print(f"[OK] {name} | {location or '(no location)'}")

    total_closed = closed_title + closed_location
    print(
        f"\nChecked {checked} records. "
        f"Closed {total_closed} ({closed_title} geo-title, {closed_location} geo-location). "
        f"Skipped {skipped}."
    )

    return {
        "checked": checked,
        "closed_title": closed_title,
        "closed_location": closed_location,
        "skipped": skipped,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Retroactively close geo-excluded opportunities in Notion."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be closed without writing to Notion",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print every record checked, not just flagged ones",
    )
    args = parser.parse_args()
    run_cleanup(dry_run=args.dry_run, verbose=args.verbose)


if __name__ == "__main__":
    main()
