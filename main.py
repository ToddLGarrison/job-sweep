import argparse
import datetime
import importlib

import notion_api as notion
from config import ATS_SCRAPER_MAP, DISCOVERY_ENABLED
from scorer import batch_score_unscored
from deduplicator import is_duplicate
from digest import (
    build_digest,
    build_subject,
    merge_stats,
    read_and_clear_last_run,
    send_digest,
    write_last_run,
)
from discovery import run_discovery
from expiry_checker import run_expiry_check
from geo_filter import check_description_geo, is_title_geo_excluded
from matcher import get_role_type, match_title
from models import Opportunity
from red_flag_detector import check_red_flags


def main() -> None:
    parser = argparse.ArgumentParser(description="Check ATS boards for matching roles and write to Notion.")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be written without making Notion changes")
    parser.add_argument("--skip-expiry", action="store_true", help="Skip the URL expiry check")
    parser.add_argument("--send-digest", action="store_true", help="Build and send the daily email digest (6am run only)")
    parser.add_argument("--score", action="store_true", help="Score unscored opportunities via Claude API after sweep")
    args = parser.parse_args()

    today = datetime.date.today()
    year = today.year

    swept = 0
    added = 0
    dupes = 0
    no_match = 0
    error_count = 0
    geo_filtered = 0
    red_flagged = 0
    new_roles: list[str] = []
    ashby_roles: list[tuple[str, str, str]] = []
    red_flagged_roles: list[tuple[str, str, list]] = []
    error_list: list[tuple[str, str]] = []
    seen_urls: set[str] = set()

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
            listings, company_geo_filtered = scraper.fetch_jobs(company.ats_slug)
            geo_filtered += company_geo_filtered
        except Exception as e:
            error_list.append((company.name, str(e)))
            error_count += 1
            notion.update_company(company.page_id, None, dry_run=args.dry_run)
            continue

        found_match = False

        try:
            for listing in listings:
                if listing.url in seen_urls:
                    continue

                matched = match_title(listing.title)
                if not matched:
                    continue

                if is_title_geo_excluded(listing.title) or \
                        check_description_geo(listing.description):
                    geo_filtered += 1
                    continue

                if is_duplicate(company, listing):
                    print(f"SKIP {company.name} / {listing.title} — duplicate found")
                    dupes += 1
                    continue

                flags = check_red_flags(listing.title, listing.description)
                if flags:
                    label = f"{company.name} / {listing.title}"
                    red_flagged_roles.append((label, listing.url, flags))
                    red_flagged += 1
                    print(f"RED FLAG {company.name} / {listing.title} — {', '.join(f.code for f in flags)}")
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
                    location=listing.location,
                )

                notion.write_opportunity(opp, dry_run=args.dry_run)
                seen_urls.add(listing.url)
                found_match = True
                added += 1

                label = f"{company.name} / {listing.title} / {year} [{company.ats}]"
                if company.ats == "Ashby":
                    label += " [UNVERIFIED]"
                    ashby_roles.append((company.name, listing.title, listing.url))
                new_roles.append(label)
        except Exception as e:
            error_list.append((company.name, str(e)))
            error_count += 1
            notion.update_company(company.page_id, None, dry_run=args.dry_run)
            continue

        hiring = "Relevant" if found_match else "Not"
        if not found_match:
            no_match += 1
        notion.update_company(company.page_id, hiring, dry_run=args.dry_run)

    # --- Discovery ---
    disc = run_discovery(dry_run=args.dry_run) if DISCOVERY_ENABLED else None

    # --- Expiry check ---
    expiry = None
    if not args.skip_expiry:
        expiry = run_expiry_check(dry_run=args.dry_run)

    # --- Run summary ---
    print(f"\n=== Job Sweep Complete — {today.isoformat()} ===")
    print(f"Companies swept: {swept}")
    print(f"New opportunities added: {added}")
    print(f"Duplicates skipped: {dupes}")
    print(f"Geo-filtered (non-US): {geo_filtered}")
    print(f"Red-flagged (skipped): {red_flagged}")
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

    if red_flagged_roles:
        print("\nRED-FLAGGED ROLES SKIPPED:")
        for label, url, flags in red_flagged_roles:
            flag_str = ", ".join(f.code for f in flags)
            print(f"  - {label} [{flag_str}]: {url}")

    if error_list:
        print("\nERRORS:")
        for cname, msg in error_list:
            print(f"  - {cname}: {msg}")

    if expiry is not None:
        print("\n--- Expiry Check ---")
        print(f"Roles still live (checked): {expiry.still_live}")
        print(f"Roles newly missed (1+ strike): {expiry.newly_missed}")
        print(f"Roles auto-closed (expired): {expiry.auto_closed}")
        if expiry.errors:
            print(f"Expiry check errors: {expiry.errors}")
        if expiry.closed_roles:
            print("\nROLES AUTO-CLOSED (EXPIRED):")
            for role in expiry.closed_roles:
                print(f"  - {role}")

    if disc is not None:
        print("\n--- Discovery ---")
        print(f"Roles found via title keyword match: {disc.title_matches}")
        print(f"Roles found via secondary JD keyword pass: {disc.jd_matches}")
        print(f"New companies auto-created: {disc.new_companies}")
        print(f"Roles added to existing companies: {disc.added_to_existing}")
        print(f"Roles skipped as duplicates: {disc.dupes}")
        print(f"Geo-filtered (non-US): {disc.geo_filtered}")
        print(f"Red-flagged (skipped): {disc.red_flagged}")
        print(f"Skipped (unknown ATS): {disc.unknown_ats}")

        if disc.new_roles:
            print("\nDISCOVERY — NEW ROLES:")
            for r in disc.new_roles:
                print(f"  - {r}")

        if disc.errors:
            print("\nDISCOVERY — ERRORS:")
            for source, msg in disc.errors:
                print(f"  - {source}: {msg}")

    # --- Fit scoring ---
    if args.score:
        print("\n--- Fit Scoring ---")
        score_stats = batch_score_unscored(dry_run=args.dry_run)
        print(f"Scored: {score_stats['scored']} opportunities")
        print(f"Skipped: {score_stats['skipped']}")
        if score_stats["errors"]:
            print(f"Errors: {score_stats['errors']}")

    # --- Persist stats and send digest ---
    all_errors: list[list[str]] = [[c, m] for c, m in error_list]
    if disc:
        all_errors += [[src, msg] for src, msg in disc.errors]
    if expiry and expiry.errors:
        all_errors.append(["Expiry checker", f"{expiry.errors} error(s) during expiry check"])

    sweep_stats = {
        "new_roles": new_roles,
        "discovery_new_roles": disc.new_roles if disc else [],
        "closed_roles": expiry.closed_roles if expiry else [],
        "errors": all_errors,
        "geo_filtered": geo_filtered + (disc.geo_filtered if disc else 0),
        "red_flagged": red_flagged + (disc.red_flagged if disc else 0),
    }

    previous = read_and_clear_last_run() if args.send_digest else None
    write_last_run(sweep_stats)

    if args.send_digest:
        combined = merge_stats(sweep_stats, previous) if previous else sweep_stats
        subject = build_subject(combined)
        body = build_digest(combined)
        send_digest(subject, body)


if __name__ == "__main__":
    main()
