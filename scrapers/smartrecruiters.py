import re

import requests

from geo_filter import is_title_geo_excluded, is_us_or_remote
from models import JobListing

_BASE_URL = "https://api.smartrecruiters.com/v1/companies/{slug}/postings"
_PAGE_LIMIT = 100


def fetch_jobs(slug: str) -> tuple[list[JobListing], int]:
    results = []
    geo_filtered = 0
    offset = 0

    while True:
        try:
            resp = requests.get(
                _BASE_URL.format(slug=slug),
                params={"limit": _PAGE_LIMIT, "offset": offset},
                timeout=15,
            )
            resp.raise_for_status()
        except Exception as e:
            print(f"ERROR [SmartRecruiters/{slug}]: {e}")
            return [], 0

        data = resp.json()
        postings = data.get("content", [])

        for posting in postings:
            title = posting.get("name", "")
            apply_url = posting.get("ref", "")
            if not title or not apply_url:
                continue

            location = _extract_location(posting.get("location", {}))

            if not is_us_or_remote(location):
                geo_filtered += 1
                continue

            if is_title_geo_excluded(title):
                geo_filtered += 1
                continue

            description = _extract_description(posting)
            results.append(JobListing(
                title=title,
                url=apply_url,
                location=location,
                description=description,
            ))

        total_found = data.get("totalFound", 0)
        offset += len(postings)
        if not postings or offset >= total_found:
            break

    return results, geo_filtered


def _extract_location(loc: dict) -> str:
    """Build a location string from a SmartRecruiters location object."""
    if not loc:
        return ""
    if loc.get("remote"):
        return "Remote"
    country = loc.get("country", "")
    city = loc.get("city", "")
    region = loc.get("region", "")
    if country in ("US", "United States", "USA"):
        if city and region:
            return f"{city}, {region}"
        return city or region or "United States"
    if city and country:
        return f"{city}, {country}"
    return country or city


def _extract_description(posting: dict) -> str:
    sections = posting.get("jobAd", {}).get("sections", {})
    parts = []
    for key in ("jobDescription", "qualifications", "additionalInformation"):
        section = sections.get(key, {})
        text = section.get("text", "")
        if text:
            parts.append(_strip_html(text))
    return " ".join(parts)


def _strip_html(text: str) -> str:
    import html
    return html.unescape(re.sub(r"<[^>]+>", " ", text))
