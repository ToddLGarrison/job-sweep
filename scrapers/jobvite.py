import xml.etree.ElementTree as ET

import requests

from geo_filter import is_title_geo_excluded, is_us_or_remote
from models import JobListing

# Jobvite's public job feed URL. Note: as of 2025, Jobvite (now Employ Inc.)
# no longer exposes a public unauthenticated feed at this endpoint — most slugs
# redirect to their support page. This scraper will return empty for such companies.
_FEED_URL = "https://jobs.jobvite.com/{slug}/feed"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}


def fetch_jobs(slug: str) -> tuple[list[JobListing], int]:
    url = _FEED_URL.format(slug=slug)
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=15, allow_redirects=True)
        resp.raise_for_status()
    except Exception as e:
        print(f"ERROR [Jobvite/{slug}]: {e}")
        return [], 0

    # Jobvite redirects unknown/deprecated slugs to their support page
    if "jobvite.com/support" in resp.url or "jobvite.com/support" in resp.text[:500]:
        print(f"ERROR [Jobvite/{slug}]: feed not available (redirected to support page)")
        return [], 0

    content_type = resp.headers.get("content-type", "")
    if "xml" in content_type:
        return _parse_xml_feed(resp.text, slug)

    return [], 0


def _parse_xml_feed(xml: str, slug: str) -> tuple[list[JobListing], int]:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as e:
        print(f"ERROR [Jobvite/{slug}]: XML parse error: {e}")
        return [], 0

    results = []
    geo_filtered = 0

    for job in root.iter("job"):
        title_el = job.find("title")
        url_el = job.find("apply-url")
        if url_el is None:
            url_el = job.find("url")
        loc_el = job.find("location")

        title = (title_el.text or "").strip() if title_el is not None else ""
        job_url = (url_el.text or "").strip() if url_el is not None else ""
        location = (loc_el.text or "").strip() if loc_el is not None else ""

        if not title or not job_url:
            continue

        if not is_us_or_remote(location):
            geo_filtered += 1
            continue

        if is_title_geo_excluded(title):
            geo_filtered += 1
            continue

        results.append(JobListing(title=title, url=job_url, location=location))

    return results, geo_filtered
