import datetime
from dataclasses import dataclass, field
from typing import Optional

import notion_api as notion
from config import (
    DISCOVERY_ENABLED,
    DISCOVERY_JD_KEYWORDS,
    DISCOVERY_ROLE_TYPE_MAP,
    DISCOVERY_SEED_COMPANIES,
    DISCOVERY_TITLES,
    SECONDARY_JD_SCAN_ENABLED,
    TITLE_EXCLUDE,
)
from deduplicator import is_duplicate
from models import Company, DiscoveryListing, JobListing, Opportunity
from geo_filter import is_title_geo_excluded
from red_flag_detector import check_red_flags


@dataclass
class DiscoveryStats:
    title_matches: int = 0
    jd_matches: int = 0
    new_companies: int = 0
    added_to_existing: int = 0
    dupes: int = 0
    geo_filtered: int = 0
    red_flagged: int = 0
    new_roles: list = field(default_factory=list)
    errors: list = field(default_factory=list)


def run_discovery(dry_run: bool = False) -> DiscoveryStats:
    if not DISCOVERY_ENABLED:
        return DiscoveryStats()

    stats = DiscoveryStats()
    seen_urls: set[str] = set()
    today = datetime.date.today()

    _run_greenhouse_discovery(stats, seen_urls, today, dry_run)
    _run_seed_discovery("Lever", stats, seen_urls, today, dry_run)
    _run_seed_discovery("Ashby", stats, seen_urls, today, dry_run)

    return stats


def _run_greenhouse_discovery(
    stats: DiscoveryStats,
    seen_urls: set[str],
    today: datetime.date,
    dry_run: bool,
) -> None:
    from scrapers.discovery_greenhouse import search_jobs

    for keyword in DISCOVERY_TITLES:
        try:
            listings, gf = search_jobs(keyword)
            stats.geo_filtered += gf
        except Exception as e:
            stats.errors.append(("Greenhouse discovery", f'keyword "{keyword}": {e}'))
            continue
        _process_listings(listings, stats, seen_urls, today, dry_run)


def _run_seed_discovery(
    ats: str,
    stats: DiscoveryStats,
    seen_urls: set[str],
    today: datetime.date,
    dry_run: bool,
) -> None:
    if ats == "Lever":
        from scrapers.discovery_lever import fetch_all_jobs
    else:
        from scrapers.discovery_ashby import fetch_all_jobs

    seed_companies = [c for c in DISCOVERY_SEED_COMPANIES if c["ats"] == ats]
    for company in seed_companies:
        try:
            listings, gf = fetch_all_jobs(company)
            stats.geo_filtered += gf
        except Exception as e:
            stats.errors.append((company["name"], str(e)))
            continue
        _process_listings(listings, stats, seen_urls, today, dry_run)


def _process_listings(
    listings: list[DiscoveryListing],
    stats: DiscoveryStats,
    seen_urls: set[str],
    today: datetime.date,
    dry_run: bool,
) -> None:
    for listing in listings:
        if listing.url in seen_urls:
            continue

        matched_title, match_type, matched_kws = _classify(listing)
        if match_type is None:
            continue

        if is_title_geo_excluded(listing.title):
            stats.geo_filtered += 1
            continue

        seen_urls.add(listing.url)

        job_listing = JobListing(title=listing.title, url=listing.url)

        try:
            company, is_new = _resolve_company(listing, dry_run)
        except Exception as e:
            stats.errors.append((listing.company_name, f"Company lookup failed: {e}"))
            continue

        if is_duplicate(company, job_listing):
            print(f"SKIP [Discovery] {listing.company_name} / {listing.title} — duplicate found")
            stats.dupes += 1
            continue

        flags = check_red_flags(listing.title, listing.description)
        if flags:
            print(f"RED FLAG [Discovery] {listing.company_name} / {listing.title} — {', '.join(f.code for f in flags)}")
            stats.red_flagged += 1
            continue

        role_type = DISCOVERY_ROLE_TYPE_MAP.get(matched_title or "", "Other")
        verified = "__NO__" if listing.ats == "Ashby" else "__YES__"
        opp_description = (
            "Surfaced via JD keyword match — verify title fit before applying."
            if match_type == "jd_keyword"
            else None
        )

        opp = Opportunity(
            company=company,
            listing=job_listing,
            matched_title=matched_title or listing.title,
            role_type=role_type,
            verified=verified,
            ats=listing.ats,
            source="Discovery",
            description=opp_description,
        )

        notion.write_opportunity(opp, dry_run=dry_run)

        label = f"{listing.company_name} / {listing.title} / {today.year} [{listing.ats}]"
        if match_type == "title":
            label += f' (keyword: "{matched_kws[0]}")'
            stats.title_matches += 1
        else:
            kw_str = ", ".join(f'"{k}"' for k in matched_kws[:3])
            label += f" (JD: {kw_str})"
            stats.jd_matches += 1

        if listing.ats == "Ashby":
            label += " [UNVERIFIED]"

        if is_new:
            stats.new_companies += 1
        else:
            stats.added_to_existing += 1

        stats.new_roles.append(label)


def _classify(
    listing: DiscoveryListing,
) -> tuple[Optional[str], Optional[str], list[str]]:
    """Return (matched_title, match_type, matched_keywords) or (None, None, [])."""
    lower_title = listing.title.lower()
    excluded = any(exc.lower() in lower_title for exc in TITLE_EXCLUDE)

    if not excluded:
        for target in DISCOVERY_TITLES:
            if target.lower() in lower_title:
                return target, "title", [target]

    if SECONDARY_JD_SCAN_ENABLED and listing.description:
        lower_desc = listing.description.lower()
        matched_kws = [kw for kw in DISCOVERY_JD_KEYWORDS if kw.lower() in lower_desc]
        if len(matched_kws) >= 2:
            return None, "jd_keyword", matched_kws

    return None, None, []


def _resolve_company(listing: DiscoveryListing, dry_run: bool) -> tuple[Company, bool]:
    """Return (company, is_new). Creates a Notion company record if not found."""
    existing = notion.find_company_by_name(listing.company_name)
    if existing:
        return existing, False
    company = notion.create_company(
        name=listing.company_name,
        ats=listing.ats,
        slug=listing.slug,
        dry_run=dry_run,
    )
    return company, True
