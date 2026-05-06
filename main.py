import argparse
import datetime
import importlib

import notion_api as notion
from config import ATS_SCRAPER_MAP
from deduplicator import is_duplicate
from matcher import get_role_type, match_title
from models import Opportunity


def main() -> None:
    parser = argparse.ArgumentParser(description="Check ATS boards for matching roles and write to Notion.")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be written without making Notion changes")
    args = parser.parse_args()

    today = datetime.date.today()
    year = today.year

    swept = 0
    added = 0
    dupes = 0
    no_match = 0
    error_count = 0
    new_roles: list[str] = []
    ashby_roles: list[tuple[str, str, str]] = []
    error_list: list[tuple[str, str]] = []

    companies = notion.fetch_companies()

    for company in companies:
        swept += 1

        if company.ats not in ATS_SCRAPER_MAP:
            error_list.append((company.name, f"Unknown ATS: {company.ats}"))
            error_count += 1
            notion.update_company(company.page_id, None, dry_run=args.dry_run)
            continue

        try:
            scraper = importlib.import_module(ATS_SCRAPER_MAP[company.ats])
            listings = scraper.fetch_jobs(company.ats_slug)
        except Exception as e:
            error_list.append((company.name, str(e)))
            error_count += 1
            notion.update_company(company.page_id, None, dry_run=args.dry_run)
            continue

        found_match = False

        for listing in listings:
            matched = match_title(listing.title)
            if not matched:
                continue

            if is_duplicate(company, listing):
                print(f"SKIP {company.name} / {listing.title} — duplicate found")
                dupes += 1
                continue

            role_type = get_role_type(matched)
            verified = "__NO__" if company.ats == "Ashby" else "__YES__"
            notes = None
            if company.ats == "Ashby":
                notes = f"Auto-added by job sweep on {today.isoformat()}. Ashby: manual verification required."

            opp = Opportunity(
                company=company,
                listing=listing,
                matched_title=matched,
                role_type=role_type,
                verified=verified,
                ats=company.ats,
                notes=notes,
            )

            notion.write_opportunity(opp, dry_run=args.dry_run)
            found_match = True
            added += 1

            label = f"{company.name} / {listing.title} / {year} [{company.ats}]"
            if company.ats == "Ashby":
                label += " [UNVERIFIED]"
                ashby_roles.append((company.name, listing.title, listing.url))
            new_roles.append(label)

        hiring = "Relevant" if found_match else "Not"
        if not found_match:
            no_match += 1
        notion.update_company(company.page_id, hiring, dry_run=args.dry_run)

    print(f"\n=== Job Sweep Complete — {today.isoformat()} ===")
    print(f"Companies swept: {swept}")
    print(f"New opportunities added: {added}")
    print(f"Duplicates skipped: {dupes}")
    print(f"Companies with no matching roles: {no_match}")
    print(f"Errors: {error_count}")

    print("\nNEW ROLES ADDED:")
    if new_roles:
        for r in new_roles:
            print(f"  - {r}")
    else:
        print("  (none)")

    if ashby_roles:
        print("\nASHBY — MANUAL VERIFICATION REQUIRED:")
        for cname, title, url in ashby_roles:
            print(f"  - {cname} / {title}: {url}")

    if error_list:
        print("\nERRORS:")
        for cname, msg in error_list:
            print(f"  - {cname}: {msg}")


if __name__ == "__main__":
    main()
