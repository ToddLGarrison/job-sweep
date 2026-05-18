import json
import re

import requests

from geo_filter import is_title_geo_excluded, is_us_or_remote
from models import JobListing

_JOBS_URL = "https://ats.rippling.com/{slug}/jobs"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}


def fetch_jobs(slug: str) -> tuple[list[JobListing], int]:
    url = _JOBS_URL.format(slug=slug)
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"ERROR [Rippling/{slug}]: {e}")
        return [], 0

    items = _extract_jobs(resp.text)
    if items is None:
        print(f"ERROR [Rippling/{slug}]: could not parse __NEXT_DATA__")
        return [], 0

    results = []
    geo_filtered = 0

    for item in items:
        title = item.get("name", "")
        job_url = item.get("url", "")
        if not title or not job_url:
            continue

        location = _extract_location(item)

        if not is_us_or_remote(location):
            geo_filtered += 1
            continue

        if is_title_geo_excluded(title):
            geo_filtered += 1
            continue

        results.append(JobListing(title=title, url=job_url, location=location))

    return results, geo_filtered


def _extract_jobs(html: str) -> list | None:
    m = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        html,
        re.DOTALL,
    )
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
        jobs_obj = data.get("props", {}).get("pageProps", {}).get("jobs", {})
        if isinstance(jobs_obj, dict):
            return jobs_obj.get("items", [])
        return []
    except (json.JSONDecodeError, AttributeError):
        return None


def _extract_location(item: dict) -> str:
    locations = item.get("locations", [])
    if not locations:
        return ""
    loc = locations[0]
    workplace = loc.get("workplaceType", "")
    if workplace == "REMOTE":
        return "Remote"
    country = loc.get("country", "") or ""
    country_code = loc.get("countryCode", "") or ""
    city = loc.get("city", "") or ""
    state = loc.get("state", "") or ""
    state_code = loc.get("stateCode", "") or ""
    if country_code == "US":
        if city and state_code:
            return f"{city}, {state_code}"
        return city or state or "United States"
    if city and country:
        return f"{city}, {country}"
    return country or city
