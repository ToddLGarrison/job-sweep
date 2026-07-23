import datetime
from dataclasses import dataclass, field
from typing import Optional

import notion_api as notion
from config import (
    COMPANY_BLOCKLIST,
    DISCOVERY_ENABLED,
    DISCOVERY_JD_KEYWORDS,
    DISCOVERY_ROLE_TYPE_MAP,
    DISCOVERY_SEED_COMPANIES,
    DISCOVERY_TITLES,
    SECONDARY_JD_SCAN_ENABLED,
    TITLE_EXCLUDE,
    YC_ENABLED,
)
from deduplicator import is_duplicate
from models import Company, DiscoveryListing, JobListing, Opportunity
from geo_filter import check_description_geo, is_title_geo_excluded
from red_flag_detector import check_red_flags


# Pre-filter for the secondary JD scan only — not a red flag check.
# Titles matching these strings are never relevant regardless of JD content.
_WRONG_ROLE_TYPE_TITLES = [
    "data engineer", "software engineer", "product manager", "program manager",
    "ux designer", "ui designer", "product designer", "data scientist",
    "data analyst", "business analyst", "marketing manager", "demand generation",
    "devops", "site reliability", "security engineer", "infrastructure engineer",
    "finance manager", "accounting", "recruiter", "talent acquisition",
    "java engineer", "backend engineer", "frontend engineer", "full stack engineer",
    "machine learning engineer", "ml engineer", "ai engineer",
]

def _is_wrong_role_type(title: str) -> bool:
    lower = title.lower()
    return any(wrong in lower for wrong in _WRONG_ROLE_TYPE_TITLES)


YC_NOTE = (
    "Sourced via YC Work at a Startup. "
    "Apply via the YC listing — ATS URL redirect may change."
)


@dataclass
class DiscoveryStats:
    title_matches: int = 0
    jd_matches: int = 0
    new_companies: int = 0
    added_to_existing: int = 0
    dupes: int = 0
    geo_filtered: int = 0
    red_flagged: int = 0
    unknown_ats: int = 0
    new_roles: list = field(default_factory=list)
    errors: list = field(default_factory=list)


def run_discovery(dry_run: bool = False) -> DiscoveryStats:
    if not DISCOVERY_ENABLED:
        return DiscoveryStats()

    stats = DiscoveryStats()
    seen_urls: set[str] = set()
    today = datetime.date.today()

    try:
        all_companies = notion.fetch_companies()
    except Exception as e:
        stats.errors.append(("Discovery", f"fetch_companies failed: {e}"))
        all_companies = []

    _run_seed_discovery("Lever", all_companies, stats, seen_urls, today, dry_run)
    _run_seed_discovery("Ashby", all_companies, stats, seen_urls, today, dry_run)
    _run_seed_discovery("SmartRecruiters", all_companies, stats, seen_urls, today, dry_run)
    _run_seed_discovery("Workday", all_companies, stats, seen_urls, today, dry_run)
    if YC_ENABLED:
        _run_yc_discovery(stats, seen_urls, today, dry_run)

    return stats


