"""Discovery scraper for YC Work at a Startup (workatastartup.com).

Fetches the sales/GTM job listing page, filters for target titles, and returns
DiscoveryListing objects. ATS is set to "YC" since apply URLs go through YC
auth and the external ATS cannot be determined without following the redirect.
"""
import html as html_mod
import json
import re

import requests

from geo_filter import is_title_geo_excluded, is_us_or_remote
from models import DiscoveryListing

_SALES_URL = "https://www.workatastartup.com/jobs/l/sales"
_JOB_URL = "https://www.workatastartup.com/jobs/{job_id}"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml",
}


def fetch_listings() -> tuple[list[DiscoveryListing], int]:
    """Return (listings, geo_filtered_count) for all relevant YC jobs."""
    try:
        resp = requests.get(_SALES_URL, headers=_HEADERS, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        print(f"ERROR [YC WaaS]: {e}")
        return [], 0

    jobs = _extract_jobs(resp.text)
    if jobs is None:
        print("ERROR [YC WaaS]: could not parse data-page attribute")
        return [], 0

    results = []
    geo_filtered = 0

    for job in jobs:
        title = (job.get("title") or "").strip()
        job_id = job.get("id")
        company_name = (job.get("companyName") or "").strip()
        company_slug = (job.get("companySlug") or "").strip()

        if not title or not job_id or not company_name:
            continue

        raw_location = (job.get("location") or "").strip()
        if not _is_yc_location_us_or_remote(raw_location):
            geo_filtered += 1
            continue

        location = _extract_location(job)

        if not is_us_or_remote(location):
            geo_filtered += 1
            continue

        if is_title_geo_excluded(title):
            geo_filtered += 1
            continue

        job_url = _JOB_URL.format(job_id=job_id)
        results.append(DiscoveryListing(
            title=title,
            url=job_url,
            company_name=company_name,
            ats="YC",
            slug=company_slug,
            location=location,
        ))

    return results, geo_filtered


def _extract_jobs(html: str) -> list | None:
    m = re.search(r'data-page="([^"]+)"', html)
    if not m:
        return None
    try:
        data = json.loads(html_mod.unescape(m.group(1)))
        jobs = data.get("props", {}).get("jobs")
        return jobs if isinstance(jobs, list) else None
    except (json.JSONDecodeError, AttributeError):
        return None


def _is_yc_location_us_or_remote(raw: str) -> bool:
    """Check the raw YC location string for a non-US country code.

    YC formats locations as "City, ST, CC" with 2-letter ISO country codes.
    If any segment has a non-US country code, the location is non-US.
    Remote segments are always accepted.
    """
    if not raw:
        return True
    segments = [s.strip() for s in raw.split(" / ")]
    for seg in segments:
        if re.search(r"\bRemote\b", seg, re.IGNORECASE):
            return True
        m = re.search(r",\s*([A-Z]{2})\s*$", seg)
        if m:
            return m.group(1) == "US"
    # No explicit country code found — fall back to is_us_or_remote on first segment
    return is_us_or_remote(segments[0] if segments else "")


def _extract_location(job: dict) -> str:
    """Extract the first location segment from YC's slash-separated location string."""
    raw = (job.get("location") or "").strip()
    if not raw:
        return ""
    # YC format: "City, ST, US / Remote (City, ST, US)" — take first segment
    first = raw.split(" / ")[0].strip()
    # Strip trailing country code like ", US" since geo_filter handles city/state
    first = re.sub(r",\s*[A-Z]{2}\s*$", "", first).strip()
    return first