def _run_seed_discovery(
    ats: str,
    all_companies: list,
    stats: DiscoveryStats,
    seen_urls: set[str],
    today: datetime.date,
    dry_run: bool,
) -> None:
    notion_companies = [c for c in all_companies if c.ats == ats]
    seed_dicts = [c for c in DISCOVERY_SEED_COMPANIES if c["ats"] == ats]

    if ats in ("Lever", "Ashby"):
        if ats == "Lever":
            from scrapers.discovery_lever import fetch_all_jobs
        else:
            from scrapers.discovery_ashby import fetch_all_jobs

        for company in notion_companies:
            company_dict = {"slug": company.ats_slug, "name": company.name, "ats": ats}
            try:
                listings, gf = fetch_all_jobs(company_dict)
                stats.geo_filtered += gf
            except Exception as e:
                stats.errors.append((company.name, str(e)))
                continue
            _process_listings(listings, stats, seen_urls, today, dry_run)
            del listings

        for company_dict in seed_dicts:
            try:
                listings, gf = fetch_all_jobs(company_dict)
                stats.geo_filtered += gf
            except Exception as e:
                stats.errors.append((company_dict["name"], str(e)))
                continue
            _process_listings(listings, stats, seen_urls, today, dry_run)
            del listings

    elif ats == "SmartRecruiters":
        from scrapers import smartrecruiters as scraper

        for company in notion_companies:
            try:
                job_listings, gf = scraper.fetch_jobs(company.ats_slug)
                stats.geo_filtered += gf
            except Exception as e:
                stats.errors.append((company.name, str(e)))
                continue
            disc_listings = [_job_listing_to_discovery(jl, company) for jl in job_listings]
            _process_listings(disc_listings, stats, seen_urls, today, dry_run)
            del disc_listings

    elif ats == "Workday":
        from scrapers import workday as scraper

        for company in notion_companies:
            if "/" not in company.ats_slug:
                print(f"SKIP [Workday/{company.ats_slug}] — malformed slug, missing '/'")
                continue
            try:
                job_listings, gf = scraper.fetch_jobs(company.ats_slug)
                stats.geo_filtered += gf
            except Exception as e:
                stats.errors.append((company.name, str(e)))
                continue
            disc_listings = [_job_listing_to_discovery(jl, company) for jl in job_listings]
            _process_listings(disc_listings, stats, seen_urls, today, dry_run)
            del disc_listings


def _run_yc_discovery(
    stats: DiscoveryStats,
    seen_urls: set[str],
    today: datetime.date,
    dry_run: bool,
) -> None:
    from scrapers.discovery_yc import fetch_listings

    try:
        listings, gf = fetch_listings()
        stats.geo_filtered += gf
    except Exception as e:
        stats.errors.append(("YC WaaS discovery", str(e)))
        return
    _process_listings(listings, stats, seen_urls, today, dry_run)
    del listings


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

        if listing.company_name in COMPANY_BLOCKLIST:
            print(f"SKIP {listing.company_name} / {listing.title} — blocklisted aggregator")
            continue

        if is_title_geo_excluded(listing.title) or \
                check_description_geo(listing.description):
            stats.geo_filtered += 1
            continue

        seen_urls.add(listing.url)

        job_listing = JobListing(title=listing.title, url=listing.url)

        try:
            company, is_new = _resolve_company(listing, dry_run)
        except Exception as e:
            stats.errors.append((listing.company_name, f"Company lookup failed: {e}"))
            continue

        try:
            dupe = is_duplicate(company, job_listing)
        except Exception as e:
            stats.errors.append((listing.company_name, f"Dedup check failed (skipping): {e}"))
            continue

        if dupe:
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
        if listing.ats == "YC":
            opp_description = f"{opp_description}\n\n{YC_NOTE}" if opp_description else YC_NOTE

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

        try:
            notion.write_opportunity(opp, dry_run=dry_run)
        except Exception as e:
            stats.errors.append((listing.company_name, f"Failed to write opportunity '{listing.title}': {e}"))
            continue

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
        if excluded:
            return None, None, []
        if _is_wrong_role_type(listing.title):
            return None, None, []
        lower_desc = listing.description.lower()
        matched_kws = [kw for kw in DISCOVERY_JD_KEYWORDS if kw.lower() in lower_desc]
        if len(matched_kws) >= 2:
            return None, "jd_keyword", matched_kws

    return None, None, []


def _resolve_company(listing: DiscoveryListing, dry_run: bool) -> tuple[Company, bool]:
    """Return (company, is_new). Creates a Notion company record if not found."""
    if listing.ats == "Greenhouse":
        existing = notion.find_company_by_slug(listing.ats, listing.slug)
        if existing:
            return existing, False
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


def _job_listing_to_discovery(job: "JobListing", company: "Company") -> DiscoveryListing:
    return DiscoveryListing(
        title=job.title,
        url=job.url,
        company_name=company.name,
        ats=company.ats,
        slug=company.ats_slug,
        description=job.description,
        location=job.location,
    )
